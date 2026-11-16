"""Text normalization and heading/cover recognition shared by format readers."""

import re
import unicodedata
from typing import Optional
import fitz


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
    return bool(
        re.fullmatch(
            r"(?:致谢|附录(?:[A-Za-z0-9一二三四五六七八九十]+)?|"
            r"攻读(?:硕士|博士)?学位期间[^。！？；]{0,30}|"
            r"ACKNOWLEDG(?:E)?MENTS?|APPENDIX(?:[A-Za-z0-9]+)?)",
            compact,
            re.IGNORECASE,
        )
    )


def _is_keyword_label(text: str) -> bool:
    label = r"(?:关\s*键\s*词|KEY\s*WORDS?)"
    return bool(
        re.match(r"^\s*" + label + r"\s*[:：]", text, re.IGNORECASE)
        or re.fullmatch(r"\s*" + label + r"\s*", text, re.IGNORECASE)
    )


def _detect_degree(text: str) -> str:
    text = sanitize_unicode(text)
    if "博士学位论文" in text or "博士论文" in text:
        return "doctor"
    if "硕士学位论文" in text or "硕士论文" in text:
        return "master"
    if "学士学位论文" in text or "学士论文" in text or "毕业设计" in text:
        return "bachelor"
    return "unknown"


def _extract_titles(
    doc_or_text, doc: Optional[fitz.Document] = None
) -> tuple[str, str]:
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

    m_en = re.search(
        r"(?:Title|English Title)[：:\s]+([^\n\r]+)", cover_text, re.IGNORECASE
    )
    if m_en:
        title_en = m_en.group(1).strip()

    skip_kws = [
        "大学",
        "学院",
        "学位论文",
        "作者",
        "导师",
        "学号",
        "专业",
        "单位代码",
        "分类号",
        "密级",
        "UDC",
        "答辩日期",
        "年月",
        "版权",
        "declaration",
        "permission",
        "学术学位",
        "专业学位",
        "指导教师",
        "学校代码",
        "学校名称",
        "姓名",
        "研究方向",
        "培养单位",
        "论文作者",
        "答辩委员会",
        "评阅人",
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
                        txt = sanitize_unicode(
                            "".join(s.get("text", "") for s in spans)
                        )
                        if not txt or len(txt) < 5:
                            continue
                        if any(kw in txt for kw in skip_kws):
                            continue
                        max_sz = max((s.get("size", 10.5) for s in spans), default=10.5)

                        if re.search(r"[\u4e00-\u9fa5]{4,}", txt) and len(txt) <= 60:
                            candidate_cn.append((max_sz, txt))
                        elif (
                            re.match(r"^[A-Za-z0-9\s,\.:\-–'\"\(\)]+$", txt)
                            and len(txt.split()) >= 3
                            and len(txt) <= 120
                        ):
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
            if 15 <= len(line_str) <= 100 and re.match(
                r"^[A-Za-z0-9\s,\.:\-–]+$", line_str
            ):
                if len(line_str.split()) >= 3 and not any(
                    kw in line_str.upper()
                    for kw in [
                        "UNIVERSITY",
                        "DISSERTATION",
                        "THESIS",
                        "SCHOOL",
                        "COPYRIGHT",
                    ]
                ):
                    title_en = line_str
                    break

    return title_cn, title_en


def _normalize_chap_num(s: str) -> Optional[int]:
    if not s:
        return None
    cn_map = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
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
    compact = [re.sub(r"\s+", "", text) for text in texts]
    if any(
        re.fullmatch(r"目录|目录[（(]续[）)]|CONTENTS|TABLEOFCONTENTS", t, re.I)
        for t in compact
    ):
        return True
    entries = sum(
        bool(
            re.match(
                r"^(?:第[一二三四五六七八九十0-9]+章|\d+(?:\.\d+)+)\s*[A-Za-z\u4e00-\u9fff]{2}",
                t,
            )
        )
        and is_toc_line(t)
        for t in texts
    )
    prose = sum(len(t) > 70 and bool(re.search(r"[。！？]", t)) for t in texts)
    return entries >= 4 and prose == 0


def join_chapter_prefixes(blocks):
    """OCR PDFs sometimes put the first character 第 in a separate text block."""
    used = set()
    for prefix in blocks:
        if prefix["text"].strip() != "第":
            continue
        a = prefix["bbox"]
        for tail in blocks:
            if id(tail) in used or not re.match(
                r"^[一二三四五六七八九十0-9]+\s*章", tail["text"]
            ):
                continue
            b = tail["bbox"]
            if (
                0 <= b[0] - a[2] <= max(15, prefix["avg_font_size"])
                and abs((a[1] + a[3] - b[1] - b[3]) / 2) < 8
            ):
                prefix.update(
                    text="第" + tail["text"],
                    bbox=(
                        min(a[0], b[0]),
                        min(a[1], b[1]),
                        max(a[2], b[2]),
                        max(a[3], b[3]),
                    ),
                    lines=prefix["lines"] + tail["lines"],
                    last_line_str=tail["last_line_str"],
                )
                used.add(id(tail))
                break
    return [b for b in blocks if id(b) not in used]
