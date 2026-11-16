import fitz
from pathlib import Path
p=Path('F:/auto-review/mokanghua.pdf');d=fitz.open(p)
for n in [79,80]:
 pg=d[n-1]; pg.get_pixmap().save(f'F:/auto-review/mok-{n}.png');print(n,[(b[:4],b[4][:130].replace('\n','|')) for b in pg.get_text('blocks') if b[6]==0][:15])
