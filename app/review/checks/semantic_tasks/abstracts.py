"""Semantic task: check_abstracts."""

import re
from typing import List, Tuple
from app.schemas import Finding, EvidenceLocation, RuleAuditItem, CheckStatus
from app.documents.models import ThesisDocumentTree


def check_abstracts(
    checker, tree: ThesisDocumentTree, model_mode: str
) -> Tuple[List[Finding], List[RuleAuditItem]]:
    findings = []
    audits = []

    # Rule 3: 中英文标题不对应
    if not tree.title_cn and tree.title_en:
        audits.append(
            RuleAuditItem(
                rule_id=3,
                rule_name="中英文标题不对应",
                category="语义核查",
                status=CheckStatus.NA.value,
                note="英文文献不适用中英文双语标题对比",
            )
        )
    elif not tree.title_cn or not tree.title_en:
        audits.append(
            RuleAuditItem(
                rule_id=3,
                rule_name="中英文标题不对应",
                category="语义核查",
                status=CheckStatus.MISSING_INPUT.value,
                note="未同时提取到中英文标题",
            )
        )
    else:
        prompt = f"请审查规则3：中英文标题的研究对象和主要内容是否存在实质不一致。允许自然翻译、单复数和措辞差异；不要仅因措辞略有差异报告问题。有实质不一致时 findings 的 rule_id 必须是 3。\n中文标题：{tree.title_cn}\n英文标题：{tree.title_en}"
        res, err = checker._call_llm(prompt, model_mode)
        if err:
            audits.append(
                RuleAuditItem(
                    rule_id=3,
                    rule_name="中英文标题不对应",
                    category="语义核查",
                    status=CheckStatus.FAILED.value,
                    note=err,
                )
            )
        else:
            found = False
            if res:
                for f in res.get("findings", []):
                    if f.get("rule_id") == 3:
                        found = True
                        findings.append(
                            Finding(
                                rule_id=3,
                                rule_category="语义核查",
                                severity="major",
                                issue=f.get("issue", "中英文标题不对应"),
                                suggestion=f.get("suggestion", "请修正英译"),
                                quote=tree.title_en,
                            )
                        )
            audits.append(
                RuleAuditItem(
                    rule_id=3,
                    rule_name="中英文标题不对应",
                    category="语义核查",
                    status=(
                        CheckStatus.FINDING.value if found else CheckStatus.PASSED.value
                    ),
                )
            )

    # Rule 4: 中英文摘要内容不对应
    if not tree.abstract_cn and tree.abstract_en:
        audits.append(
            RuleAuditItem(
                rule_id=4,
                rule_name="中英文摘要内容不对应",
                category="语义核查",
                status=CheckStatus.NA.value,
                note="英文文献不适用双语摘要对比",
            )
        )
    elif not tree.abstract_cn or not tree.abstract_en:
        audits.append(
            RuleAuditItem(
                rule_id=4,
                rule_name="中英文摘要内容不对应",
                category="语义核查",
                status=CheckStatus.MISSING_INPUT.value,
                note="缺少英文或中文摘要",
            )
        )
    else:
        prompt = f"请审查规则4：中英文摘要内容是否对齐一致，有无漏译误译；有问题时 findings 的 rule_id 必须是 4。\n【中文摘要】：\n{' '.join(p.text for p in tree.abstract_cn)}\n\n【英文摘要】：\n{' '.join(p.text for p in tree.abstract_en)}"
        res, err = checker._call_llm(prompt, model_mode)
        if err:
            audits.append(
                RuleAuditItem(
                    rule_id=4,
                    rule_name="中英文摘要内容不对应",
                    category="语义核查",
                    status=CheckStatus.FAILED.value,
                    note=err,
                )
            )
        else:
            found = False
            if res:
                for f in res.get("findings", []):
                    if f.get("rule_id") == 4:
                        found = True
                        findings.append(
                            Finding(
                                rule_id=4,
                                rule_category="语义核查",
                                severity="major",
                                issue=f.get("issue", "摘要内容不对应"),
                                suggestion=f.get("suggestion", "请补齐翻译"),
                                quote=f.get("quote", ""),
                            )
                        )
            audits.append(
                RuleAuditItem(
                    rule_id=4,
                    rule_name="中英文摘要内容不对应",
                    category="语义核查",
                    status=(
                        CheckStatus.FINDING.value if found else CheckStatus.PASSED.value
                    ),
                )
            )

    # Rule 6: 摘要缺少总结段（3-4句话）
    if not tree.abstract_cn:
        audits.append(
            RuleAuditItem(
                rule_id=6,
                rule_name="摘要缺少总结段",
                category="语义核查",
                status=(
                    CheckStatus.NA.value
                    if tree.abstract_en
                    else CheckStatus.MISSING_INPUT.value
                ),
                note="无中文摘要，不适用中文摘要总结段规范",
            )
        )
    else:
        last_p = tree.abstract_cn[-1]
        sents = [s for s in re.split(r"[。！？\n]+", last_p.text) if len(s.strip()) > 5]
        if len(sents) < 2 or not any(
            kw in last_p.text
            for kw in [
                "表明",
                "结果",
                "意义",
                "价值",
                "贡献",
                "展望",
                "为",
                "提供了",
            ]
        ):
            findings.append(
                Finding(
                    rule_id=6,
                    rule_category="语义核查",
                    dimension="规范与逻辑",
                    severity="minor",
                    status="supported",
                    block_id=last_p.id,
                    quote=last_p.text[:60],
                    locations=[
                        EvidenceLocation(
                            page=page,
                            block_id=last_p.id,
                            quote=last_p.text[:80],
                            description="摘要末段",
                        )
                        for page in (last_p.source_pages or [last_p.page])
                    ],
                    issue="中文摘要末尾缺少对研究成果意义或应用价值的精炼总结段（建议 3-4 句话）。",
                    suggestion="建议在中文摘要最后独立设置一段，用 3~4 句简明扼要的话总结本研究成果的学术价值、工程意义或推广前景。",
                )
            )
            audits.append(
                RuleAuditItem(
                    rule_id=6,
                    rule_name="摘要缺少总结段",
                    category="语义核查",
                    status=CheckStatus.FINDING.value,
                    findings_count=1,
                )
            )
        else:
            audits.append(
                RuleAuditItem(
                    rule_id=6,
                    rule_name="摘要缺少总结段",
                    category="语义核查",
                    status=CheckStatus.PASSED.value,
                )
            )

    return findings, audits
