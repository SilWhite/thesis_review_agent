"""Recreate the two small synthetic PDFs; no real thesis data is used."""

from pathlib import Path
import runpy
import fitz

ROOT = Path(__file__).resolve().parents[2]
runpy.run_path(str(ROOT / "tests/integration/test_page_continuity.py"))["create"]()
path = Path(__file__).parent / "ocr_concession.pdf"
doc = fitz.open()
page = doc.new_page(width=600, height=850)
page.insert_text((50, 80), "第一章 绪论", fontname="china-s", fontsize=16)
page.insert_text(
    (50, 140),
    "LLaMA3虽然是一个强大的通用模型，但是其设计侧重英文。",
    fontname="china-s",
    fontsize=12,
)
page.insert_text(
    (50, 165), "因此在特定应用中存在局限。", fontname="china-s", fontsize=12
)
doc.save(path)
doc.close()
print("Created", path)
