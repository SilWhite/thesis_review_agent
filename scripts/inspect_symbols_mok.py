import sys,pickle
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
t=pickle.loads(Path('F:/auto-review/mokanghua-tree-before.pkl').read_bytes())
for c in t.chapters:
 for f in c.formulas:
  if f.page in [29,50,56,60,96,102]: print(f.page,f.num_str,repr(f.structured_text))
