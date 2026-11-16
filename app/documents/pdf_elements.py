"""Attach figure, table and formula records to the current PDF chapter."""

import re
from app.documents.formulas import structured_line_text
from app.documents.formula_symbols import unreadable, normalize as normalize_formula
from app.documents.structure import figure_caption, table_caption

from app.documents.models import FigureData, TableData, FormulaData


def append_elements(p_data, block_item, current_chapter, re_formula):
    full_p_text, page_num = p_data.text, p_data.page
    avg_font_size, b_lines = p_data.font_size, block_item["lines"]
    # Figures and tables
    m_fig = figure_caption(full_p_text)
    if m_fig:
        p_data.is_caption = True
        f_num_raw = m_fig.group(2)
        f_num = re.sub(r"\s+", "", f_num_raw)
        is_sub = bool(re.search(r"\([a-z]\)", full_p_text, re.IGNORECASE))
        fig_item = FigureData(
            num=f_num,
            caption=full_p_text,
            page=page_num,
            is_subfig=is_sub,
            bbox=p_data.bbox,
        )
        if current_chapter:
            current_chapter.figures.append(fig_item)

    m_tbl = table_caption(full_p_text)
    if m_tbl:
        p_data.is_caption = True
        t_num_raw = m_tbl.group(2)
        t_num = re.sub(r"\s+", "", t_num_raw)
        tbl_item = TableData(
            num=t_num,
            caption=full_p_text,
            page=page_num,
            bbox=p_data.bbox,
            font_size=avg_font_size,
        )
        if current_chapter:
            current_chapter.tables.append(tbl_item)

    # Formulas: require explicit formula number (X-Y) or standalone single-line math equation
    m_form = re_formula.search(full_p_text) or re_formula.search(
        block_item.get("formula_number", "")
    )
    is_standalone_math = False
    zh_count = sum(1 for c in full_p_text if "\u4e00" <= c <= "\u9fa5")
    if (
        "=" in full_p_text
        and len(full_p_text) < 60
        and zh_count == 0
        and not block_item.get("inline_math")
    ):
        if any(c in full_p_text for c in "+-*/∑∫√SoftmaxLayerNormAttentionℝ"):
            is_standalone_math = True

    if (
        not p_data.is_table_cell
        and not block_item.get("inline_math")
        and (
            (
                m_form
                and zh_count < 5
                and not p_data.is_caption
                and not p_data.is_heading
            )
            or is_standalone_math
        )
    ):
        p_data.is_formula = True
        has_num = bool(m_form)
        num_str = re.sub(r"\s+", "", m_form.group(1)) if m_form else ""
        structured = " ".join(structured_line_text(line) for line in b_lines)
        if block_item.get("formula_number"):
            number_text = block_item["formula_number"]
            structured = structured.replace(number_text, "").strip() + " " + number_text
        corrupted = unreadable(structured)
        content = re_formula.sub("", structured).strip(" .…")
        quality = "unreadable" if corrupted or not content else "native"
        if "=" in content and (
            not any(c.isalpha() for c in content.split("=", 1)[0])
            or not content.split("=", 1)[1].strip()
        ):
            quality = "partial"
        if re.search(
            r"(?<![A-Za-z0-9}])_\{[^{}]*(?:exp|log|softmax)\(",
            normalize_formula(structured),
        ):
            quality = "partial"
        form_item = FormulaData(
            text=full_p_text,
            has_number=has_num,
            num_str=num_str,
            page=page_num,
            bbox=p_data.bbox,
            structured_text=structured,
            extraction_status=quality,
            numbering_status=(
                "found"
                if has_num
                else ("uncertain" if quality != "native" else "missing")
            ),
        )
        if current_chapter:
            current_chapter.formulas.append(form_item)
