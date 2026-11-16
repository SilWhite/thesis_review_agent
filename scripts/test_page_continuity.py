"""Actual PDF regression: abstract, reference and formula explanation cross a page."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fitz
from app.checkers import build_document_tree_from_pdf, DeterministicChecker, SemanticChecker

path = Path('tests/fixtures/cross_page.pdf')


def create():
    doc = fitz.open()
    pages = [doc.new_page(width=595, height=842) for _ in range(5)]
    # Page objects must be fetched after page creation (MuPDF invalidates them).
    def put(index, x, y, text, size=12, chinese=True):
        doc[index].insert_text((x, y), text, fontsize=size, fontname='china-s' if chinese else 'helv')
    for i in range(5):
        put(i, 270, 40, '测试论文', 10.5)
        put(i, 295, 800, str(i + 1), 10.5, False)
    put(0, 270, 100, '摘要', 15)
    put(0, 190, 130, '跨页测试论文', 16)
    put(0, 114, 710, '本文研究关键词识别方法，提出了能够检查参考文献和公式的系统。')
    put(0, 90, 735, '实验结果显示，该方法能够保留跨页段落，在下一页继续说明具体方法')
    put(1, 90, 70, '系统在复杂文档中仍然可以读取完整内容。')
    put(1, 90, 115, '关键词：论文；跨页')
    put(1, 260, 180, 'Abstract', 15, False)
    put(1, 90, 220, 'We develop a system for reviewing theses.', 12, False)
    put(1, 90, 260, 'Keywords: thesis, review', 12, False)
    put(2, 90, 100, '第一章 研究方法', 15)
    put(2, 114, 145, '本章介绍一种论文审查方法。')
    put(2, 200, 240, 'q = a + b', 12, False)
    put(2, 90, 275, '其中 a 表示权重，b 表示偏差。')
    put(2, 200, 350, 'w = m + n                 (1.2)', 12, False)
    put(2, 200, 735, 'x = y + z                 (1.1)', 12, False)
    put(3, 90, 70, '式中，y 表示输入数值，z 表示偏移量。')
    put(3, 90, 600, '参考文献', 15)
    put(3, 90, 735, '[1] Zhang A. Complete reference[J]. Journal,', 10.5, False)
    put(4, 90, 70, '2020, 3(2): 1-8.', 10.5, False)
    put(4, 90, 115, '[2] Li B. Missing year[J]. Journal: 2-4.', 10.5, False)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    doc.close()
    print('Created', path)


def test():
    tree = build_document_tree_from_pdf(path, path.name)
    assert len(tree.abstract_cn) == 1, [(p.text, p.source_pages) for p in tree.abstract_cn]
    assert tree.abstract_cn[0].source_pages == [1, 2]
    assert tree.abstract_cn[0].text.endswith('系统在复杂文档中仍然可以读取完整内容。')
    assert len(tree.references) == 2
    assert any('We develop a system' in p.text for p in tree.abstract_en)
    assert tree.references[0].source_pages == [4, 5]
    assert '2020' in tree.references[0].raw_text and '1-8' in tree.references[0].raw_text
    det = DeterministicChecker()
    findings, _ = det._check_rule_19_reference_incomplete(tree)
    assert [f.block_id for f in findings] == ['ref_2'], [f.model_dump() for f in findings]
    numbered = [f for ch in tree.chapters for f in ch.formulas if f.num_str == '1.1']
    assert len(numbered) == 1 and 'y 表示' in numbered[0].definition_context
    findings, _ = det._check_rule_12_formula_number(tree)
    assert len(findings) == 1 and 'q' in findings[0].quote, [f.quote for f in findings]
    findings, _ = SemanticChecker()._run_task_4_formula_symbols(tree, 'mock')
    assert len(findings) == 1 and 'm' in findings[0].issue and 'n' in findings[0].issue
    print('Cross-page PDF regression passed')


if __name__ == '__main__':
    create() if '--create' in sys.argv else test()
