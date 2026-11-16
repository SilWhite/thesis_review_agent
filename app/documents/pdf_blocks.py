"""Read PDF page geometry, classify text blocks and reconstruct paragraphs."""

import re
from collections import Counter
import fitz  # PyMuPDF
from app.documents.formulas import (
    recovered_page_dict,
    stitch_numbered_rows,
    structured_line_text,
)
from app.documents.continuity import margin_key, text_margins
from app.documents.regions import (
    supplemental_regions,
    join_inline_fragments,
    figure_text_regions,
    split_region_blocks,
)
from app.documents.structure import caption_match, split_reference_blocks

from app.documents.models import FigureData, TextLine, TextSpan, ParagraphData

from .headings import (
    sanitize_unicode,
    _is_keyword_label,
    is_toc_page,
    join_chapter_prefixes,
)


def image_bounds(page, doc, page_data):
    page_num, p_height = page_data.page_num, page_data.height
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

    return page_top_y, page_bottom_y


def read_regions(page, page_data, font_cache, body_font_size, in_references):
    p_height = page_data.height
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
    page_data.is_toc = is_toc_page(
        [
            "".join(s.get("text", "") for s in line.get("spans", []))
            for b in raw_blocks
            if b.get("type") == 0
            for line in b.get("lines", [])
        ]
    )
    if in_references or any(
        re.fullmatch(
            r"\s*(?:参\s*考\s*文\s*献|References)\s*",
            "".join(
                s.get("text", "")
                for line in block.get("lines", [])
                for s in line.get("spans", [])
            ),
            re.I,
        )
        for block in raw_blocks
    ):
        raw_blocks = split_reference_blocks(raw_blocks)
    tab_rects.extend(supplemental_regions(page, raw_blocks))
    figure_rects = figure_text_regions(page, raw_blocks, body_font_size)
    raw_blocks = split_region_blocks(raw_blocks, tab_rects, figure_rects)
    # Retain physical line coordinates before assembling logical paragraphs.
    for block in raw_blocks:
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = sanitize_unicode("".join(s.get("text", "") for s in spans))
            if text:
                page_data.lines.append(
                    TextLine(
                        text,
                        tuple(line["bbox"]),
                        max((s.get("size", 10.5) for s in spans), default=10.5),
                        spans[0].get("font", "") if spans else "",
                        [
                            TextSpan(
                                sanitize_unicode(s.get("text", "")),
                                s.get("size", 10.5),
                                s.get("font", ""),
                                tuple(s["bbox"]),
                            )
                            for s in spans
                        ],
                    )
                )
    page_data.lines.sort(key=lambda line: (round(line.bbox[1], 1), line.bbox[0]))
    # Vector charts and table rules occupy the page just like bitmap images.
    page_data.graphic_regions = [
        tuple(d["rect"])
        for d in page.get_drawings()
        if d["rect"].y1 > 72
        and d["rect"].y0 < p_height - 78
        and (d["rect"].width > 8 or d["rect"].height > 8)
    ]
    definition_text = " ".join(
        structured_line_text(line)
        for block in raw_blocks
        if block.get("type") == 0
        for line in block.get("lines", [])
    )

    return raw_blocks, tab_rects, definition_text


def text_blocks(raw_blocks, tab_rects, recurring_margins, page_height, top, bottom):
    p_height, page_top_y, page_bottom_y = page_height, top, bottom
    # The old merge rule uses the last measured block font, even after filtering.
    avg_font_size = 10.5
    # Step 1: Filter and extract valid text blocks on the page
    valid_blocks = []
    for b_idx, block in enumerate(raw_blocks):
        if block.get("type") == 0:  # text block
            b_lines = block.get("lines", [])
            b_bbox = block.get("bbox", (0, 0, 0, 0))

            block_text_list = []
            dominant_font = ""
            last_line_str = ""

            for line in b_lines:
                l_spans = line.get("spans", [])
                line_text = "".join(s.get("text", "") for s in l_spans)
                if not line_text.strip():
                    continue
                block_text_list.append(line_text.strip())
                last_line_str = line_text.strip()

                for s in l_spans:
                    fn = s.get("font", "")
                    dominant_font = fn

            if not block_text_list:
                continue

            max_font_sz = max(
                (
                    s.get("size", 10.5)
                    for line in b_lines
                    for s in line.get("spans", [])
                ),
                default=10.5,
            )
            weighted_spans = [
                (s, len(s.get("text", "").strip()))
                for line in b_lines
                for s in line.get("spans", [])
            ]
            font_weights = Counter()
            for s, weight in weighted_spans:
                if weight:
                    font_weights[
                        (round(s.get("size", 10.5), 1), s.get("font", ""))
                    ] += weight
            if font_weights:
                avg_font_size, dominant_font = font_weights.most_common(1)[0][0]
            else:
                avg_font_size = 10.5

            # Repeated marginal text is a header/footer; small text near the
            # top can also be a genuine reference or abstract continuation.
            b_h = b_bbox[3] - b_bbox[1]
            if len(b_lines) <= 2 or b_h <= 30.0:
                marginal_text = "".join(block_text_list)
                key = margin_key(marginal_text, b_bbox, p_height)
                if key in recurring_margins:
                    continue
                if key and re.fullmatch(
                    r"[\s\dIVXLCDMivxlcdm一二三四五六七八九十-]+", marginal_text
                ):
                    continue

            page_top_y = min(page_top_y, b_bbox[1])
            page_bottom_y = max(page_bottom_y, b_bbox[3])

            full_p_text = sanitize_unicode(" ".join(block_text_list).strip())
            if not full_p_text:
                continue

            brect = fitz.Rect(b_bbox)
            in_table = block.get("region_kind") == "table"
            for tr in tab_rects:
                if (
                    tr.contains(brect)
                    or (tr & brect).get_area() / max(brect.get_area(), 1) > 0.75
                ):
                    in_table = True
                    break

            valid_blocks.append(
                {
                    "b_idx": b_idx,
                    "bbox": b_bbox,
                    "lines": b_lines,
                    "text": full_p_text,
                    "avg_font_size": avg_font_size,
                    "max_font_sz": max_font_sz,
                    "dominant_font": dominant_font,
                    "last_line_str": last_line_str,
                    "in_table": in_table,
                    "in_figure": block.get("region_kind") == "figure",
                }
            )

    return valid_blocks, avg_font_size, page_top_y, page_bottom_y


def paragraph_blocks(
    valid_blocks, p_width, avg_font_size, re_formula, heading_patterns
):
    re_cn_chap, re_num_chap, re_chap2, re_chap3, re_chap4, re_cn_sec = heading_patterns
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
        in_tab = b.get("in_table", False) or b.get("in_figure", False)

        is_h = bool(
            re_cn_chap.match(b_txt)
            or re_num_chap.match(b_txt)
            or re_chap2.match(b_txt)
            or re_chap3.match(b_txt)
            or re_chap4.match(b_txt)
            or re_cn_sec.match(b_txt)
        )
        is_cap = bool(caption_match(b_txt))
        b_clean = b_txt.replace(" ", "")
        is_special = bool(
            re.match(
                r"^(摘\s*要|Abstract|参\s*考\s*文\s*献|References|目\s*录|Contents|致\s*谢|附\s*录)$",
                b_txt.strip(),
                re.I,
            )
            or b_clean in ["摘要", "参考文献", "目录", "致谢", "附录"]
        )
        is_special = is_special or _is_keyword_label(b_txt)
        is_lst = bool(
            re.match(r"^\[\d+\]", b_txt)
            or re.match(r"^\(?\d+[\)）\.]\s*", b_txt)
            or b_txt.startswith(
                ("•", "-", "*", "·", "一、", "二、", "三、", "四、", "五、")
            )
            or re.match(r"^[①②③④⑤⑥⑦⑧⑨⑩]", b_txt)
        )
        is_form = (
            bool(re_formula.search(b_txt)) or b.get("is_formula", False)
        ) and not b.get("inline_math")
        if (
            not in_tab
            and not is_cap
            and not is_lst
            and not b.get("inline_math")
            and len(b_txt) < 150
            and len(re.findall(r"[\u4e00-\u9fff]", b_txt)) < 3
            and re.search(r"[=≤≥≈≠]", b_txt)
            and not re.search(r"https?://|www\.", b_txt)
        ):
            is_form = True

        if in_tab:
            if curr_b:
                processed_blocks.append(curr_b)
                curr_b = None
            processed_blocks.append(
                dict(
                    b,
                    is_heading=False,
                    is_caption=False,
                    is_special=False,
                    is_formula=False,
                    is_list=False,
                    in_table=True,
                )
            )
            continue

        if curr_b is None:
            curr_b = dict(
                b,
                is_heading=is_h,
                is_caption=is_cap,
                is_special=is_special,
                is_formula=is_form,
                is_list=is_lst,
                in_table=False,
            )
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
            curr_b["bbox"] = (
                min(c_bb[0], b["bbox"][0]),
                min(c_bb[1], b["bbox"][1]),
                max(c_bb[2], b["bbox"][2]),
                max(c_bb[3], b["bbox"][3]),
            )
            curr_b["last_line_str"] = b.get("last_line_str", "")
            curr_b["max_font_sz"] = max(curr_b["max_font_sz"], b["max_font_sz"])
            if is_form:
                curr_b["is_formula"] = True
        else:
            processed_blocks.append(curr_b)
            curr_b = dict(
                b,
                is_heading=is_h,
                is_caption=is_cap,
                is_special=is_special,
                is_formula=is_form,
                is_list=is_lst,
                in_table=False,
            )

    if curr_b:
        processed_blocks.append(curr_b)

    return processed_blocks


def paragraph_from_block(block_item, page_num, p_height, prev_block_tail):
    """Create one physical paragraph, retaining legacy font and prefix rules."""
    b_idx = block_item["b_idx"]
    b_bbox = block_item["bbox"]
    b_lines = block_item["lines"]
    full_p_text = block_item["text"]
    avg_font_size = block_item["avg_font_size"]
    dominant_font = block_item["dominant_font"]
    weights = Counter()
    for line in b_lines:
        for s in line["spans"]:
            weights[(round(s.get("size", 10.5), 1), s.get("font", ""))] += len(
                s.get("text", "").strip()
            )
    if weights:
        avg_font_size, dominant_font = weights.most_common(1)[0][0]
    last_line_str = block_item["last_line_str"]

    # Merge split '第' with '一章...'
    if prev_block_tail == "第" and re.match(
        r"^[一二三四五六七八九十0-9]+\s*章", full_p_text
    ):
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
        is_figure_text=block_item.get("in_figure", False),
        is_footnote=bool(
            b_bbox[1] > p_height * 0.7 and re.match(r"^\d+\s*https?://", full_p_text)
        ),
        source_pages=[page_num],
        last_line_bbox=tuple(b_lines[-1]["bbox"]) if b_lines else b_bbox,
    )
    return p_data
