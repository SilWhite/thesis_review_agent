"""Run the user's Mo thesis through the deployed HTTP upload/review/report path."""
import json,time,requests
from pathlib import Path
base='http://127.0.0.1:8088'
with Path('../mokanghua.pdf').open('rb') as f:
 r=requests.post(base+'/api/v1/documents',files={'file':('面向大模型智能体决策链的输入操控攻击研究_莫康华.pdf',f,'application/pdf')},timeout=60)
r.raise_for_status();doc=r.json()['id']
r=requests.post(base+'/api/v1/jobs',json={'document_ids':[doc],'model_mode':'local'},timeout=30);r.raise_for_status();job=r.json()['id'];print('job:',job,flush=True)
Path('../live-job.json').write_text(json.dumps({'id':job,'document_id':doc}))
for _ in range(600):
 r=requests.get(base+'/api/v1/jobs/'+job,timeout=30);r.raise_for_status();state=r.json()
 if state['status'] in ['completed','partial','failed']:break
 time.sleep(1)
assert state['status'] in ('completed','partial'),state
r=requests.get(base+'/api/v1/jobs/'+job+'/report',timeout=30);r.raise_for_status();report=r.json()
Path('../live-final-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
assert {r['rule_id'] for r in report['rule_matrix']}==set(range(2,39))
assert not any(f['rule_id'] in (12,30,31,32,34) for f in report['findings'])
assert any(f['rule_id']==19 and '[168]' in f['issue'] for f in report['findings'])
from collections import Counter
receipt={'job':job,'status':state['status'],'findings_by_rule':dict(Counter(f['rule_id'] for f in report['findings'])),'rules':37}
Path('../live-receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt),flush=True)
