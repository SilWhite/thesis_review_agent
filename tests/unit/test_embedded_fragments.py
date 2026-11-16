import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.documents.regions import join_inline_fragments


def span(text, box):
    return {"text": text, "bbox": box, "size": 12, "font": "test"}


def block(lines, box):
    return {
        "text": " ".join(x[0] for x in lines),
        "bbox": box,
        "lines": [{"bbox": b, "spans": [span(t, b)]} for t, b in lines],
        "avg_font_size": 12,
        "last_line_str": lines[-1][0],
    }


a = block(
    [
        ("虽然是", (50, 100, 250, 112)),
        ("其设计侧重英文。", (50, 125, 490, 137)),
        ("因此有局限。", (50, 150, 490, 162)),
    ],
    (50, 100, 490, 162),
)
b = block([("一个强大的模型，但是", (260, 100, 490, 112))], (260, 100, 490, 112))
merged = join_inline_fragments([b, a])
assert len(merged) == 1 and "虽然是一个强大的模型,但是" in merged[0]["text"]
a = block(
    [
        ("正常正文", (50, 100, 250, 112)),
        ("第二行正文", (50, 125, 490, 137)),
        ("第三行正文", (50, 150, 490, 162)),
    ],
    (50, 100, 490, 162),
)
b = block([("表内文字", (260, 100, 490, 112))], (260, 100, 490, 112))
b["in_table"] = True
assert len(join_inline_fragments([b, a])) == 2
print("Embedded OCR fragment recovery and table exclusion passed")

from app.documents import build_document_tree_from_pdf

t = build_document_tree_from_pdf(
    (Path(__file__).resolve().parents[1] / "fixtures/ocr_concession.pdf"),
    "ocr_concession.pdf",
)
paragraphs = [p for p in t.pages[0].paragraphs if "LLaMA3虽然是" in p.text]
assert (
    paragraphs
    and "一个强大的通用模型" in paragraphs[0].text
    and "但" in paragraphs[0].text
)
print("Real OCR concession retains both clauses")
