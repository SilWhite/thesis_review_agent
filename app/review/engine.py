"""Review adapters and 37-rule negative checklist engine."""

from typing import List
from pathlib import Path
import hashlib
import json
import uuid
from app.schemas import Assessment, Finding, RuleAuditItem, CheckStatus
from app.evidence.locating import attach_evidence
from app.documents import (
    ThesisDocumentTree,
    build_document_tree_from_pdf,
    build_document_tree_from_docx,
    build_document_tree_from_blocks,
)
from .checks.deterministic import DeterministicChecker
from .checks.layout import LayoutChecker
from .checks.semantic import SemanticChecker
from .verdict import build_assessment


class NegativeChecklistReviewer:
    def __init__(self, settings=None):
        self.settings = settings
        self.deterministic_checker = DeterministicChecker()
        self.layout_checker = LayoutChecker()
        self.semantic_checker = SemanticChecker(settings)

    def assess(
        self,
        request,
        blocks: list,
        policies: list,
        source_path: Path = None,
        tree: ThesisDocumentTree = None,
    ) -> Assessment:
        # Build Document Tree if not provided
        filename = blocks[0].get("filename", "thesis") if blocks else "thesis"
        if tree is None:
            if source_path and source_path.exists():
                suffix = source_path.suffix.lower()
                if suffix == ".pdf":
                    tree = build_document_tree_from_pdf(source_path, filename)
                elif suffix == ".docx":
                    tree = build_document_tree_from_docx(source_path, filename)
                else:
                    tree = build_document_tree_from_blocks(blocks, filename)
            else:
                tree = build_document_tree_from_blocks(blocks, filename)

        if request.degree and request.degree != "unknown":
            tree.degree = request.degree
        self.semantic_checker.review_focus = getattr(
            request, "custom_prompt", ""
        ).strip()

        if request.model_mode == "local" and self.semantic_checker.settings is not None:
            trace = (
                Path(self.semantic_checker.settings.data_dir)
                / "review_traces"
                / uuid.uuid4().hex
            )
            trace.mkdir(parents=True, exist_ok=True)
            self.semantic_checker.model.trace_dir = trace
            (trace / "metadata.json").write_text(
                json.dumps(
                    {
                        "document_ids": request.document_ids,
                        "filename": tree.filename,
                        "source_sha256": (
                            hashlib.sha256(source_path.read_bytes()).hexdigest()
                            if source_path and source_path.exists()
                            else None
                        ),
                        "source_hashes": {
                            name: hashlib.sha256(
                                (
                                    Path(__file__).resolve().parents[1] / name
                                ).read_bytes()
                            ).hexdigest()
                            for name in (
                                "review/engine.py",
                                "model_client.py",
                                *sorted(
                                    str(
                                        p.relative_to(
                                            Path(__file__).resolve().parents[1]
                                        )
                                    ).replace("\\", "/")
                                    for p in (Path(__file__).parent / "checks").rglob(
                                        "*.py"
                                    )
                                ),
                            )
                        },
                        "model": self.semantic_checker.settings.model_name,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        all_findings: List[Finding] = []
        all_audits: List[RuleAuditItem] = []

        # 1. Deterministic checks (9 rules)
        det_findings, det_audits = self.deterministic_checker.check_all(tree)
        all_findings.extend(det_findings)
        all_audits.extend(det_audits)

        # 2. Layout checks (14 rules)
        lay_findings, lay_audits = self.layout_checker.check_all(tree)
        all_findings.extend(lay_findings)
        all_audits.extend(lay_audits)

        # 3. Semantic checks (14 rules)
        sem_findings, sem_audits = self.semantic_checker.check_all(
            tree, model_mode=request.model_mode
        )
        all_findings.extend(sem_findings)
        all_audits.extend(sem_audits)

        # A narrow heuristic cannot establish that every instance is clean.
        limitations = {
            2: "中文使用固定长度片段，未完整覆盖连续十个词及所有重复位置。",
            7: "仅按少量文献综述用词筛查，尚未完整判断分类与优缺点。",
            13: "已检查可识别符号及前文和下一页说明；复杂公式仍需结合原页核对。",
            14: "仅比较识别出的摘要和小结文字，未覆盖所有语义雷同。",
            16: "已比较识别出的摘要、小结和总结文字；语义改写仍需复核。",
            21: "当前只筛查图表标题中的部分英文，未覆盖图片和表格内部文字。",
            22: "当前只检查部分表格字号，尚未识别图内文字字号。",
            25: "当前只筛查部分位图分辨率，未完整判断图表是否清晰。",
            27: "当前主要依据题注位置，可能漏掉题注前的图片。",
        }
        for audit in all_audits:
            if (
                audit.status == CheckStatus.PASSED.value
                and audit.rule_id in limitations
            ):
                audit.status = CheckStatus.UNCERTAIN.value
                audit.note = limitations[audit.rule_id]

        # A parser that never reaches the body cannot substantiate a clean review.
        if not tree.all_body_paragraphs:
            all_findings = []
            for audit in all_audits:
                if audit.status != CheckStatus.NA.value:
                    audit.status = CheckStatus.UNCERTAIN.value
                    audit.findings_count = 0
                    audit.note = (
                        "未识别到正文，无法确认本项是否通过；请检查文件文本提取结果。"
                    )

        # Sort findings by rule_id
        attach_evidence(tree, all_findings)
        all_findings.sort(key=lambda f: (f.severity != "major", f.rule_id))

        return build_assessment(all_findings, all_audits)


class MockReviewer:
    def __init__(self):
        self.engine = NegativeChecklistReviewer()

    def assess(self, request, blocks, policies, source_path=None, tree=None):
        return self.engine.assess(request, blocks, policies, source_path, tree=tree)


class LocalReviewer:
    def __init__(self, settings):
        self.engine = NegativeChecklistReviewer(settings)

    def assess(self, request, blocks, policies, source_path=None, tree=None):
        return self.engine.assess(request, blocks, policies, source_path, tree=tree)
