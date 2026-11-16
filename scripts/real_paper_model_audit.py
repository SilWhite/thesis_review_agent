"""Run one complete review of an authorized paper against the existing model."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.checkers import build_document_tree_from_pdf
from app.review import NegativeChecklistReviewer
from app.schemas import ReviewRequest

path = Path(sys.argv[1])
out = Path(sys.argv[2])
started = time.time()
tree = build_document_tree_from_pdf(path, path.name)
print('parsed:', tree.total_pages, 'pages,', len(tree.chapters), 'chapters,', len(tree.references), 'references', flush=True)
result = NegativeChecklistReviewer(Settings()).assess(ReviewRequest(document_ids=['test'], model_mode='local'), [], [], tree=tree)
out.write_text(json.dumps({'seconds': round(time.time()-started, 2), 'assessment': result.model_dump()}, ensure_ascii=False, indent=2), encoding='utf-8')
print('finished', len(result.findings), 'findings in', round(time.time()-started, 2), 'seconds', flush=True)
