"""Semantic task: check_conclusion."""

import re
from typing import List, Tuple
from app.schemas import Finding, EvidenceLocation, RuleAuditItem, CheckStatus
from app.documents.models import ThesisDocumentTree
from app.review.checks.coverage_body import review_body


from .common import _summary_text, _shared_fragment


def check_conclusion(
    checker, tree: ThesisDocumentTree, model_mode: str, body_review=None
) -> Tuple[List[Finding], List[RuleAuditItem]]:
    findings = []
    audits = []

    abstract_text = " ".join(p.text for p in tree.abstract_cn)
    conclusion_text = " ".join(
        p.text
        for p in (tree.conclusion_chapter.paragraphs if tree.conclusion_chapter else [])
    )

    def jaccard(s1, s2):
        w1 = set(re.findall(r"[\u4e00-\u9fa5]{2}", s1))
        w2 = set(re.findall(r"[\u4e00-\u9fa5]{2}", s2))
        if not w1 or not w2:
            return 0.0
        return len(w1 & w2) / len(w1 | w2)

    # Rule 16: 全文总结与展望部分与摘要或各章小结雷同
    if abstract_text and conclusion_text:
        sim = jaccard(abstract_text, conclusion_text)
        shared = _shared_fragment(abstract_text, conclusion_text)
        if sim > 0.45 or shared:
            findings.append(
                Finding(
                    rule_id=16,
                    rule_category="语义核查",
                    dimension="规范与逻辑",
                    severity="major",
                    status="pending_verification",
                    block_id="conclusion_rep",
                    quote=shared or conclusion_text[:60],
                    locations=[
                        EvidenceLocation(
                            quote=abstract_text[:80], description="中文摘要内容"
                        ),
                        EvidenceLocation(
                            quote=conclusion_text[:80],
                            description="全文总结雷同段落",
                        ),
                    ],
                    measurement=f"全文词汇重叠度 {sim * 100:.1f}%"
                    + (f"；存在相同片段：{shared}" if shared else ""),
                    issue="全文总结与摘要存在相似或重复的文字，请结合上下文核对。",
                    suggestion="全文总结不应直接从摘要机械复制黏贴。总结部分应在更高学术理论维度，系统概括研究的整体规律、工程价值并深化展望。",
                )
            )
            audits.append(
                RuleAuditItem(
                    rule_id=16,
                    rule_name="总结与摘要内容雷同",
                    category="语义核查",
                    status=CheckStatus.FINDING.value,
                    findings_count=1,
                )
            )
        else:
            audits.append(
                RuleAuditItem(
                    rule_id=16,
                    rule_name="总结与摘要内容雷同",
                    category="语义核查",
                    status=CheckStatus.PASSED.value,
                )
            )
    else:
        audits.append(
            RuleAuditItem(
                rule_id=16,
                rule_name="总结与摘要内容雷同",
                category="语义核查",
                status=CheckStatus.MISSING_INPUT.value,
                note="缺少摘要或总结章节",
            )
        )

    # Rule 14: 各章小结与摘要雷同
    r14_found = False
    summaries_seen = 0
    if abstract_text:
        for ch in tree.chapters:
            ch_sum_text = _summary_text(ch)
            if ch_sum_text:
                summaries_seen += 1
                sim_ch = jaccard(abstract_text, ch_sum_text)
                shared = _shared_fragment(abstract_text, ch_sum_text)
                if sim_ch > 0.50 or shared:
                    r14_found = True
                    findings.append(
                        Finding(
                            rule_id=14,
                            rule_category="语义核查",
                            dimension="规范与逻辑",
                            severity="major",
                            status="pending_verification",
                            block_id=(
                                ch.paragraphs[0].id if ch.paragraphs else "ch_sum"
                            ),
                            quote=shared or ch_sum_text[:60],
                            locations=[
                                EvidenceLocation(
                                    quote=abstract_text[:60], description="中文摘要"
                                ),
                                EvidenceLocation(
                                    quote=ch_sum_text[:60],
                                    description=f"{ch.title} 本章小结",
                                ),
                            ],
                            issue=f"{ch.title} 的小结与摘要存在相似或重复的文字，请结合上下文核对。",
                            suggestion="各章小结应专注于提炼本章实验结果与本章理论发现，不应大段照抄全篇摘要通用性表述。",
                        )
                    )
    r14_status = (
        CheckStatus.FINDING.value
        if r14_found
        else (
            CheckStatus.PASSED.value
            if abstract_text and summaries_seen
            else CheckStatus.MISSING_INPUT.value
        )
    )
    audits.append(
        RuleAuditItem(
            rule_id=14,
            rule_name="各章小结与摘要雷同",
            category="语义核查",
            status=r14_status,
            note=(
                None
                if summaries_seen and abstract_text
                else "缺少摘要或未识别到章节小结正文"
            ),
        )
    )

    # Rule 16 also compares each chapter summary with the overall conclusion.
    if conclusion_text:
        for ch in tree.chapters:
            if ch is tree.conclusion_chapter or ch.role == "summary":
                continue
            summary = _summary_text(ch)
            shared = _shared_fragment(summary, conclusion_text)
            if not shared:
                continue
            findings.append(
                Finding(
                    rule_id=16,
                    rule_category="语义核查",
                    severity="major",
                    status="pending_verification",
                    quote=shared,
                    locations=[
                        EvidenceLocation(
                            page=ch.page,
                            quote=shared,
                            description=f"{ch.title} 小结",
                        ),
                        EvidenceLocation(
                            page=tree.conclusion_chapter.page,
                            quote=shared,
                            description="全文总结",
                        ),
                    ],
                    issue=f"{ch.title} 的小结和全文总结存在相同文字，请结合上下文核对。",
                    suggestion="请检查重复段落，按章节和全文总结各自的重点调整。",
                )
            )
        r16 = next(a for a in audits if a.rule_id == 16)
        r16_count = sum(f.rule_id == 16 for f in findings)
        if r16_count:
            r16.status = CheckStatus.FINDING.value
            r16.findings_count = r16_count
            r16.note = None

    # Rule 21: 图表中非专业术语用英文表达
    all_figs = []
    for ch in tree.chapters:
        all_figs.extend(ch.figures)
        all_figs.extend(ch.tables)

    re_eng_bad = re.compile(
        r"\b(Result|Comparison|Step\s*\d+|Input\s*data|Output\s*data|Flowchart|System\s*Architecture)\b",
        re.IGNORECASE,
    )
    r21_count = 0
    for f in all_figs:
        m = re_eng_bad.search(f.caption)
        if m:
            r21_count += 1
            findings.append(
                Finding(
                    rule_id=21,
                    rule_category="语义核查",
                    dimension="规范与逻辑",
                    severity="minor",
                    status="supported",
                    block_id=f"fig_{f.num}",
                    quote=f.caption,
                    locations=[
                        EvidenceLocation(
                            page=f.page,
                            quote=f.caption,
                            description="图表非专业英文",
                        )
                    ],
                    issue=f"图表标题中出现非专业日常英文词汇（'{m.group(0)}'）。",
                    suggestion=f"中文学位论文图表中，除通用的行业专业术语与缩写（如 CNN, Transformer, Loss 等）外，日常说明文字（如 {m.group(0)}）必须使用规范中文表达。",
                )
            )
            break
    audits.append(
        RuleAuditItem(
            rule_id=21,
            rule_name="图表中非专业术语用英文表达",
            category="语义核查",
            status=(
                CheckStatus.FINDING.value if r21_count else CheckStatus.PASSED.value
            ),
            findings_count=r21_count,
        )
    )

    body_review = (
        body_review
        if body_review is not None
        else review_body(checker, tree, model_mode, (38,))
    )
    logic_findings, logic_audit = body_review[38]
    findings.extend(logic_findings)
    audits.append(logic_audit)

    return findings, audits
