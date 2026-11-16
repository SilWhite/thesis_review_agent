"""Build a human-reviewed report without changing the source assessment."""

from collections import Counter
from copy import deepcopy
import hashlib
import json

from app.storage import now

UNRESOLVED = {"无法可靠判断", "执行失败", "缺少输入"}


def report_digest(report):
    return hashlib.sha256(
        json.dumps(
            report, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def validate_exclusions(report, indices):
    if len(indices) != len(set(indices)):
        raise ValueError("划除清单包含重复条目。")
    if any(
        type(i) is not int or i < 0 or i >= len(report.get("findings", []))
        for i in indices
    ):
        raise ValueError("划除清单包含不存在的条目。")
    return sorted(indices)


def build_final_report(report, indices):
    indices = validate_exclusions(report, indices)
    excluded = set(indices)
    result = deepcopy(report)
    original = result.get("findings", [])
    removed_by_rule = Counter(
        f.get("rule_id") for i, f in enumerate(original) if i in excluded
    )
    result["findings"] = [
        dict(f, source_finding_index=i)
        for i, f in enumerate(original)
        if i not in excluded
    ]
    remaining_by_rule = Counter(f.get("rule_id") for f in result["findings"])
    for row in result.get("rule_matrix", []):
        rule = row.get("rule_id")
        row["findings_count"] = remaining_by_rule[rule]
        if removed_by_rule[rule]:
            original_note = row.get("note") or ""
            if row.get("status") not in UNRESOLVED:
                row["status"] = (
                    "发现问题" if remaining_by_rule[rule] else "问题提示已划除"
                )
            row["note"] = (
                original_note if row.get("status") in UNRESOLVED else ""
            ) + f"人工复核划除 {removed_by_rule[rule]} 项，保留 {remaining_by_rule[rule]} 项。"
    total = len(result["findings"])
    major = sum(f.get("severity") == "major" for f in result["findings"])
    unresolved = sum(
        row.get("status") in UNRESOLVED for row in result.get("rule_matrix", [])
    )
    result["verdict"] = (
        "存在重大问题"
        if major
        else (
            "需修改"
            if total
            else (
                "信息不足"
                if unresolved
                or report.get("mode") == "mock"
                or report.get("verdict") == "信息不足"
                else "基本满足"
            )
        )
    )
    result["summary"] = (
        f"人工复核后保留 {total} 项问题，其中较严重 {major} 项、一般 {total-major} 项。"
        f"已划除 {len(excluded)} 项。"
        + (f"另有 {unresolved} 项检查待核对。" if unresolved else "")
    )
    actions = []
    for f in result["findings"]:
        action = f"【规则 {f.get('rule_id', '')}】{f.get('issue', '')} → {f.get('suggestion', '')}"
        if action not in actions:
            actions.append(action)
    if unresolved:
        actions.append(f"请复核尚未可靠完成的 {unresolved} 项检查。")
    result["priority_actions"] = actions[:5] + (
        [actions[-1]] if unresolved and len(actions) > 5 else []
    )
    result["generated_at"] = now()
    result["report_type"] = "final"
    result["human_review"] = dict(
        excluded_findings=indices,
        original_count=len(original),
        retained_count=total,
        source_report_sha256=report_digest(report),
    )
    # Legacy demo copy may still occur in historical reports.
    result["limitations"] = [
        s.replace("本 demo", "本系统") for s in result.get("limitations", [])
    ]
    return result
