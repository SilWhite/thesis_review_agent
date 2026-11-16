"""Review adapters and 37-rule negative checklist engine."""

from typing import List
from pathlib import Path
import hashlib
import json
import uuid
from .schemas import Assessment, Finding, RuleAuditItem, CheckStatus
from .evidence import attach_evidence
from .checkers import (
    ThesisDocumentTree,
    DeterministicChecker,
    LayoutChecker,
    SemanticChecker,
    build_document_tree_from_pdf,
    build_document_tree_from_docx,
    build_document_tree_from_blocks,
)


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
        self.semantic_checker.review_focus = getattr(request, 'custom_prompt', '').strip()

        if request.model_mode == 'local' and self.semantic_checker.settings is not None:
            trace = Path(self.semantic_checker.settings.data_dir) / 'review_traces' / uuid.uuid4().hex
            trace.mkdir(parents=True,exist_ok=True)
            self.semantic_checker.trace_dir = trace
            (trace/'metadata.json').write_text(json.dumps({
                'document_ids':request.document_ids,'filename':tree.filename,
                'source_sha256':hashlib.sha256(source_path.read_bytes()).hexdigest() if source_path and source_path.exists() else None,
                'source_hashes':{name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
                    for name in ('review.py','checkers/semantic_checker.py','checkers/semantic_coverage.py')},
                'model':self.semantic_checker.settings.model_name,
            },ensure_ascii=False,indent=2),encoding='utf-8')

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
        sem_findings, sem_audits = self.semantic_checker.check_all(tree, model_mode=request.model_mode)
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
            if audit.status == CheckStatus.PASSED.value and audit.rule_id in limitations:
                audit.status = CheckStatus.UNCERTAIN.value
                audit.note = limitations[audit.rule_id]

        # A parser that never reaches the body cannot substantiate a clean review.
        if not tree.all_body_paragraphs:
            all_findings = []
            for audit in all_audits:
                if audit.status != CheckStatus.NA.value:
                    audit.status = CheckStatus.UNCERTAIN.value
                    audit.findings_count = 0
                    audit.note = "未识别到正文，无法确认本项是否通过；请检查文件文本提取结果。"

        # Sort findings by rule_id
        attach_evidence(tree, all_findings)
        all_findings.sort(key=lambda f: (f.severity != "major", f.rule_id))

        # Overall verdict
        major_count = sum(1 for f in all_findings if f.severity == "major")
        minor_count = sum(1 for f in all_findings if f.severity == "minor")
        incomplete_count = sum(1 for a in all_audits if a.status in {
            CheckStatus.FAILED.value, CheckStatus.MISSING_INPUT.value, CheckStatus.UNCERTAIN.value
        })

        if major_count >= 3:
            verdict = "存在重大问题"
        elif major_count > 0 or minor_count > 0:
            verdict = "需修改"
        elif incomplete_count:
            verdict = "信息不足"
        else:
            verdict = "基本满足"

        summary = (
            f"本次针对毕业论文负面写作与格式规范清单（共37项）开展全自动深度核查。"
            f"共检出 {len(all_findings)} 条问题提示（包含 {major_count} 条较严重提示、{minor_count} 条一般提示），请结合证据核对。"
        )
        if incomplete_count:
            summary += f" 另有 {incomplete_count} 项未能可靠完成，请查看各项状态。"
        elif not all_findings:
            summary = "本次 37 项写作负面与格式规范核查全部通过，未检测出明确违规项。"

        # Priority actions
        priority_actions = []
        for f in all_findings[:5]:
            priority_actions.append(f"【规则 {f.rule_id}】{f.issue} -> {f.suggestion}")
        if incomplete_count:
            priority_actions.append(f"请人工复核未能可靠完成的 {incomplete_count} 项检查。")
        elif not priority_actions:
            priority_actions.append("论文各项格式规范均达到要求，建议继续推进答辩审批流程。")

        return Assessment(
            verdict=verdict,
            summary=summary,
            findings=all_findings,
            rule_matrix=all_audits,
            priority_actions=priority_actions,
        )


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


def validate_evidence(assessment: Assessment, blocks: list) -> List[Finding]:
    lookup = {b["id"]: b for b in blocks}
    
    for finding in assessment.findings:
        if finding.locations and all(loc.verified for loc in finding.locations):
            continue
        # 1. If block_id is already valid
        if finding.block_id and finding.block_id in lookup:
            continue
            
        matched_id = None
        # 2. Try matching quote in block texts
        quote_snippet = (finding.quote or "").strip()
        if len(quote_snippet) >= 4:
            search_key = quote_snippet[:40]
            for b in blocks:
                if search_key in b.get("text", ""):
                    matched_id = b["id"]
                    break

        # 3. Try matching page from locations
        if not matched_id and finding.locations:
            for loc in finding.locations:
                if loc.block_id and loc.block_id in lookup:
                    matched_id = loc.block_id
                    break
                if matched_id:
                    break

        if matched_id:
            finding.block_id = matched_id
        else:
            # If quote exists but cannot be verified in extracted blocks, mark pending_verification
            if finding.quote and len(finding.quote.strip()) > 0:
                finding.status = "pending_verification"
            # Do NOT falsely assign to the first paragraph/block
            finding.block_id = ""

    return assessment.findings


def markdown(report: dict) -> str:
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", "<br>")

    out = [
        "# 毕业论文写作负面清单与格式规范审核" + ("最终报告" if report.get('report_type') == 'final' else "报告"),
        "",
        (f"**生成时间**：{report.get('generated_at', '')}" if report.get('report_type') == 'final' else
         f"**审核模式**：{report.get('mode', 'local')} | **模型引擎**：{report.get('model_name', 'Qwen3')} | **生成时间**：{report.get('generated_at', '')}"),
        "",
        "## 总体审核结论",
        f"**结论判定**：{report.get('verdict', '信息不足')}",
        "",
        report.get("summary", ""),
        "",
        "## 问题提示",
        "| 规则序号 | 分类 | 严重度 | 核实状态 | 定位与原句 | 问题及测量值 | 修改建议 |",
        "| :---: | :---: | :---: | :---: | :--- | :--- | :--- |",
    ]

    findings = report.get("findings", [])
    if findings:
        for f in findings:
            r_id = f.get("rule_id", 0)
            cat = f.get("rule_category", "通用")
            sev = "严重 (Major)" if f.get("severity") == "major" else "轻微 (Minor)"
            loc_str = f"{f.get('location', '')} [{f.get('quote', '')[:30]}]"
            meas = f"<br>*(测量值: {f.get('measurement')})*" if f.get("measurement") else ""
            issue_text = f"{f.get('issue', '')}{meas}"
            sugg_text = f.get("suggestion", "")

            out.append(
                f"| {r_id} | {cell(cat)} | {cell(sev)} | {'待核实' if f.get('status') == 'pending_verification' else '有依据'} | {cell(loc_str)} | {cell(issue_text)} | {cell(sugg_text)} |"
            )
    else:
        out += ["", "未输出问题提示，请结合下方每项状态查看检查范围。"]

    if findings:
        out += ['', '## 逐项原文与证据']
        for index, finding in enumerate(findings, 1):
            out += ['', f"### {index}. 规则 {finding.get('rule_id')}：{finding.get('issue', '')}"]
            if finding.get('evidence_note'):
                out.append(f"核对重点：{finding['evidence_note']}")
            if finding.get('measurement'):
                out.append(f"检查结果：{finding['measurement']}")
            for loc in finding.get('locations', []):
                out += ['', f"PDF 第 {loc['page']} 页" if loc.get('page') else '原文位置']
                if loc.get('description'):
                    out.append(loc['description'])
                text = loc.get('context') or loc.get('quote') or ''
                if text:
                    out.extend('> ' + line for line in text.splitlines())

    if report.get("rule_matrix"):
        out += ["", "## 各项检查状态", "| 序号 | 检查项 | 状态 | 数量 | 说明 |", "| :---: | :--- | :--- | :---: | :--- |"]
        for rule in sorted(report["rule_matrix"], key=lambda item: item.get("rule_id", 0)):
            out.append(f"| {rule.get('rule_id', '')} | {cell(rule.get('rule_name', ''))} | {cell(rule.get('status', ''))} | {rule.get('findings_count', 0)} | {cell(rule.get('note') or '')} |")

    out += [
        "",
        "## 优先整改行动建议",
        *[f"- {s}" for s in report.get("priority_actions", [])],
        "",
        "## 审查说明与限制",
        *[f"- {s}" for s in report.get("limitations", [])],
    ]
    return "\n".join(out)
