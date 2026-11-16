import pickle,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
t=pickle.loads(Path('F:/auto-review/mokanghua-tree-before.pkl').read_bytes())
for n in [29,30,96,97,106]:
 print('PAGE',n)
 for p in t.pages[n-1].paragraphs:
  if not p.is_formula and not p.is_table_cell:print(p.text)
