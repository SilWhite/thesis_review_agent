"""CPU text extraction with stable source locations; no implicit cloud OCR."""

from docx import Document
from pypdf import PdfReader


def sanitize_unicode(text: str) -> str:
    if not isinstance(text, str):
        return text
    try:
        text = text.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
    except Exception:
        pass
    return text.encode("utf-8", "replace").decode("utf-8")


def parse_document(store, identifier):
    folder = store.folder("documents", identifier)
    meta = store.read(folder, "document.json")
    source = folder / ("source" + meta["suffix"])
    blocks, warnings = [], []

    def append(text, location):
        text = sanitize_unicode(text)
        if text.strip():
            blocks.append(
                dict(
                    id=f"{identifier}:b{len(blocks)+1}",
                    document_id=identifier,
                    filename=meta["filename"],
                    location=location,
                    text=text.strip(),
                )
            )

    if meta["suffix"] == ".pdf":
        for number, page in enumerate(PdfReader(source).pages, 1):
            text = page.extract_text() or ""
            append(text, f"PDF 物理页 {number}")
            if not text.strip():
                warnings.append(
                    f'{meta["filename"]} 第 {number} 页无可提取文本（未配置 OCR）。'
                )
    elif meta["suffix"] == ".docx":
        doc = Document(source)
        for number, paragraph in enumerate(doc.paragraphs, 1):
            append(paragraph.text, f"段落 {number}")
        for number, table in enumerate(doc.tables, 1):
            for row_num, row in enumerate(table.rows, 1):
                append(
                    " | ".join(cell.text for cell in row.cells),
                    f"表格 {number} / 行 {row_num}",
                )
        warnings.append(
            f'{meta["filename"]}：当前仅提取正文段落和表格，未审图片、公式、页眉页脚和脚注。'
        )
    elif meta["suffix"] == ".txt":
        for number, paragraph in enumerate(
            source.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            append(paragraph, f"文本行 {number}")
    else:
        warnings.append(
            f'{meta["filename"]}：图片已保存，当前未配置 OCR／视觉解析，不纳入文本评审。'
        )
    if meta["suffix"] == ".pdf":
        warnings.append(f'{meta["filename"]}：仅评审提取文本，未验证图像及表格版面。')
    return blocks, warnings
