import fitz
from pathlib import Path
p=next(Path('F:/auto-review/test_papers/cnki_new').glob('*莫康华.pdf'));d=fitz.open(p);pg=d[50];print(pg.cluster_drawings());print([(b[:4],b[4][:70]) for b in pg.get_text('blocks') if b[6]==0]);pg.get_pixmap().save('F:/auto-review/mok-51.png')
