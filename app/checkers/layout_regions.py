"""Recognize aligned table rows and framed algorithms before paragraph assembly."""
import re
import statistics
import unicodedata
import fitz
from .formula_extraction import baseline, union_boxes
from .structure import caption_match


def _plain_spans(spans):
    return unicodedata.normalize('NFKC', re.sub(r'[\ue000-\uf8ff]', '', ''.join(s['text'] for s in spans))).strip()


def supplemental_regions(page, blocks):
    rows = []
    for block in blocks:
        if block.get('type') != 0:
            continue
        for line in block.get('lines', []):
            text = ''.join(s.get('text', '') for s in line['spans']).strip()
            if text and line['bbox'][1] > 65 and line['bbox'][3] < page.rect.height - 60:
                rows.append((baseline([line]), line, text))
    groups = []
    for y, line, text in sorted(rows, key=lambda r: r[0]):
        if not groups or abs(y - statistics.median(v[0] for v in groups[-1])) > 3:
            groups.append([])
        groups[-1].append((y, line, text))
    candidates = []
    table_caption_y = [line['bbox'][3] for _, line, text in rows if (caption_match(text) and caption_match(text).group(1).lower() in ('表', 'table', 'tables'))]
    prose_y = [line['bbox'][1] for _, line, text in rows
               if line['bbox'][2] - line['bbox'][0] > page.rect.width * .65
               and len(re.findall(r'[\u4e00-\u9fff]', text)) > 15
               and not (caption_match(text) and caption_match(text).group(1).lower() in ('表', 'table', 'tables'))]
    for group in groups:
        cells = [v for v in group if v[1]['bbox'][2] - v[1]['bbox'][0] < page.rect.width * .28]
        digits = sum(bool(re.search(r'\d|^[-–—]+$', v[2])) for v in cells)
        # Several separated columns are essential: inline maths in prose do not
        # turn an entire sentence into a table.
        cells.sort(key=lambda v: v[1]['bbox'][0])
        gaps = sum(max(0, b[1]['bbox'][0] - a[1]['bbox'][2]) for a, b in zip(cells, cells[1:]))
        y = statistics.median(v[0] for v in group)
        captioned = any(c < y and not any(c < py < y for py in prose_y) for c in table_caption_y)
        if len(cells) >= 3 and gaps >= 12 and (digits >= 2 or len(cells) >= 5 or captioned):
            candidates.append((statistics.median(v[0] for v in group), union_boxes([v[1]['bbox'] for v in group])))
    runs = []
    for y, box in candidates:
        if not runs or y - runs[-1][-1][0] > 36:
            runs.append([])
        runs[-1].append((y, box))
    regions = [fitz.Rect(union_boxes([v[1] for v in run])) + (-2, -3, 2, 3)
               for run in runs if len(run) >= 2]
    code_rows = [line['bbox'] for _, line, text in rows if re.match(r'^\d{1,3}\s*[:：]', text)]
    code_tokens = [text for _, line, text in rows if re.match(r'^\d{1,3}\s*[:：]', text)
                   and re.search(r'\b(?:for|foreach|if|end|return|while)\b|←', text, re.I)]
    if len(code_rows) >= 3 and len(code_tokens) >= 2:
        box = fitz.Rect(union_boxes(code_rows))
        regions.append(fitz.Rect(page.rect.width * .1, box.y0 - 2, page.rect.width * .9, box.y1 + 3))
    for caption_y in table_caption_y:
        stops = prose_y + [line['bbox'][1] for _, line, text in rows
                           if (caption_match(text) or re.match(r'^\d+(?:\.\d+)+\s', text))]
        stop = min((y for y in stops if y > caption_y), default=page.rect.height - 65)
        support = [y for y, _ in candidates if caption_y < y < stop]
        content = [line['bbox'] for _, line, text in rows if caption_y < line['bbox'][1] < stop]
        if len(support) >= 2 and content:
            region = fitz.Rect(union_boxes(content)) + (-2, -1, 2, 1)
            region.y0 = caption_y + 1
            regions.append(region)
    # Three-line algorithm boxes have no cell grid. Their explicit caption and
    # enclosing rules distinguish them from ordinary equations.
    rules = []
    for drawing in page.get_drawings():
        for item in drawing['items']:
            if item[0] == 'l':
                a, b = item[1:3]
                if abs(a.y - b.y) < 2 and abs(a.x - b.x) > page.rect.width * .5 and a.y > 65:
                    rules.append((min(a.x, b.x), a.y, max(a.x, b.x), b.y))
            elif item[0] == 're':
                r = item[1]
                if r.width > page.rect.width * .5 and r.height < 3 and r.y0 > 65:
                    rules.append(tuple(r))
    for _, line, text in rows:
        if not re.match(r'^算法\s*\d|^Algorithm\s*\d', text, re.I):
            continue
        y = line['bbox'][1]
        top = [r for r in rules if 0 < y - r[1] < 25]
        bottom = [r for r in rules if r[1] > line['bbox'][3] + 35]
        if top and bottom:
            t, b = max(top, key=lambda r: r[1]), min(bottom, key=lambda r: r[1])
            regions.append(fitz.Rect(min(t[0], b[0]), t[1], max(t[2], b[2]), b[3] + 2))
    # Repeated model groups and their shared headers form one table region.
    merged = []
    for region in sorted(regions, key=lambda r: r.y0):
        if merged and region.y0 - merged[-1].y1 < 45 and min(region.x1, merged[-1].x1) > max(region.x0, merged[-1].x0):
            merged[-1] |= region
        else:
            merged.append(region)
    for region in merged:
        captions = [line['bbox'] for _, line, text in rows
                    if (caption_match(text) and caption_match(text).group(1).lower() in ('表', 'table', 'tables'))
                    and 0 < region.y0 - line['bbox'][3] < 100]
        if captions:
            region.y0 = max(captions, key=lambda b: b[3])[3] + 1
    return merged


def figure_text_regions(page, blocks, body_size=12):
    """Associate the whole multi-panel illustration and its labels with its caption."""
    lines = [(line, _plain_spans(line['spans'])) for block in blocks if block.get('type') == 0
             for line in block.get('lines', [])]
    captions = [(line, text) for line, text in lines if caption_match(text)]

    def prose(line, text):
        box = fitz.Rect(line['bbox'])
        size = max((s.get('size', 0) for s in line['spans']), default=0)
        chinese = len(re.findall(r'[\u4e00-\u9fff]', text))
        in_graphic = any((box & r).get_area() > box.get_area() * .6 for r in components)
        if caption_match(text) or in_graphic:
            return False
        return ((box.width > page.rect.width * .55 and chinese >= 16)
                or (chinese >= 2 and size >= body_size - 1 and text.rstrip().endswith(('。', '：', ':')))
                or (chinese >= 5 and re.search(r'(?:如图|见图|由图|如表|见表)\s*\d', text)))

    def heading(line, text):
        size = max((s.get('size', 0) for s in line['spans']), default=0)
        return (size >= body_size and bool(re.match(r'^(?:第[一二三四五六七八九十0-9]+章|\d+(?:\.\d+)+\s)', text)))

    components = list(page.cluster_drawings())
    for info in page.get_images(full=True):
        components.extend(page.get_image_rects(info[0]))
    components = [fitz.Rect(r) for r in components if r.y0 > 65 and r.y1 < page.rect.height - 65
                  and r.width > 20 and r.height > 3 and r.get_area() < page.rect.get_area() * .9]
    barriers = [fitz.Rect(line['bbox']) for line, text in lines
                if caption_match(text) or prose(line, text) or heading(line, text)]
    result = []
    for caption, text in captions:
        match = caption_match(text)
        if match.group(1).lower() not in ('图', 'figure', 'figures', 'fig.'):
            continue
        cap = fitz.Rect(caption['bbox'])
        floor = max([65.] + [r.y1 for r in barriers if r.y1 < cap.y0 - 2])
        eligible = [r for r in components if r.y0 >= floor - 2 and r.y1 <= cap.y0 + 1]
        seeds = [r for r in eligible if 0 <= cap.y0 - r.y1 < 80
                 and r.width > page.rect.width * .15 and r.height > 12]
        if not seeds:
            continue
        region = fitz.Rect(max(seeds, key=lambda r: r.y1))
        changed = True
        while changed:
            changed = False
            for r in eligible:
                if region.contains(r):
                    continue
                x_overlap = min(r.x1, region.x1) - max(r.x0, region.x0)
                y_overlap = min(r.y1, region.y1) - max(r.y0, region.y0)
                x_gap = max(0, r.x0-region.x1, region.x0-r.x1)
                y_gap = max(0, r.y0-region.y1, region.y0-r.y1)
                # Adjacent columns and separated subplot rows belong together.
                if ((x_overlap > min(r.width, region.width) * .2 and y_gap < 72)
                        or (y_overlap > min(r.height, region.height) * .2 and x_gap < 48)):
                    region |= r
                    changed = True
        region += (-14, -36, 14, 24)
        region.y0, region.y1 = max(floor + 1, region.y0), min(cap.y0 - 2, region.y1)
        # Tick labels and legends can extend outside the drawing's rectangle.
        for line, label in lines:
            box = fitz.Rect(line['bbox'])
            if (box.y0 >= floor and box.y1 < cap.y0 - 1 and region.intersects(box)
                    and not (caption_match(label) or prose(line, label) or heading(line, label))
                    and len(label) <= 160):
                region |= box
        region &= page.rect
        if not region.is_empty:
            result.append(region)
    return result


def split_region_blocks(blocks, tables, figures):
    result = []
    for b in blocks:
        if b.get('type') != 0:
            result.append(b)
            continue
        groups = []
        for line in b['lines']:
            box = fitz.Rect(line['bbox'])
            kind = next((name for name, regions in [('table', tables), ('figure', figures)]
                         if any((box & r).get_area() / max(1, box.get_area()) > .65 for r in regions)), '')
            if not groups or groups[-1][0] != kind:
                groups.append((kind, []))
            groups[-1][1].append(line)
        for kind, lines in groups:
            result.append(dict(b, lines=lines, bbox=union_boxes([l['bbox'] for l in lines]), region_kind=kind))
    return result


def join_inline_fragments(blocks):
    """Reunite a prose row split by Word's inline equation objects."""
    used = set()
    # A short OCR fragment can sit on a line inside a multi-line block.
    # Sorting entire blocks puts that fragment before the paragraph and drops
    # clauses such as the second half of a concession from semantic checks.
    for anchor in blocks:
        if anchor.get('in_table') or anchor.get('in_figure') or len(anchor['lines']) < 3:
            continue
        a = anchor['bbox']
        for fragment in blocks:
            if (fragment is anchor or id(fragment) in used or fragment.get('in_table')
                    or fragment.get('in_figure') or len(fragment['lines']) != 1):
                continue
            b = fragment['bbox']
            if not (a[0] - 2 <= b[0] and b[2] <= a[2] + 2 and a[1] - 2 <= b[1] < a[3]):
                continue
            for line in anchor['lines']:
                c = line['bbox']
                overlap = min(c[3], b[3]) - max(c[1], b[1])
                if (overlap > .6 * min(c[3]-c[1], b[3]-b[1])
                        and (b[0] >= c[2] - 1 or c[0] >= b[2] - 1)):
                    spans = sorted(line['spans'] + fragment['lines'][0]['spans'], key=lambda s: s['bbox'][0])
                    line.update(spans=spans, bbox=union_boxes([c,b]))
                    used.add(id(fragment))
                    anchor['text'] = ' '.join(_plain_spans(l['spans']) for l in anchor['lines'])
                    anchor['last_line_str'] = _plain_spans(anchor['lines'][-1]['spans'])
                    break
    for anchor in blocks:
        if id(anchor) in used or anchor.get('in_table') or anchor.get('in_figure') or len(re.findall(r'[\u4e00-\u9fff]', anchor['text'])) < 3:
            continue
        if (anchor['bbox'][3] - anchor['bbox'][1] > 34
                or (len(anchor['lines']) > 2 and anchor['bbox'][3] - anchor['bbox'][1] > 22)):
            continue
        y = baseline(anchor['lines'])
        parts = [anchor]
        for other in blocks:
            if other is anchor or id(other) in used or other.get('in_table') or other.get('in_figure'):
                continue
            a, b = anchor['bbox'], other['bbox']
            overlap = min(a[3], b[3]) - max(a[1], b[1])
            same_row = (abs(baseline(other['lines']) - y) <= 8
                        or overlap > .65 * min(a[3]-a[1], b[3]-b[1]))
            if same_row and other['bbox'][3] - other['bbox'][1] < 34:
                parts.append(other)
                used.add(id(other))
        if len(parts) > 1:
            spans = sorted([s for p in parts for line in p['lines'] for s in line['spans']], key=lambda s: s['bbox'][0])
            box = union_boxes([p['bbox'] for p in parts])
            anchor.update(text=_plain_spans(spans), bbox=box,
                          lines=[{'spans': spans, 'bbox': box}], inline_math=True)
            anchor['last_line_str'] = anchor['text']
    return [b for b in blocks if id(b) not in used]
