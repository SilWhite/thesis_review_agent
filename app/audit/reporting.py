"""A separate, evidence-linked supplemental report, never a 37-rule verdict."""


def markdown(report):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", "<br>")

    out = [
        "# 创新性与实验材料审查",
        "",
        f"生成时间：{report['generated_at']}",
        f"模式：{report['mode']}；本报告不修改原 37 项检查及其结论。",
        "",
        "## 创新性初判",
        report["novelty"]["status"],
        report["novelty"]["basis"],
    ]
    novelty = report["novelty"]
    lookup = {s["id"]: s for s in novelty["sources"]}
    for item in novelty["comparisons"]:
        source = lookup[item["source_id"]]
        out += [
            "",
            f"### {source['title']}",
            f"来源：{source['url']}；范围：{source['scope']}",
            f"初判：{item['judgment']}",
            f"论文依据：{item['paper_quote']}",
            f"相关工作依据：{item['source_quote']}",
            item["difference"],
        ]
    out += ["", "### 已取得的候选文献"]
    out.extend(
        f"- {s['id']}：{s['title']}；{s['url']}；{s['published'] or '日期未知'}；{s['scope']}"
        for s in novelty["sources"]
    )
    out.extend("- " + n for n in novelty["notes"])
    for experiment in report["experiments"]:
        coverage = experiment["coverage"]
        out += [
            "",
            f"## 实验 {experiment['id']}：{experiment['name']}",
            experiment["status"],
            "具有同名数值字段："
            + (", ".join(coverage["numeric_fields"]) or "无")
            + f"；具有完整指定 ID 列的数据文件：{len(coverage['id_files'])} 份。不同字段值、单位和实验关系仍需核实。",
            "",
            "| 检查 | 状态 | 位置与依据 | 问题 | 核查建议 |",
            "| --- | --- | --- | --- | --- |",
        ]
        for item in experiment["findings"]:
            evidence = "; ".join(
                f"{e['filename']} / {e.get('location', '')}：{e.get('quote', e.get('value', ''))}"
                for e in item["evidence"]
            )
            out.append(
                "| "
                + " | ".join(
                    cell(x)
                    for x in [
                        item["check"],
                        item["status"],
                        evidence,
                        item["issue"],
                        item["suggestion"],
                    ]
                )
                + " |"
            )
        out.extend("- " + note for note in experiment["notes"])
    out += ["", "## 范围与限制", *["- " + n for n in report["limitations"]]]
    return "\n".join(out) + "\n"
