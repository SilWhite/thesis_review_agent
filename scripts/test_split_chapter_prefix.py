import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.checkers import build_document_tree_from_pdf
out=[]
for path in [Path('F:/auto-review/test_papers/wangliqiang_thesis.pdf'),next(Path('F:/auto-review/test_papers/cnki_new').glob('*闻豪.pdf'))]:
 t=build_document_tree_from_pdf(path,path.name)
 print(path.name,[(c.title,c.page) for c in t.chapters],len(t.references),flush=True)
 assert len(t.chapters)>=4,(path.name,[(p.text,p.is_heading) for p in t.pages[9].paragraphs[:3]])
 out.append({'file':path.name,'chapters':[(c.title,c.page) for c in t.chapters]})
Path('F:/auto-review/ocr-heading-controls.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
