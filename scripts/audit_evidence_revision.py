import sys,json,pickle
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from app.checkers import build_document_tree_from_pdf, DeterministicChecker,LayoutChecker
from app.evidence import attach_evidence
from collections import Counter
records=[]
for author in ['刘潇潇','韩葳','莫康华']:
 p=next(Path('F:/auto-review/test_papers/cnki_new').glob('*'+author+'.pdf'))
 t=build_document_tree_from_pdf(p,p.name)
 findings=[]
 for checker in [DeterministicChecker(),LayoutChecker()]:
  f,a=checker.check_all(t);findings.extend(f)
 attach_evidence(t,findings)
 Path('F:/auto-review/evidence-'+author+'.pkl').write_bytes(pickle.dumps(t))
 record={'author':author,'chapters':[[c.title,c.page,c.end_page] for c in t.chapters],'references':len(t.references),'counts':dict(Counter(f.rule_id for f in findings)), 'findings':[f.model_dump() for f in findings if f.rule_id in [19,24,29]]}
 records.append(record)
 Path('F:/auto-review/evidence-after.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
 print(author,record['chapters'],record['counts'],flush=True)
