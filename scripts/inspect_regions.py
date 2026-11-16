import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
import fitz
from app.checkers.formula_extraction import recovered_page_dict
from app.checkers.layout_regions import supplemental_regions
p=next(Path('F:/auto-review/test_papers/cnki_new').glob('*莫康华.pdf'));d=fitz.open(p)
for n in [88,113]:
 bs=recovered_page_dict(d[n-1],{})['blocks'];print(n,'regions',supplemental_regions(d[n-1],bs))
 for b in bs:
  if b['type']==0 and 245<b['bbox'][1]<505 and n==113:
   print('BLOCK',b['bbox'])
   for l in b['lines'][:7]: print('LINE',l['bbox'],[(s['text'],s['origin']) for s in l['spans']])
