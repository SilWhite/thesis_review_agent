"""Distinguish actual headings/captions from prose that begins with their number."""

import re
from collections import Counter

CAPTION = re.compile(
    r"^(图|表|Figures?|Fig\.|Tables?)\s*(\d+(?:\s*[.．·\-_—–－]\s*\d+)?)\s*(.*)", re.I
)


def caption_match(text):
    match = CAPTION.match(text.strip())
    if not match or len(text) > 800:
        return None
    tail = match.group(3).strip()
    if re.match(
        r"^(?:shows?|illustrates?|depicts?|demonstrates?|summari[sz]es?|presents?|compares?|lists?|reports?|indicates?|reveals?|is|are|has|have|can|provides?|gives?)\b",
        tail,
        re.I,
    ):
        return None
    if re.match(
        r"^(?:the\s+)?(?:results?|experiments?|data)\s+(?:show|indicate|suggest|demonstrate)",
        tail,
        re.I,
    ):
        return None
    # These words connect a numbered illustration to a statement in the prose.
    if re.match(
        r"^(?:[。，,;；)）\]］]|为|是|表示|示意了|如下|可以|可见|所示|所列|所绘|所描述|展示|显示|总结|汇总|给出|给出了|表明|说明|反映|揭示|列出|列出了|对比了|比较了|呈现|描述了|分析了|中(?:$|[。，,]|的|所|直观|可以|可见|展示|给出)|所展示|所反映|所给出)",
        tail,
    ):
        return None
    if re.match(
        r"^的.{0,18}(?:显示|表明|说明|展示|可以|可见|反映|给出|总结|如下)", tail
    ):
        return None
    return match


def figure_caption(text):
    match = caption_match(text)
    return (
        match
        if match and match.group(1).lower() in ("图", "figure", "figures", "fig.")
        else None
    )


def table_caption(text):
    match = caption_match(text)
    return (
        match if match and match.group(1).lower() in ("表", "table", "tables") else None
    )


def dominant_body_size(doc):
    counts = Counter()
    for page in doc:
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    n = len(re.findall(r"[\u4e00-\u9fff]", span.get("text", "")))
                    if n >= 8:
                        counts[round(span["size"] * 2) / 2] += n
    return counts.most_common(1)[0][0] if counts else 10.5


def heading_layout(text, box, size, font, body_size, page_width):
    if len(text) > 90:
        return False
    tail = re.sub(r"^第\s*[一二三四五六七八九十百0-9]+\s*章\s*", "", text)
    roadmap = bool(
        re.match(
            r"^(?:介绍|提出|研究了|阐述|讨论|总结了|总结本文|对本文|主要|首先|围绕|分析了|将|为后续)",
            tail,
        )
    )
    distinct_size = size >= body_size + 1
    centered = abs((box[0] + box[2]) / 2 - page_width / 2) <= 35
    bold = bool(re.search(r"bold|hei|黑", font, re.I))
    return distinct_size or (centered and bold and not roadmap)


def split_reference_blocks(blocks):
    """A native PDF block may contain several numbered reference entries."""
    from app.documents.formulas import union_boxes

    output = []
    for block in blocks:
        if block.get("type") != 0:
            output.append(block)
            continue
        groups = []
        for line in block.get("lines", []):
            text = "".join(s.get("text", "") for s in line.get("spans", []))
            if not groups or re.match(
                r"^\s*(?:[\[［]\s*\d+\s*[\]］]|\d{1,3}[.．]\s+|[（(]\d{1,3}[)）]\s+)",
                text,
            ):
                groups.append([])
            groups[-1].append(line)
        for lines in groups:
            output.append(
                dict(
                    block,
                    lines=lines,
                    bbox=union_boxes([line["bbox"] for line in lines]),
                )
            )
    return output
