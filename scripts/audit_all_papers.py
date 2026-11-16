import sys,json,pickle,time
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.checkers import build_document_tree_from_pdf,DeterministicChecker,LayoutChecker,SemanticChecker
from app.evidence import attach_evidence
root=Path('F:/auto-review');out=root/'occurrence_audit';out.mkdir(exist_ok=True)
papers=list((root/'test_papers/cnki_new').glob('*.pdf'))+[root/'test_papers/xuhuiwen_thesis.pdf',root/'test_papers/wangliqiang_thesis.pdf']
records=[]
for paper in papers:
 if not paper.exists():continue
 t=build_document_tree_from_pdf(paper,paper.name);fs=[];audits=[]
 for c in [DeterministicChecker(),LayoutChecker()]:
  f,a=c.check_all(t);fs+=f;audits+=a
 for method in [SemanticChecker()._run_task_2_intro_survey,SemanticChecker()._run_task_5_conclusion_conjunctions]:
  f,a=method(t,'mock');fs+=f;audits+=a
 attach_evidence(t,fs)
 record={'file':str(paper),'counts':dict(Counter(f.rule_id for f in fs)),'audits':[a.model_dump() for a in audits],'chapters':[[c.title,c.page,c.end_page] for c in t.chapters], 'R2_missing_boxes':sum(not l.bbox for f in fs if f.rule_id==2 for l in f.locations),'findings':[f.model_dump() for f in fs]}
 (out/(paper.stem+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
 (out/(paper.stem+'.pkl')).write_bytes(pickle.dumps(t))
 records.append(record);(out/'current-cpu-census.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
 print(paper.name,record['counts'],'R2_missing',record['R2_missing_boxes'],flush=True)
