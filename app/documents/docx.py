"""DOCX document-tree reader."""

import re
from pathlib import Path
from typing import Optional
from app.documents.structure import figure_caption, table_caption
from docx import Document

from app.documents.models import (
    ThesisDocumentTree,
    ChapterData,
    ParagraphData,
    FigureData,
    TableData,
    ReferenceItem,
)

from .headings import sanitize_unicode, _detect_degree, _extract_titles


def build_document_tree_from_docx(docx_path: Path, filename: str) -> ThesisDocumentTree:
    doc = Document(str(docx_path))
    tree = ThesisDocumentTree(filename=filename, total_pages=1)
    current_chapter: Optional[ChapterData] = None

    re_cn_chap = re.compile(r"^\s*第\s*([一二三四五六七八九十0-9]+)\s*章\s*([^\n]*)")
    re_num_chap = re.compile(
        r"^\s*([1-9]|1[0-9]|20)\.?\s+([A-Za-z\u4e00-\u9fa5][^\n]*)"
    )
    re_chap2 = re.compile(r"^\s*([1-9]|1[0-9])\.([1-9]|1[0-9])\.?\s+([^\n]+)")
    re_chap3 = re.compile(
        r"^\s*([1-9]|1[0-9])\.([1-9]|1[0-9])\.([1-9]|1[0-9])\.?\s+([^\n]+)"
    )
    re_ref = re.compile(r"^(?:\[(\d+)\]|(\d{1,3})\.|\((\d+)\))\s*(.*)")

    body_paras = []
    in_abstract_cn = False
    in_abstract_en = False
    in_references = False

    full_raw_text = "\n".join(sanitize_unicode(p.text) for p in doc.paragraphs)
    tree.degree = _detect_degree(full_raw_text[:3000])
    tree.title_cn, tree.title_en = _extract_titles(full_raw_text[:3000])

    for idx, p in enumerate(doc.paragraphs, 1):
        text = sanitize_unicode(p.text).strip()
        if not text:
            continue
        p_clean = text.replace(" ", "")

        sz = 10.5
        fn = ""
        if p.runs:
            for r in p.runs:
                if r.font.size:
                    sz = r.font.size.pt
                if r.font.name:
                    fn = r.font.name
                break

        p_data = ParagraphData(
            id=f"docx_p_{idx}",
            text=text,
            page=1,
            line_count=max(1, len(text) // 40),
            ratio_of_page=min(1.0, len(text) / 800.0),
            font_size=sz,
            font_name=fn,
            last_line_text=text[-20:],
        )

        if "中文摘要" in p_clean or (p_clean.startswith("摘要") and len(p_clean) < 10):
            in_abstract_cn = True
            in_abstract_en = False
            continue
        elif "ABSTRACT" in text.upper() and len(text) < 20:
            in_abstract_cn = False
            in_abstract_en = True
            continue
        elif re.search(
            r"^(参\s*考\s*文\s*献|REFERENCES?|BIBLIOGRAPHY)$", text, re.IGNORECASE
        ) or (p_clean == "参考文献"):
            in_abstract_cn = False
            in_abstract_en = False
            in_references = True
            continue

        if in_abstract_cn:
            if "关键词" in p_clean or re_cn_chap.match(text):
                in_abstract_cn = False
            else:
                tree.abstract_cn.append(p_data)
                continue

        if in_abstract_en:
            if "KEY WORDS" in text.upper() or re_cn_chap.match(text):
                in_abstract_en = False
            else:
                tree.abstract_en.append(p_data)
                continue

        if in_references:
            m_ref = re_ref.match(text)
            if m_ref:
                ref_id = (
                    m_ref.group(1)
                    or m_ref.group(2)
                    or m_ref.group(3)
                    or str(len(tree.references) + 1)
                )
                tree.references.append(
                    ReferenceItem(id_str=ref_id, raw_text=text, page_num=1)
                )
                continue
            elif tree.references and len(text) > 1:
                tree.references[-1].raw_text += " " + text
                continue

        is_chap1 = False
        m_cn = re_cn_chap.match(text)
        if m_cn and len(text) < 60:
            rest = m_cn.group(2).strip()
            if not any(p in rest for p in ["，", "。", "；", "、"]):
                is_chap1 = True
        else:
            m_num = re_num_chap.match(text)
            if m_num and len(text) < 60 and tree.degree == "unknown":
                is_chap1 = True

        if is_chap1:
            p_data.is_heading = True
            p_data.heading_level = 1
            role = "method"
            u_text = text.upper()
            if any(kw in text for kw in ["绪论", "引言"]) or "INTRODUCTION" in u_text:
                role = "intro"
            elif (
                any(kw in text for kw in ["现状", "相关工作", "综述"])
                or "BACKGROUND" in u_text
                or "RELATED WORK" in u_text
            ):
                role = "survey"
            elif (
                any(kw in text for kw in ["总结", "结论", "展望"])
                or "CONCLUSION" in u_text
            ):
                role = "summary"

            current_chapter = ChapterData(title=text, level=1, page=1, role=role)
            tree.chapters.append(current_chapter)
            if role == "summary":
                tree.conclusion_chapter = current_chapter

        elif re_chap2.match(text) and len(text) < 60:
            p_data.is_heading = True
            p_data.heading_level = 2
        elif re_chap3.match(text) and len(text) < 70:
            p_data.is_heading = True
            p_data.heading_level = 3

        m_fig = figure_caption(text)
        if m_fig:
            p_data.is_caption = True
            f_num = re.sub(r"\s+", "", m_fig.group(2))
            is_sub = bool(re.search(r"\([a-z]\)", text, re.IGNORECASE))
            fig_item = FigureData(num=f_num, caption=text, page=1, is_subfig=is_sub)
            if current_chapter:
                current_chapter.figures.append(fig_item)

        m_tbl = table_caption(text)
        if m_tbl:
            p_data.is_caption = True
            t_num = re.sub(r"\s+", "", m_tbl.group(2))
            tbl_item = TableData(num=t_num, caption=text, page=1, font_size=sz)
            if current_chapter:
                current_chapter.tables.append(tbl_item)

        if current_chapter and not in_references:
            current_chapter.paragraphs.append(p_data)
            body_paras.append(p_data)

    tree.all_body_paragraphs = body_paras
    tree.body_text_only = "\n".join(
        p.text for p in body_paras if not p.is_heading and not p.is_caption
    )
    tree.all_text = full_raw_text

    if tree.conclusion_chapter:
        c_chars = sum(len(p.text) for p in tree.conclusion_chapter.paragraphs)
        tree.conclusion_pages_count = max(0.5, c_chars / 750.0)

    return tree
