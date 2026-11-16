"""Focused regression tests for known false passes and missed findings."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.checkers.deterministic_checker import DeterministicChecker, _expand_citations_in_text
from app.checkers.layout_checker import LayoutChecker
from app.checkers.semantic_checker import SemanticChecker, _parse_model_response
from app.checkers.tree_builder import _is_back_matter_heading, _is_keyword_label
from app.checkers.document_model import ChapterData, ParagraphData, ThesisDocumentTree, FormulaData, PageData, FigureData, ReferenceItem
from app.schemas import CheckStatus
from app.schemas import RuleAuditItem
from app.workflow import _review_is_partial
from app.review import markdown
from app.review import NegativeChecklistReviewer
from app.schemas import ReviewRequest


def main():
    assert _parse_model_response('```json\n{"findings": []}\n```') == {'findings': []}
    audit = RuleAuditItem(rule_id=13, rule_name='公式符号', category='语义核查', status=CheckStatus.UNCERTAIN.value, note='需要复核')
    assert _review_is_partial([], 'local', [audit])
    assert not _review_is_partial([], 'local', [])
    report_md = markdown({'rule_matrix': [audit.model_dump()], 'findings': []})
    assert '无法可靠判断' in report_md and '需要复核' in report_md
    assert _is_back_matter_heading('致 谢') and _is_back_matter_heading('附录 A')
    assert not _is_back_matter_heading('更详细的结果可以参见附录A。')
    assert not _is_back_matter_heading('本文对参与测试的同学表示感谢。')
    assert _is_keyword_label('关键词') and _is_keyword_label('Key words: research')
    assert not _is_keyword_label('本文提出一种关键词识别方法。')
    assert not _is_keyword_label('We extract keywords from documents.')
    assert _expand_citations_in_text('［1， 3 - 5］') == [1, 3, 4, 5]
    assert _expand_citations_in_text('[1 2 4 - 5]') == [1, 2, 4, 5]
    checker = DeterministicChecker()
    phrase = 'The quick brown fox jumps over the lazy dog every morning'
    tree = ThesisDocumentTree(filename='test', all_body_paragraphs=[
        ParagraphData(id='a', page=1, text=phrase),
        ParagraphData(id='b', page=1, text=phrase),
    ])
    findings, _ = checker._check_rule_2_duplicate_sentences(tree)
    assert findings and findings[0].locations[0].page == findings[0].locations[1].page
    tree.all_body_paragraphs = [ParagraphData(id='a', page=1, text=phrase + '. ' + phrase + '.')]
    assert checker._check_rule_2_duplicate_sentences(tree)[0]
    tree.all_body_paragraphs = [ParagraphData(id=str(i), page=1, text='这个自然段文字很短。') for i in range(11)]
    assert LayoutChecker()._check_rule_31_short_paragraphs(tree)[0]
    tree.chapters = [ChapterData(title='第二章 方法', level=1, page=2, role='method', paragraphs=tree.all_body_paragraphs)]
    _, audits = SemanticChecker()._run_task_3_core_chapters(tree, 'local')
    statuses = {a.rule_id: a.status for a in audits}
    assert statuses[10] == statuses[11] == CheckStatus.FAILED.value
    assert statuses[37] == CheckStatus.FAILED.value
    # Generic context and familiar metric names must not hide undefined symbols.
    tree.chapters[0].formulas = [FormulaData(text='Accuracy = TP / (TP + FN)', has_number=True,
                                             context_text='该指标为模型的性能。')]
    findings, _ = SemanticChecker()._run_task_4_formula_symbols(tree, 'mock')
    assert findings and 'TP' in findings[0].issue and 'FN' in findings[0].issue
    # Search all pages, including abstract and acknowledgements, without duplicates.
    outside = ParagraphData(id='outside', page=1, text='我们感谢所有参与者。')
    tree.pages = [PageData(page_num=1, width=595, height=842, paragraphs=[outside])]
    tree.abstract_cn = [outside]
    findings, _ = checker._check_rule_36_we_usage(tree)
    assert len(findings) == 1 and findings[0].locations[0].page == 1
    # A short copied chapter summary can be hidden within a longer conclusion.
    copied = '本文提出一种方法用于提升图像分类任务的准确率和稳定性。'
    ch = ChapterData(title='方法', level=1, page=2, summary_text=copied)
    conclusion = ChapterData(title='总结', level=1, page=5, role='summary',
                             paragraphs=[ParagraphData(id='c', page=5, text='其他不同的文字。' * 20 + copied)])
    tree = ThesisDocumentTree(filename='t', chapters=[ch, conclusion], conclusion_chapter=conclusion,
                              abstract_cn=[ParagraphData(id='a', page=1, text='完全不同的摘要。' * 5)])
    findings, _ = SemanticChecker()._run_task_5_conclusion_conjunctions(tree, 'mock')
    assert any(f.rule_id == 16 and f.quote for f in findings)
    tree.abstract_cn = [ParagraphData(id='a', page=1, text='摘要其他文字。' * 20 + copied)]
    findings, _ = SemanticChecker()._run_task_5_conclusion_conjunctions(tree, 'mock')
    assert any(f.rule_id == 14 and f.quote for f in findings)
    # A figure numbered 11 does not cite figure 1.1.
    ch = ChapterData(title='方法', level=1, page=2,
                     figures=[FigureData(num='1.1', caption='图1.1 流程', page=2)])
    tree = ThesisDocumentTree(filename='t', chapters=[ch], body_text_only='如图11所示。')
    assert checker._check_rule_24_figures_tables_unreferenced(tree)[0]
    tree.references = [ReferenceItem(id_str='1', raw_text='[1] 文章[J].'),
                       ReferenceItem(id_str='2', raw_text='[2] 另一篇文章.')]
    assert checker._check_rule_20_reference_inconsistent_format(tree)[0]
    # Broken section extraction must not turn an absorbed abstract into findings.
    broken = ThesisDocumentTree(filename='broken.pdf', total_pages=20,
        abstract_cn=[ParagraphData(id='bad', page=1, text='摘要和正文混在一起。' * 100)])
    report = NegativeChecklistReviewer().assess(ReviewRequest(document_ids=['test'], model_mode='mock'), [], [], tree=broken)
    assert not report.findings and report.verdict == '信息不足'
    assert len(report.rule_matrix) == 37
    print('Regression tests passed')


if __name__ == '__main__':
    main()
