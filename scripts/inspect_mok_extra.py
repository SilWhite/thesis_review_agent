import fitz
from pathlib import Path
p=next(Path('F:/auto-review/test_papers/cnki_new').glob('*莫康华.pdf'));d=fitz.open(p)
for n in [25,105,113]:
 pg=d[n-1]; pg.get_pixmap(matrix=fitz.Matrix(1.25,1.25)).save(f'F:/auto-review/mok-{n}.png');print(n,'clusters',pg.cluster_drawings())
 print([(tuple(b[:4]),b[4][:100].replace('\n','|')) for b in pg.get_text('blocks') if b[6]==0][:10])
