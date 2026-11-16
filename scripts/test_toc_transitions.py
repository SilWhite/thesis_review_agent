import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.checkers.tree_builder import is_toc_page
from app.checkers.layout_checker import LayoutChecker
from app.checkers.document_model import *
assert is_toc_page(['目 录','第一章 绪论','1','1.1 研究背景','1'])
assert is_toc_page(['Contents','Chapter 1','1'])
assert is_toc_page(['1.1 背景……1','1.2 内容……2','2.1 方法……3','2.2 实验……4'])
assert not is_toc_page(['0.01', '0.02', '0.03', '0.04', '图4-1 实验结果'])
assert not is_toc_page(['第一章 绪论','1.1 研究背景','这段话介绍研究的背景和意义。'])
a=ParagraphData('a','第一章 绪论',1,is_heading=True,heading_level=1)
b=ParagraphData('b','1.1 背景',1,is_heading=True,heading_level=2)
t=ThesisDocumentTree('toc',all_body_paragraphs=[a,b],pages=[PageData(1,600,800,is_toc=True)])
c=LayoutChecker();assert not c._check_rule_26_heading_transition(t)[0]
t.pages[0].is_toc=False;assert c._check_rule_26_heading_transition(t)[0]
t.all_body_paragraphs.insert(1,ParagraphData('intro','本章介绍研究背景。',1));assert not c._check_rule_26_heading_transition(t)[0]
print('Contents-page and genuine heading-transition controls passed')
