"""Tree builder for transforming raw PDF/DOCX into ThesisDocumentTree."""

import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import List, Optional
import fitz  # PyMuPDF
from .formula_extraction import recovered_page_dict, stitch_numbered_rows, structured_line_text
from .page_continuity import running_margins, margin_key, text_margins, join_page_continuations
from .formula_symbols import unreadable, normalize as normalize_formula
from .layout_regions import supplemental_regions, join_inline_fragments, figure_text_regions, split_region_blocks
from .structure import caption_match, figure_caption, table_caption, dominant_body_size, heading_layout, split_reference_blocks
from docx import Document

from .document_model import (
    ThesisDocumentTree,
    ChapterData,
    ParagraphData,
    FigureData,
    TableData,
    FormulaData,
    ReferenceItem,
    PageData,
    TextLine,
    TextSpan,
)


def sanitize_unicode(text: str) -> str:
    if not isinstance(text, str):
        return text
    try:
        text = text.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
    except Exception:
        pass
    # Strip PUA characters \uE000-\uF8FF
    text = re.sub(r"[\ue000-\uf8ff]", "", text)
    # NFKC normalize full-width digits, letters, brackets
    text = unicodedata.normalize("NFKC", text)
    # Normalize spaces inside numbers and dots (e.g. "1 . 1" -> "1.1")
    text = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", text)
    return text.strip()


def _is_back_matter_heading(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    return bool(re.fullmatch(
        r"(?:致谢|附录(?:[A-Za-z0-9一二三四五六七八九十]+)?|"
        r"攻读(?:硕士|博士)?学位期间[^。！？；]{0,30}|"
        r"ACKNOWLEDG(?:E)?MENTS?|APPENDIX(?:[A-Za-z0-9]+)?)",
        compact, re.IGNORECASE))


def _is_keyword_label(text: str) -> bool:
    label = r'(?:关\s*键\s*词|KEY\s*WORDS?)'
    return bool(re.match(r'^\s*' + label + r'\s*[:：]', text, re.IGNORECASE)
                or re.fullmatch(r'\s*' + label + r'\s*', text, re.IGNORECASE))


def _detect_degree(text: str) -> str:
    text = sanitize_unicode(text)
    if "博士学位论文" in text or "博士论文" in text:
        return "doctor"
    if "硕士学位论文" in text or "硕士论文" in text:
        return "master"
    if "学士学位论文" in text or "学士论文" in text or "毕业设计" in text:
        return "bachelor"
    return "unknown"


def _extract_titles(doc_or_text, doc: Optional[fitz.Document] = None) -> tuple[str, str]:
    title_cn = ""
    title_en = ""
    cover_text = doc_or_text if isinstance(doc_or_text, str) else ""

    if doc is not None and not cover_text:
        for page_idx in range(min(5, len(doc))):
            cover_text += sanitize_unicode(doc[page_idx].get_text()) + "\n"

    # Regex search for explicit markers
    m_cn = re.search(r"(?:题目|论文题目|中文题目)[：:\s]+([^\n\r]+)", cover_text)
    if m_cn:
        title_cn = m_cn.group(1).strip()

    m_en = re.search(r"(?:Title|English Title)[：:\s]+([^\n\r]+)", cover_text, re.IGNORECASE)
    if m_en:
        title_en = m_en.group(1).strip()

    skip_kws = [
        "大学", "学院", "学位论文", "作者", "导师", "学号", "专业", "单位代码",
        "分类号", "密级", "UDC", "答辩日期", "年月", "版权", "declaration",
        "permission", "学术学位", "专业学位", "指导教师", "学校代码", "学校名称",
        "姓名", "研究方向", "培养单位", "论文作者", "答辩委员会", "评阅人"
    ]

    # Heuristic font size search if PDF doc provided and title still empty
    if doc is not None and (not title_cn or not title_en):
        candidate_cn = []
        candidate_en = []

        # Scan first 3 pages (covers cover, flyleaf, and title page)
        for page_idx in range(min(3, len(doc))):
            p_dict = doc[page_idx].get_text("dict")
            for b in p_dict.get("blocks", []):
                if b.get("type") == 0:
                    for line in b.get("lines", []):
                        spans = line.get("spans", [])
                        txt = sanitize_unicode("".join(s.get("text", "") for s in spans))
                        if not txt or len(txt) < 5:
                            continue
                        if any(kw in txt for kw in skip_kws):
                            continue
                        max_sz = max((s.get("size", 10.5) for s in spans), default=10.5)

                        if re.search(r"[\u4e00-\u9fa5]{4,}", txt) and len(txt) <= 60:
                            candidate_cn.append((max_sz, txt))
                        elif re.match(r"^[A-Za-z0-9\s,\.:\-–'\"\(\)]+$", txt) and len(txt.split()) >= 3 and len(txt) <= 120:
                            candidate_en.append((max_sz, txt))

        if not title_cn and candidate_cn:
            candidate_cn.sort(key=lambda x: x[0], reverse=True)
            title_cn = candidate_cn[0][1]
        if not title_en and candidate_en:
            candidate_en.sort(key=lambda x: x[0], reverse=True)
            title_en = candidate_en[0][1]

    # Text-only fallback
    if not title_cn:
        for line in cover_text.splitlines():
            line_str = line.strip()
            if 6 <= len(line_str) <= 50 and not any(kw in line_str for kw in skip_kws):
                if re.search(r"[\u4e00-\u9fa5]{4,}", line_str):
                    title_cn = line_str
                    break

    if not title_en:
        for line in cover_text.splitlines():
            line_str = line.strip()
            if 15 <= len(line_str) <= 100 and re.match(r"^[A-Za-z0-9\s,\.:\-–]+$", line_str):
                if len(line_str.split()) >= 3 and not any(kw in line_str.upper() for kw in ["UNIVERSITY", "DISSERTATION", "THESIS", "SCHOOL", "COPYRIGHT"]):
                    title_en = line_str
                    break

    return title_cn, title_en


def _normalize_chap_num(s: str) -> Optional[int]:
    if not s:
        return None
    cn_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    s = s.strip()
    if s.isdigit():
        return int(s)
    if s in cn_map:
        return cn_map[s]
    if s.startswith("十") and len(s) == 2 and s[1] in cn_map:
        return 10 + cn_map[s[1]]
    return None


def is_toc_line(text: str) -> bool:
    if re.search(r"(\.{2,}|·{2,}|…{2,}|\s{3,}|\D)\s*\d{1,3}$", text):
        return True
    return False


def is_toc_page(texts):
    """Keep the entire contents page out, including entries with detached numbers."""
    compact = [re.sub(r'\s+', '', text) for text in texts]
    if any(re.fullmatch(r'目录|目录[（(]续[）)]|CONTENTS|TABLEOFCONTENTS', t, re.I) for t in compact):
        return True
    entries = sum(bool(re.match(r'^(?:第[一二三四五六七八九十0-9]+章|\d+(?:\.\d+)+)\s*[A-Za-z\u4e00-\u9fff]{2}', t))
                  and is_toc_line(t) for t in texts)
    prose = sum(len(t) > 70 and bool(re.search(r'[。！？]', t)) for t in texts)
    return entries >= 4 and prose == 0


def join_chapter_prefixes(blocks):
    """OCR PDFs sometimes put the first character 第 in a separate text block."""
    used = set()
    for prefix in blocks:
        if prefix['text'].strip() != '第':
            continue
        a = prefix['bbox']
        for tail in blocks:
            if id(tail) in used or not re.match(r'^[一二三四五六七八九十0-9]+\s*章', tail['text']):
                continue
            b = tail['bbox']
            if (0 <= b[0] - a[2] <= max(15, prefix['avg_font_size'])
                    and abs((a[1]+a[3]-b[1]-b[3])/2) < 8):
                prefix.update(text='第' + tail['text'],
                              bbox=(min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3])),
                              lines=prefix['lines'] + tail['lines'], last_line_str=tail['last_line_str'])
                used.add(id(tail))
                break
    return [b for b in blocks if id(b) not in used]


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
    re_num_chap = re.compile(r"^\s*([1-9]|1[0-9]|20)\.?\s+([A-Za-z\u4e00-\u9fa5][^\n]*)")
    re_chap2 = re.compile(r"^\s*([1-9]|1[0-9])\.([1-9]|1[0-9])\.?\s+([^\n]+)")
    re_chap3 = re.compile(r"^\s*([1-9]|1[0-9])\.([1-9]|1[0-9])\.([1-9]|1[0-9])\.?\s+([^\n]+)")
    re_chap4 = re.compile(r"^\s*([1-9]|1[0-9])\.([1-9]|1[0-9])\.([1-9]|1[0-9])\.([1-9]|1[0-9])\.?\s+([^\n]+)")
    re_cn_sec = re.compile(r"^\s*[（\(][一二三四五六七八九十]+[）\)]\s*([^\n]+)")
    re_fig = re.compile(r"^(图|Figure|Fig\.)\s*(\d+\s*[\.\-_—–~～]\s*\d+|\d+)\s*(.*)", re.IGNORECASE)
    re_tbl = re.compile(r"^(表|Table)\s*(\d+\s*[\.\-_—–~～]\s*\d+|\d+)\s*(.*)", re.IGNORECASE)
    re_ref = re.compile(r"^(?:\[(\d+)\]|(\d{1,3})\.|\((\d+)\))\s*(.*)")
    re_formula = re.compile(r"[\(\（](\d+\s*[\.\-_—–~～]\s*\d+|\d+)[\)\）]\s*$")

    unit_kws = ["年", "月", "日", "条", "个", "篇", "页", "万", "人", "倍", "次", "点", "%", "、", "：", ":", ")", "）"]

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

        page_top_y = p_height
        page_bottom_y = 0.0

        # Extract images and DPI
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                base_img = doc.extract_image(xref)
                w_px, h_px = base_img["width"], base_img["height"]
                img_rects = page.get_image_rects(xref)
                for irect in img_rects:
                    render_w_inch = max(0.1, irect.width / 72.0)
                    dpi = w_px / render_w_inch
                    fig_data = FigureData(
                        num="",
                        caption="",
                        page=page_num,
                        bbox=(irect.x0, irect.y0, irect.x1, irect.y1),
                        dpi=dpi,
                    )
                    page_data.images.append(fig_data)
                    # Include image bbox in page layout range (excluding running headers/footers)
                    if irect.y1 > 55.0 and irect.y0 < p_height - 55.0:
                        page_top_y = min(page_top_y, irect.y0)
                        page_bottom_y = max(page_bottom_y, irect.y1)
            except Exception:
                pass

        # Extract table rectangles on the page to identify table content
        tab_rects = []
        try:
            tabs = page.find_tables()
            for t in tabs.tables:
                tab_rects.append(fitz.Rect(t.bbox))
        except Exception:
            pass

        page_dict = recovered_page_dict(page, font_cache)
        raw_blocks = page_dict.get("blocks", [])
        page_data.is_toc = is_toc_page([
            ''.join(s.get('text', '') for s in line.get('spans', []))
            for b in raw_blocks if b.get('type') == 0 for line in b.get('lines', [])])
        if in_references or any(re.fullmatch(r'\s*(?:参\s*考\s*文\s*献|References)\s*',
                ''.join(s.get('text', '') for line in block.get('lines', []) for s in line.get('spans', [])), re.I)
                for block in raw_blocks):
            raw_blocks = split_reference_blocks(raw_blocks)
        tab_rects.extend(supplemental_regions(page, raw_blocks))
        figure_rects = figure_text_regions(page, raw_blocks, body_font_size)
        raw_blocks = split_region_blocks(raw_blocks, tab_rects, figure_rects)
        # Retain physical line coordinates before assembling logical paragraphs.
        for block in raw_blocks:
            for line in block.get('lines', []):
                spans = line.get('spans', [])
                text = sanitize_unicode(''.join(s.get('text', '') for s in spans))
                if text:
                    page_data.lines.append(TextLine(text, tuple(line['bbox']),
                        max((s.get('size', 10.5) for s in spans), default=10.5),
                        spans[0].get('font', '') if spans else '',
                        [TextSpan(sanitize_unicode(s.get('text', '')), s.get('size', 10.5),
                                  s.get('font', ''), tuple(s['bbox'])) for s in spans]))
        page_data.lines.sort(key=lambda line: (round(line.bbox[1], 1), line.bbox[0]))
        # Vector charts and table rules occupy the page just like bitmap images.
        page_data.graphic_regions = [tuple(d['rect']) for d in page.get_drawings()
            if d['rect'].y1 > 72 and d['rect'].y0 < p_height - 78
            and (d['rect'].width > 8 or d['rect'].height > 8)]
        definition_lines[page_num] = ' '.join(structured_line_text(line)
            for block in raw_blocks if block.get('type') == 0 for line in block.get('lines', []))

        # Step 1: Filter and extract valid text blocks on the page
        valid_blocks = []
        for b_idx, block in enumerate(raw_blocks):
            if block.get("type") == 0:  # text block
                b_lines = block.get("lines", [])
                b_bbox = block.get("bbox", (0, 0, 0, 0))

                block_text_list = []
                font_size_sum = 0.0
                dominant_font = ""
                span_count = 0
                last_line_str = ""

                for line in b_lines:
                    l_spans = line.get("spans", [])
                    line_text = "".join(s.get("text", "") for s in l_spans)
                    if not line_text.strip():
                        continue
                    block_text_list.append(line_text.strip())
                    last_line_str = line_text.strip()

                    for s in l_spans:
                        sz = s.get("size", 10.5)
                        fn = s.get("font", "")
                        font_size_sum += sz
                        dominant_font = fn
                        span_count += 1

                if not block_text_list:
                    continue

                max_font_sz = max((s.get("size", 10.5) for line in b_lines for s in line.get("spans", [])), default=10.5)
                weighted_spans = [(s, len(s.get('text', '').strip())) for line in b_lines for s in line.get('spans', [])]
                font_weights = Counter()
                for s, weight in weighted_spans:
                    if weight:
                        font_weights[(round(s.get('size', 10.5), 1), s.get('font', ''))] += weight
                if font_weights:
                    avg_font_size, dominant_font = font_weights.most_common(1)[0][0]
                else:
                    avg_font_size = 10.5

                # Repeated marginal text is a header/footer; small text near the
                # top can also be a genuine reference or abstract continuation.
                b_h = b_bbox[3] - b_bbox[1]
                if len(b_lines) <= 2 or b_h <= 30.0:
                    marginal_text = ''.join(block_text_list)
                    key = margin_key(marginal_text, b_bbox, p_height)
                    if key in recurring_margins:
                        continue
                    if key and re.fullmatch(r'[\s\dIVXLCDMivxlcdm一二三四五六七八九十-]+', marginal_text):
                        continue

                page_top_y = min(page_top_y, b_bbox[1])
                page_bottom_y = max(page_bottom_y, b_bbox[3])

                full_p_text = sanitize_unicode(" ".join(block_text_list).strip())
                if not full_p_text:
                    continue

                brect = fitz.Rect(b_bbox)
                in_table = block.get('region_kind') == 'table'
                for tr in tab_rects:
                    if tr.contains(brect) or (tr & brect).get_area() / max(brect.get_area(), 1) > .75:
                        in_table = True
                        break

                valid_blocks.append({
                    "b_idx": b_idx,
                    "bbox": b_bbox,
                    "lines": b_lines,
                    "text": full_p_text,
                    "avg_font_size": avg_font_size,
                    "max_font_sz": max_font_sz,
                    "dominant_font": dominant_font,
                    "last_line_str": last_line_str,
                    "in_table": in_table,
                    "in_figure": block.get('region_kind') == 'figure',
                })

        # Sort blocks top-to-bottom, left-to-right
        valid_blocks = join_chapter_prefixes(valid_blocks)
        valid_blocks = join_inline_fragments(valid_blocks)
        valid_blocks.sort(key=lambda b: (round(b["bbox"][1], 1), b["bbox"][0]))

        # Formula rows use text baselines, not oversized math font rectangles.
        valid_blocks = stitch_numbered_rows(valid_blocks, re_formula)

        # Step 3: Reconstruct lines into natural paragraphs
        left_margin, right_margin = text_margins(valid_blocks, p_width)
        processed_blocks = []
        curr_b = None
        for b in valid_blocks:
            b_txt = b["text"]
            x0 = b["bbox"][0]
            in_tab = b.get("in_table", False) or b.get('in_figure', False)

            is_h = bool(re_cn_chap.match(b_txt) or re_num_chap.match(b_txt) or re_chap2.match(b_txt) or re_chap3.match(b_txt) or re_chap4.match(b_txt) or re_cn_sec.match(b_txt))
            is_cap = bool(caption_match(b_txt))
            b_clean = b_txt.replace(" ", "")
            is_special = bool(re.match(r"^(摘\s*要|Abstract|参\s*考\s*文\s*献|References|目\s*录|Contents|致\s*谢|附\s*录)$", b_txt.strip(), re.I) or b_clean in ["摘要", "参考文献", "目录", "致谢", "附录"])
            is_special = is_special or _is_keyword_label(b_txt)
            is_lst = bool(re.match(r"^\[\d+\]", b_txt) or re.match(r"^\(?\d+[\)）\.]\s*", b_txt) or b_txt.startswith(("•", "-", "*", "·", "一、", "二、", "三、", "四、", "五、")) or re.match(r"^[①②③④⑤⑥⑦⑧⑨⑩]", b_txt))
            is_form = (bool(re_formula.search(b_txt)) or b.get("is_formula", False)) and not b.get('inline_math')
            if (not in_tab and not is_cap and not is_lst and not b.get('inline_math') and len(b_txt) < 150
                    and len(re.findall(r'[\u4e00-\u9fff]', b_txt)) < 3
                    and re.search(r'[=≤≥≈≠]', b_txt) and not re.search(r'https?://|www\.', b_txt)):
                is_form = True

            if in_tab:
                if curr_b:
                    processed_blocks.append(curr_b)
                    curr_b = None
                processed_blocks.append(dict(b, is_heading=False, is_caption=False, is_special=False, is_formula=False, is_list=False, in_table=True))
                continue

            if curr_b is None:
                curr_b = dict(b, is_heading=is_h, is_caption=is_cap, is_special=is_special, is_formula=is_form, is_list=is_lst, in_table=False)
                continue

            prev_is_h = curr_b.get("is_heading", False)
            prev_is_cap = curr_b.get("is_caption", False)
            prev_is_special = curr_b.get("is_special", False)
            prev_is_form = curr_b.get("is_formula", False)
            gap = b["bbox"][1] - curr_b["bbox"][3]

            should_merge = False
            if is_h or is_cap or is_special or prev_is_h or prev_is_cap or prev_is_special:
                should_merge = False
            elif is_lst:
                should_merge = False
            elif is_form or prev_is_form:
                should_merge = False
            elif x0 > left_margin + avg_font_size * 1.2:
                should_merge = False
            elif -5.0 <= gap <= 2.0 * avg_font_size:
                should_merge = True

            if should_merge:
                curr_b["text"] += " " + b["text"]
                curr_b["lines"].extend(b["lines"])
                c_bb = curr_b["bbox"]
                curr_b["bbox"] = (min(c_bb[0], b["bbox"][0]), min(c_bb[1], b["bbox"][1]), max(c_bb[2], b["bbox"][2]), max(c_bb[3], b["bbox"][3]))
                curr_b["last_line_str"] = b.get("last_line_str", "")
                curr_b["max_font_sz"] = max(curr_b["max_font_sz"], b["max_font_sz"])
                if is_form:
                    curr_b["is_formula"] = True
            else:
                processed_blocks.append(curr_b)
                curr_b = dict(b, is_heading=is_h, is_caption=is_cap, is_special=is_special, is_formula=is_form, is_list=is_lst, in_table=False)

        if curr_b:
            processed_blocks.append(curr_b)

        # Step 4: Iterate through processed blocks to construct document tree elements
        for block_item in processed_blocks:
            b_idx = block_item["b_idx"]
            b_bbox = block_item["bbox"]
            b_lines = block_item["lines"]
            full_p_text = block_item["text"]
            avg_font_size = block_item["avg_font_size"]
            max_font_sz = block_item["max_font_sz"]
            dominant_font = block_item["dominant_font"]
            weights = Counter()
            for line in b_lines:
                for s in line['spans']:
                    weights[(round(s.get('size', 10.5), 1), s.get('font', ''))] += len(s.get('text', '').strip())
            if weights:
                avg_font_size, dominant_font = weights.most_common(1)[0][0]
            last_line_str = block_item["last_line_str"]

            # Merge split '第' with '一章...'
            if prev_block_tail == "第" and re.match(r"^[一二三四五六七八九十0-9]+\s*章", full_p_text):
                full_p_text = "第" + full_p_text
            prev_block_tail = full_p_text

            p_height_val = b_bbox[3] - b_bbox[1]
            ratio_val = p_height_val / max(1.0, (p_height - 144.0))

            clean_last_line = sanitize_unicode(last_line_str)

            p_data = ParagraphData(
                id=f"p_{page_num}_{b_idx+1}",
                text=full_p_text,
                page=page_num,
                bbox=(b_bbox[0], b_bbox[1], b_bbox[2], b_bbox[3]),
                line_count=len(b_lines),
                height=p_height_val,
                ratio_of_page=ratio_val,
                font_size=avg_font_size,
                font_name=dominant_font,
                last_line_text=clean_last_line,
                is_caption=block_item.get("is_caption", False),
                is_formula=block_item.get("is_formula", False),
                is_table_cell=block_item.get("in_table", False),
                is_figure_text=block_item.get('in_figure', False),
                is_footnote=bool(b_bbox[1] > p_height * .7 and re.match(r'^\d+\s*https?://', full_p_text)),
                source_pages=[page_num],
                last_line_bbox=tuple(b_lines[-1]['bbox']) if b_lines else b_bbox,
            )
            page_data.paragraphs.append(p_data)
            all_paras.append(p_data)

            p_clean = full_p_text.replace(" ", "")

            if page_data.is_toc:
                in_toc = True
                in_abstract_cn = in_abstract_en = False
                continue

            # Detect TOC
            if re.match(r"^(目\s*录|TABLE\s+OF\s+CONTENTS|Contents)$", full_p_text, re.IGNORECASE) or (p_clean == "目录"):
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
                if not any(p in rest for p in ["，", "。", "；", "、"]) and not rest.startswith("为") and not re.search(r"\s+\d+$", rest):
                    if heading_layout(full_p_text, b_bbox, avg_font_size, dominant_font, body_font_size, p_width):
                        is_chap1 = True
                        c_num_str = m_cn.group(1).strip()
                        if c_num_str in ["一", "1"]:
                            is_first_chapter = True
            else:
                m_num = re_num_chap.match(full_p_text)
                if m_num and len(full_p_text) < 60 and not is_toc_line(full_p_text):
                    rest = m_num.group(2).strip()
                    if tree.degree == "unknown" and not any(rest.startswith(u) for u in unit_kws) and not any(p in rest for p in ["，", "。", "；"]):
                        if heading_layout(full_p_text, b_bbox, avg_font_size, dominant_font, body_font_size, p_width):
                            is_chap1 = True
                            if m_num.group(1) == "1":
                                is_first_chapter = True

            if in_toc:
                if (is_first_chapter or "中文摘要" in p_clean or (p_clean.startswith("摘要") and len(p_clean) < 10) or ("ABSTRACT" in full_p_text.upper() and len(full_p_text) < 20)) and not is_toc_line(full_p_text):
                    in_toc = False
                else:
                    continue

            # Abstract detection
            if re.fullmatch(r'(?:中文摘要|摘要|英文摘要|ABSTRACT|参考文献|REFERENCES?)\s*[（(](?:续|continued)[）)]',
                            full_p_text, re.IGNORECASE):
                continue
            if "中文摘要" in p_clean or (p_clean.startswith("摘要") and len(p_clean) < 10):
                in_abstract_cn = True
                in_abstract_en = False
                continue
            elif ("ABSTRACT" in full_p_text.upper() and len(full_p_text) < 20) or ("英文摘要" in p_clean and len(p_clean) < 10):
                in_abstract_cn = False
                in_abstract_en = True
                continue
            elif re.search(r"^(参\s*考\s*文\s*献|REFERENCES?|BIBLIOGRAPHY)$", full_p_text, re.IGNORECASE) or (p_clean == "参考文献"):
                in_abstract_cn = False
                in_abstract_en = False
                in_references = True
                in_toc = False
                if tree.chapters:
                    last = tree.chapters[-1]
                    last.end_page = max((p.page for p in last.paragraphs), default=last.page)
                in_conclusion = False
                continue
            elif _is_back_matter_heading(full_p_text):
                in_references = False
                in_back_matter = True
                if tree.chapters and in_conclusion:
                    last = tree.chapters[-1]
                    last.end_page = max((p.page for p in last.paragraphs), default=last.page)
                in_conclusion = False
                continue

            if in_back_matter:
                continue

            if in_abstract_cn:
                if _is_keyword_label(full_p_text) or is_chap1 or p_clean.startswith("目录"):
                    in_abstract_cn = False
                else:
                    tree.abstract_cn.append(p_data)
                    continue

            if in_abstract_en:
                if _is_keyword_label(full_p_text) or is_chap1 or re.fullmatch(r'\s*CONTENTS\s*', full_p_text, re.I):
                    in_abstract_en = False
                else:
                    tree.abstract_en.append(p_data)
                    continue

            if in_references:
                ref_text_to_check = pending_ref_prefix + full_p_text
                if ref_text_to_check in ["[", "［"] or re.match(r"^\[\s*\d*$", ref_text_to_check):
                    pending_ref_prefix = ref_text_to_check
                    pending_ref_segments.append(p_data)
                    continue

                pending_ref_prefix = ""
                m_ref = re_ref.match(ref_text_to_check)
                re_author = re.compile(r"^[A-Z][a-zA-Z\.\-]+(?:\s+[A-Z][a-zA-Z\.\-]+){1,3}(?:,\s*|\s+and\s+|\s+et\s+al\.)")
                # Once a numbered bracket list is established, continuation lines
                # beginning with an author or a page number remain in that entry.
                bracket_list = bool(tree.references and re.match(r"^\s*\[\d+\]", tree.references[0].raw_text))
                numbered_list = bool(tree.references and re_ref.match(tree.references[0].raw_text))
                if bracket_list and m_ref and not m_ref.group(1):
                    m_ref = None
                if m_ref:
                    ref_id = m_ref.group(1) or m_ref.group(2) or m_ref.group(3) or str(len(tree.references) + 1)
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
                elif not numbered_list and re_author.match(ref_text_to_check) and len(ref_text_to_check) > 20:
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
                    cur_num = _normalize_chap_num(c_num_str) if ('c_num_str' in locals() and c_num_str) else None
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
                    current_chapter.end_page = max((p.page for p in current_chapter.paragraphs), default=current_chapter.page)
                if in_conclusion:
                    in_conclusion = False

                role = "method"
                u_text = full_p_text.upper()
                if any(kw in full_p_text for kw in ["绪论", "引言"]) or "INTRODUCTION" in u_text:
                    role = "intro"
                elif any(kw in full_p_text for kw in ["现状", "相关工作", "综述", "相关技术"]) or "BACKGROUND" in u_text or "RELATED WORK" in u_text:
                    role = "survey"
                elif any(kw in full_p_text for kw in ["总结", "结论", "展望"]) or "CONCLUSION" in u_text:
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

            elif re_chap2.match(full_p_text) and len(full_p_text) < 60 and not is_toc_line(full_p_text):
                p_data.is_heading = True
                p_data.heading_level = 2
            elif re_chap3.match(full_p_text) and len(full_p_text) < 70 and not is_toc_line(full_p_text):
                p_data.is_heading = True
                p_data.heading_level = 3
            elif re_chap4.match(full_p_text) and len(full_p_text) < 70 and not is_toc_line(full_p_text):
                p_data.is_heading = True
                p_data.heading_level = 4
            elif re_cn_sec.match(full_p_text) and len(full_p_text) < 50 and not is_toc_line(full_p_text):
                p_data.is_heading = True
                p_data.heading_level = 4

            # Figures and tables
            m_fig = figure_caption(full_p_text)
            if m_fig:
                p_data.is_caption = True
                f_num_raw = m_fig.group(2)
                f_num = re.sub(r"\s+", "", f_num_raw)
                is_sub = bool(re.search(r"\([a-z]\)", full_p_text, re.IGNORECASE))
                fig_item = FigureData(num=f_num, caption=full_p_text, page=page_num, is_subfig=is_sub, bbox=p_data.bbox)
                if current_chapter:
                    current_chapter.figures.append(fig_item)

            m_tbl = table_caption(full_p_text)
            if m_tbl:
                p_data.is_caption = True
                t_num_raw = m_tbl.group(2)
                t_num = re.sub(r"\s+", "", t_num_raw)
                tbl_item = TableData(num=t_num, caption=full_p_text, page=page_num, bbox=p_data.bbox, font_size=avg_font_size)
                if current_chapter:
                    current_chapter.tables.append(tbl_item)

            # Formulas: require explicit formula number (X-Y) or standalone single-line math equation
            m_form = re_formula.search(full_p_text) or re_formula.search(block_item.get('formula_number', ''))
            is_standalone_math = False
            zh_count = sum(1 for c in full_p_text if '\u4e00' <= c <= '\u9fa5')
            if "=" in full_p_text and len(full_p_text) < 60 and zh_count == 0 and not block_item.get('inline_math'):
                if any(c in full_p_text for c in "+-*/∑∫√SoftmaxLayerNormAttentionℝ"):
                    is_standalone_math = True

            if not p_data.is_table_cell and not block_item.get('inline_math') and ((m_form and zh_count < 5 and not p_data.is_caption and not p_data.is_heading) or is_standalone_math):
                p_data.is_formula = True
                has_num = bool(m_form)
                num_str = re.sub(r"\s+", "", m_form.group(1)) if m_form else ""
                structured = ' '.join(structured_line_text(line) for line in b_lines)
                if block_item.get('formula_number'):
                    number_text = block_item['formula_number']
                    structured = structured.replace(number_text, '').strip() + ' ' + number_text
                corrupted = unreadable(structured)
                content = re_formula.sub('', structured).strip(' .…')
                quality = 'unreadable' if corrupted or not content else 'native'
                if '=' in content and (not any(c.isalpha() for c in content.split('=', 1)[0]) or not content.split('=', 1)[1].strip()):
                    quality = 'partial'
                if re.search(r'(?<![A-Za-z0-9}])_\{[^{}]*(?:exp|log|softmax)\(', normalize_formula(structured)):
                    quality = 'partial'
                form_item = FormulaData(text=full_p_text, has_number=has_num, num_str=num_str, page=page_num, bbox=p_data.bbox,
                                        structured_text=structured, extraction_status=quality,
                                        numbering_status='found' if has_num else ('uncertain' if quality != 'native' else 'missing'))
                if current_chapter:
                    current_chapter.formulas.append(form_item)

            # ONLY append to body_paras if a chapter has begun and not in references
            if current_chapter is not None and not in_references:
                current_chapter.paragraphs.append(p_data)
                if not p_data.is_table_cell:
                    body_paras.append(p_data)

        # Populate formula context (preceding and following paragraphs)
        if current_chapter and current_chapter.formulas:
            for f in current_chapter.formulas:
                if f.page == page_num and not f.context_text:
                    fy = (f.bbox[1] + f.bbox[3]) / 2.0
                    ctx_list = [
                        p.text for p in page_data.paragraphs
                        if not p.is_formula and not p.is_caption and abs((p.bbox[1] + p.bbox[3]) / 2.0 - fy) <= 150.0
                    ]
                    f.context_text = " ".join(ctx_list)

        if page_bottom_y > page_top_y:
            page_data.content_height_ratio = (page_bottom_y - page_top_y) / p_height
        intervals = [(p.bbox[1], p.bbox[3]) for p in page_data.paragraphs]
        intervals += [(b[1], b[3]) for b in page_data.graphic_regions]
        intervals += [(f.bbox[1], f.bbox[3]) for f in page_data.images]
        cursor, largest = 72., (0., 0.)
        for top, bottom in sorted(intervals):
            top, bottom = max(72., top), min(p_height - 78., bottom)
            if bottom < top:
                continue
            if top - cursor > largest[1] - largest[0]:
                largest = (cursor, top)
            cursor = max(cursor, bottom)
        if p_height - 78 - cursor > largest[1] - largest[0]:
            largest = (cursor, p_height - 78)
        page_data.largest_blank = largest
        tree.pages.append(page_data)

    doc.close()

    if tree.chapters and tree.chapters[-1].end_page == 1:
        tree.chapters[-1].end_page = tree.total_pages

    tree.all_body_paragraphs = body_paras
    tree.body_text_only = "\n".join(p.text for p in body_paras if not p.is_heading)
    tree.all_text = "\n".join(p.text for p in all_paras)

    page_map = {p.page_num: p for p in tree.pages}
    for ch in tree.chapters:
        ch.paragraphs = join_page_continuations(ch.paragraphs, page_map)
        for formula in ch.formulas:
            formula.definition_context = ' '.join(definition_lines.get(number, '')
                for number in range(ch.page, min(ch.end_page, formula.page + 1) + 1))
    # Section titles immediately below “摘要” are not abstract prose.
    for name in ('abstract_cn', 'abstract_en'):
        paras = getattr(tree, name)
        if paras:
            prose_size = sorted(p.font_size for p in paras)[len(paras) // 2]
            while paras and paras[0].font_size > prose_size + 1 and len(paras[0].text) < 200:
                paras = paras[1:]
        setattr(tree, name, join_page_continuations(paras, page_map))
    tree.all_body_paragraphs = [p for ch in tree.chapters for p in ch.paragraphs if not p.is_table_cell and not p.is_figure_text]
    tree.body_text_only = '\n'.join(p.text for p in tree.all_body_paragraphs if not p.is_heading and not p.is_caption)

    # Conclusion pages count
    if tree.conclusion_chapter:
        c_start = tree.conclusion_chapter.page
        c_end = tree.conclusion_chapter.end_page if tree.conclusion_chapter.end_page >= c_start else len(tree.pages)
        tree.conclusion_pages_count = max(0.5, float(c_end - c_start + 1))

    return tree


def build_document_tree_from_docx(docx_path: Path, filename: str) -> ThesisDocumentTree:
    doc = Document(str(docx_path))
    tree = ThesisDocumentTree(filename=filename, total_pages=1)
    current_chapter: Optional[ChapterData] = None

    re_cn_chap = re.compile(r"^\s*第\s*([一二三四五六七八九十0-9]+)\s*章\s*([^\n]*)")
    re_num_chap = re.compile(r"^\s*([1-9]|1[0-9]|20)\.?\s+([A-Za-z\u4e00-\u9fa5][^\n]*)")
    re_chap2 = re.compile(r"^\s*([1-9]|1[0-9])\.([1-9]|1[0-9])\.?\s+([^\n]+)")
    re_chap3 = re.compile(r"^\s*([1-9]|1[0-9])\.([1-9]|1[0-9])\.([1-9]|1[0-9])\.?\s+([^\n]+)")
    re_fig = re.compile(r"^(图|Figure|Fig\.)\s*(\d+\s*[\.\-_—–~～]\s*\d+|\d+)\s*(.*)", re.IGNORECASE)
    re_tbl = re.compile(r"^(表|Table)\s*(\d+\s*[\.\-_—–~～]\s*\d+|\d+)\s*(.*)", re.IGNORECASE)
    re_ref = re.compile(r"^(?:\[(\d+)\]|(\d{1,3})\.|\((\d+)\))\s*(.*)")

    all_paras = []
    body_paras = []
    in_abstract_cn = False
    in_abstract_en = False
    in_references = False
    in_conclusion = False

    full_raw_text = "\n".join(sanitize_unicode(p.text) for p in doc.paragraphs)
    tree.degree = _detect_degree(full_raw_text[:3000])
    tree.title_cn, tree.title_en = _extract_titles(full_raw_text[:3000])

    for idx, p in enumerate(doc.paragraphs, 1):
        text = sanitize_unicode(p.text).strip()
        if not text:
            continue
        all_paras.append(text)
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
        elif re.search(r"^(参\s*考\s*文\s*献|REFERENCES?|BIBLIOGRAPHY)$", text, re.IGNORECASE) or (p_clean == "参考文献"):
            in_abstract_cn = False
            in_abstract_en = False
            in_references = True
            in_conclusion = False
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
                ref_id = m_ref.group(1) or m_ref.group(2) or m_ref.group(3) or str(len(tree.references) + 1)
                tree.references.append(ReferenceItem(id_str=ref_id, raw_text=text, page_num=1))
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
            elif any(kw in text for kw in ["现状", "相关工作", "综述"]) or "BACKGROUND" in u_text or "RELATED WORK" in u_text:
                role = "survey"
            elif any(kw in text for kw in ["总结", "结论", "展望"]) or "CONCLUSION" in u_text:
                role = "summary"
                in_conclusion = True

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
    tree.body_text_only = "\n".join(p.text for p in body_paras if not p.is_heading and not p.is_caption)
    tree.all_text = full_raw_text

    if tree.conclusion_chapter:
        c_chars = sum(len(p.text) for p in tree.conclusion_chapter.paragraphs)
        tree.conclusion_pages_count = max(0.5, c_chars / 750.0)

    return tree


def build_document_tree_from_blocks(blocks: list, filename: str) -> ThesisDocumentTree:
    tree = ThesisDocumentTree(filename=filename, total_pages=1)
    re_cn_chap = re.compile(r"^\s*第\s*([一二三四五六七八九十0-9]+)\s*章\s*([^\n]*)")
    re_num_chap = re.compile(r"^\s*([1-9]|1[0-9]|20)\.?\s+([A-Za-z\u4e00-\u9fa5][^\n]*)")
    re_ref = re.compile(r"^(?:\[(\d+)\]|(\d{1,3})\.|\((\d+)\))\s*(.*)")
    current_chapter = None
    body_paras = []
    all_paras = []

    full_text = "\n".join(sanitize_unicode(b.get("text", "")) for b in blocks)
    tree.degree = _detect_degree(full_text[:3000])
    tree.title_cn, tree.title_en = _extract_titles(full_text[:3000])

    in_references = False
    in_conclusion = False

    for b in blocks:
        t = sanitize_unicode(b.get("text", "")).strip()
        if not t:
            continue
        all_paras.append(t)
        p = ParagraphData(id=b.get("id", "b"), text=t, page=1, last_line_text=t[-20:])

        if re.search(r"^(参\s*考\s*文\s*献|REFERENCES?|BIBLIOGRAPHY)$", t, re.IGNORECASE) or (t.replace(" ", "") == "参考文献"):
            in_references = True
            in_conclusion = False
            continue

        if in_references:
            m_ref = re_ref.match(t)
            if m_ref:
                ref_id = m_ref.group(1) or m_ref.group(2) or m_ref.group(3) or str(len(tree.references) + 1)
                tree.references.append(ReferenceItem(id_str=ref_id, raw_text=t, page_num=1))
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
            elif any(kw in t for kw in ["现状", "相关工作"]) or "BACKGROUND" in u_text or "RELATED WORK" in u_text:
                role = "survey"
            elif any(kw in t for kw in ["总结", "结论", "展望"]) or "CONCLUSION" in u_text:
                role = "summary"
                in_conclusion = True

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
