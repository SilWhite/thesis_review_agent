"""Read-only PDF evidence previews."""


def render_evidence_page(path, location, full_page=False):
    import fitz

    with fitz.open(path) as doc:
        number = location.get("page")
        if not isinstance(number, int) or not 1 <= number <= len(doc):
            raise ValueError("原页页码无效。")
        page = doc[number - 1]
        boxes = []
        candidates = location.get("bboxes") or [location.get("bbox")]
        for bbox in candidates:
            if not bbox or len(bbox) != 4:
                continue
            rect = fitz.Rect(bbox) & page.rect
            if not rect.is_empty and not rect.is_infinite:
                boxes.append(rect)
        if not boxes:
            quote = location.get("quote") or ""
            if len(quote) >= 4:
                boxes = page.search_for(quote[:100])
        for rect in boxes:
            page.draw_rect(rect, color=(0.85, 0.15, 0.1), width=1.5, overlay=True)
        clip = page.rect
        if boxes and not full_page:
            region = fitz.Rect(boxes[0])
            for rect in boxes[1:]:
                region |= rect
            clip = fitz.Rect(
                page.rect.x0,
                max(0, region.y0 - 65),
                page.rect.x1,
                min(page.rect.y1, region.y1 + 65),
            )
        return page.get_pixmap(
            matrix=fitz.Matrix(1.5, 1.5), clip=clip, alpha=False
        ).tobytes("png")
