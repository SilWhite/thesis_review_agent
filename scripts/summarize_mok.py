import sys,pickle,json
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from app.checkers import DeterministicChecker,SemanticChecker,LayoutChecker
p=Path('F:/auto-review/mokanghua-tree-before.pkl');t=pickle.loads(p.read_bytes())
fs=[]
for checker in [DeterministicChecker(),LayoutChecker()]:
 f,a=checker.check_all(t);fs+=f
f,a=SemanticChecker()._run_task_4_formula_symbols(t,'mock');fs+=f
Path('F:/auto-review/mokanghua-current-checks.json').write_text(json.dumps([f.model_dump() for f in fs],ensure_ascii=False,indent=2),encoding='utf-8')
from collections import Counter
print(Counter(f.rule_id for f in fs))
for f in fs:
 if f.rule_id in [12,13,30,31,32,34]:print(f.rule_id,[l.page for l in f.locations],f.quote,f.issue)
for n in [28,61,64,65,85,88]:
 page=t.pages[n-1];print('PAGE',n,'paras',len(page.paragraphs),'table',sum(p.is_table_cell for p in page.paragraphs),'formulas',[(f.num_str,f.text[:30]) for c in t.chapters for f in c.formulas if f.page==n])
