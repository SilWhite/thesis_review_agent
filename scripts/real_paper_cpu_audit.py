"""Record parser and CPU review results for local test papers."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.checkers import build_document_tree_from_pdf
from app.review import NegativeChecklistReviewer
from app.schemas import ReviewRequest

for filename in ('xuhuiwen_thesis.pdf', 'wangliqiang_thesis.pdf'):
    path = Path(filename)
    tree = build_document_tree_from_pdf(path, filename)
    result = NegativeChecklistReviewer().assess(ReviewRequest(document_ids=['test'], model_mode='mock'), [], [], tree=tree)
    data = {'file': filename, 'pages': tree.total_pages, 'body_paragraphs': len(tree.all_body_paragraphs),
            'chapter_count': len(tree.chapters), 'references': len(tree.references),
            'abstract_cn': len(tree.abstract_cn), 'abstract_en': len(tree.abstract_en),
            'chapters': [{'title': c.title, 'page': c.page, 'paragraphs': len(c.paragraphs)} for c in tree.chapters],
            'assessment': result.model_dump()}
    Path(filename + '.cpu.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(filename, 'pages', tree.total_pages, 'chapters', len(tree.chapters), 'references', len(tree.references),
          'findings', len(result.findings), 'incomplete', sum(a.status in ('缺少输入', '无法可靠判断', '执行失败') for a in result.rule_matrix), flush=True)
