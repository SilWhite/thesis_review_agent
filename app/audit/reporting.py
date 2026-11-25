"""A separate, evidence-linked supplemental report, never a 37-rule verdict."""


def markdown(report):
    def cell(value):
        return str(value or "").replace("|", "\\|").replace("\n", "<br>")

    out = [
        "# 论文综合补充审查报告",
        "",
        f"生成时间：{report['generated_at']}",
        f"模式：{report['mode']}；本报告不修改原 37 项规范审查及其结论。",
        "",
    ]

    # --- 1. Novelty & Idea Plagiarism Audit ---
    novelty = report.get("novelty", {})
    if novelty.get("status") != "未启用":
        out += [
            "## 思想抄袭与创新性核查",
            f"**审查结论**：{novelty.get('status', '未知')}",
            "",
            f"> **总结评语**：{novelty.get('summary') or novelty.get('basis', '')}",
            "",
        ]

        # Taxonomy Tree (OpenNovelty style)
        tax = novelty.get("taxonomy_tree") or {}
        lookup = {s["id"]: s for s in novelty.get("sources", [])}
        if tax.get("branches"):
            out += [
                "### 相关工作技术范式演进分类树（Taxonomy Tree）",
                f"- **课题核心领域**：{tax.get('root_topic', '学术前沿')}",
                f"- **待审论文定位**：{tax.get('target_position', '前沿探索')}",
                "",
            ]
            for b in tax.get("branches", []):
                star = " ★ 【待审论文锚定此路线】" if b.get("is_target_branch") else ""
                paper_items = []
                for pid in b.get("papers", []):
                    ps = lookup.get(pid, {})
                    title = ps.get("title", pid)
                    year = ps.get("year") or ps.get("published") or ""
                    yr_str = f" ({year})" if year else ""
                    paper_items.append(f"`{pid}` 《{title}》{yr_str}")
                papers_str = "、".join(paper_items) if paper_items else "暂无"
                out += [
                    f"#### 范式路线：{b.get('name', '技术分支')}{star}",
                    f"- **范式特征**：{b.get('description', '')}",
                    f"- **涵盖核心文献**：{papers_str}",
                    "",
                ]

        comparisons = novelty.get("comparisons", [])
        if comparisons:
            out.append("### 逐创新点（Claim-by-Claim）细粒度碰撞对比")
            for idx, item in enumerate(comparisons):
                source = lookup.get(item.get("source_id"), {})
                if source:
                    source_title = source.get("title") or "相关文献"
                    source_url = source.get("url") or ""
                    venue_str = (
                        f" · 刊物/会议: {source['venue']}"
                        if source.get("venue")
                        else ""
                    )
                    cit_str = (
                        f" · 被引: {source['citation_count']}"
                        if source.get("citation_count") is not None
                        else ""
                    )
                    source_line = f"- **对标先验文献**：[{source_title}]({source_url})（{source.get('year') or source.get('published') or '年份未知'}{venue_str}{cit_str}）"
                else:
                    source_line = (
                        "- **对标先验文献**：（当前检索库未匹配到可直接对标的先验文献）"
                    )
                out += [
                    "",
                    f"#### 创新主张 #{idx + 1}：“{item.get('claim', '核心方法')}”",
                    f"- **所属技术分支**：{item.get('taxonomy_branch', '前沿范式')}",
                    f"- **审查判定**：**{item.get('judgment', '增量改进')}**",
                    source_line,
                ]
                if item.get("prior_works_summary"):
                    out.append(f"- **前人已有工作概括**：{item['prior_works_summary']}")
                if item.get("prosecutor_overlap"):
                    out.append(
                        f"- **思想重合审查（重合风险）**：{item['prosecutor_overlap']}"
                    )
                if item.get("defender_novelty"):
                    out.append(
                        f"- **独特增量抗辩（创新保护）**：{item['defender_novelty']}"
                    )
                out += [
                    f"- **Delta 核心差异裁决**：{item.get('difference', '')}",
                    "- **原文佐证依据**：",
                    f"  - **待审论文陈述**：> {item.get('paper_quote', '')}",
                    f"  - **先验文献依据**：> {item.get('source_quote', '')}",
                ]

        sources = novelty.get("sources") or []
        if sources:
            out += [
                "",
                f"### 已检索的公开学术候选文献库（共 {len(sources)} 篇）",
                "",
                "| 编号 | 论文标题 | 年份 | 刊物/会议 | 引用量 | 核心摘要/TLDR |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
            for s in sources:
                link_title = f"[{s.get('title', '')}]({s.get('url') or '#'})"
                tldr = s.get("tldr") or (s.get("abstract") or "")[:150]
                out.append(
                    "| "
                    + " | ".join(
                        cell(x)
                        for x in [
                            s.get("id", ""),
                            link_title,
                            s.get("year") or s.get("published") or "-",
                            s.get("venue") or "-",
                            (
                                str(s["citation_count"])
                                if s.get("citation_count") is not None
                                else "-"
                            ),
                            tldr,
                        ]
                    )
                    + " |"
                )
        if novelty.get("notes"):
            out.extend("- " + n for n in novelty["notes"])
        out.append("")

    # --- 2. Citation Hallucination Verification ---
    citations = report.get("citations", {})
    if citations and citations.get("status") != "未启用":
        out += [
            "## 参考文献防幻觉与真实性核查",
            f"**核查状态**：{citations.get('status', '未知')}",
            "",
            f"> **核查结论**：{citations.get('summary', '')}",
            "",
            f"- **核查总数**：{citations.get('total_checked', 0)} 篇",
            f"- **确认存在**：{citations.get('verified_count', 0)} 篇",
            f"- **元数据偏差**：{citations.get('mismatch_count', 0)} 篇",
            f"- **疑似编造/虚构**：{citations.get('phantom_count', 0)} 篇",
            "",
        ]
        items = citations.get("items", [])
        if items:
            out += [
                "| 序号 | 论文著录信息 | 数据库匹配文献 | 匹配度 | 判定结果 | 说明与建议 |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
            for it in items:
                matched_desc = ""
                if it.get("matched_title"):
                    matched_desc = f"《{it['matched_title']}》"
                    if it.get("matched_doi"):
                        matched_desc += f"<br>DOI: {it['matched_doi']}"
                else:
                    matched_desc = "（无匹配记录）"

                out.append(
                    "| "
                    + " | ".join(
                        cell(x)
                        for x in [
                            it.get("id", ""),
                            it.get("raw", ""),
                            matched_desc,
                            (
                                f"{int(it.get('similarity', 0)*100)}%"
                                if it.get("similarity")
                                else "0%"
                            ),
                            it.get("status_cn", ""),
                            it.get("note", ""),
                        ]
                    )
                    + " |"
                )
        if citations.get("notes"):
            out.extend("- " + n for n in citations["notes"])
        out.append("")

    # --- 3. Consistency with Materials ---
    experiments = report.get("experiments", [])
    if experiments:
        out.append("## 实验材料一致性核查")
        for experiment in experiments:
            coverage = experiment.get("coverage", {})
            num_fields = coverage.get("numeric_fields", [])
            id_files = coverage.get("id_files", [])
            out += [
                "",
                f"### 实验 {experiment.get('id', '')}：{experiment.get('name', '')}",
                f"状态：{experiment.get('status', '')}",
                "具有同名数值字段："
                + (", ".join(num_fields) or "无")
                + f"；具有完整指定 ID 列的数据文件：{len(id_files)} 份。",
                "",
                "| 检查 | 状态 | 位置与依据 | 问题 | 核查建议 |",
                "| --- | --- | --- | --- | --- |",
            ]
            for item in experiment.get("findings", []):
                evidence = "; ".join(
                    f"{e.get('filename', '')} / {e.get('location', '')}：{e.get('quote', e.get('value', ''))}"
                    for e in item.get("evidence", [])
                )
                out.append(
                    "| "
                    + " | ".join(
                        cell(x)
                        for x in [
                            item.get("check", ""),
                            item.get("status", ""),
                            evidence,
                            item.get("issue", ""),
                            item.get("suggestion", ""),
                        ]
                    )
                    + " |"
                )
            if experiment.get("repository"):
                repo = experiment["repository"]
                out += [
                    "",
                    f"仓库：{repo['location']}；commit：{repo['commit']}；索引文件：{repo['file_count']}",
                ]
                out.extend(f"- {f['path']}：{f['sha256']}" for f in repo["files"])
                out.extend(
                    f"- 主张 {c['id']} [{c['kind']}]：{c['evidence']['filename']} / {c['evidence']['location']}：{c['evidence']['quote']}"
                    for c in experiment.get("claims", [])
                )
            out.extend("- " + note for note in experiment.get("notes", []))
        out.append("")

    out += ["## 审查范围与限制", *["- " + n for n in report.get("limitations", [])]]
    return "\n".join(out) + "\n"
