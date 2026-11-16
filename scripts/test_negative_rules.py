"""Comprehensive validation suite for the 37 graduate thesis negative items review."""

import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from app.schemas import ReviewRequest
from app.checkers.document_model import (
    ThesisDocumentTree,
    ChapterData,
    ParagraphData,
    FigureData,
    TableData,
    FormulaData,
    ReferenceItem,
    PageData,
)
from app.review import NegativeChecklistReviewer, markdown


def build_mock_test_thesis() -> ThesisDocumentTree:
    """Build a synthetic thesis tree containing targeted violations to test detection."""
    tree = ThesisDocumentTree(filename="测试硕士学位论文.pdf", degree="master", total_pages=15)

    # 1. Title & Abstract
    tree.title_cn = "基于深度学习的图像分类方法研究"
    tree.title_en = "Research on Image Classification Methods Based on Deep Learning"
    tree.abstract_cn = [
        ParagraphData(
            id="p_abs_1",
            text="随着人工智能与计算机视觉技术的迅猛发展，图像分类作为视觉理解领域的核心基础任务，受到学术界与工业界的广泛关注。然而在实际工业复杂场景下，由于目标光照剧烈变化、类内差异巨大、背景强干扰以及噪声普遍存在，现有的传统卷积神经网络在特征抽象提取与跨尺度表征融合方面仍然存在明显的泛化瓶颈与鲁棒性不足问题，难以在高动态多变环境下保持稳定高效的识别精度，亟需发展更为鲁棒的自适应特征提取新架构以满足高精尖工业质检与自动化分析的严苛指标需求。" * 3,  # > 0.6 page (Rule 5)
            page=2,
            ratio_of_page=0.75,
            line_count=25,
        ),
        ParagraphData(
            id="p_abs_2",
            text="本文针对上述核心瓶颈展开深入研究，提出了一系列改进方案，包括动态注意力融合模块和多尺度监督机制。",
            page=2,
        ),
    ]
    tree.abstract_en = [
        ParagraphData(
            id="p_abs_en_1",
            text="With the rapid development of artificial intelligence, image classification has attracted wide attention.",
            page=3,
        )
    ]

    # 2. Chapter 1: Intro & Survey
    ch1 = ChapterData(title="第一章 绪论", level=1, page=4, role="intro")
    p_dup_1 = ParagraphData(
        id="p_dup_1",
        text="本研究在国家自然科学基金重大科研项目的资助下顺利展开实施完成，为后续深入探索奠定了坚实基础。",  # Duplicate sentence part 1 (Rule 2)
        page=4,
    )
    p_we = ParagraphData(
        id="p_we",
        text="我们提出了全新的多尺度卷积拓扑结构，我们发现该结构在大规模公开测试基准上能够显著降低经验分类误差并加速收敛。",  # "我们" (Rule 36)
        page=4,
    )
    p_comma = ParagraphData(
        id="p_comma",
        text="在特征提取阶段，系统首先对原始输入图像进行双线性滤波，随后计算各通道特征均值，接着通过可分离卷积提取高维空间相关性，紧接着送入自注意力多头投影空间完成特征解耦，随后利用门控机制自适应滤除低频噪声，最后通过非线性激活函数输出强化后的判别表征向量并在全连接层完成分类概率打分预测。" * 2,  # 一逗到底 (Rule 35)
        page=4,
    )
    ch1.paragraphs.extend([p_dup_1, p_we, p_comma])

    # 3. Chapter 2: Method
    ch2 = ChapterData(title="第二章 基于动态注意力的特征提取方法", level=1, page=6, role="method")
    # Rule 26: Heading followed immediately by sub-heading
    p_h2 = ParagraphData(id="p_h2", text="2.1 动态注意力模块构建", page=6, is_heading=True, heading_level=2)
    p_dup_2 = ParagraphData(
        id="p_dup_2",
        text="本研究在国家自然科学基金重大科研项目的资助下顺利展开实施完成，为后续深入探索奠定了坚实基础。",  # Duplicate sentence part 2 (Rule 2)
        page=6,
    )
    # Rule 34: Inconsistent font size (14.0pt in body)
    p_bad_font = ParagraphData(id="p_font", text="该模块通过自适应重校准通道响应，大幅提升了模型表征能力。", page=6, font_size=14.0)

    ch2.paragraphs.extend([p_h2, p_dup_2, p_bad_font])

    # Formulas: Rule 12 (un-numbered formula)
    f_unnum = FormulaData(text="y = \\sigma(W x + b)", has_number=False, page=7)
    ch2.formulas.append(f_unnum)

    # Figures: Rule 23 (subfig without main), Rule 24 (unreferenced), Rule 25 (low DPI), Rule 35 (caption period)
    fig_sub = FigureData(num="2.1", caption="图 2.1 (a) 网络浅层特征图输出。", page=7, is_subfig=True, dpi=96.0)
    ch2.figures.append(fig_sub)

    # Table: Rule 22 (font size > body + 1pt)
    tbl_big = TableData(num="2.1", caption="表 2.1 模块参数量与计算开销对比", page=8, font_size=13.5)
    ch2.tables.append(tbl_big)

    # 4. Chapter 3: Conclusion & Summary
    ch3 = ChapterData(title="第三章 全文总结与展望", level=1, page=14, role="summary")
    ch3.paragraphs.append(
        ParagraphData(id="p_c1", text="本文围绕复杂场景下的图像分类任务开展研究，取得了预期的研究成果。", page=14)
    )
    tree.conclusion_chapter = ch3
    tree.conclusion_pages_count = 1.0  # Rule 15: master requires >= 2.0 pages

    tree.chapters.extend([ch1, ch2, ch3])
    tree.all_body_paragraphs = ch1.paragraphs + ch2.paragraphs + ch3.paragraphs

    # Pages for layout checks
    # Page 6 has orphan heading (Rule 28)
    p6_heading = ParagraphData(id="p6_h", text="2.2 损失函数设计", page=6, is_heading=True, heading_level=2)
    tree.pages.append(PageData(page_num=6, width=595.0, height=842.0, paragraphs=[p_h2, p_dup_2, p_bad_font, p6_heading], content_height_ratio=0.85))
    # Page 10 has blank space (Rule 29)
    tree.pages.append(PageData(page_num=10, width=595.0, height=842.0, paragraphs=[ParagraphData(id="p10_1", text="测试文本", page=10)], content_height_ratio=0.35))
    # Page 11 has single line page (Rule 33)
    tree.pages.append(PageData(page_num=11, width=595.0, height=842.0, paragraphs=[ParagraphData(id="p11_1", text="这是从前一章溢出的单独一行文字。", page=11, line_count=1)], content_height_ratio=0.08))

    # Add images for page 7
    tree.pages.append(PageData(page_num=7, width=595.0, height=842.0, images=[fig_sub], content_height_ratio=0.75))

    # References
    # Rule 17 (out of order), Rule 18 (unreferenced), Rule 19 (missing year/pages), Rule 20 (inconsistent format)
    tree.references = [
        ReferenceItem(id_str="1", raw_text="[1] 华罗庚. 高等数学引论[M]. 北京: 科学出版社.", page_num=15),  # missing year (Rule 19)
        ReferenceItem(id_str="3", raw_text="[3] Lecun Y, Bengio Y, Hinton G. Deep learning[J]. Nature, 2015, 521(7553): 436-444.", page_num=15),  # jump from 1 to 3 (Rule 17)
        ReferenceItem(id_str="4", raw_text="[4] Vaswani A. Attention Is All You Need. NIPS, 2017.", page_num=15),  # missing [C] type, unreferenced (Rule 18, 20)
    ]

    tree.all_text = "\n".join(p.text for p in tree.all_body_paragraphs)
    return tree


def test_deterministic_and_clean_cases():
    """Verify deterministic checker on positive, negative, and edge cases."""
    from app.checkers.deterministic_checker import DeterministicChecker
    checker = DeterministicChecker()

    # 1. Completely clean tree
    clean_tree = ThesisDocumentTree(filename="clean.pdf", degree="master", total_pages=50)
    ch1 = ChapterData(title="第一章 绪论", level=1, page=1, role="intro")
    ch1.paragraphs = [
        ParagraphData(id="p1", text="本文提出了一种新颖的方法，在多个基准测试上取得了优异性能。如[1]和[2]所述，特征融合极为关键。如[3-5]所示，自注意力机制广泛应用。", page=1),
        ParagraphData(id="p2", text="图1.1展示了系统整体结构。如表1.1所列，实验指标显著提升。", page=2),
    ]
    ch1.figures = [FigureData(num="1.1", caption="图1.1 总体架构示意图", page=2)]
    ch1.tables = [TableData(num="1.1", caption="表1.1 实验对比结果", page=2)]
    ch1.formulas = [FormulaData(text="E = m c^2", has_number=True, page=2)]
    clean_tree.chapters = [ch1]
    clean_tree.all_body_paragraphs = ch1.paragraphs
    clean_tree.body_text_only = "\n".join(p.text for p in ch1.paragraphs)
    clean_tree.all_text = clean_tree.body_text_only
    clean_tree.references = [
        ReferenceItem(id_str="1", raw_text="[1] 著录者. 文献标题[J]. 刊名, 2020, 1(1): 1-10.", page_num=50),
        ReferenceItem(id_str="2", raw_text="[2] 著录者. 文献标题[J]. 刊名, 2021, 2(2): 11-20.", page_num=50),
        ReferenceItem(id_str="3", raw_text="[3] 著录者. 文献标题[J]. 刊名, 2022, 3(3): 21-30.", page_num=50),
        ReferenceItem(id_str="4", raw_text="[4] 著录者. 文献标题[J]. 刊名, 2023, 4(4): 31-40.", page_num=50),
        ReferenceItem(id_str="5", raw_text="[5] 著录者. 文献标题[J]. 刊名, 2024, 5(5): 41-50.", page_num=50),
    ]

    findings, audits = checker.check_all(clean_tree)
    assert len(findings) == 0, f"Clean tree should have 0 deterministic findings, got: {[f.issue for f in findings]}"
    assert all(a.status == "检查通过" for a in audits), "All clean audits should be 检查通过"
    print("  [PASS] 确定性检查：干净阴性用例全绿放行通过")

    # 2. Test interval citation expansion: [1-3] should cover 1, 2, 3
    test_tree = ThesisDocumentTree(filename="cite.pdf")
    test_tree.all_body_paragraphs = [ParagraphData(id="p1", text="参见相关工作[1-3]的研究。", page=1)]
    test_tree.body_text_only = test_tree.all_body_paragraphs[0].text
    test_tree.references = [
        ReferenceItem(id_str="1", raw_text="[1] A. Title[J]. J, 2020.", page_num=2),
        ReferenceItem(id_str="2", raw_text="[2] B. Title[J]. J, 2021.", page_num=2),
        ReferenceItem(id_str="3", raw_text="[3] C. Title[J]. J, 2022.", page_num=2),
    ]
    f_cite, _ = checker.check_all(test_tree)
    r18_findings = [f for f in f_cite if f.rule_id == 18]
    assert len(r18_findings) == 0, f"References [1], [2], [3] covered by [1-3] should not be flagged as unreferenced! Got: {r18_findings}"
    print("  [PASS] 规则 18：区间引用 [1-3] 展开覆盖断言通过")


def test_degree_and_layout_rules():
    """Verify Rule 15 degree logic (bachelor NA, master 2p, doctor 4p) and layout checks."""
    from app.checkers.layout_checker import LayoutChecker
    checker = LayoutChecker()

    # Bachelor: should be NA
    tree_bachelor = ThesisDocumentTree(filename="b.pdf", degree="bachelor", total_pages=20)
    tree_bachelor.conclusion_chapter = ChapterData(title="结论", level=1, page=19, role="summary")
    tree_bachelor.conclusion_pages_count = 0.5
    f_b, a_b = checker.check_all(tree_bachelor)
    r15_b = next(a for a in a_b if a.rule_id == 15)
    assert r15_b.status == "不适用", f"Bachelor should be NA for Rule 15, got: {r15_b.status}"
    assert not any(f.rule_id == 15 for f in f_b), "Bachelor should have no finding for Rule 15"
    print("  [PASS] 规则 15：本科学位不适用 (NA) 逻辑断言通过")

    # Master: 1.5 pages -> VIOLATION, 2.5 pages -> PASSED
    tree_m1 = ThesisDocumentTree(filename="m.pdf", degree="master", total_pages=30)
    tree_m1.conclusion_chapter = ChapterData(title="结论", level=1, page=28, role="summary")
    tree_m1.conclusion_pages_count = 1.5
    f_m1, _ = checker.check_all(tree_m1)
    assert any(f.rule_id == 15 for f in f_m1), "Master with 1.5 pages conclusion should trigger Rule 15"

    tree_m2 = ThesisDocumentTree(filename="m.pdf", degree="master", total_pages=30)
    tree_m2.conclusion_chapter = ChapterData(title="结论", level=1, page=28, role="summary")
    tree_m2.conclusion_pages_count = 2.5
    f_m2, _ = checker.check_all(tree_m2)
    assert not any(f.rule_id == 15 for f in f_m2), "Master with 2.5 pages conclusion should pass Rule 15"
    print("  [PASS] 规则 15：硕士学位 2 页阈值判别断言通过")

    # Doctor: 3.0 pages -> VIOLATION, 4.5 pages -> PASSED
    tree_d1 = ThesisDocumentTree(filename="d.pdf", degree="doctor", total_pages=100)
    tree_d1.conclusion_chapter = ChapterData(title="总结与展望", level=1, page=95, role="summary")
    tree_d1.conclusion_pages_count = 3.0
    f_d1, _ = checker.check_all(tree_d1)
    assert any(f.rule_id == 15 for f in f_d1), "Doctor with 3.0 pages conclusion should trigger Rule 15"

    tree_d2 = ThesisDocumentTree(filename="d.pdf", degree="doctor", total_pages=100)
    tree_d2.conclusion_chapter = ChapterData(title="总结与展望", level=1, page=95, role="summary")
    tree_d2.conclusion_pages_count = 4.5
    f_d2, _ = checker.check_all(tree_d2)
    assert not any(f.rule_id == 15 for f in f_d2), "Doctor with 4.5 pages conclusion should pass Rule 15"
    print("  [PASS] 规则 15：博士学位 4 页阈值判别断言通过")


def test_evidence_validation():
    """Verify validate_evidence does not falsely pin everything to block 0."""
    from app.review import validate_evidence
    from app.schemas import Assessment, Finding, CheckStatus

    blocks = [
        {"id": "b_intro", "text": "这是论文第一段绪论背景说明。", "location": "第 1 页"},
        {"id": "b_method", "text": "这是论文方法论详细公式推导段落。", "location": "第 5 页"},
    ]

    # Finding with quote in method block
    f1 = Finding(rule_id=12, issue="公式缺编号", quote="详细公式推导段落", suggestion="修改")
    # Finding with unmatchable global quote
    f2 = Finding(rule_id=3, issue="题目过长", quote="基于长长长题目的研究", suggestion="精简")

    mock_assessment = Assessment(
        verdict="需修改",
        summary="测试",
        findings=[f1, f2],
        rule_matrix=[],
        priority_actions=[],
    )

    validated = validate_evidence(mock_assessment, blocks)
    assert validated[0].block_id == "b_method", f"f1 should match b_method, got {validated[0].block_id}"
    assert validated[1].block_id == "", f"f2 should not be forced to b_intro! Got {validated[1].block_id}"
    assert validated[1].status == "pending_verification", f"f2 status should be pending_verification, got {validated[1].status}"
    print("  [PASS] 证据回溯与段落定位增强：杜绝第 1 段强制误绑断言通过")


def main():
    print("=" * 60)
    print("开始执行毕业论文 37 项负面清单与格式规范全自动核查测试")
    print("=" * 60)

    print("\n--- 阶段 1：专项单元断言测试 ---")
    test_deterministic_and_clean_cases()
    test_degree_and_layout_rules()
    test_evidence_validation()

    print("\n--- 阶段 2：全真合成论文端到端综合评估 ---")
    tree = build_mock_test_thesis()
    reviewer = NegativeChecklistReviewer()
    req = ReviewRequest(document_ids=["doc_1"], model_mode="mock", degree="master")

    # Run assessment
    blocks = [{"id": p.id, "text": p.text, "filename": tree.filename, "location": f"物理页 {p.page}"} for p in tree.all_body_paragraphs]
    assessment = reviewer.assess(req, blocks, policies=[], tree=tree)

    print(f"\n[总体判定]：{assessment.verdict}")
    print(f"[核查摘要]：{assessment.summary}")
    print(f"[检出违规总数]：{len(assessment.findings)} 项\n")

    # Verify all 37 rules are accounted for in matrix
    assert len(assessment.rule_matrix) == 37, f"Rule matrix must contain exactly 37 rules, got {len(assessment.rule_matrix)}"
    matrix_ids = {item.rule_id for item in assessment.rule_matrix}
    assert matrix_ids == set(range(2, 39)), f"Rule IDs must be 2 to 38, got: {matrix_ids}"
    print("  [PASS] 37 项负面规则矩阵覆盖完整性 (Rule 2~38) 断言通过")

    # Rule Audit matrix summary
    print("-" * 60)
    print("37 项规则审计状态矩阵统计：")
    print("-" * 60)
    status_counts = {}
    for item in assessment.rule_matrix:
        status_counts[item.status] = status_counts.get(item.status, 0) + 1
    for st, count in status_counts.items():
        print(f"  - {st}: {count} 项")

    # Verify Markdown generation
    report_dict = dict(
        assessment.model_dump(),
        mode="mock",
        model_name="deterministic-engine-v2",
        generated_at="2026-11-10 15:40:00",
        findings=[
            dict(
                f.model_dump(),
                filename=tree.filename,
                location=f"物理页 {f.locations[0].page if f.locations else 1}",
            )
            for f in assessment.findings
        ],
        limitations=["本测试为规则完备性自动化校验。"],
    )
    md_content = markdown(report_dict)
    assert len(md_content) > 500
    assert "恭喜！在已完成检查的规则范围内" not in md_content
    print("\n[OK] 纯违规项汇总流 Markdown 报告生成正常，长度:", len(md_content), "字符")
    print("=" * 60)
    print("规则编号覆盖及所列专项断言完成；这不代表 37 条规则均已验证准确。")
    print("=" * 60)


if __name__ == "__main__":
    main()

