"""Attach precise extracted evidence and render read-only PDF page previews."""

import re
import unicodedata


def compact(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


def _occurrence_locations(tree, loc):
    """Resolve a logical paragraph offset onto its physical pages and lines."""
    logical = next((p for p in tree.all_body_paragraphs if p.id == loc.block_id), None)
    if logical is None or loc.text_offset is None:
        return []
    target_start = len(compact(logical.text[: loc.text_offset]))
    target_end = target_start + len(compact(loc.quote))
    whole = compact(logical.text)
    cursor = 0
    started = False
    results = []
    for page in tree.pages:
        if page.page_num not in (logical.source_pages or [logical.page]):
            continue
        for para in page.paragraphs:
            if not started:
                if para.id != logical.id:
                    continue
                started = True
            text = compact(para.text)
            start = whole.find(text, cursor) if text else -1
            if start < 0:
                continue
            stop = start + len(text)
            cursor = stop
            lo, hi = max(start, target_start), min(stop, target_end)
            if lo >= hi:
                continue
            # Original lines retain physical coordinates after paragraph joining.
            lines = [
                line
                for line in page.lines
                if line.bbox[1] >= para.bbox[1] - 2
                and line.bbox[3] <= para.bbox[3] + 2
                and line.bbox[0] < para.bbox[2]
                and line.bbox[2] > para.bbox[0]
            ]
            line_text = "".join(compact(line.text) for line in lines)
            base = line_text.find(text)
            boxes = []
            if base >= 0:
                a, b = base + lo - start, base + hi - start
                offset = 0
                for line in lines:
                    length = len(compact(line.text))
                    if max(offset, a) < min(offset + length, b):
                        boxes.append(list(line.bbox))
                    offset += length
            if not boxes and any(para.bbox):
                boxes = [list(para.bbox)]
            segment = text[lo - start : hi - start]
            results.append(
                loc.model_copy(
                    update={
                        "page": page.page_num,
                        "block_id": para.id,
                        "quote": segment,
                        "bboxes": boxes,
                        "bbox": boxes[0] if boxes else None,
                        "verified": True,
                        "highlight_texts": [segment],
                    }
                )
            )
    return results


def attach_evidence(tree, findings):
    from app.schemas import EvidenceLocation

    pages = {p.page_num: p for p in tree.pages}
    for finding in findings:
        if not finding.locations and len(compact(finding.quote)) >= 6:
            needle = compact(finding.quote)
            for page in tree.pages:
                if any(needle in compact(p.text) for p in page.paragraphs):
                    finding.locations.append(
                        EvidenceLocation(
                            page=page.page_num,
                            quote=finding.quote,
                            description="引文所在位置",
                        )
                    )
                    if len(finding.locations) >= 2:
                        break
        if not finding.evidence_note:
            if finding.rule_id == 13:
                finding.evidence_note = (
                    "重点核对问题中列出的符号；下方展示公式及原文说明。"
                )
            elif finding.rule_id in (2, 14, 16):
                finding.evidence_note = "请对照下方各处原文，查看重复的文字。"
        resolved = []
        for loc in finding.locations:
            precise = _occurrence_locations(tree, loc)
            resolved.extend(precise or [loc])
        finding.locations = resolved
        for loc in finding.locations:
            page = pages.get(loc.page)
            if not page:
                continue
            needle = compact(loc.quote or finding.quote).strip(".…")
            matches = [
                p for p in page.paragraphs if needle and needle in compact(p.text)
            ]
            if not matches:
                continue
            para = min(matches, key=lambda p: (p.id != loc.block_id, len(p.text)))
            loc.verified = True
            loc.context = loc.context or para.text
            if not loc.bbox and para.bbox[2] > para.bbox[0]:
                loc.bbox = list(para.bbox)
            if not loc.highlight_texts:
                focus = (
                    finding.quote
                    if finding.quote and compact(finding.quote) in compact(para.text)
                    else loc.quote
                )
                loc.highlight_texts = [focus] if focus else []
