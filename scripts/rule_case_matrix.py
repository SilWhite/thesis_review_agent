"""Labeled, small, hand-constructed rule checks; save every result, including misses."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.checkers.document_model import (ThesisDocumentTree as Tree, ChapterData as Chapter,
    ParagraphData as Para, ReferenceItem as Ref, FigureData as Fig, TableData as Table,
    FormulaData as Formula, PageData as Page)
from app.checkers import DeterministicChecker, LayoutChecker, SemanticChecker

D, L, S = DeterministicChecker(), LayoutChecker(), SemanticChecker()


def p(text='普通正文内容用于测试。', **kw):
    return Para(id=kw.pop('id', 'p'), page=kw.pop('page', 1), text=text, **kw)


def tree(**kw):
    return Tree(filename='case.pdf', **kw)


def chapter(**kw):
    return Chapter(title='第二章 方法', level=1, page=1, **kw)


cases = []
def add(rule, name, expected, checker, t):
    cases.append((rule, name, expected, checker, t))

dup = '这是一个用于检查完全重复内容的测试句子而且长度足够。'
for flag in (False, True):
    add(2, 'same_page_' + str(flag), flag, D._check_rule_2_duplicate_sentences,
        tree(all_body_paragraphs=[p(dup, id='a'), p(dup if flag else '这段文字与之前的句子含义和内容都完全不同。', id='b')]))
    add(5, 'abstract_ratio_' + str(flag), flag, L._check_rule_5_abstract_first_para,
        tree(abstract_cn=[p('摘要开头。', ratio_of_page=.61 if flag else .59)]))
    add(12, 'formula_number_' + str(flag), flag, D._check_rule_12_formula_number,
        tree(chapters=[chapter(formulas=[Formula(text='y=x+1', has_number=not flag)])]))
    conclusion = chapter(role='summary')
    add(15, 'master_pages_' + str(flag), flag, L._check_rule_15_conclusion_length,
        tree(degree='master', conclusion_chapter=conclusion, conclusion_pages_count=1.5 if flag else 2.5))
    refs = [Ref(id_str=str(i), raw_text=f'[{i}] 作者. 标题[J]. 期刊, 2020: 1-10.') for i in ([1, 3] if flag else [1, 2])]
    add(17, 'reference_order_' + str(flag), flag, D._check_rule_17_reference_ordering,
        tree(references=refs, body_text_only='参考文献[1][2][3]。'))
    refs = [Ref(id_str=str(i), raw_text=f'[{i}] 作者. 标题[J]. 期刊, 2020: 1-10.') for i in (1, 2)]
    add(18, 'reference_unused_' + str(flag), flag, D._check_rule_18_reference_unreferenced,
        tree(references=refs, body_text_only='已有研究[1]。' + ('' if flag else '另见[2]。')))
    add(19, 'reference_year_' + str(flag), flag, D._check_rule_19_reference_incomplete,
        tree(references=[Ref(id_str='1', raw_text='[1] 作者. 标题[J]. 期刊' + ('.' if flag else ', 2020: 1-10.'))]))
    refs = [Ref(id_str=str(i), raw_text=f'[{i}] 作者. 标题[J]. 期刊, 2020: 1-10.') for i in range(1, 6)]
    if flag: refs[-1].raw_text = '[5] 作者. 标题. 期刊, 2020: 1-10.'
    add(20, 'reference_format_' + str(flag), flag, D._check_rule_20_reference_inconsistent_format, tree(references=refs))
    add(22, 'table_font_' + str(flag), flag, L._check_rule_22_figure_font_size,
        tree(all_body_paragraphs=[p(font_size=10.5)], chapters=[chapter(tables=[Table(num='1.1', caption='表1.1', page=1, font_size=14 if flag else 10.5)])]))
    add(23, 'subfigure_' + str(flag), flag, L._check_rule_23_missing_main_caption,
        tree(chapters=[chapter(figures=[Fig(num='1.1', caption='图1.1(a) 图片', page=1, is_subfig=True)] + ([] if flag else [Fig(num='1.1', caption='图1.1 总图', page=1)]))]))
    add(24, 'figure_reference_' + str(flag), flag, D._check_rule_24_figures_tables_unreferenced,
        tree(body_text_only='实验结果如图1-1所示。' if not flag else '实验结果如下。', chapters=[chapter(figures=[Fig(num='1.1', caption='图1.1 结果', page=1)])]))
    add(25, 'image_dpi_' + str(flag), flag, L._check_rule_25_image_dpi_blur,
        tree(pages=[Page(page_num=1, width=595, height=842, images=[Fig(num='1', caption='', page=1, bbox=(0,0,200,100), dpi=90 if flag else 300)])]))
    add(26, 'subheading_' + str(flag), flag, L._check_rule_26_heading_transition,
        tree(all_body_paragraphs=[p('2.1 方法', id='h', is_heading=True, heading_level=2)] + ([] if flag else [p('本节介绍方法。', id='body')]) + [p('2.1.1 模型', id='sub', is_heading=True, heading_level=3)]))
    add(27, 'caption_after_heading_' + str(flag), flag, L._check_rule_27_heading_followed_by_figure,
        tree(all_body_paragraphs=[p('2.1 方法', id='h', is_heading=True, heading_level=2)] + ([] if flag else [p('如图所示。', id='body')]) + [p('图2-1 系统架构', id='fig', is_caption=True)]))
    add(28, 'heading_last_' + str(flag), flag, L._check_rule_28_orphan_heading,
        tree(pages=[Page(page_num=1, width=595, height=842, paragraphs=[p('2.1 方法', is_heading=flag, heading_level=2)])]))
    add(30, 'paragraph_ratio_' + str(flag), flag, L._check_rule_30_long_paragraph,
        tree(all_body_paragraphs=[p('一段文字。', ratio_of_page=.61 if flag else .59)]))
    add(31, 'short_paragraphs_' + str(flag), flag, L._check_rule_31_short_paragraphs,
        tree(all_body_paragraphs=[p('这是一段较短的文字。', id=str(i)) for i in range(11 if flag else 10)]))
    add(32, 'orphan_character_' + str(flag), flag, L._check_rule_32_orphan_character,
        tree(all_body_paragraphs=[p('测试正文' * 10, line_count=2, last_line_text='字' if flag else '末行有若干文字')]))
    add(33, 'single_line_page_' + str(flag), flag, L._check_rule_33_single_line_page,
        tree(pages=[Page(page_num=1, width=595, height=842, paragraphs=[p(line_count=1)], images=[] if flag else [Fig(num='1',caption='',page=1)])]))
    add(34, 'body_font_' + str(flag), flag, L._check_rule_34_inconsistent_body_font,
        tree(all_body_paragraphs=[p('正常正文' * 12, id='a', font_size=10.5), p('另一段正文' * 12, id='b', font_size=14 if flag else 10.5)]))
    add(35, 'caption_punctuation_' + str(flag), flag, D._check_rule_35_punctuation_abuse,
        tree(chapters=[chapter(figures=[Fig(num='1.1', caption='图1.1 系统架构' + ('。' if flag else ''), page=1)])]))
    add(36, 'we_' + str(flag), flag, D._check_rule_36_we_usage,
        tree(all_body_paragraphs=[p('我们提出了新方法。' if flag else '本文提出了新方法。')]))


# Semantic and layout checks that require several related fields.
for flag in (False, True):
    ending = '本研究提出了方法。' if flag else '研究结果表明该方法有效。该成果具有应用价值。'
    add(6, 'abstract_ending_' + str(flag), flag, lambda t: S._run_task_1_bilingual_abstract(t, 'mock'), tree(abstract_cn=[p(ending)]))
    survey = ('张三等人提出方法。李四等人提出方法。王五等人提出方法。赵六等人提出方法。'
              + ('' if flag else '现有方法可分类比较其不足之处。'))
    intro = Chapter(title='第一章 绪论', level=1, page=1, role='intro', paragraphs=[p(survey)])
    add(7, 'survey_list_' + str(flag), flag, lambda t: S._run_task_2_intro_survey(t, 'mock'), tree(chapters=[intro]))
    f = Formula(text='z = x + y', has_number=True, context_text='' if flag else '式中 z 表示输出，x 表示输入，y 表示偏差。')
    add(13, 'symbol_explanation_' + str(flag), flag, lambda t: S._run_task_4_formula_symbols(t, 'mock'), tree(chapters=[chapter(formulas=[f])]))
    abstract = '本文针对图像识别设计卷积网络并在实验中提高分类准确率。'
    summary = abstract if flag else '本章介绍了系统的运行环境和部署方式。'
    ch = chapter(paragraphs=[p('本章小结', is_heading=True, heading_level=2), p(summary, id='summary')], summary_text=summary)
    add(14, 'chapter_summary_copy_' + str(flag), flag, lambda t: S._run_task_5_conclusion_conjunctions(t, 'mock'), tree(abstract_cn=[p(abstract)], chapters=[ch]))
    conclusion = Chapter(title='总结', level=1, page=5, role='summary', paragraphs=[p(abstract if flag else '未来工作可以研究其他任务。')])
    add(16, 'conclusion_copy_' + str(flag), flag, lambda t: S._run_task_5_conclusion_conjunctions(t, 'mock'), tree(abstract_cn=[p(abstract)], conclusion_chapter=conclusion))
    add(21, 'figure_english_' + str(flag), flag, lambda t: S._run_task_5_conclusion_conjunctions(t, 'mock'),
        tree(chapters=[chapter(figures=[Fig(num='1.1', caption='图1.1 ' + ('System Architecture' if flag else '系统架构'), page=1)])]))
    pages = [Page(page_num=1, width=595, height=842, content_height_ratio=.3 if flag else .8, paragraphs=[p()]),
             Page(page_num=2, width=595, height=842, content_height_ratio=.8, paragraphs=[p(page=2)])]
    ch = chapter(end_page=3)
    add(29, 'nonfinal_blank_' + str(flag), flag, L._check_rule_29_blank_space, tree(chapters=[ch], pages=pages))


def main():
    rows = []
    for rule, name, expected, check, t in cases:
        try:
            findings, audit = check(t)
            if isinstance(audit, list): audit = next(a for a in audit if a.rule_id == rule)
            found = any(f.rule_id == rule for f in findings)
            rows.append({'rule': rule, 'case': name, 'expected': expected, 'found': found,
                         'status': audit.status, 'correct': expected == found})
        except Exception as exc:
            rows.append({'rule': rule, 'case': name, 'expected': expected, 'error': repr(exc), 'correct': False})
    Path(sys.argv[1]).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    assert all(row['correct'] for row in rows), 'Rule case matrix contains a failing case; see saved JSON'

if __name__ == '__main__': main()
