"""Machine-assessment policy; human-reviewed policy stays in reporting/final.py."""

from app.schemas import Assessment, CheckStatus


def build_assessment(all_findings, all_audits):
    # Overall verdict
    major_count = sum(1 for f in all_findings if f.severity == "major")
    minor_count = sum(1 for f in all_findings if f.severity == "minor")
    incomplete_count = sum(
        1
        for a in all_audits
        if a.status
        in {
            CheckStatus.FAILED.value,
            CheckStatus.MISSING_INPUT.value,
            CheckStatus.UNCERTAIN.value,
        }
    )

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
        priority_actions.append(
            "论文各项格式规范均达到要求，建议继续推进答辩审批流程。"
        )

    return Assessment(
        verdict=verdict,
        summary=summary,
        findings=all_findings,
        rule_matrix=all_audits,
        priority_actions=priority_actions,
    )
