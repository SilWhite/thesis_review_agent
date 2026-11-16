import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.checkers.document_model import *
from app.checkers.semantic_checker import SemanticChecker
from app.checkers.layout_checker import LayoutChecker
p=ParagraphData('survey','张三提出第一种图像分类算法。李四设计了第二种图像分类算法。王五提出第三种方法。赵六设计了第四种方法。',2)
h=ParagraphData('heading','1.2 国内外研究现状',2,is_heading=True,heading_level=2)
t=ThesisDocumentTree('control',chapters=[ChapterData('第一章 绪论',1,1,role='intro',paragraphs=[h,p])])
s=SemanticChecker();s._call_llm=lambda *args:({'findings':[{'rule_id':7,'quote':p.text,'issue':'连续罗列四项研究，缺少对方法的比较。','suggestion':'增加对方法的分类和比较。'}]},None)
fs,a=s._run_task_2_intro_survey(t,'local');assert any(f.rule_id==7 for f in fs)
s._call_llm=lambda *args:({'findings':[{'rule_id':7,'quote':'模型编造了一段完全不在论文中的文字','issue':'fake'}]},None)
assert not any(f.rule_id==7 for f in s._run_task_2_intro_survey(t,'local')[0])
s._call_llm=lambda *args:({'findings':[]},None)
assert not any(f.rule_id==7 for f in s._run_task_2_intro_survey(t,'local')[0])
# Rule 38 now requires a complete model review; mock cannot claim a pass or a problem.
t.all_body_paragraphs=[ParagraphData('bad','虽然所有电源已经断开，所以设备停止运行。',3)]
fs, audits=s._run_task_5_conclusion_conjunctions(t,'mock')
assert not any(f.rule_id==38 for f in fs)
assert next(a for a in audits if a.rule_id==38).status=='执行失败'
for ratio,expected in [(.59,False),(.61,True)]:
 t.abstract_cn=[ParagraphData('abstract','摘要文字。',1,ratio_of_page=ratio)]
 assert bool(LayoutChecker()._check_rule_5_abstract_first_para(t)[0])==expected
print('Never-fired rules: scope, long-pair, semantic follow-up and fabricated-quote controls passed')

# A survey's nested headings must not end its reading scope.
s=SemanticChecker();prompts=[]
s._call_llm=lambda prompt,*args:(prompts.append(prompt) or {'findings':[]},None)
paras=[ParagraphData('scope','1.2 国内外研究现状',1,is_heading=True,heading_level=2),
       ParagraphData('nested','1.2.1 卷积网络',1,is_heading=True,heading_level=3),
       ParagraphData('inside','这段属于综述子节，需要读到其方法和优缺点分析。',1),
       ParagraphData('next','1.3 研究内容',1,is_heading=True,heading_level=2),
       ParagraphData('outside','这段位于综述结束之后，不属于该次研究现状检查。',1)]
t=ThesisDocumentTree('scope',chapters=[ChapterData('第一章 绪论',1,1,role='intro',paragraphs=paras)])
s._run_task_2_intro_survey(t,'local')
assert any(paras[2].text in prompt for prompt in prompts)
assert not any(paras[4].text in prompt for prompt in prompts if prompt.startswith('审查规则7'))
print('Nested survey sections stay in scope; the next section ends it')
