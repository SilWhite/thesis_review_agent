import json,hashlib,shutil,datetime
from pathlib import Path
from collections import Counter
root=Path('/data01/amax/thesis_review_agent')
out=Path('/data01/amax/thesis_review_occurrences_20261112');out.mkdir(exist_ok=True)
if not (out/'app_before').exists():shutil.copytree(root/'app',out/'app_before')
records=[]
for folder in (root/'data/jobs').iterdir():
 try:
  state=json.loads((folder/'state.json').read_text());report=json.loads((folder/'report.json').read_text());request=json.loads((folder/'request.json').read_text())
 except (OSError,ValueError):continue
 records.append({'job':folder.name,'title':state.get('title'),'created_at':state.get('created_at'),'status':state.get('status'),'mode':state.get('mode'),'documents':request.get('document_ids'),'counts':dict(Counter(str(f.get('rule_id',0)) for f in report.get('findings',[]))),'matrix':report.get('rule_matrix',[])})
(out/'all-job-census.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
print(json.dumps([{k:r[k] for k in ['job','title','created_at','mode']} for r in records],ensure_ascii=False))

