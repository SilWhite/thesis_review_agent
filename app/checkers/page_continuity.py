"""Keep logical sections intact while retaining physical page boundaries."""
import re
from collections import Counter
from dataclasses import replace


def margin_key(text, bbox, height):
    text = re.sub(r'\s+', '', text)
    if len(text) > 90:
        return None
    if bbox[3] < 100:
        return ('top', round(bbox[1] / 12), text)
    if bbox[1] > height - 85:
        return ('bottom', round((height - bbox[3]) / 12), text)
    return None


def running_margins(doc):
    counts = Counter()
    for page in doc:
        seen = set()
        for block in page.get_text('blocks'):
            if block[6] != 0:
                continue
            key = margin_key(block[4], block[:4], page.rect.height)
            if key and not re.search(r'[\[\]，。,;:：]|(?:19|20)\d{2}', key[2]):
                seen.add(key)
        counts.update(seen)
    return {key for key, count in counts.items() if count >= 2}


def text_margins(blocks, page_width):
    wide = [b for b in blocks if b['bbox'][2] - b['bbox'][0] > page_width * .45
            and len(b['text']) > 20 and not b.get('in_table')]
    if not wide:
        return page_width * .15, page_width * .85
    # Paragraph starts are indented; the smaller frequent left edge is the column.
    counts = Counter(round(b['bbox'][0] / 3) * 3 for b in wide)
    frequent = [x for x, n in counts.items() if n >= max(counts.values()) * .3]
    left = min(frequent)
    right = Counter(round(b['bbox'][2] / 3) * 3 for b in wide).most_common(1)[0][0]
    return left, right


def join_page_continuations(paragraphs, page_map):
    """Join only consecutive, full-width, flush-left continuations across pages."""
    joined = []
    for original in paragraphs:
        p = replace(original, source_pages=list(original.source_pages or [original.page]))
        if joined:
            prev = joined[-1]
            prev_page = (prev.source_pages or [prev.page])[-1]
            page = page_map.get(p.page)
            old_page = page_map.get(prev_page)
            if page and old_page and p.page == prev_page + 1:
                normal = lambda x: not (x.is_heading or x.is_caption or x.is_formula or x.is_table_cell)
                candidates = [x for x in page.paragraphs if normal(x) and len(x.text) > 20]
                left = min((x.bbox[0] for x in candidates), default=p.bbox[0])
                prior_right = max((x.bbox[2] for x in old_page.paragraphs if normal(x)), default=0)
                last_right = prev.last_line_bbox[2] or prev.bbox[2]
                is_list = bool(re.match(r'^(?:\(?\d+[)）.]|[（(][一二三四五六七八九十]+[)）]|[•①②③])', p.text))
                if (normal(p) and normal(prev) and not is_list
                        and p.bbox[0] <= left + .7 * p.font_size
                        and last_right >= prior_right - 1.5 * prev.font_size
                        and abs(p.font_size - prev.font_size) < 1):
                    prev.text += ' ' + p.text
                    prev.source_pages.extend(p.source_pages)
                    prev.line_count += p.line_count
                    prev.height += p.height
                    prev.ratio_of_page += p.ratio_of_page
                    prev.last_line_text = p.last_line_text
                    prev.last_line_bbox = p.last_line_bbox
                    continue
        joined.append(p)
    return joined
