"""Inspect all real-introduction reads with source-bound model traces."""
import sys,json,hashlib,pickle
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.checkers import build_document_tree_from_pdf
from app.checkers.semantic_checker import SemanticChecker
from app.checkers.semantic_coverage import review_intro

pdf,out=Path(sys.argv[1]),Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
tree=build_document_tree_from_pdf(pdf,pdf.name)
(out/'tree.pkl').write_bytes(pickle.dumps(tree))
checker=SemanticChecker(Settings(model_url='http://127.0.0.1:8122/v1',model_name='Qwen3.8-27B',model_timeout=600))
checker.trace_dir=out/'model_calls'
intro=next(c for c in tree.chapters if c.role=='intro' or c.level==1)
fs,aa=review_intro(checker,tree,intro,'local')
result={'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
        'findings':[f.model_dump() for f in fs],'audits':[a.model_dump() for a in aa]}
(out/'intro-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
assert all(a.status=='检查通过' for a in aa),result
