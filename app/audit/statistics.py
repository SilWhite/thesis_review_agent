"""Deterministic bounds on explicitly named statistics, without inferring raw data."""

import re

NUMBER = r"-?\d+(?:\.\d+)?"


def review(blocks):
    findings = []
    for block in blocks:
        for line in block["text"].splitlines():
            issues = []
            for match in re.finditer(
                rf"(?:准确率|accuracy|macro[-_ ]?f1)\s*[:=为]?\s*({NUMBER})\s*(%)?",
                line,
                re.I,
            ):
                value = float(match[1])
                upper = 100 if match[2] else 1
                if value < 0 or (match[2] and value > upper):
                    issues.append(
                        "显式准确率/F1数值超出其定义范围，请核对单位和计算方式。"
                    )
            values = {}
            for label, key in [
                ("最小值", "min"),
                ("最大值", "max"),
                ("均值", "mean"),
                ("标准差", "std"),
            ]:
                matches = list(re.finditer(rf"{label}\s*[:=为]?\s*({NUMBER})", line))
                if len(matches) == 1:
                    values[key] = float(matches[0][1])
            if values.get("std", 0) < 0:
                issues.append("标准差不能为负数。")
            if "min" in values and "max" in values:
                if values["min"] > values["max"]:
                    issues.append(
                        "同一行报告的最小值大于最大值，需核实是否为同一统计对象。"
                    )
                elif (
                    "mean" in values
                    and not values["min"] <= values["mean"] <= values["max"]
                ):
                    issues.append(
                        "同一行报告的均值不在最小值与最大值之间，需核实统计对象及口径。"
                    )
            for issue in issues:
                findings.append(
                    dict(
                        check="statistical_bounds",
                        status="发现数值疑点，待核实",
                        evidence=[
                            dict(
                                source_id=block["id"],
                                filename=block["filename"],
                                location=block["location"],
                                quote=line,
                            )
                        ],
                        issue=issue,
                        suggestion="核对原始表格、单位、统计总体与计算过程；不据此认定数据虚构。",
                    )
                )
    return findings
