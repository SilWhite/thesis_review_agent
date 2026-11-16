"""Semantic task: check_introduction."""

import re
from typing import List, Tuple
from app.schemas import Finding, EvidenceLocation, RuleAuditItem, CheckStatus
from app.documents.models import ThesisDocumentTree
from app.review.checks.coverage_intro import review_intro


def check_introduction(
    checker, tree: ThesisDocumentTree, model_mode: str
) -> Tuple[List[Finding], List[RuleAuditItem]]:
    findings = []
    audits = []

    intro_ch = next(
        (ch for ch in tree.chapters if ch.role == "intro" or ch.level == 1), None
    )
    if not intro_ch:
        return findings, [
            RuleAuditItem(
                rule_id=7,
                rule_name="现状分析仅文献罗列",
                category="语义核查",
                status=CheckStatus.MISSING_INPUT.value,
                note="未识别到第一章或引言",
            ),
            RuleAuditItem(
                rule_id=8,
                rule_name="未在现状后总结关键问题",
                category="语义核查",
                status=CheckStatus.MISSING_INPUT.value,
                note="未识别到第一章或引言",
            ),
            RuleAuditItem(
                rule_id=9,
                rule_name="未阐明各章有机联系",
                category="语义核查",
                status=CheckStatus.MISSING_INPUT.value,
                note="未识别到第一章或引言",
            ),
        ]

    ch1_text = " ".join(p.text for p in intro_ch.paragraphs)

    # Rule 7: 现状分析仅罗列无分类优缺点
    re_pure_list = re.findall(
        r"([\u4e00-\u9fa5]{2,4}|[A-Za-z]+)\s*(等人|提出|设计了)", ch1_text
    )
    has_framework = any(
        kw in ch1_text
        for kw in ["分类", "归纳", "对比", "优缺点", "局限性", "不足之处"]
    )
    if len(re_pure_list) >= 4 and not has_framework:
        findings.append(
            Finding(
                rule_id=7,
                rule_category="语义核查",
                dimension="规范与逻辑",
                severity="major",
                status="supported",
                block_id=(intro_ch.paragraphs[0].id if intro_ch.paragraphs else "ch1"),
                quote=intro_ch.title,
                locations=[
                    EvidenceLocation(
                        page=intro_ch.page,
                        quote=ch1_text[:100],
                        description="第一章文献综述片段",
                    )
                ],
                issue="第一章国内外研究现状分析仅有文献内容的机械罗列，缺少系统的方法分类框架与优缺点批判性对比分析。",
                suggestion="请重塑文献综述结构：按照技术路线或方法属性将已有文献分类（如基于机理模型 vs 基于数据驱动），并增加分类对比表格，评述各类方法的优势与固有瓶颈。",
            )
        )
        audits.append(
            RuleAuditItem(
                rule_id=7,
                rule_name="现状分析仅文献罗列",
                category="语义核查",
                status=CheckStatus.FINDING.value,
                findings_count=1,
            )
        )
    else:
        audits.append(
            RuleAuditItem(
                rule_id=7,
                rule_name="现状分析仅文献罗列",
                category="语义核查",
                status=CheckStatus.PASSED.value,
            )
        )

    intro_findings, intro_audits = review_intro(checker, tree, intro_ch, model_mode)
    findings.extend(intro_findings)
    audits.extend(intro_audits)

    if model_mode != "mock" and not any(f.rule_id == 7 for f in findings):
        survey = []
        for ch in tree.chapters:
            if ch is not intro_ch and ch.role != "survey":
                continue
            active = ch.role == "survey"
            survey_level = ch.level
            for p in ch.paragraphs:
                if p.is_heading:
                    if re.search(
                        r"研究现状|相关研究|相关工作|文献综述|国内外|related work|literature review",
                        p.text,
                        re.I,
                    ):
                        active, survey_level = True, p.heading_level
                    elif (
                        active
                        and p.heading_level <= survey_level
                        and ch.role != "survey"
                    ):
                        active = False
                    if active:
                        survey.append(p)
                elif active and not (
                    p.is_caption or p.is_formula or p.is_table_cell or p.is_figure_text
                ):
                    survey.append(p)
        # If no survey headings survived extraction, inspect the introduction.
        if not survey:
            survey = [
                p for p in intro_ch.paragraphs if not p.is_heading and not p.is_caption
            ]
        extra, errors = checker._grounded_review(
            7,
            survey,
            "检查研究现状是否持续罗列各篇文献，缺少方法分类、联系及优缺点分析。"
            "按内容判断，出现“分类”等词也可能只是在描述任务名称。"
            "材料可能是综述的一部分；局部罗列常用于介绍某类方法，不足以单独证明整篇没有分类。"
            "明确缺少分析时，issue说明哪些文献被连续罗列及缺少什么分析。",
            model_mode,
        )
        findings.extend(extra)
        audit = next(a for a in audits if a.rule_id == 7)
        audit.findings_count = len(extra)
        audit.status = (
            CheckStatus.FINDING.value if extra else CheckStatus.UNCERTAIN.value
        )
        audit.note = "已补查研究现状文字；长篇分段检查，需结合完整综述核对。" + (
            " 模型补查失败。" if errors else ""
        )
    return findings, audits
