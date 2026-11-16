from pathlib import Path
import sys,json,pickle,fitz
sys.path.insert(0,str(Path.cwd()))
from app.checkers import build_document_tree_from_pdf
p=next(Path('F:/auto-review/test_papers/cnki_new').glob('*莫康华.pdf'))
t=build_document_tree_from_pdf(p,p.name)
Path('F:/auto-review/mokanghua-tree-before.pkl').write_bytes(pickle.dumps(t))
d=fitz.open(p)
for n in [28,29,61,64,65,85,88,125,127,138]:
 pg=d[n-1]; pg.get_pixmap(matrix=fitz.Matrix(1.25,1.25)).save(f'F:/auto-review/mok-{n}.png')
 print('PAGE',n,'tables',[x.bbox for x in pg.find_tables().tables],'drawings',len(pg.get_drawings()))
print('REFS',len(t.references))
for r in t.references:
 if r.id_str in ['5','25','27','33','168']: print(r.id_str,repr(r.raw_text))
