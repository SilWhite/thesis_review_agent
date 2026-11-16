from pathlib import Path
import json,time,requests
base='http://127.0.0.1:8088'
old=['job_cdeb1f8d1dde4105bfa9b1675f66bf3c','job_ac82f93aba234813b3debfcad905a62d']
root=Path('/data01/amax/thesis_review_evidence_20261112');data=Path('/data01/amax/thesis_review_agent/data')
receipts=[]
for previous in old:
 request=json.loads((data/'jobs'/previous/'request.json').read_text());request['model_mode']='local'
 response=requests.post(base+'/api/v1/jobs',json=request,timeout=30);response.raise_for_status();job=response.json()['id']
 print('submitted:',job,flush=True)
 receipts.append({'old':previous,'job':job})
(root/'live-jobs.json').write_text(json.dumps(receipts,indent=2))
for receipt in receipts:
 job=receipt['job']
 for _ in range(900):
  response=requests.get(base+'/api/v1/jobs/'+job,timeout=30);response.raise_for_status();state=response.json()
  if state['status'] in ['completed','partial','failed','interrupted']:break
  time.sleep(1)
 assert state['status'] in ['completed','partial'],state
 response=requests.get(base+'/api/v1/jobs/'+job+'/report',timeout=30);response.raise_for_status();report=response.json()
 (root/(job+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 assert {r['rule_id'] for r in report['rule_matrix']}==set(range(2,39))
 assert not [f for f in report['findings'] if f['rule_id'] in [24,29]]
 f19=[(i,f) for i,f in enumerate(report['findings']) if f['rule_id']==19]
 assert f19
 index,finding=f19[0];loc=finding['locations'][0]
 assert finding['evidence_note'] and len(loc['context'])>60 and loc['bbox']
 url=base+f'/api/v1/jobs/{job}/evidence/{index}/0'
 image=requests.get(url,timeout=30);image.raise_for_status();assert image.headers['content-type']=='image/png'
 (root/(job+'-evidence.png')).write_bytes(image.content)
 receipt.update(status=state['status'],R24=0,R29=0,R19=len(f19),evidence_image='passed')
 print(json.dumps(receipt),flush=True)
(root/'live-receipts.json').write_text(json.dumps(receipts,indent=2))
