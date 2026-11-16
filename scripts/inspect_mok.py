from pathlib import Path
import fitz,pickle
p=next(Path('F:/auto-review/test_papers/cnki_new').glob('*莫康华.pdf'));d=fitz.open(p)
for n in [28,61,64,65,85,88]:
 pg=d[n-1];print('\nPAGE',n)
 lines=[]
 for dr in pg.get_drawings():
  r=dr['rect']
  if r.width>pg.rect.width*.3 and r.height<2: lines.append(tuple(round(v,1) for v in r))
 print('horiz',lines[:40])
 print('blocks',[(tuple(round(v,1) for v in b[:4]),b[4][:65].replace('\n','|')) for b in pg.get_text('blocks') if b[6]==0][:40])
