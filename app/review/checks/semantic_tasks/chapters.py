"""Semantic task: check_chapters."""

from typing import List, Tuple
from app.schemas import Finding, RuleAuditItem, CheckStatus
from app.documents.models import ThesisDocumentTree
from app.review.checks.coverage_body import review_body


def check_chapters(
    checker, tree: ThesisDocumentTree, model_mode: str, body_review=None
) -> Tuple[List[Finding], List[RuleAuditItem]]:
    findings = []
    audits = []

    body_review = (
        body_review
        if body_review is not None
        else review_body(checker, tree, model_mode, (37,))
    )
    topic_findings, topic_audit = body_review[37]
    method_chapters = [ch for ch in tree.chapters if ch.role == "method"]
    if not method_chapters:
        return topic_findings, [
            RuleAuditItem(
                rule_id=10,
                rule_name="各章缺少本章拟解决关键问题",
                category="语义核查",
                status=CheckStatus.MISSING_INPUT.value,
                note="未识别到主体方法章节",
            ),
            RuleAuditItem(
                rule_id=11,
                rule_name="各章缺少方法动机描述",
                category="语义核查",
                status=CheckStatus.MISSING_INPUT.value,
                note="未识别到主体方法章节",
            ),
            topic_audit,
        ]

    # Rule 10 & 11: LLM-based semantic detection on core chapter introductions
    # Check chapter opening text for problem/goal introduction (Rule 10) and method motivation (Rule 11)
    r10_count = 0
    r11_count = 0

    # Construct prompt for LLM evaluating all method chapter introductions together
    ch_summaries = []
    for index, ch in enumerate(method_chapters, start=1):
        head_paras = [p.text for p in ch.paragraphs if not p.is_heading][:3]
        head_text = " ".join(head_paras)[:600]
        ch_summaries.append(f"【章节{index}】（开头内容）：\n{head_text}")

    prompt_10_11 = (
        "请审查以下各主体章节的开头导论部分，核实是否存在学术规范缺陷：\n"
        "只按正文实际陈述判断是否有研究问题及方法动机，不要因正文与章节标题不符就判定缺少问题或动机；标题是否跑题由另一规则单独检查。\n"
        "规则10：各主体章节开头是否完全缺少'本章拟解决的关键问题或研究目标/任务'的明确介绍？（注意：若本章开头段落已明确交代了本章研究内容、设计目标、解决的问题或研究重点，则判定合格，不要误报！只有在完全未提任何目标与问题直接罗列细节时才报问题）。\n"
        "规则11：各主体章节在提出模型或方法前，是否完全缺少设计动机（Motivation）？（说明为何设计此方法、为何现有方案不足）。\n\n"
        + "\n\n".join(ch_summaries)
        + "\n\n若发现确有章节完全缺失，请返回JSON中的findings，rule_id设为10或11，并在issue中说明具体章节标题与缺失内容；若各章开头均有合理解释则findings返回空列表[]。"
    )

    res, err = checker._call_llm(prompt_10_11, model_mode)
    if not err and res:
        for f in res.get("findings", []):
            r_id = f.get("rule_id")
            issue = f.get("issue", "")
            for index, ch in enumerate(method_chapters, start=1):
                issue = issue.replace(f"章节{index}", ch.title)
            if r_id == 10:
                r10_count += 1
                findings.append(
                    Finding(
                        rule_id=10,
                        rule_category="语义核查",
                        dimension="规范与逻辑",
                        severity="minor",
                        status="supported",
                        issue=issue or "主体章节开头缺少拟解决关键问题与研究目标",
                        suggestion=f.get(
                            "suggestion",
                            "建议在章节首段开门见山点出本章旨在攻克的关键难点与研究目标。",
                        ),
                        quote=f.get("quote", ""),
                    )
                )
            elif r_id == 11:
                r11_count += 1
                findings.append(
                    Finding(
                        rule_id=11,
                        rule_category="语义核查",
                        dimension="规范与逻辑",
                        severity="minor",
                        status="supported",
                        issue=issue
                        or "主体章节缺少对所提出方法的动机描述（Motivation）",
                        suggestion=f.get(
                            "suggestion",
                            "在给出模型或算法前，建议补充阐述为何现有方法不足以及设计这一机制的动机。",
                        ),
                        quote=f.get("quote", ""),
                    )
                )
    audits.append(
        RuleAuditItem(
            rule_id=10,
            rule_name="各章缺少本章拟解决关键问题",
            category="语义核查",
            status=(
                CheckStatus.FINDING.value
                if r10_count
                else (CheckStatus.FAILED.value if err else CheckStatus.PASSED.value)
            ),
            findings_count=r10_count,
            note=err,
        )
    )
    audits.append(
        RuleAuditItem(
            rule_id=11,
            rule_name="各章缺少方法动机描述",
            category="语义核查",
            status=(
                CheckStatus.FINDING.value
                if r11_count
                else (CheckStatus.FAILED.value if err else CheckStatus.PASSED.value)
            ),
            findings_count=r11_count,
            note=err,
        )
    )
    findings.extend(topic_findings)
    audits.append(topic_audit)
    return findings, audits
