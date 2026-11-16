"""Small constructed cases for parser/task equivalence; no real papers."""

from pathlib import Path
import fitz
from docx import Document

FIXTURES = Path(__file__).parent


def cases(directory):
    for name in ("cross_page.pdf", "ocr_concession.pdf"):
        yield name, FIXTURES / name

    path = directory / "layout.pdf"
    doc = fitz.open()
    for _ in range(3):
        doc.new_page(width=595, height=842)
    for i, lines in enumerate(
        [
            [
                (90, 100, "题目：论文审查方法研究", 18),
                (90, 160, "摘要", 15),
                (90, 200, "本文研究论文审查方法，结果表明该方法具有应用价值。", 12),
            ],
            [
                (90, 100, "第一章 绪论", 16),
                (90, 150, "本章研究文献组织方法，比较不同方案的优点与局限。", 12),
                (90, 210, "1.1 研究问题", 14),
                (90, 260, "我们基于比较结果总结研究问题。", 12),
                (180, 500, "图1.1 方法流程", 11),
            ],
            [
                (90, 100, "第二章 总结", 16),
                (90, 160, "本文研究论文审查方法，结果表明该方法具有应用价值。", 12),
                (90, 600, "参考文献", 15),
                (90, 650, "[1] A. Title[J]. Journal, 2020, 1: 1-9.", 11),
            ],
        ]
    ):
        for x, y, text, size in lines:
            doc[i].insert_text((x, y), text, fontname="china-s", fontsize=size)
        doc[i].insert_text((280, 40), "测试论文", fontname="china-s", fontsize=10)
        doc[i].insert_text((280, 800), str(i + 1), fontsize=10)
    doc[1].draw_rect(fitz.Rect(90, 320, 480, 460))
    doc[1].insert_text((180, 350), "100 200 300", fontsize=9)
    # A tiny embedded bitmap exercises DPI and image bounds without external files.
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8), False)
    pix.clear_with(255)
    doc[1].insert_image(fitz.Rect(100, 370, 220, 440), stream=pix.tobytes("png"))
    doc.save(path)
    doc.close()
    yield path.name, path

    for name, paragraphs in [
        (
            "sections.docx",
            [
                "题目：论文审查方法研究",
                "Title: Thesis Review Methods",
                "摘要",
                "本文研究论文审查方法。实验结果说明该方法有效。",
                "关键词：论文",
                "第一章 绪论",
                "已有方法存在局限，本章提出研究目标。",
                "1.1 方法",
                "如图1.1所示。",
                "图1.1 方法流程",
                "第二章 总结",
                "本文总结论文审查方法。",
                "参考文献",
                "[1] A. Title[J]. Journal, 2020, 1: 1-9.",
            ],
        ),
        (
            "numbered.docx",
            [
                "1 Introduction",
                "We study thesis review.",
                "2 Method",
                "This chapter explains the method.",
                "References",
                "(1) A. Title[J]. Journal, 2020, 1: 1-9.",
            ],
        ),
    ]:
        path = directory / name
        docx = Document()
        for text in paragraphs:
            docx.add_paragraph(text)
        docx.add_table(rows=1, cols=1).cell(0, 0).text = "构造表格内容"
        docx.save(path)
        yield name, path

    yield "blocks", [
        {"id": "b1", "text": "第一章 绪论"},
        {"id": "b2", "text": "我们研究论文审查方法，因此需要构造测试。"},
        {"id": "b3", "text": "第二章 总结"},
        {"id": "b4", "text": "我们研究论文审查方法，因此需要构造测试。"},
        {"id": "b5", "text": "参考文献"},
        {"id": "b6", "text": "[1] A. Title[J]. Journal, 2020, 1: 1-9."},
    ]
