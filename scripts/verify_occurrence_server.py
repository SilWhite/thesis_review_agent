import sys,subprocess,json,hashlib,os,time
from pathlib import Path
root=Path('/data01/amax/thesis_review_occurrences_20261112');candidate=root/'candidate';live=Path('/data01/amax/thesis_review_agent')
manifest=json.loads((candidate/'manifest.json').read_text())
assert all(hashlib.sha256((candidate/p).read_bytes()).hexdigest()==h for p,h in manifest.items())
records=[]
for name in ['test_review_regressions.py','test_duplicate_occurrences.py','test_toc_transitions.py','test_zero_hit_rules.py','test_evidence.py','test_evidence_api.py','test_structure_and_citations.py','test_page_continuity.py']:
 result=subprocess.run([sys.executable,str(candidate/'scripts'/name)],cwd=candidate,capture_output=True,text=True)
 records.append({'script':name,'returncode':result.returncode,'output':result.stdout[-5000:],'stderr':result.stderr[-2000:]});(root/'cpu-test-receipt.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
 print(name,result.returncode,flush=True)
 assert result.returncode==0,records[-1]
result=subprocess.run([sys.executable,str(candidate/'scripts/rule_case_matrix.py'),str(root/'rule-matrix.json')],cwd=candidate,capture_output=True,text=True);assert result.returncode==0,result.stderr
print('CPU and 64 rule controls passed',flush=True)
sys.path.insert(0,str(candidate))
from app.config import Settings
from app.checkers.document_model import *
from app.checkers.semantic_checker import SemanticChecker
checker=SemanticChecker(Settings(model_url='http://127.0.0.1:8122/v1',model_name='Qwen3.8-27B',model_key='none'))
controls=[]
for rule,label,text,expected in [
(7,'list_with_task_word','张三等人提出了用于图像分类的卷积网络，准确率为80%。李四等人提出了用于图像分类的循环网络，准确率为81%。王五等人提出了用于图像分类的注意力网络，准确率为82%。赵六等人提出了用于图像分类的混合网络，准确率为83%。孙七等人提出第五种图像分类网络，准确率为84%。周八等人提出第六种图像分类网络，准确率为85%。以上就是全部国内外研究现状。',True),
(7,'analysed_survey','现有图像分类方法可以按局部特征和全局建模分为两类。卷积方法局部归纳偏置强，在小样本中稳定，但感受野较小。注意力方法能够建立全局联系，在远程依赖上更有效，但需要更大的数据量和计算资源。这两类方法各有优势，需要按照数据规模和计算条件选择。',False),
(38,'wrong_semantic_relation','虽然所有电源都已经断开，但是设备因此停止运行。',True),
(38,'correct_concession','虽然这次实验使用的数据很少，但是模型的效果仍然很好。',False),
(38,'correct_cause','因为所有电源都已经断开，所以设备停止运行。',False),
]:
 p=ParagraphData('p',text,1);tree=ThesisDocumentTree('controlled-test',all_body_paragraphs=[p])
 if rule==7:
  h=ParagraphData('h','1.2 国内外研究现状',1,is_heading=True,heading_level=2);tree.chapters=[ChapterData('第一章 绪论',1,1,role='intro',paragraphs=[h,p])]
  fs,au=checker._run_task_2_intro_survey(tree,'local')
 else:fs,au=checker._run_task_5_conclusion_conjunctions(tree,'local')
 found=any(f.rule_id==rule for f in fs)
 controls.append({'rule':rule,'case':label,'expected':expected,'found':found,'correct':found==expected,'findings':[f.model_dump() for f in fs if f.rule_id==rule]})
 (root/'model-control-receipt.json').write_text(json.dumps(controls,ensure_ascii=False,indent=2))
 print(rule,label,found,'expected',expected,flush=True)
assert all(r['correct'] for r in controls),controls
print('Existing-model positive and negative controls passed',flush=True)
