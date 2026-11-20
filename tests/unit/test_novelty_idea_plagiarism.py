"""Unit tests for idea plagiarism detection and claim extraction."""

import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from app.audit.novelty import (
    assess,
    build_method_context,
    extract_claims_from_paper,
    locate_claim_sections,
    rank_and_deduplicate_sources,
    retrieve,
)
from app.audit.schemas import AuditRequest
from app.audit.service import AuditService
from app.config import Settings
from app.search import clean_text as crossref_clean_text
from app.storage import Store, new_id


class NoveltyIdeaPlagiarismTests(unittest.TestCase):
    def test_extract_claims_heuristic(self):
        claims = extract_claims_from_paper(None, "mock", "论文正文内容" * 20)
        self.assertGreaterEqual(len(claims), 1)
        self.assertIn("claim", claims[0])
        self.assertIn("query", claims[0])

    def test_assess_duplicate_idea_collision(self):
        client = Mock()
        sources = [
            dict(
                id="lit_1",
                title="A Prior Method on Dynamic Masking",
                doi="10.1000/prior",
                abstract="We propose a dynamic masking method for temporal sequences.",
                authors=["Alice Smith"],
                year="2023",
                scope="abstract",
            )
        ]
        # LLM reports a duplicate collision
        client.call.return_value = (
            dict(
                status="🔴 发现已有相同工作（存在思想撞车/抄袭风险）",
                summary="论文提出的核心方法与 Alice Smith 2023 年的工作实质重合，存在思想抄袭风险。",
                comparisons=[
                    dict(
                        source_id="lit_1",
                        claim="自适应动态掩码时序特征提取",
                        verdict_level="duplicate",
                        judgment="🔴 已被前人做过（撞车/疑似思想抄袭）",
                        paper_quote="提出自适应动态掩码提取时序特征。",
                        source_quote="We propose a dynamic masking method for temporal sequences.",
                        difference="两者的核心数学模型和动态掩码机制完全一致，未见明显差异。",
                    )
                ],
            ),
            None,
        )
        res = assess(
            client,
            "local",
            "提出自适应动态掩码提取时序特征。",
            sources,
            "master",
        )
        self.assertIn("思想撞车/抄袭风险", res["status"])
        self.assertEqual(len(res["comparisons"]), 1)
        self.assertEqual(res["comparisons"][0]["judgment"], "🔴 已被前人做过（撞车/疑似思想抄袭）")

    def test_assess_incremental_improvement(self):
        client = Mock()
        sources = [
            dict(
                id="lit_2",
                title="Baseline Framework",
                doi="10.1000/base",
                abstract="Standard baseline framework for NLP.",
                authors=["Bob"],
                year="2022",
                scope="abstract",
            )
        ]
        client.call.return_value = (
            dict(
                status="🟡 主要属于相近工作的增量改进",
                summary="在 Bob 2022 基础框架上进行了轻量化适应性改进。",
                comparisons=[
                    dict(
                        source_id="lit_2",
                        claim="轻量化注意力结构",
                        verdict_level="incremental",
                        judgment="🟡 存在相近工作（增量改进）",
                        paper_quote="在标准Transformer基础上引入稀疏剪枝。",
                        source_quote="Standard baseline framework for NLP.",
                        difference="相比基线框架增加了稀疏剪枝结构，降低了计算量。",
                    )
                ],
            ),
            None,
        )
        res = assess(
            client,
            "local",
            "在标准Transformer基础上引入稀疏剪枝。",
            sources,
            "master",
        )
        self.assertIn("增量改进", res["status"])
        self.assertEqual(res["comparisons"][0]["judgment"], "🟡 存在相近工作（增量改进）")

    def test_locate_claim_sections_skips_toc_and_includes_bilingual_abstracts(self):
        toc = (
            "目 录\n"
            + "\n".join(f"第 {i} 节 章节内容 .......... {i}" for i in range(1, 220))
            + "\n1.3 主要工作与创新点 .......... 10\n"
        )
        paper = (
            "硕士学位论文封面与独创性声明\n" * 120
            + toc
            + "\n摘 要\n本文研究面向番茄病害的多模态识别。\n"
            + "\nAbstract\nThis thesis studies multimodal tomato disease recognition.\n"
            + "\n第 1 章 绪论\n" + "\n".join(f"第{i}段常规背景介绍内容。" for i in range(500))
            + "\n1.3 主要工作与创新点\n正文核心贡献：构建了SwinTransformer与CLIP对齐模型。\n"
            + "\n第 5 章 系统实现\n" + "\n".join(f"第{i}段系统详细实现内容。" for i in range(500))
            + "\n总结与展望\n全文工作总结与未来展望。\n"
            + "\n参考文献\n[1] Someone. Old Paper. 2020.\n"
        )
        selected = locate_claim_sections(paper)
        self.assertIn("本文研究面向番茄病害的多模态识别", selected)
        self.assertIn("multimodal tomato disease recognition", selected)
        self.assertIn("构建了SwinTransformer与CLIP对齐模型", selected)
        self.assertIn("全文工作总结与未来展望", selected)
        self.assertNotIn("..........", selected)
        self.assertNotIn("Old Paper", selected)

    def test_build_method_context_retrieves_claim_matched_body_paragraphs(self):
        filler = "\n".join(["无关的文献综述段落，介绍了常规实验流程[1][2][3][4][5][6][7]。"] * 40)
        method_block = (
            "\n第 5 章 系统架构\n"
            + "本系统采用 SpringBoot 后端与 Neo4j 图数据库，集成多模态诊断引擎与知识图谱推理服务，实现病害智能诊断Web接口。\n" * 12
        )
        paper = (
            "摘 要\n本文提出番茄病害智能诊断方法。\n"
            + "\n第 1 章 绪论\n" + filler
            + method_block
            + "\n总结与展望\n完成所有实验。\n"
            + "其他填充文本。\n" * 900
        )
        claims = [
            dict(
                claim="集成多模态识别模型与Neo4j知识图谱的SpringBoot诊断系统",
                queries=["SpringBoot Neo4j tomato disease diagnosis web system"],
            )
        ]
        ctx = build_method_context(paper, claims)
        self.assertIn("SpringBoot 后端与 Neo4j 图数据库", ctx)

    def test_rejected_and_missing_claims_become_uncertain_never_fake_novel(self):
        client = Mock()
        sources = [
            dict(
                id="lit_1",
                title="Llama3-8B Value Alignment Study",
                abstract="We evaluate Llama3-8B value alignment on safety benchmarks.",
                year="2024",
                scope="abstract",
            )
        ]
        claims = [
            dict(claim="主张一", queries=["value alignment"]),
            dict(claim="主张二", queries=["other task"]),
        ]
        # Model hallucinates an unverified metric in claim 1 and omits claim 2
        client.call.return_value = (
            dict(
                status="🟡 主要属于相近工作的增量改进",
                summary="部分增量。",
                comparisons=[
                    dict(
                        source_id="lit_1",
                        claim="主张一",
                        verdict_level="incremental",
                        judgment="🟡 存在相近工作（增量改进）",
                        paper_quote="提出价值观对齐方法。",
                        source_quote="We evaluate Llama3-8B value alignment on safety benchmarks.",
                        difference="将准确率提高到99.9%。",
                    )
                ],
            ),
            None,
        )
        res = assess(client, "local", "提出价值观对齐方法。", sources, "master", claims=claims)
        self.assertEqual(res["status"], "信息不足")
        self.assertEqual(len(res["comparisons"]), 2)
        for comp in res["comparisons"]:
            self.assertEqual(comp["verdict_level"], "uncertain")
            self.assertEqual(comp["judgment"], "信息不足")
            self.assertFalse(comp["quote_grounded"])

    def test_model_failures_surface_errors_without_fake_fallback(self):
        client = Mock()
        client.call.return_value = (None, "HTTP Error 502: Bad Gateway")
        errors = []
        claims = extract_claims_from_paper(client, "local", "论文正文内容" * 40, errors=errors)
        self.assertEqual(claims, [])
        self.assertTrue(any("502" in e for e in errors))

        sources = [dict(id="lit_1", title="Some Work", abstract="Some abstract.", year="2024")]
        res = assess(client, "local", "论文正文内容" * 40, sources, "master")
        self.assertEqual(res["status"], "信息不足")
        self.assertTrue(any("502" in n for n in res["notes"]))

    def test_number_guard_allows_model_versions_but_rejects_invented_metrics(self):
        client = Mock()
        sources = [
            dict(
                id="lit_1",
                title="BiCMT Plant Disease Classification",
                abstract="We combine YOLOv5s with ResNet50 and Llama3-8B for disease detection.",
                year="2024",
                scope="abstract",
            )
        ]
        client.call.return_value = (
            dict(
                status="🟡 主要属于相近工作的增量改进",
                summary="对比明确。",
                comparisons=[
                    dict(
                        source_id="lit_1",
                        claim="CLIP 跨模态融合",
                        verdict_level="incremental",
                        judgment="🟡 存在相近工作（增量改进）",
                        paper_quote="本文采用 SwinTransformer 与 CLIP 实现图文融合。",
                        source_quote="We combine YOLOv5s with ResNet50 and Llama3-8B for disease detection.",
                        difference="候选文献采用 YOLOv5s 与 ResNet50，本文基于 CLIP 进行改进。",
                    )
                ],
            ),
            None,
        )
        res = assess(
            client,
            "local",
            "本文采用 SwinTransformer 与 CLIP 实现图文融合。",
            sources,
            "master",
        )
        self.assertEqual(res["comparisons"][0]["verdict_level"], "incremental")

        # Standalone hallucinated number must still be rejected
        client.call.return_value = (
            dict(
                status="🟡 主要属于相近工作的增量改进",
                comparisons=[
                    dict(
                        source_id="lit_1",
                        claim="CLIP 跨模态融合",
                        verdict_level="incremental",
                        judgment="🟡 存在相近工作（增量改进）",
                        paper_quote="本文采用 SwinTransformer 与 CLIP 实现图文融合。",
                        source_quote="We combine YOLOv5s with ResNet50 and Llama3-8B for disease detection.",
                        difference="性能提升至 98.7%。",
                    )
                ],
            ),
            None,
        )
        rejected = assess(
            client,
            "local",
            "本文采用 SwinTransformer 与 CLIP 实现图文融合。",
            sources,
            "master",
        )
        self.assertEqual(rejected["comparisons"], [])

    def test_hallucinated_source_quote_and_title_only_cannot_be_duplicate(self):
        client = Mock()
        sources = [
            dict(
                id="lit_1",
                title="Title Only Paper",
                abstract="",
                tldr="",
                year="2024",
                scope="metadata_only",
            ),
            dict(
                id="lit_2",
                title="Paper With Abstract",
                abstract="We use convolutional layers for leaf classification.",
                year="2024",
                scope="abstract",
            ),
        ]
        client.call.return_value = (
            dict(
                status="🔴 发现已有相同工作（存在思想撞车/抄袭风险）",
                comparisons=[
                    dict(
                        source_id="lit_1",
                        claim="主张一",
                        verdict_level="duplicate",
                        judgment="🔴 已被前人做过（撞车/疑似思想抄袭）",
                        paper_quote="本文提出了方法A。",
                        source_quote="Title Only Paper",
                        difference="仅题目相同。",
                    ),
                    dict(
                        source_id="lit_2",
                        claim="主张二",
                        verdict_level="duplicate",
                        judgment="🔴 已被前人做过（撞车/疑似思想抄袭）",
                        paper_quote="本文提出了方法B。",
                        source_quote="Completely fabricated reinforcement learning mechanism.",
                        difference="模型编造了摘要引文。",
                    ),
                ],
            ),
            None,
        )
        res = assess(
            client,
            "local",
            "本文提出了方法A。本文提出了方法B。",
            sources,
            "master",
            claims=[dict(claim="主张一"), dict(claim="主张二")],
        )
        self.assertEqual(res["status"], "信息不足")
        for comp in res["comparisons"]:
            self.assertEqual(comp["verdict_level"], "uncertain")
            self.assertEqual(comp["judgment"], "信息不足")

    def test_cutoff_blocks_same_year_future_s2_and_keeps_prior_year_crossref(self):
        s2_items = [
            dict(
                title="Future Same Year S2",
                abstract="Abstract.",
                year="2024",
                published="2024-09-15",
                doi="10.1/s2future",
                source="semantic_scholar",
            ),
            dict(
                title="Valid Same Year S2",
                abstract="Abstract.",
                year="2024",
                published="2024-02-10",
                doi="10.1/s2valid",
                source="semantic_scholar",
            ),
            dict(
                title="Ambiguous Same Year S2",
                abstract="Abstract.",
                year="2024",
                published="",
                doi="10.1/s2ambig",
                source="semantic_scholar",
            ),
        ]
        cr_items = [
            dict(
                DOI="10.1/crprior",
                title=["Prior Year Only Crossref"],
                abstract="Abstract.",
                published={"date-parts": [[2022]]},
            ),
            dict(
                DOI="10.1/crsameyear",
                title=["Same Year No Day Crossref"],
                abstract="Abstract.",
                published={"date-parts": [[2024]]},
            ),
        ]
        with patch("app.audit.novelty.search_semantic_scholar", return_value=s2_items), patch(
            "app.audit.novelty.search_items", return_value=cr_items
        ):
            sources, _ = retrieve(["tomato disease"], cutoff="2024-06-01", s2_api_key="test-key")
        titles = {s["title"] for s in sources}
        self.assertEqual(titles, {"Valid Same Year S2", "Prior Year Only Crossref"})

    def test_s2_zero_hit_concise_retry_and_per_claim_relevance_ranking(self):
        calls = []

        def fake_s2(q, **kwargs):
            calls.append(q)
            if len(calls) == 1:
                return []
            return [
                dict(
                    title="Unrelated 2026 General Framework",
                    abstract="General paper from 2026.",
                    year="2026",
                    published="2026-01-01",
                    citation_count=200,
                    doi="10.1/unrel",
                    source="semantic_scholar",
                ),
                dict(
                    title="CLIP Tomato Disease Recognition",
                    abstract="Multimodal tomato disease classification with SwinTransformer and CLIP.",
                    year="2022",
                    published="2022-05-01",
                    citation_count=10,
                    doi="10.1/rel",
                    source="semantic_scholar",
                ),
            ]

        claims = [
            dict(
                claim="基于CLIP与SwinTransformer的番茄病害识别",
                queries=["based on CLIP SwinTransformer tomato disease multimodal recognition method"],
            )
        ]
        with patch("app.audit.novelty.search_semantic_scholar", side_effect=fake_s2), patch(
            "app.audit.novelty.search_items", return_value=[]
        ):
            sources, _ = retrieve([claims[0]["queries"][0]], s2_api_key="test-key", claims=claims)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1], "CLIP SwinTransformer tomato disease")
        self.assertEqual(sources[0]["title"], "CLIP Tomato Disease Recognition")

    def test_clean_text_strips_escaped_html_tags(self):
        raw = "&lt;p&gt;First &lt;strong&gt;paragraph&lt;/strong&gt;.&lt;/p&gt;"
        cleaned = crossref_clean_text(raw)
        self.assertIn("First paragraph", cleaned)
        self.assertNotIn("<", cleaned)
        self.assertNotIn("&lt;", cleaned)

    def test_audit_service_honors_check_novelty_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            doc = store.save_document("a.txt", ("测试正文内容" * 20).encode("utf-8"))
            svc = AuditService(store, Settings(data_dir=Path(tmp)), Mock())
            req = AuditRequest(
                document_id=doc["id"],
                check_novelty=False,
                check_citations=False,
                public_queries=["public topic"],
                search_approved=True,
                model_mode="mock",
            )
            audit_id = new_id("audit")
            state = {
                "identifier": audit_id,
                "request": req,
                "blocks": [{"text": "测试正文内容" * 20}],
            }
            store.write(store.folder("audits", audit_id), "state.json", {"status": "running"})
            out = svc.novelty(state)
            self.assertEqual(out["novelty"]["status"], "未启用")
            self.assertIn("关闭", out["novelty"]["basis"])


if __name__ == "__main__":
    unittest.main()
