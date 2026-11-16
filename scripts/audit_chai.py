import sys,json,pickle
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fitz
from app.checkers import build_document_tree_from_pdf,DeterministicChecker,LayoutChecker
root=Path('F:/auto-review/chai_audit');root.mkdir(exist_ok=True)
p=Path('F:/auto-review/chailongfei.pdf');tree=build_document_tree_from_pdf(p,p.name);(root/'after.pkl').write_bytes(pickle.dumps(tree))
findings=[]
for checker in [DeterministicChecker(),LayoutChecker()]:f,a=checker.check_all(tree);findings+=f
(root/'after-cpu.json').write_text(json.dumps({'chapters':[(c.title,c.page,c.end_page) for c in tree.chapters],'counts':{str(i):sum(f.rule_id==i for f in findings) for i in [2,24,30,31,32,34]},'findings':[f.model_dump() for f in findings]},ensure_ascii=False,indent=2),encoding='utf8')
with fitz.open(p) as doc:
 for n in [27,32,33,35,57,74]:
  pg=doc[n-1];(root/f'page-{n}.png').write_bytes(pg.get_pixmap(matrix=fitz.Matrix(1.2,1.2)).tobytes('png'))
  print('page',n,'clusters',[list(r) for r in pg.cluster_drawings()],'images',[list(r) for im in pg.get_images() for r in pg.get_image_rects(im[0])],flush=True)
print('pages',tree.total_pages,'chapters',len(tree.chapters),flush=True)
