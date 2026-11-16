"""TEXT document-tree reader."""

import re

from app.documents.models import (
    ThesisDocumentTree,
    ChapterData,
    ParagraphData,
    ReferenceItem,
)

from .headings import sanitize_unicode, _detect_degree, _extract_titles


def build_document_tree_from_blocks(blocks: list, filename: str) -> ThesisDocumentTree:
    tree = ThesisDocumentTree(filename=filename, total_pages=1)
    re_cn_chap = re.compile(r"^\s*第\s*([一二三四五六七八九十0-9]+)\s*章\s*([^\n]*)")
    re_num_chap = re.compile(
        r"^\s*([1-9]|1[0-9]|20)\.?\s+([A-Za-z\u4e00-\u9fa5][^\n]*)"
    )
    re_ref = re.compile(r"^(?:\[(\d+)\]|(\d{1,3})\.|\((\d+)\))\s*(.*)")
    current_chapter = None
    body_paras = []

    full_text = "\n".join(sanitize_unicode(b.get("text", "")) for b in blocks)
    tree.degree = _detect_degree(full_text[:3000])
    tree.title_cn, tree.title_en = _extract_titles(full_text[:3000])

    in_references = False

    for b in blocks:
        t = sanitize_unicode(b.get("text", "")).strip()
        if not t:
            continue
        p = ParagraphData(id=b.get("id", "b"), text=t, page=1, last_line_text=t[-20:])

        if re.search(
            r"^(参\s*考\s*文\s*献|REFERENCES?|BIBLIOGRAPHY)$", t, re.IGNORECASE
        ) or (t.replace(" ", "") == "参考文献"):
            in_references = True
            continue

        if in_references:
            m_ref = re_ref.match(t)
            if m_ref:
                ref_id = (
                    m_ref.group(1)
                    or m_ref.group(2)
                    or m_ref.group(3)
                    or str(len(tree.references) + 1)
                )
                tree.references.append(
                    ReferenceItem(id_str=ref_id, raw_text=t, page_num=1)
                )
                continue
            elif tree.references and len(t) > 1:
                tree.references[-1].raw_text += " " + t
                continue

        is_chap1 = False
        m_cn = re_cn_chap.match(t)
        if m_cn and len(t) < 60:
            rest = m_cn.group(2).strip()
            if not any(p in rest for p in ["，", "。", "；", "、"]):
                is_chap1 = True
        else:
            m_num = re_num_chap.match(t)
            if m_num and len(t) < 60 and tree.degree == "unknown":
                is_chap1 = True

        if is_chap1:
            p.is_heading = True
            p.heading_level = 1
            role = "method"
            u_text = t.upper()
            if any(kw in t for kw in ["绪论", "引言"]) or "INTRODUCTION" in u_text:
                role = "intro"
            elif (
                any(kw in t for kw in ["现状", "相关工作"])
                or "BACKGROUND" in u_text
                or "RELATED WORK" in u_text
            ):
                role = "survey"
            elif (
                any(kw in t for kw in ["总结", "结论", "展望"])
                or "CONCLUSION" in u_text
            ):
                role = "summary"

            current_chapter = ChapterData(title=t, level=1, page=1, role=role)
            tree.chapters.append(current_chapter)
            if role == "summary":
                tree.conclusion_chapter = current_chapter

        if current_chapter and not in_references:
            current_chapter.paragraphs.append(p)
            body_paras.append(p)

    tree.all_body_paragraphs = body_paras
    tree.body_text_only = "\n".join(p.text for p in body_paras if not p.is_heading)
    tree.all_text = full_text

    if tree.conclusion_chapter:
        c_chars = sum(len(p.text) for p in tree.conclusion_chapter.paragraphs)
        tree.conclusion_pages_count = max(0.5, c_chars / 750.0)

    return tree
