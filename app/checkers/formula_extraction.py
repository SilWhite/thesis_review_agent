"""Recover PDF font characters before arranging formula lines."""
import io
import re
import statistics
import unicodedata


def _font_key(name):
    return re.sub(r"[^a-z0-9]", "", name.split("+")[-1].lower())


def _glyph_map(doc, xref, expected_name):
    try:
        from fontTools.ttLib import TTFont, TTCollection
        data = doc.extract_font(xref)[3]
        if not data:
            return {}
        if data[:4] == b"ttcf":
            fonts = TTCollection(io.BytesIO(data)).fonts
        else:
            fonts = [TTFont(io.BytesIO(data))]
        expected = _font_key(expected_name)
        font = next((f for f in fonts if _font_key(f['name'].getDebugName(6) or '') == expected), None)
        if font is None:
            return {}
        choices = {}
        for code, glyph in (font.getBestCmap() or {}).items():
            if not 0xD800 <= code <= 0xDFFF:
                choices.setdefault(font.getGlyphID(glyph), set()).add(chr(code))
        # Ambiguous glyphs keep the PDF's original character.
        result = {gid: next(iter(chars)) for gid, chars in choices.items() if len(chars) == 1}
        for opened in fonts:
            opened.close()
        return result
    except Exception:
        return {}


def recovered_page_dict(page, font_cache):
    """Return DICT-compatible spans with Unicode repaired using font glyph IDs.

    Trace glyph IDs and RAWDICT origins come from the same PDF rendering stream.
    Font tables are optional; missing or ambiguous mappings remain unchanged.
    """
    maps = {}
    for entry in page.get_fonts(full=True):
        xref, name = entry[0], entry[3]
        key = (xref, name)
        if key not in font_cache:
            font_cache[key] = _glyph_map(page.parent, xref, name)
        maps.setdefault(_font_key(name), []).append(font_cache[key])
    # Multiple subsets can have the same display name. Keep only glyph mappings
    # that agree across every such font on this page.
    for name, alternatives in maps.items():
        common = set.intersection(*(set(m) for m in alternatives))
        maps[name] = {gid: alternatives[0][gid] for gid in common
                      if len({m[gid] for m in alternatives}) == 1}
    chars_by_origin = {}
    for span in page.get_texttrace():
        key = _font_key(span['font'])
        mapping = maps.get(key, {})
        for code, gid, origin, bbox in span['chars']:
            recovered = mapping.get(gid)
            if recovered:
                loc = (key, round(origin[0], 2), round(origin[1], 2))
                chars_by_origin.setdefault(loc, set()).add(recovered)
    result = page.get_text('rawdict')
    for block in result.get('blocks', []):
        if block.get('type') != 0:
            continue
        for line in block.get('lines', []):
            for span in line.get('spans', []):
                key = _font_key(span['font'])
                text = []
                for char in span.pop('chars', []):
                    loc = (key, round(char['origin'][0], 2), round(char['origin'][1], 2))
                    replacements = chars_by_origin.get(loc, set())
                    text.append(next(iter(replacements)) if len(replacements) == 1 else char['c'])
                span['text'] = ''.join(text)
                # Cambria Math can advertise a bbox several lines tall. Baselines
                # describe the actual row much more faithfully than that font box.
                x0, y0, x1, y1 = span['bbox']
                if y1 - y0 > 2 * span['size']:
                    y = span['origin'][1]
                    span['bbox'] = (x0, y - .9 * span['size'], x1, y + .3 * span['size'])
            if line['spans']:
                line['bbox'] = union_boxes([s['bbox'] for s in line['spans']])
        if block.get('lines'):
            block['bbox'] = union_boxes([line['bbox'] for line in block['lines']])
    return result


def union_boxes(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def baseline(lines):
    spans = [s for line in lines for s in line['spans'] if s.get('text', '').strip()]
    if not spans:
        return 0.
    size = max(s['size'] for s in spans)
    return statistics.median(s['origin'][1] for s in spans if s['size'] >= size * .9)


def structured_line_text(line):
    spans = line['spans']
    if not spans:
        return ''
    size = max(s['size'] for s in spans)
    y = baseline([line])
    pieces = []
    for span in spans:
        text = unicodedata.normalize('NFKC', span['text'])
        if text.strip() and span['size'] < size * .85:
            dy = span['origin'][1] - y
            if dy > 1:
                text = '_{' + text.strip() + '}'
            elif dy < -1:
                text = '^{' + text.strip() + '}'
        pieces.append(text)
    return ''.join(pieces)


def stitch_numbered_rows(blocks, number_pattern):
    """Split numbered blocks into rows; join only fragments on the same baseline."""
    rows = []
    for block in blocks:
        if number_pattern.search(block['text']) and not block.get('in_table'):
            for index, line in enumerate(block['lines']):
                item = dict(block)
                item.update(b_idx=f"{block['b_idx']}_{index}", lines=[line], bbox=line['bbox'],
                            text=''.join(s['text'] for s in line['spans']),
                            last_line_str=''.join(s['text'] for s in line['spans']))
                rows.append(item)
        else:
            rows.append(block)
    anchors = [b for b in rows if number_pattern.search(b['text'])
               and len(re.findall(r'[\u4e00-\u9fff]', b['text'])) < 5 and not b.get('in_table')]
    anchor_positions = sorted((baseline(b['lines']), id(b)) for b in anchors)
    prose_positions = [baseline([line]) for b in rows for line in b['lines']
                       if len(re.findall(r'[\u4e00-\u9fff]', ''.join(s['text'] for s in line['spans']))) >= 3]
    used = set()
    for anchor in anchors:
        number_text = number_pattern.search(anchor['text']).group(0).strip()
        anchor_y = baseline(anchor['lines'])
        above = [y for y in prose_positions if y < anchor_y]
        below = [y for y in prose_positions if y > anchor_y]
        low = max(above, default=anchor_y - 65) + 3
        high = min(below, default=anchor_y + 65) - 3
        for other_y, other_id in anchor_positions:
            if other_id == id(anchor):
                continue
            if other_y < anchor_y:
                low = max(low, (other_y + anchor_y) / 2)
            else:
                high = min(high, (other_y + anchor_y) / 2)
        fragments = [anchor]
        for row in rows:
            if row is anchor or row in anchors or row['b_idx'] in used or row.get('in_table'):
                continue
            if len(re.findall(r'[\u4e00-\u9fff]', row['text'])) >= 3:
                continue
            row_y = baseline(row['lines'])
            math_font = any('math' in s['font'].lower() or 'symbol' in s['font'].lower()
                            for line in row['lines'] for s in line['spans'])
            math_text = bool(re.search(r'[=∑∫√≤≥+*/(){}]', row['text']) or re.fullmatch(r'[\sA-Za-z0-9.-]{1,6}', row['text']))
            # A distant full-sized equation can be an independently unnumbered
            # formula. Small bounds such as i=1 belong to a nearby sum instead.
            equals_size = max((s['size'] for line in row['lines'] for s in line['spans'] if '=' in s['text']), default=0)
            full_size_equation = ('=' in row['text'] and abs(row_y - anchor_y) > 28
                                  and equals_size >= anchor['max_font_sz'] * .9)
            if low < row_y < high and (math_font or math_text) and not full_size_equation:
                fragments.append(row)
                used.add(row['b_idx'])
        fragments.sort(key=lambda b: b['bbox'][0])
        anchor['text'] = ' '.join(number_pattern.sub('', b['text']).strip() for b in fragments).strip() + ' ' + number_text
        anchor['formula_number'] = number_text
        anchor['lines'] = [line for b in fragments for line in b['lines']]
        anchor['bbox'] = union_boxes([b['bbox'] for b in fragments])
        anchor['is_formula'] = True
    result = sorted([row for row in rows if row['b_idx'] not in used],
                    key=lambda row: (baseline(row['lines']), row['bbox'][0]))
    for index, row in enumerate(result):
        row['b_idx'] = index
    return result
