"""End-to-end pipeline verification test with real PDF and DOCX files."""

import sys
import time
import tempfile
from pathlib import Path

# Add project root to path
root_dir = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root_dir))

import fitz  # PyMuPDF
import docx  # python-docx
from app.config import Settings
from app.storage import Store
from app.jobs import ReviewService
from app.schemas import ReviewRequest
from app.documents.pdf import build_document_tree_from_pdf
from app.documents.docx import build_document_tree_from_docx


def create_sample_pdf(filepath: Path):
    """Generate a 3-page synthetic PDF with specific test elements."""
    doc = fitz.open()

    # Page 1: Cover & Abstract
    p1 = doc.new_page()
    p1.insert_text(
        (72, 100),
        "题目：基于深度学习的图像分类方法研究",
        fontname="china-s",
        fontsize=18,
    )
    p1.insert_text(
        (72, 140),
        "Title: Research on Image Classification Methods Based on Deep Learning",
        fontsize=14,
    )
    p1.insert_text((72, 200), "摘要", fontname="china-s", fontsize=14)
    p1.insert_text(
        (72, 230),
        "随着人工智能技术的发展，图像分类成为关键基础任务。本文针对这一难题开展研究。我们提出了新网络结构并进行了验证。",
        fontname="china-s",
        fontsize=10.5,
    )

    # Page 2: Chapter 1 & Chapter 2
    p2 = doc.new_page()
    p2.insert_text((72, 80), "第一章 绪论", fontname="china-s", fontsize=15)
    p2.insert_text(
        (72, 120),
        "相关工作如文献[1]和[2]所述，特征提取是核心步骤。如[3-4]所示，多尺度表征非常有效。",
        fontname="china-s",
        fontsize=10.5,
    )
    p2.insert_text((72, 160), "第二章 方法设计", fontname="china-s", fontsize=15)
    p2.insert_text((72, 200), "2.1 模块构建", fontname="china-s", fontsize=12)
    p2.insert_text(
        (72, 230),
        "本章提出动态门控机制。如图 2.1 所示，该机制通过自适应通道权重提升表征力。",
        fontname="china-s",
        fontsize=10.5,
    )
    p2.insert_text(
        (72, 350), "图 2.1 网络整体架构流程图", fontname="china-s", fontsize=10.5
    )

    # Page 3: References
    p3 = doc.new_page()
    p3.insert_text((72, 80), "参考文献", fontname="china-s", fontsize=15)
    p3.insert_text(
        (72, 120),
        "[1] 张三, 李四. 深度学习理论与实践[M]. 北京: 科学出版社, 2021: 10-20.",
        fontname="china-s",
        fontsize=10,
    )
    p3.insert_text(
        (72, 150),
        "[2] 王五. 卷积神经网络进展[J]. 计算机学报, 2022, 45(3): 500-515.",
        fontname="china-s",
        fontsize=10,
    )
    p3.insert_text(
        (72, 180),
        "[3] Lecun Y. Deep learning[J]. Nature, 2015, 521: 436-444.",
        fontsize=10,
    )
    p3.insert_text(
        (72, 210),
        "[4] Vaswani A. Attention is all you need[C]. NeurIPS, 2017: 1-11.",
        fontsize=10,
    )

    doc.save(str(filepath))
    doc.close()
    print(f"  [Created PDF] {filepath} ({filepath.stat().st_size} bytes)")


def create_sample_docx(filepath: Path):
    """Generate a sample DOCX file with headings and tables."""
    doc = docx.Document()
    doc.add_heading("题目：基于深度学习的图像分类方法研究", level=0)
    doc.add_paragraph(
        "Title: Research on Image Classification Methods Based on Deep Learning"
    )
    doc.add_heading("摘要", level=1)
    doc.add_paragraph(
        "随着人工智能技术的发展，图像分类成为关键基础任务。本文针对这一难题开展研究。我们提出了新网络结构并进行了验证。"
    )

    doc.add_heading("第一章 绪论", level=1)
    doc.add_paragraph(
        "相关工作如文献[1]和[2]所述，特征提取是核心步骤。如[3-4]所示，多尺度表征非常有效。"
    )

    doc.add_heading("第二章 方法设计", level=1)
    doc.add_heading("2.1 模块构建", level=2)
    doc.add_paragraph(
        "本章提出动态门控机制。如图 2.1 所示，该机制通过自适应通道权重提升表征力。"
    )
    doc.add_paragraph("图 2.1 网络整体架构流程图")

    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "方法"
    table.cell(0, 1).text = "准确率"
    table.cell(1, 0).text = "本文方法"
    table.cell(1, 1).text = "95.5%"
    doc.add_paragraph("表 2.1 实验结果对比")

    doc.add_heading("参考文献", level=1)
    doc.add_paragraph(
        "[1] 张三, 李四. 深度学习理论与实践[M]. 北京: 科学出版社, 2021: 10-20."
    )
    doc.add_paragraph(
        "[2] 王五. 卷积神经网络进展[J]. 计算机学报, 2022, 45(3): 500-515."
    )
    doc.add_paragraph("[3] Lecun Y. Deep learning[J]. Nature, 2015, 521: 436-444.")
    doc.add_paragraph(
        "[4] Vaswani A. Attention is all you need[C]. NeurIPS, 2017: 1-11."
    )

    doc.save(str(filepath))
    print(f"  [Created DOCX] {filepath} ({filepath.stat().st_size} bytes)")


def test_tree_builders(pdf_path: Path, docx_path: Path):
    """Test PDF and DOCX tree extraction."""
    print("\n--- 测试 1: 文档树构建引擎 (PDF & DOCX) ---")

    # PDF Tree
    pdf_tree = build_document_tree_from_pdf(pdf_path, "sample.pdf")
    assert (
        pdf_tree.total_pages == 3
    ), f"Expected 3 pages in PDF, got {pdf_tree.total_pages}"
    assert (
        "深度学习" in pdf_tree.title_cn
    ), f"Failed to extract title from PDF: {pdf_tree.title_cn}"
    assert (
        len(pdf_tree.chapters) >= 2
    ), f"Expected >= 2 chapters in PDF, got {len(pdf_tree.chapters)}"
    assert (
        len(pdf_tree.references) == 4
    ), f"Expected 4 references in PDF, got {len(pdf_tree.references)}"
    print(
        f"  [PASS] PDF 文档树构建正常：{len(pdf_tree.chapters)} 个章节，{len(pdf_tree.references)} 条参考文献，总页数 {pdf_tree.total_pages}"
    )

    # DOCX Tree
    docx_tree = build_document_tree_from_docx(docx_path, "sample.docx")
    assert (
        "深度学习" in docx_tree.title_cn
    ), f"Failed to extract title from DOCX: {docx_tree.title_cn}"
    assert (
        len(docx_tree.chapters) >= 2
    ), f"Expected >= 2 chapters in DOCX, got {len(docx_tree.chapters)}"
    assert (
        len(docx_tree.references) == 4
    ), f"Expected 4 references in DOCX, got {len(docx_tree.references)}"
    print(
        f"  [PASS] DOCX 文档树构建正常：{len(docx_tree.chapters)} 个章节，{len(docx_tree.references)} 条参考文献"
    )


def test_review_service(pdf_path: Path, tmp_data_dir: Path):
    """Test ReviewService workflow execution with PDF."""
    print("\n--- 测试 2: ReviewService 完整任务提交与审查流程 ---")
    settings = Settings(data_dir=tmp_data_dir)
    store = Store(tmp_data_dir)
    service = ReviewService(store, settings)

    # Save document into store
    doc_meta = store.save_document("test_thesis.pdf", pdf_path.read_bytes())
    doc_id = doc_meta["id"]

    req = ReviewRequest(
        document_ids=[doc_id],
        policy_ids=[],
        model_mode="mock",
        degree="master",
        language="zh-CN",
    )

    state = service.submit(req)
    job_id = state["id"]
    print(f"  [Job Submitted] ID = {job_id}, initial status = {state['status']}")

    # Wait for job completion
    for _ in range(30):
        time.sleep(0.5)
        cur_state = store.read(store.folder("jobs", job_id), "state.json")
        if cur_state["status"] in ("completed", "partial", "failed"):
            break

    print(f"  [Job Finished] Final status = {cur_state['status']}")
    assert cur_state["status"] in (
        "completed",
        "partial",
    ), f"Job failed: {cur_state.get('error')}"

    # Verify report.json and report.md
    job_folder = store.folder("jobs", job_id)
    report_json_path = job_folder / "report.json"
    report_md_path = job_folder / "report.md"

    assert report_json_path.exists(), "report.json was not generated!"
    assert report_md_path.exists(), "report.md was not generated!"

    import json

    report = json.loads(report_json_path.read_text(encoding="utf-8"))
    assert "verdict" in report
    assert "findings" in report
    assert "rule_matrix" in report
    assert (
        len(report["rule_matrix"]) == 37
    ), f"Expected 37 rules in matrix, got {len(report['rule_matrix'])}"

    md_content = report_md_path.read_text(encoding="utf-8")
    assert "毕业论文写作负面清单与格式规范审核报告" in md_content
    assert "各项检查状态" in md_content
    assert "本 demo" not in md_content

    print(
        f"  [PASS] 审查报告校验通过！检出 {len(report['findings'])} 项问题，37项规则矩阵完整。"
    )
    print(f"  [PASS] 报告已落盘至 {job_folder}")


def main():
    print("=" * 60)
    print("开始执行端到端物理真实文件与工作流集成验证")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        pdf_path = tmp_path / "test_thesis.pdf"
        docx_path = tmp_path / "test_thesis.docx"
        store_dir = tmp_path / "store"

        create_sample_pdf(pdf_path)
        create_sample_docx(docx_path)

        test_tree_builders(pdf_path, docx_path)
        test_review_service(pdf_path, store_dir)

    print("\n" + "=" * 60)
    print("端到端物理真实文件与工作流集成验证全部通过！")
    print("=" * 60)


if __name__ == "__main__":
    main()
