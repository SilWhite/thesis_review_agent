"""PDF section assembly. Page reading and geometry live in pdf_* helpers."""

import re
from pathlib import Path
from typing import List, Optional
import fitz  # PyMuPDF
from app.documents.continuity import running_margins
from app.documents.structure import dominant_body_size, heading_layout

from app.documents.models import (
    ThesisDocumentTree,
    ChapterData,
    ParagraphData,
    ReferenceItem,
    PageData,
)

from .headings import (
    sanitize_unicode,
    _is_back_matter_heading,
    _is_keyword_label,
    _detect_degree,
    _extract_titles,
    _normalize_chap_num,
    is_toc_line,
)
from .pdf_blocks import (
    image_bounds,
    read_regions,
    text_blocks,
    paragraph_blocks,
    paragraph_from_block,
)
from .pdf_elements import append_elements
from .pdf_finalize import finish_page, finish_tree


def build_document_tree_from_pdf(pdf_path: Path, filename: str) -> ThesisDocumentTree:
    doc = fitz.open(str(pdf_path))
    tree = ThesisDocumentTree(filename=filename, total_pages=len(doc))

    all_paras: List[ParagraphData] = []
    body_paras: List[ParagraphData] = []
    current_chapter: Optional[ChapterData] = None
    in_abstract_cn = False
    in_abstract_en = False
    in_references = False
    in_back_matter = False
    in_conclusion = False
    in_toc = False

    cover_text = ""
    for page_idx in range(min(5, len(doc))):
        cover_text += sanitize_unicode(doc[page_idx].get_text()) + "\n"
    tree.degree = _detect_degree(cover_text)
    tree.title_cn, tree.title_en = _extract_titles(cover_text, doc)

    # Patterns
    re_cn_chap = re.compile(r"^\s*第\s*([一二三四五六七八九十0-9]+)\s*章\s*([^\n]*)")
    re_num_chap = re.compile(
        r"^\s*([1-9]|1[0-9]|20)\.?\s+([A-Za-z\u4e00-\u9fa5][^\n]*)"
    )
    re_chap2 = re.compile(r"^\s*([1-9]|1[0-9])\.([1-9]|1[0-9])\.?\s+([^\n]+)")
    re_chap3 = re.compile(
        r"^\s*([1-9]|1[0-9])\.([1-9]|1[0-9])\.([1-9]|1[0-9])\.?\s+([^\n]+)"
    )
    re_chap4 = re.compile(
        r"^\s*([1-9]|1[0-9])\.([1-9]|1[0-9])\.([1-9]|1[0-9])\.([1-9]|1[0-9])\.?\s+([^\n]+)"
    )
    re_cn_sec = re.compile(r"^\s*[（\(][一二三四五六七八九十]+[）\)]\s*([^\n]+)")
    re_ref = re.compile(r"^(?:\[(\d+)\]|(\d{1,3})\.|\((\d+)\))\s*(.*)")
    re_formula = re.compile(r"[\(\（](\d+\s*[\.\-_—–~～]\s*\d+|\d+)[\)\）]\s*$")

    unit_kws = [
        "年",
        "月",
        "日",
        "条",
        "个",
        "篇",
        "页",
        "万",
        "人",
        "倍",
        "次",
        "点",
        "%",
        "、",
        "：",
        ":",
        ")",
        "）",
    ]

    prev_block_tail = ""
    pending_ref_prefix = ""
    pending_ref_segments = []
    font_cache = {}
    recurring_margins = running_margins(doc)
    body_font_size = dominant_body_size(doc)
    definition_lines = {}

    for page_num in range(1, len(doc) + 1):
        page = doc[page_num - 1]
        p_width, p_height = page.rect.width, page.rect.height
        page_data = PageData(page_num=page_num, width=p_width, height=p_height)

        page_top_y, page_bottom_y = image_bounds(page, doc, page_data)
        raw_blocks, tab_rects, definition_text = read_regions(
            page, page_data, font_cache, body_font_size, in_references
        )
        definition_lines[page_num] = definition_text
        valid_blocks, merge_font_size, page_top_y, page_bottom_y = text_blocks(
            raw_blocks,
            tab_rects,
            recurring_margins,
            p_height,
            page_top_y,
            page_bottom_y,
        )
        processed_blocks = paragraph_blocks(
            valid_blocks,
            p_width,
            merge_font_size,
            re_formula,
            (re_cn_chap, re_num_chap, re_chap2, re_chap3, re_chap4, re_cn_sec),
        )

        # Step 4: Iterate through processed blocks to construct document tree elements
        for block_item in processed_blocks:
            p_data = paragraph_from_block(
                block_item, page_num, p_height, prev_block_tail
            )
            prev_block_tail = full_p_text = p_data.text
            b_bbox = block_item["bbox"]
            avg_font_size, dominant_font = p_data.font_size, p_data.font_name
            page_data.paragraphs.append(p_data)
            all_paras.append(p_data)

            p_clean = full_p_text.replace(" ", "")

            if page_data.is_toc:
                in_toc = True
                in_abstract_cn = in_abstract_en = False
                continue

            # Detect TOC
            if re.match(
                r"^(目\s*录|TABLE\s+OF\s+CONTENTS|Contents)$",
                full_p_text,
                re.IGNORECASE,
            ) or (p_clean == "目录"):
                in_toc = True
                in_abstract_cn = False
                in_abstract_en = False
                continue

            # Chapter 1 candidate detection
            is_chap1 = False
            is_first_chapter = False
            m_cn = re_cn_chap.match(full_p_text)
            if m_cn and len(full_p_text) < 60 and not is_toc_line(full_p_text):
                rest = m_cn.group(2).strip()
                if (
                    not any(p in rest for p in ["，", "。", "；", "、"])
                    and not rest.startswith("为")
                    and not re.search(r"\s+\d+$", rest)
                ):
                    if heading_layout(
                        full_p_text,
                        b_bbox,
                        avg_font_size,
                        dominant_font,
                        body_font_size,
                        p_width,
                    ):
                        is_chap1 = True
                        c_num_str = m_cn.group(1).strip()
                        if c_num_str in ["一", "1"]:
                            is_first_chapter = True
            else:
                m_num = re_num_chap.match(full_p_text)
                if m_num and len(full_p_text) < 60 and not is_toc_line(full_p_text):
                    rest = m_num.group(2).strip()
                    if (
                        tree.degree == "unknown"
                        and not any(rest.startswith(u) for u in unit_kws)
                        and not any(p in rest for p in ["，", "。", "；"])
                    ):
                        if heading_layout(
                            full_p_text,
                            b_bbox,
                            avg_font_size,
                            dominant_font,
                            body_font_size,
                            p_width,
                        ):
                            is_chap1 = True
                            if m_num.group(1) == "1":
                                is_first_chapter = True

            if in_toc:
                if (
                    is_first_chapter
                    or "中文摘要" in p_clean
                    or (p_clean.startswith("摘要") and len(p_clean) < 10)
                    or ("ABSTRACT" in full_p_text.upper() and len(full_p_text) < 20)
                ) and not is_toc_line(full_p_text):
                    in_toc = False
                else:
                    continue

            # Abstract detection
            if re.fullmatch(
                r"(?:中文摘要|摘要|英文摘要|ABSTRACT|参考文献|REFERENCES?)\s*[（(](?:续|continued)[）)]",
                full_p_text,
                re.IGNORECASE,
            ):
                continue
            if "中文摘要" in p_clean or (
                p_clean.startswith("摘要") and len(p_clean) < 10
            ):
                in_abstract_cn = True
                in_abstract_en = False
                continue
            elif ("ABSTRACT" in full_p_text.upper() and len(full_p_text) < 20) or (
                "英文摘要" in p_clean and len(p_clean) < 10
            ):
                in_abstract_cn = False
                in_abstract_en = True
                continue
            elif re.search(
                r"^(参\s*考\s*文\s*献|REFERENCES?|BIBLIOGRAPHY)$",
                full_p_text,
                re.IGNORECASE,
            ) or (p_clean == "参考文献"):
                in_abstract_cn = False
                in_abstract_en = False
                in_references = True
                in_toc = False
                if tree.chapters:
                    last = tree.chapters[-1]
                    last.end_page = max(
                        (p.page for p in last.paragraphs), default=last.page
                    )
                in_conclusion = False
                continue
            elif _is_back_matter_heading(full_p_text):
                in_references = False
                in_back_matter = True
                if tree.chapters and in_conclusion:
                    last = tree.chapters[-1]
                    last.end_page = max(
                        (p.page for p in last.paragraphs), default=last.page
                    )
                in_conclusion = False
                continue

            if in_back_matter:
                continue

            if in_abstract_cn:
                if (
                    _is_keyword_label(full_p_text)
                    or is_chap1
                    or p_clean.startswith("目录")
                ):
                    in_abstract_cn = False
                else:
                    tree.abstract_cn.append(p_data)
                    continue

            if in_abstract_en:
                if (
                    _is_keyword_label(full_p_text)
                    or is_chap1
                    or re.fullmatch(r"\s*CONTENTS\s*", full_p_text, re.I)
                ):
                    in_abstract_en = False
                else:
                    tree.abstract_en.append(p_data)
                    continue

            if in_references:
                ref_text_to_check = pending_ref_prefix + full_p_text
                if ref_text_to_check in ["[", "［"] or re.match(
                    r"^\[\s*\d*$", ref_text_to_check
                ):
                    pending_ref_prefix = ref_text_to_check
                    pending_ref_segments.append(p_data)
                    continue

                pending_ref_prefix = ""
                m_ref = re_ref.match(ref_text_to_check)
                re_author = re.compile(
                    r"^[A-Z][a-zA-Z\.\-]+(?:\s+[A-Z][a-zA-Z\.\-]+){1,3}(?:,\s*|\s+and\s+|\s+et\s+al\.)"
                )
                # Once a numbered bracket list is established, continuation lines
                # beginning with an author or a page number remain in that entry.
                bracket_list = bool(
                    tree.references
                    and re.match(r"^\s*\[\d+\]", tree.references[0].raw_text)
                )
                numbered_list = bool(
                    tree.references and re_ref.match(tree.references[0].raw_text)
                )
                if bracket_list and m_ref and not m_ref.group(1):
                    m_ref = None
                if m_ref:
                    ref_id = (
                        m_ref.group(1)
                        or m_ref.group(2)
                        or m_ref.group(3)
                        or str(len(tree.references) + 1)
                    )
                    ref_item = ReferenceItem(
                        id_str=ref_id,
                        raw_text=ref_text_to_check,
                        page_num=page_num,
                        source_pages=[page_num],
                        segments=pending_ref_segments + [p_data],
                    )
                    ref_item.source_pages = sorted({p.page for p in ref_item.segments})
                    ref_item.page_num = ref_item.source_pages[0]
                    pending_ref_segments = []
                    tree.references.append(ref_item)
                    continue
                elif (
                    not numbered_list
                    and re_author.match(ref_text_to_check)
                    and len(ref_text_to_check) > 20
                ):
                    ref_id = str(len(tree.references) + 1)
                    ref_item = ReferenceItem(
                        id_str=ref_id,
                        raw_text=ref_text_to_check,
                        page_num=page_num,
                        source_pages=[page_num],
                        segments=[p_data],
                    )
                    tree.references.append(ref_item)
                    continue
                elif tree.references and full_p_text.strip():
                    tree.references[-1].raw_text += " " + full_p_text
                    tree.references[-1].segments.append(p_data)
                    if page_num not in tree.references[-1].source_pages:
                        tree.references[-1].source_pages.append(page_num)
                    continue

            # Headings
            if is_chap1:
                # Ignore if in extreme top header margin (b_bbox[3] <= 55.0)
                if b_bbox[3] <= 55.0:
                    is_chap1 = False
                # Ignore duplicate chapter numbers or non-increasing sequence
                elif tree.chapters:
                    last_ch = tree.chapters[-1]
                    cur_num = (
                        _normalize_chap_num(c_num_str)
                        if ("c_num_str" in locals() and c_num_str)
                        else None
                    )
                    last_m = re_cn_chap.match(last_ch.title)
                    last_num = _normalize_chap_num(last_m.group(1)) if last_m else None
                    if cur_num is not None and last_num is not None:
                        if cur_num <= last_num:
                            is_chap1 = False
                    elif full_p_text == last_ch.title:
                        is_chap1 = False

            if is_chap1:
                p_data.is_heading = True
                p_data.heading_level = 1
                if current_chapter:
                    current_chapter.end_page = max(
                        (p.page for p in current_chapter.paragraphs),
                        default=current_chapter.page,
                    )
                if in_conclusion:
                    in_conclusion = False

                role = "method"
                u_text = full_p_text.upper()
                if (
                    any(kw in full_p_text for kw in ["绪论", "引言"])
                    or "INTRODUCTION" in u_text
                ):
                    role = "intro"
                elif (
                    any(
                        kw in full_p_text
                        for kw in ["现状", "相关工作", "综述", "相关技术"]
                    )
                    or "BACKGROUND" in u_text
                    or "RELATED WORK" in u_text
                ):
                    role = "survey"
                elif (
                    any(kw in full_p_text for kw in ["总结", "结论", "展望"])
                    or "CONCLUSION" in u_text
                ):
                    role = "summary"
                    in_conclusion = True

                current_chapter = ChapterData(
                    title=full_p_text,
                    level=1,
                    page=page_num,
                    role=role,
                )
                tree.chapters.append(current_chapter)
                if role == "summary":
                    tree.conclusion_chapter = current_chapter

            elif (
                re_chap2.match(full_p_text)
                and len(full_p_text) < 60
                and not is_toc_line(full_p_text)
            ):
                p_data.is_heading = True
                p_data.heading_level = 2
            elif (
                re_chap3.match(full_p_text)
                and len(full_p_text) < 70
                and not is_toc_line(full_p_text)
            ):
                p_data.is_heading = True
                p_data.heading_level = 3
            elif (
                re_chap4.match(full_p_text)
                and len(full_p_text) < 70
                and not is_toc_line(full_p_text)
            ):
                p_data.is_heading = True
                p_data.heading_level = 4
            elif (
                re_cn_sec.match(full_p_text)
                and len(full_p_text) < 50
                and not is_toc_line(full_p_text)
            ):
                p_data.is_heading = True
                p_data.heading_level = 4

            append_elements(p_data, block_item, current_chapter, re_formula)

            # ONLY append to body_paras if a chapter has begun and not in references
            if current_chapter is not None and not in_references:
                current_chapter.paragraphs.append(p_data)
                if not p_data.is_table_cell:
                    body_paras.append(p_data)

        finish_page(page_data, current_chapter, page_top_y, page_bottom_y)
        tree.pages.append(page_data)

    doc.close()

    return finish_tree(tree, all_paras, body_paras, definition_lines)
