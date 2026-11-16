"""Coordinate semantic tasks while preserving the existing checker entry points."""

from typing import List, Tuple
from app.model_client import ModelClient
from app.schemas import Finding, RuleAuditItem, CheckStatus
from app.documents.models import ThesisDocumentTree
from app.review.checks.coverage_body import review_body
from .semantic_tasks import abstracts, introduction, chapters, formulas, conclusion
from .semantic_tasks.common import grounded_review


class SemanticChecker:
    def __init__(self, settings=None):
        self.settings = settings
        self.model = ModelClient(settings)
        self.review_focus = ""

    def _call_llm(self, prompt, model_mode):
        self.model.review_focus = self.review_focus
        return self.model.call(prompt, model_mode)

    def check_all(
        self, tree: ThesisDocumentTree, model_mode: str = "mock"
    ) -> Tuple[List[Finding], List[RuleAuditItem]]:
        findings: List[Finding] = []
        audit_items: List[RuleAuditItem] = []
        if tree.total_pages and not tree.all_body_paragraphs:
            names = {
                3: "中英文标题对应",
                4: "中英文摘要对应",
                6: "摘要总结段",
                7: "研究现状分析",
                8: "拟解决问题",
                9: "章节联系",
                10: "章节研究目标",
                11: "方法动机",
                13: "公式符号定义",
                14: "小结与摘要雷同",
                16: "总结内容雷同",
                21: "图表英文",
                37: "标题与内容对应",
                38: "逻辑连词",
            }
            return [], [
                RuleAuditItem(
                    rule_id=rid,
                    rule_name=name,
                    category="语义核查",
                    status=CheckStatus.MISSING_INPUT.value,
                    note="未可靠识别正文，暂停语义判断以避免把读取问题当成论文问题",
                )
                for rid, name in names.items()
            ]

        for task in (
            self._run_task_1_bilingual_abstract,
            self._run_task_2_intro_survey,
        ):
            found, audited = task(tree, model_mode)
            findings.extend(found)
            audit_items.extend(audited)

        body_review = review_body(self, tree, model_mode)
        for task, args in (
            (self._run_task_3_core_chapters, (tree, model_mode, body_review)),
            (self._run_task_4_formula_symbols, (tree, model_mode)),
            (self._run_task_5_conclusion_conjunctions, (tree, model_mode, body_review)),
        ):
            found, audited = task(*args)
            findings.extend(found)
            audit_items.extend(audited)

        return findings, audit_items

    def _grounded_review(
        self, rule, paragraphs, instruction, model_mode, max_batches=4
    ):
        return grounded_review(
            self, rule, paragraphs, instruction, model_mode, max_batches
        )

    def _run_task_1_bilingual_abstract(
        self, tree: ThesisDocumentTree, model_mode: str
    ) -> Tuple[List[Finding], List[RuleAuditItem]]:
        return abstracts.check_abstracts(self, tree, model_mode)

    def _run_task_2_intro_survey(
        self, tree: ThesisDocumentTree, model_mode: str
    ) -> Tuple[List[Finding], List[RuleAuditItem]]:
        return introduction.check_introduction(self, tree, model_mode)

    def _run_task_3_core_chapters(
        self, tree: ThesisDocumentTree, model_mode: str, body_review=None
    ) -> Tuple[List[Finding], List[RuleAuditItem]]:
        return chapters.check_chapters(self, tree, model_mode, body_review)

    def _run_task_4_formula_symbols(
        self, tree: ThesisDocumentTree, model_mode: str
    ) -> Tuple[List[Finding], List[RuleAuditItem]]:
        return formulas.check_formulas(self, tree, model_mode)

    def _run_task_5_conclusion_conjunctions(
        self, tree: ThesisDocumentTree, model_mode: str, body_review=None
    ) -> Tuple[List[Finding], List[RuleAuditItem]]:
        return conclusion.check_conclusion(self, tree, model_mode, body_review)
