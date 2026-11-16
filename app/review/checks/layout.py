"""Layout and visual presentation checks (Rules: 5, 15, 22, 23, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34)."""

import re
from typing import List, Tuple
from collections import Counter
from app.schemas import Finding, EvidenceLocation, RuleAuditItem, CheckStatus
from app.documents.models import ThesisDocumentTree


class LayoutChecker:
    def check_all(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], List[RuleAuditItem]]:
        findings: List[Finding] = []
        audit_items: List[RuleAuditItem] = []

        runners = [
            (5, "中文摘要第一段篇幅超过0.6页", self._check_rule_5_abstract_first_para),
            (
                15,
                "博士论文总结少于4页/硕士少于2页",
                self._check_rule_15_conclusion_length,
            ),
            (
                22,
                "图表中文字字体显著偏离正文字体",
                self._check_rule_22_figure_font_size,
            ),
            (23, "缺少总图题直接分图标题", self._check_rule_23_missing_main_caption),
            (25, "图表分辨率不够导致内容模糊", self._check_rule_25_image_dpi_blur),
            (
                26,
                "章节标题后无总述文字直接跟子标题",
                self._check_rule_26_heading_transition,
            ),
            (
                27,
                "章节标题后直接跟图或表",
                self._check_rule_27_heading_followed_by_figure,
            ),
            (28, "章节标题在任何页的最后一行", self._check_rule_28_orphan_heading),
            (29, "非章末留有大片空白", self._check_rule_29_blank_space),
            (30, "任何段落超过0.6页长度", self._check_rule_30_long_paragraph),
            (31, "全文超过10个段落少于1行", self._check_rule_31_short_paragraphs),
            (32, "单字或单标点符号占1行", self._check_rule_32_orphan_character),
            (33, "单行占用整页", self._check_rule_33_single_line_page),
            (34, "正文字体字号不一致", self._check_rule_34_inconsistent_body_font),
        ]

        for r_id, r_name, method in runners:
            f_list, a_item = method(tree)
            findings.extend(f_list)
            audit_items.append(a_item)

        return findings, audit_items

    def _check_rule_5_abstract_first_para(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "中文摘要第一段篇幅超过0.6页"
        if not tree.abstract_cn:
            return findings, RuleAuditItem(
                rule_id=5,
                rule_name=rule_name,
                category="版面排版",
                status=CheckStatus.MISSING_INPUT.value,
                note="未提取到中文摘要正文",
            )

        first_p = tree.abstract_cn[0]
        ratio = first_p.ratio_of_page
        if ratio > 0.6 or len(first_p.text) > 650:
            pct_str = (
                f"{ratio * 100:.1f}%"
                if ratio > 0
                else f"约 {len(first_p.text) / 800.0 * 100:.1f}%"
            )
            findings.append(
                Finding(
                    rule_id=5,
                    rule_category="版面排版",
                    dimension="规范与逻辑",
                    severity="minor",
                    status="supported",
                    block_id=first_p.id,
                    quote=first_p.text[:60] + "...",
                    locations=[
                        EvidenceLocation(
                            page=page,
                            block_id=first_p.id,
                            quote=first_p.text[:80],
                            description="中文摘要首段",
                        )
                        for page in (first_p.source_pages or [first_p.page])
                    ],
                    measurement=f"实际篇幅占比: {pct_str}, 阈值: 60%",
                    issue=f"中文摘要第一段篇幅过长（占有效版面 {pct_str}，超过 0.6 页规范限制）。",
                    suggestion="摘要第一段应当高度概括研究背景与核心目标，建议将其适度精简或分段阐述，首段篇幅控制在半页以内。",
                )
            )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=5,
            rule_name=rule_name,
            category="版面排版",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_15_conclusion_length(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "博士论文总结少于4页/硕士少于2页"
        if tree.degree == "bachelor":
            return findings, RuleAuditItem(
                rule_id=15,
                rule_name=rule_name,
                category="版面排版",
                status=CheckStatus.NA.value,
                note="学士/本科毕业论文不套用硕博4/2页强制要求",
            )

        if tree.degree == "unknown":
            return findings, RuleAuditItem(
                rule_id=15,
                rule_name=rule_name,
                category="版面排版",
                status=CheckStatus.MISSING_INPUT.value,
                note="封面未明确学位层级（硕士/博士），保留待核验",
            )

        if not tree.conclusion_chapter:
            return findings, RuleAuditItem(
                rule_id=15,
                rule_name=rule_name,
                category="版面排版",
                status=CheckStatus.MISSING_INPUT.value,
                note="未识别到总结与展望独立章节",
            )

        required = 4.0 if tree.degree == "doctor" else 2.0
        actual = tree.conclusion_pages_count
        if actual < required:
            findings.append(
                Finding(
                    rule_id=15,
                    rule_category="版面排版",
                    dimension="规范与逻辑",
                    severity="major",
                    status="supported",
                    block_id=f"p_{tree.conclusion_chapter.page}",
                    quote=tree.conclusion_chapter.title,
                    locations=[
                        EvidenceLocation(
                            page=tree.conclusion_chapter.page,
                            description=f"{tree.conclusion_chapter.title} 起始页",
                        )
                    ],
                    measurement=f"实际排版页数: 约 {actual:.1f} 页, 最低要求: {required} 整页",
                    issue=f"{'博士' if tree.degree == 'doctor' else '硕士'}学位论文的'全文总结与展望'章节实际篇幅（约 {actual:.1f} 页）少于规范要求的 {required} 整页。",
                    suggestion="请深化全文总结与未来展望章节：更系统地概括全文创新点与关键成果，并从理论拓展、实际工程应用等维度展开更有学术深度的未来工作设想。",
                )
            )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=15,
            rule_name=rule_name,
            category="版面排版",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_22_figure_font_size(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "图表中文字字体显著偏离正文字体"
        base_size = 10.5
        all_sizes = [p.font_size for p in tree.all_body_paragraphs if p.font_size > 0]
        if all_sizes:
            base_size = Counter(all_sizes).most_common(1)[0][0]

        for ch in tree.chapters:
            for tbl in ch.tables:
                if tbl.font_size > 0 and (
                    tbl.font_size > base_size + 1.0 or tbl.font_size < 8.0
                ):
                    findings.append(
                        Finding(
                            rule_id=22,
                            rule_category="版面排版",
                            dimension="规范与逻辑",
                            severity="minor",
                            status="supported",
                            block_id=f"tbl_{tbl.num}",
                            quote=tbl.caption,
                            locations=[
                                EvidenceLocation(
                                    page=tbl.page,
                                    quote=tbl.caption,
                                    description="表格字号异常",
                                )
                            ],
                            measurement=f"表格文字字号: {tbl.font_size:.1f}pt, 正文字号: {base_size:.1f}pt",
                            issue=f"表格 {tbl.num} 内文字字号（{tbl.font_size:.1f}pt）显著偏离正文字体标准（正文为 {base_size:.1f}pt）。",
                            suggestion="规范建议表格字号通常比正文略小半号（如正文为小四12pt时表格采用五号10.5pt，正文为五号时表格采用小五9pt），不应大于正文或过小影响印刷可读性。",
                        )
                    )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=22,
            rule_name=rule_name,
            category="版面排版",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_23_missing_main_caption(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "缺少总图题直接分图标题"
        for ch in tree.chapters:
            for f in ch.figures:
                if f.is_subfig:
                    has_main = any(
                        not other.is_subfig and other.num == f.num
                        for other in ch.figures
                    )
                    if not has_main:
                        findings.append(
                            Finding(
                                rule_id=23,
                                rule_category="版面排版",
                                dimension="规范与逻辑",
                                severity="minor",
                                status="supported",
                                block_id=f"fig_{f.num}",
                                quote=f.caption,
                                locations=[
                                    EvidenceLocation(
                                        page=f.page,
                                        quote=f.caption,
                                        description="缺失总图题的分图题",
                                    )
                                ],
                                issue=f"图 {f.num} 缺少总体图题，直接使用了分图标题（原标题：'{f.caption}'）。",
                                suggestion="根据规范，组合图必须先具有居中的总图题（如'图 5 系统整体架构'），下方各个子图再分别标注'(a) ...'、'(b) ...'。",
                            )
                        )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=23,
            rule_name=rule_name,
            category="版面排版",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_25_image_dpi_blur(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "图表分辨率不够导致内容模糊"
        for p in tree.pages:
            for img in p.images:
                w = img.bbox[2] - img.bbox[0]
                if w > 120 and img.dpi < 150:
                    findings.append(
                        Finding(
                            rule_id=25,
                            rule_category="版面排版",
                            dimension="规范与逻辑",
                            severity="major",
                            status="supported",
                            block_id=f"img_p{img.page}",
                            quote=f"第 {img.page} 页插入图片",
                            locations=[
                                EvidenceLocation(
                                    page=img.page,
                                    bbox=list(img.bbox),
                                    description="低分辨率模糊图片",
                                )
                            ],
                            measurement=f"实际有效印刷DPI: {img.dpi:.0f}, 最低要求: 150~300 DPI",
                            issue=f"第 {img.page} 页插入的图片有效分辨率不足（约为 {img.dpi:.0f} DPI），印刷后将出现严重马赛克或模糊。",
                            suggestion="学术论文印刷标准要求位图插图至少达到 300 DPI（线条图 600 DPI）。建议重新导出高分辨率无损原图（PNG/TIFF）或优先采用矢量格式（PDF/SVG/EPS）。",
                        )
                    )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=25,
            rule_name=rule_name,
            category="版面排版",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_26_heading_transition(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "章节标题后无总述文字直接跟子标题"
        toc_pages = {p.page_num for p in tree.pages if getattr(p, "is_toc", False)}
        for p_idx in range(len(tree.all_body_paragraphs) - 1):
            curr_p = tree.all_body_paragraphs[p_idx]
            next_p = tree.all_body_paragraphs[p_idx + 1]
            if curr_p.page in toc_pages or next_p.page in toc_pages:
                continue
            if curr_p.is_heading and curr_p.heading_level > 0:
                if (
                    next_p.is_heading
                    and next_p.heading_level == curr_p.heading_level + 1
                ):
                    findings.append(
                        Finding(
                            rule_id=26,
                            rule_category="版面排版",
                            dimension="规范与逻辑",
                            severity="minor",
                            status="supported",
                            block_id=curr_p.id,
                            quote=curr_p.text,
                            locations=[
                                EvidenceLocation(
                                    page=curr_p.page,
                                    block_id=curr_p.id,
                                    quote=curr_p.text,
                                    description=f"{curr_p.heading_level}级标题",
                                ),
                                EvidenceLocation(
                                    page=next_p.page,
                                    block_id=next_p.id,
                                    quote=next_p.text,
                                    description=f"紧随的{next_p.heading_level}级子标题",
                                ),
                            ],
                            issue=f"章节标题（{curr_p.text}）后没有安排总述文字，直接跟了下一级子标题（{next_p.text}）。",
                            suggestion="建议在这两个标题之间补充简短总述，介绍这一部分的内容和各小节的联系。",
                        )
                    )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=26,
            rule_name=rule_name,
            category="版面排版",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_27_heading_followed_by_figure(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "章节标题后直接跟图或表"
        # Check if between heading and figure there is no body paragraph
        for p_idx in range(len(tree.all_body_paragraphs) - 1):
            curr_p = tree.all_body_paragraphs[p_idx]
            next_p = tree.all_body_paragraphs[p_idx + 1]
            if curr_p.is_heading:
                # Check if next element is figure caption
                if next_p.is_caption or re.match(
                    r"^(?:图|表|Figure|Table)\s*\d", next_p.text, re.IGNORECASE
                ):
                    findings.append(
                        Finding(
                            rule_id=27,
                            rule_category="版面排版",
                            dimension="规范与逻辑",
                            severity="minor",
                            status="supported",
                            block_id=curr_p.id,
                            quote=curr_p.text,
                            locations=[
                                EvidenceLocation(
                                    page=curr_p.page,
                                    block_id=curr_p.id,
                                    quote=curr_p.text,
                                    description="直接跟图表的标题",
                                )
                            ],
                            issue=f"章节标题（{curr_p.text}）后未见文字引导陈述，直接跟了图表。",
                            suggestion="根据学术写作规范，图表前应先有文字陈述或背景交代，避免在小节标题下方紧随图表。",
                        )
                    )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=27,
            rule_name=rule_name,
            category="版面排版",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_28_orphan_heading(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "章节标题在任何页的最后一行"
        first_body_page = tree.chapters[0].page if tree.chapters else 1
        for p in tree.pages:
            if p.page_num < first_body_page or not p.paragraphs:
                continue
            last_p = p.paragraphs[-1]
            if last_p.is_heading:
                findings.append(
                    Finding(
                        rule_id=28,
                        rule_category="版面排版",
                        dimension="规范与逻辑",
                        severity="major",
                        status="supported",
                        block_id=last_p.id,
                        quote=last_p.text,
                        locations=[
                            EvidenceLocation(
                                page=p.page_num,
                                block_id=last_p.id,
                                quote=last_p.text,
                                description="孤行标题",
                            )
                        ],
                        issue=f"第 {p.page_num} 页的最后一行出现了章节标题（'{last_p.text}'），下方无正文内容（孤行标题）。",
                        suggestion="排版中严禁出现标题孤行留在页尾。请在 Word/LaTeX 中开启'段中不分页'与'与下段同页 (keepWithNext)'属性，将标题推至下一页顶部。",
                    )
                )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=28,
            rule_name=rule_name,
            category="版面排版",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_29_blank_space(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "非章末留有大片空白"
        if not tree.chapters:
            return findings, RuleAuditItem(
                rule_id=29,
                rule_name=rule_name,
                category="版面排版",
                status=CheckStatus.PASSED.value,
            )

        first_body_page = tree.chapters[0].page
        last_body_page = (
            tree.conclusion_chapter.end_page
            if (
                tree.conclusion_chapter
                and tree.conclusion_chapter.end_page >= first_body_page
            )
            else (
                tree.chapters[-1].end_page
                if tree.chapters[-1].end_page >= first_body_page
                else len(tree.pages)
            )
        )

        chapter_end_pages = set()
        for ch in tree.chapters:
            if ch.end_page > 0:
                chapter_end_pages.add(ch.end_page)

        for idx in range(len(tree.pages) - 1):
            p = tree.pages[idx]
            # Only check pages inside the body chapters
            if p.page_num < first_body_page or p.page_num >= last_body_page:
                continue
            if p.page_num in chapter_end_pages:
                continue

            next_p = tree.pages[idx + 1]
            if (
                next_p.paragraphs
                and next_p.paragraphs[0].is_heading
                and next_p.paragraphs[0].heading_level == 1
            ):
                continue

            blank_ratio = (
                (p.largest_blank[1] - p.largest_blank[0]) / max(1, p.height - 150)
                if p.largest_blank is not None
                else 1 - p.content_height_ratio
            )
            if (
                blank_ratio > 0.45
                and p.content_height_ratio > 0.05
                and len(p.paragraphs) > 0
            ):
                if len(findings) < 5:
                    chapter = next(
                        (
                            c
                            for c in tree.chapters
                            if c.page <= p.page_num <= c.end_page
                        ),
                        None,
                    )
                    blank = p.largest_blank
                    before = [
                        q.text
                        for q in p.paragraphs
                        if not blank or q.bbox[3] <= blank[0] + 1
                    ]
                    after = [
                        q.text
                        for q in p.paragraphs
                        if blank and q.bbox[1] >= blank[1] - 1
                    ]
                    context = (
                        "留白前：" + before[-1] if before else "留白位于正文区域顶部。"
                    )
                    if after:
                        context += "\n留白后：" + after[0]
                    findings.append(
                        Finding(
                            rule_id=29,
                            rule_category="版面排版",
                            dimension="规范与逻辑",
                            severity="minor",
                            status="supported",
                            block_id=f"page_{p.page_num}",
                            quote=f"第 {p.page_num} 页",
                            locations=[
                                EvidenceLocation(
                                    page=p.page_num,
                                    description="红框范围为连续留白区域",
                                    bbox=(
                                        [65, blank[0], p.width - 65, blank[1]]
                                        if blank
                                        else None
                                    ),
                                    context=context,
                                    verified=bool(blank),
                                )
                            ],
                            evidence_note=(
                                f"本页属于“{chapter.title}”，该章正文位于 PDF 第 {chapter.page}–{chapter.end_page} 页。"
                                if chapter
                                else "请核对本页在章节中的位置。"
                            ),
                            measurement=f"正文区域最大连续留白: {blank_ratio * 100:.1f}%",
                            issue=f"第 {p.page_num} 页非章节末尾，出现大片连续空白（占正文区域 {blank_ratio * 100:.1f}%）。",
                            suggestion="通常由前方图表强行分页引起。请调整图表插入锚点位置或开启文字环绕排版，消除不必要的页面断层大片空白。",
                        )
                    )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=29,
            rule_name=rule_name,
            category="版面排版",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_30_long_paragraph(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "任何段落超过0.6页长度"
        for p in tree.all_body_paragraphs:
            if (
                p.is_heading
                or p.is_caption
                or p.is_formula
                or p.is_table_cell
                or p.is_figure_text
                or p.is_footnote
            ):
                continue
            is_en = not bool(re.search(r"[\u4e00-\u9fa5]", p.text))
            if is_en:
                is_long = (
                    len(p.text.split()) > 350
                    or p.ratio_of_page > 0.6
                    or p.line_count > 25
                )
                len_desc = f"{len(p.text.split())} 词 / {p.line_count} 行"
            else:
                is_long = (
                    len(p.text) > 800 or p.ratio_of_page > 0.6 or p.line_count > 25
                )
                len_desc = f"{len(p.text)} 字 / {p.line_count} 行"

            if is_long:
                findings.append(
                    Finding(
                        rule_id=30,
                        rule_category="版面排版",
                        dimension="规范与逻辑",
                        severity="minor",
                        status="supported",
                        block_id=p.id,
                        quote=p.text[:60] + "...",
                        locations=[
                            EvidenceLocation(
                                page=page,
                                block_id=p.id,
                                quote=p.text[:80],
                                description="超长段落",
                            )
                            for page in (p.source_pages or [p.page])
                        ],
                        measurement=f"段落长度: {len_desc}, 超过 0.6 页",
                        issue=f"检测到长度超过 0.6 页的超长自然段（共 {len_desc} 未分段）。",
                        suggestion="超长段落易导致视觉压迫感与行文逻辑涣散，建议提炼段落核心观点，拆分为 2~3 个层级清晰的自然段。",
                    )
                )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=30,
            rule_name=rule_name,
            category="版面排版",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_31_short_paragraphs(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "全文超过10个段落少于1行"
        short_count = 0
        samples = []
        page_map = {page.page_num: page for page in tree.pages}
        skip_bullets = (
            "•",
            "-",
            "*",
            "·",
            "1)",
            "(1)",
            "①",
            "②",
            "③",
            "一、",
            "二、",
            "1.",
            "2.",
            "3.",
        )
        for p in tree.all_body_paragraphs:
            if (
                p.is_heading
                or p.is_caption
                or p.is_formula
                or p.is_table_cell
                or p.is_figure_text
                or p.is_footnote
                or len(p.text) < 5
            ):
                continue
            if (
                p.text.startswith(skip_bullets)
                or re.match(r"^\(?\d+[\)）\.]\s*", p.text)
                or re.match(r"^[（\(][一二三四五六七八九十]+[）\)]", p.text)
                or re.match(r"^[一二三四五六七八九十]+、", p.text)
                or re.match(r"^[①②③④⑤⑥⑦⑧⑨⑩]", p.text)
            ):
                continue
            if any(
                p.text.startswith(pfx) for pfx in ["第", "图", "表", "Figure", "Table"]
            ):
                continue
            if any(
                kw in p.text
                for kw in ["其中", "式中", "如表", "如图", "参见", "注：", "Note:"]
            ) or p.text.endswith((":", "：", "为：", "如下：", "如：")):
                continue
            if re.search(r"公式[（\(].*?[）\)]", p.text) and len(p.text) < 30:
                continue
            if re.match(r"^[\d\.\s%±\-/–—]+$", p.text):
                continue
            if p.line_count == 1 and len(p.text) < 25:
                page = page_map.get(p.page)
                if (
                    page
                    and p.bbox[2] > p.bbox[0]
                    and re.search(r"[\u4e00-\u9fff]", p.text)
                ):
                    prose = [
                        q
                        for q in page.paragraphs
                        if not (
                            q.is_heading
                            or q.is_caption
                            or q.is_formula
                            or q.is_table_cell
                            or q.is_figure_text
                        )
                        and len(q.text) > 30
                        and q.bbox[2] - q.bbox[0] > page.width * 0.45
                    ]
                    if (
                        prose
                        and p.bbox[0]
                        < min(q.bbox[0] for q in prose) + p.font_size * 0.7
                    ):
                        continue
                short_count += 1
                if len(samples) < 3:
                    samples.append(p)

        if short_count > 10:
            findings.append(
                Finding(
                    rule_id=31,
                    rule_category="版面排版",
                    dimension="规范与逻辑",
                    severity="minor",
                    status="pending_verification",
                    block_id=samples[0].id if samples else "p_short",
                    quote=samples[0].text if samples else "",
                    locations=[
                        EvidenceLocation(
                            page=s.page,
                            block_id=s.id,
                            quote=s.text,
                            description="少于1行的碎裂短段",
                        )
                        for s in samples
                    ],
                    measurement=f"全篇少于1行的超短段落数量: {short_count} 处, 阈值: 10 处",
                    issue=f"检测到 {short_count} 处疑似短段落，需核对是否由文字提取拆分造成。",
                    suggestion="段落碎裂化表明论述不充分或存在列表滥用，请对碎裂孤句予以充实展开或合并入前后段落。",
                )
            )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=31,
            rule_name=rule_name,
            category="版面排版",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_32_orphan_character(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "单字或单标点符号占1行"
        for p in tree.all_body_paragraphs:
            if (
                p.is_heading
                or p.is_caption
                or p.is_formula
                or p.is_table_cell
                or p.is_figure_text
                or p.is_footnote
                or p.line_count < 2
                or len(p.text) < 30
            ):
                continue
            import re

            last_line = p.last_line_text.strip()
            # Strip PUA, spaces, invisible characters
            last_line_clean = re.sub(r"[\ue000-\uf8ff\s]", "", last_line)
            if len(last_line_clean) == 1 and len(findings) < 10:
                findings.append(
                    Finding(
                        rule_id=32,
                        rule_category="版面排版",
                        dimension="规范与逻辑",
                        severity="minor",
                        status="supported",
                        block_id=p.id,
                        quote=p.text[-15:],
                        locations=[
                            EvidenceLocation(
                                page=p.page,
                                block_id=p.id,
                                quote=p.text[-20:],
                                description=f"排版末行仅由单个字符'{last_line_clean}'独占一行",
                            )
                        ],
                        issue=f"段落末行出现单个字符（'{last_line_clean}'）独占 1 行的排版孤行现象。",
                        suggestion="请微调该段落字间距或前文用词字数，消除排版孤字与孤悬标点。",
                    )
                )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=32,
            rule_name=rule_name,
            category="版面排版",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_33_single_line_page(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "单行占用整页"
        first_body_page = tree.chapters[0].page if tree.chapters else 1
        for p in tree.pages:
            if p.page_num < first_body_page:
                continue
            if len(p.paragraphs) == 1 and not p.images and not p.graphic_regions:
                single_p = p.paragraphs[0]
                if not single_p.is_heading and single_p.line_count == 1:
                    findings.append(
                        Finding(
                            rule_id=33,
                            rule_category="版面排版",
                            dimension="规范与逻辑",
                            severity="major",
                            status="supported",
                            block_id=single_p.id,
                            quote=single_p.text,
                            locations=[
                                EvidenceLocation(
                                    page=p.page_num,
                                    block_id=single_p.id,
                                    quote=single_p.text,
                                    description="单行整页",
                                )
                            ],
                            issue=f"第 {p.page_num} 页整页仅包含前一章节溢出的单行文本（'{single_p.text[:30]}'），随后整页空白。",
                            suggestion="严禁单行占用整页。请微调前一章相关段落的字距或行距，将该溢出单行收回上一页末尾。",
                        )
                    )

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=33,
            rule_name=rule_name,
            category="版面排版",
            status=status,
            findings_count=len(findings),
        )

    def _check_rule_34_inconsistent_body_font(
        self, tree: ThesisDocumentTree
    ) -> Tuple[List[Finding], RuleAuditItem]:
        findings = []
        rule_name = "正文字体字号不一致"
        # Only evaluate normal-length body paragraphs
        normal_paras = [
            p
            for p in tree.all_body_paragraphs
            if not (
                p.is_heading
                or p.is_caption
                or p.is_formula
                or p.is_table_cell
                or p.is_figure_text
                or p.is_footnote
            )
            and len(p.text) > 30
            and p.font_size > 5.0
        ]
        if not normal_paras:
            return findings, RuleAuditItem(
                rule_id=34,
                rule_name=rule_name,
                category="版面排版",
                status=CheckStatus.PASSED.value,
            )

        dominant_sz = Counter(p.font_size for p in normal_paras).most_common(1)[0][0]
        fonts = [p.font_name for p in normal_paras if p.font_name]
        dominant_font = Counter(fonts).most_common(1)[0][0] if fonts else ""

        for p in normal_paras:
            sz_diff = abs(p.font_size - dominant_sz) > 1.0
            fn_diff = (
                dominant_font
                and p.font_name
                and p.font_name != dominant_font
                and not any(
                    kw in p.font_name for kw in ["Symbol", "Math", "MT", "Bold"]
                )
            )

            if sz_diff or fn_diff:
                meas = []
                if sz_diff:
                    meas.append(
                        f"字号: {p.font_size:.1f}pt (基准: {dominant_sz:.1f}pt)"
                    )
                if fn_diff:
                    meas.append(f"字体: {p.font_name} (基准: {dominant_font})")

                findings.append(
                    Finding(
                        rule_id=34,
                        rule_category="版面排版",
                        dimension="规范与逻辑",
                        severity="minor",
                        status="supported",
                        block_id=p.id,
                        quote=p.text[:40],
                        locations=[
                            EvidenceLocation(
                                page=p.page,
                                block_id=p.id,
                                quote=p.text[:50],
                                description="字体或字号异常段落",
                            )
                        ],
                        measurement=", ".join(meas),
                        issue=f"论文正文字体或字号不一致（检测到：{', '.join(meas)}）。",
                        suggestion="请统一正文样式，重新应用正文段落样式模板，确保全书正文字号与字体一致。",
                    )
                )
                break

        status = CheckStatus.FINDING.value if findings else CheckStatus.PASSED.value
        return findings, RuleAuditItem(
            rule_id=34,
            rule_name=rule_name,
            category="版面排版",
            status=status,
            findings_count=len(findings),
        )
