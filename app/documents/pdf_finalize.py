"""Complete PDF page geometry, cross-page paragraphs and formula contexts."""

from app.documents.continuity import join_page_continuations


def finish_page(page_data, current_chapter, page_top_y, page_bottom_y):
    page_num, p_height = page_data.page_num, page_data.height
    # Populate formula context (preceding and following paragraphs)
    if current_chapter and current_chapter.formulas:
        for f in current_chapter.formulas:
            if f.page == page_num and not f.context_text:
                fy = (f.bbox[1] + f.bbox[3]) / 2.0
                ctx_list = [
                    p.text
                    for p in page_data.paragraphs
                    if not p.is_formula
                    and not p.is_caption
                    and abs((p.bbox[1] + p.bbox[3]) / 2.0 - fy) <= 150.0
                ]
                f.context_text = " ".join(ctx_list)

    if page_bottom_y > page_top_y:
        page_data.content_height_ratio = (page_bottom_y - page_top_y) / p_height
    intervals = [(p.bbox[1], p.bbox[3]) for p in page_data.paragraphs]
    intervals += [(b[1], b[3]) for b in page_data.graphic_regions]
    intervals += [(f.bbox[1], f.bbox[3]) for f in page_data.images]
    cursor, largest = 72.0, (0.0, 0.0)
    for top, bottom in sorted(intervals):
        top, bottom = max(72.0, top), min(p_height - 78.0, bottom)
        if bottom < top:
            continue
        if top - cursor > largest[1] - largest[0]:
            largest = (cursor, top)
        cursor = max(cursor, bottom)
    if p_height - 78 - cursor > largest[1] - largest[0]:
        largest = (cursor, p_height - 78)
    page_data.largest_blank = largest


def finish_tree(tree, all_paras, body_paras, definition_lines):
    if tree.chapters and tree.chapters[-1].end_page == 1:
        tree.chapters[-1].end_page = tree.total_pages

    tree.all_body_paragraphs = body_paras
    tree.body_text_only = "\n".join(p.text for p in body_paras if not p.is_heading)
    tree.all_text = "\n".join(p.text for p in all_paras)

    page_map = {p.page_num: p for p in tree.pages}
    for ch in tree.chapters:
        ch.paragraphs = join_page_continuations(ch.paragraphs, page_map)
        for formula in ch.formulas:
            formula.definition_context = " ".join(
                definition_lines.get(number, "")
                for number in range(ch.page, min(ch.end_page, formula.page + 1) + 1)
            )
    # Section titles immediately below “摘要” are not abstract prose.
    for name in ("abstract_cn", "abstract_en"):
        paras = getattr(tree, name)
        if paras:
            prose_size = sorted(p.font_size for p in paras)[len(paras) // 2]
            while (
                paras
                and paras[0].font_size > prose_size + 1
                and len(paras[0].text) < 200
            ):
                paras = paras[1:]
        setattr(tree, name, join_page_continuations(paras, page_map))
    tree.all_body_paragraphs = [
        p
        for ch in tree.chapters
        for p in ch.paragraphs
        if not p.is_table_cell and not p.is_figure_text
    ]
    tree.body_text_only = "\n".join(
        p.text
        for p in tree.all_body_paragraphs
        if not p.is_heading and not p.is_caption
    )

    # Conclusion pages count
    if tree.conclusion_chapter:
        c_start = tree.conclusion_chapter.page
        c_end = (
            tree.conclusion_chapter.end_page
            if tree.conclusion_chapter.end_page >= c_start
            else len(tree.pages)
        )
        tree.conclusion_pages_count = max(0.5, float(c_end - c_start + 1))

    return tree
