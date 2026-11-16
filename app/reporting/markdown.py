"""Render original and final reports with the existing format."""


def markdown(report: dict) -> str:
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", "<br>")

    out = [
        "# 毕业论文写作负面清单与格式规范审核"
        + ("最终报告" if report.get("report_type") == "final" else "报告"),
        "",
        (
            f"**生成时间**：{report.get('generated_at', '')}"
            if report.get("report_type") == "final"
            else f"**审核模式**：{report.get('mode', 'local')} | **模型引擎**：{report.get('model_name', 'Qwen3')} | **生成时间**：{report.get('generated_at', '')}"
        ),
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
            meas = (
                f"<br>*(测量值: {f.get('measurement')})*"
                if f.get("measurement")
                else ""
            )
            issue_text = f"{f.get('issue', '')}{meas}"
            sugg_text = f.get("suggestion", "")

            out.append(
                f"| {r_id} | {cell(cat)} | {cell(sev)} | {'待核实' if f.get('status') == 'pending_verification' else '有依据'} | {cell(loc_str)} | {cell(issue_text)} | {cell(sugg_text)} |"
            )
    else:
        out += ["", "未输出问题提示，请结合下方每项状态查看检查范围。"]

    if findings:
        out += ["", "## 逐项原文与证据"]
        for index, finding in enumerate(findings, 1):
            out += [
                "",
                f"### {index}. 规则 {finding.get('rule_id')}：{finding.get('issue', '')}",
            ]
            if finding.get("evidence_note"):
                out.append(f"核对重点：{finding['evidence_note']}")
            if finding.get("measurement"):
                out.append(f"检查结果：{finding['measurement']}")
            for loc in finding.get("locations", []):
                out += [
                    "",
                    f"PDF 第 {loc['page']} 页" if loc.get("page") else "原文位置",
                ]
                if loc.get("description"):
                    out.append(loc["description"])
                text = loc.get("context") or loc.get("quote") or ""
                if text:
                    out.extend("> " + line for line in text.splitlines())

    if report.get("rule_matrix"):
        out += [
            "",
            "## 各项检查状态",
            "| 序号 | 检查项 | 状态 | 数量 | 说明 |",
            "| :---: | :--- | :--- | :---: | :--- |",
        ]
        for rule in sorted(
            report["rule_matrix"], key=lambda item: item.get("rule_id", 0)
        ):
            out.append(
                f"| {rule.get('rule_id', '')} | {cell(rule.get('rule_name', ''))} | {cell(rule.get('status', ''))} | {rule.get('findings_count', 0)} | {cell(rule.get('note') or '')} |"
            )

    out += [
        "",
        "## 优先整改行动建议",
        *[f"- {s}" for s in report.get("priority_actions", [])],
        "",
        "## 审查说明与限制",
        *[f"- {s}" for s in report.get("limitations", [])],
    ]
    return "\n".join(out)
