import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.documents.structure import (
    caption_match,
    heading_layout,
    split_reference_blocks,
)
from app.review.checks.citations import references
from app.documents.models import (
    ThesisDocumentTree,
    ChapterData,
    FigureData,
    ReferenceItem,
)
from app.review.checks.deterministic import DeterministicChecker
from app.documents import build_document_tree_from_docx
from docx import Document
import tempfile

checker = DeterministicChecker()
for text in [
    "图3.4 所示。BraTS-2021是一项挑战。",
    "图2-10所示，下面是分析。",
    "表3-3 的跨模型实验结果显示很强的效果。",
    "图4-3展示了滤波器的接受范围。",
]:
    assert not caption_match(text), text
for text in [
    "Figure 3.1 shows results.",
    "Table 4.2 summarizes the results.",
    "Figure 3.1 illustrates the model.",
    "Table 4.2 Results show a clear gain.",
]:
    assert not caption_match(text), text
for text in [
    "图3.1为各方法的实验结果。",
    "表3.1为不同模型的性能对比。",
    "图3.1的结果如下。",
    "图3.1示意了整体框架。",
]:
    assert not caption_match(text), text
for text in [
    "图3.4 数据集中的图像示例",
    "图4-3 不同可解释性学习方法的神经元激活图。以IoU为指标。",
    "表5.1 不同方法的比较",
]:
    assert caption_match(text), text
assert not heading_layout(
    "第二章介绍基础知识", (90, 100, 490, 120), 12, "SimSun", 12, 600
)
assert heading_layout("第二章 基础知识", (170, 100, 430, 125), 15, "SimHei", 12, 600)
for text in ["如图3.1所示。", "如图3-1所示。", "Fig. 3.1 shows results."]:
    assert "3.1" in references(text)["figure"], text
assert "3.1" not in references("见图3.10。")["figure"]
assert references("图3.1–3.3及图4.2。")["figure"] >= {"3.1", "3.2", "3.3", "4.2"}
mixed = references("图3.1，表4.2。")
assert mixed["figure"] == {"3.1"} and mixed["table"] == {"4.2"}
mixed_tree = ThesisDocumentTree(
    "test",
    body_text_only="图3.1，表4.2。",
    chapters=[
        ChapterData("第三章", 1, 1, figures=[FigureData("4.2", "图4.2 未引用", 1)])
    ],
)
assert len(checker._check_rule_24_figures_tables_unreferenced(mixed_tree)[0]) == 1
for number in ["3·1", "3．1", "3－1"]:
    for cited in [False, True]:
        with tempfile.TemporaryDirectory() as directory:
            doc = Document()
            doc.add_paragraph("第一章 绪论")
            doc.add_paragraph(
                "Figure 3.1 shows the results."
                if cited
                else "This paragraph describes results."
            )
            doc.add_paragraph("Figure " + number + " Experimental results")
            path = Path(directory) / "test.docx"
            doc.save(path)
            tree = build_document_tree_from_docx(path, path.name)
            assert len(tree.chapters[0].figures) == 1
            assert len(
                checker._check_rule_24_figures_tables_unreferenced(tree)[0]
            ) == int(not cited), number
for body, expected in [("正文如图3.1所示。", 0), ("正文只有实验结果。", 1)]:
    fig = FigureData("3.1", "图3.1 实验结果", 1)
    tree = ThesisDocumentTree(
        "test",
        body_text_only=body,
        chapters=[ChapterData("第三章", 1, 1, figures=[fig, fig])],
    )
    assert len(checker._check_rule_24_figures_tables_unreferenced(tree)[0]) == expected
for text in [
    "[1] A. Title[J]. Source, 2022, 43(Supplement_2): ehac544.177.",
    "[1] A. Title[J]. CoRR, 2014, abs/1409.1556.",
    "[1] A. Title[J]. Journal, 2024, 3: 12-18.",
]:
    tree = ThesisDocumentTree("test", references=[ReferenceItem("1", text)])
    assert not checker._check_rule_19_reference_incomplete(tree)[0], text
for text in ["[1] A. Title[J]. Journal, 2024.", "[1] A. Title[J]. Journal, 3: 12-18."]:
    assert checker._check_rule_19_reference_incomplete(
        ThesisDocumentTree("test", references=[ReferenceItem("1", text)])
    )[0]
for first, second in [("[1]", "[2]"), ("［1］", "［2］"), ("1.", "2."), ("(1)", "(2)")]:
    lines = [
        {
            "bbox": (70, 100 + i * 20, 500, 115 + i * 20),
            "spans": [{"text": prefix + " Author. Title[J]. Journal, 2020."}],
        }
        for i, prefix in enumerate([first, second])
    ]
    assert (
        len(
            split_reference_blocks(
                [{"type": 0, "lines": lines, "bbox": (70, 100, 500, 135)}]
            )
        )
        == 2
    )
    with tempfile.TemporaryDirectory() as directory:
        doc = Document()
        doc.add_paragraph("第一章 绪论")
        doc.add_paragraph("正文内容。")
        doc.add_paragraph("参考文献")
        for prefix in [first, second]:
            doc.add_paragraph(prefix + " Author. Title[J]. Journal, 2020, 3: 1-8.")
        path = Path(directory) / "refs.docx"
        doc.save(path)
        tree = build_document_tree_from_docx(path, path.name)
        assert [r.id_str for r in tree.references] == ["1", "2"], (
            first,
            tree.references,
        )
print(
    "Roadmap/caption/citation-range/reference-locator positive and negative tests passed"
)
