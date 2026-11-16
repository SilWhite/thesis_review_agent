from pathlib import Path
import requests,json,time
root=Path('/data01/amax/thesis_review_occurrences_20261112/final');jobs=json.loads((root/'live-jobs.json').read_text());base='http://127.0.0.1:8088'
last={}
for _ in range(240):
 pending=[]
 for r in jobs:
  if r.get('verified'):continue
  job=r['job'];response=requests.get(base+'/api/v1/jobs/'+job,timeout=30);response.raise_for_status();state=response.json()
  if last.get(job)!=state['status']:
   print(job,state['status'],state.get('stage'),flush=True);last[job]=state['status']
  if state['status'] not in ['completed','partial','failed','interrupted']:
   pending.append(job);continue
  assert state['status'] in ['completed','partial'],state
  report=requests.get(base+'/api/v1/jobs/'+job+'/report',timeout=30).json()
  (root/(job+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2))
  assert {a['rule_id'] for a in report['rule_matrix']}==set(range(2,39))
  duplicates=[(i,f) for i,f in enumerate(report['findings']) if f['rule_id']==2]
  assert duplicates
  assert all(l.get('bbox') and l.get('verified') for i,f in duplicates for l in f['locations'])
  i,f=duplicates[0]
  for n in range(min(2,len(f['locations']))):
   response=requests.get(base+f'/api/v1/jobs/{job}/evidence/{i}/{n}',timeout=30);response.raise_for_status();assert response.content.startswith(b'\x89PNG')
   (root/(job+f'-R2-{n}.png')).write_bytes(response.content)
  r.update(verified=True,status=state['status'],R2=len(duplicates),R7=sum(f['rule_id']==7 for f in report['findings']),R38=sum(f['rule_id']==38 for f in report['findings']),all_37_items=True,all_R2_boxes=True)
  print(json.dumps(r),flush=True)
 (root/'live-receipts.json').write_text(json.dumps(jobs,indent=2))
 if not pending:break
 time.sleep(5)
assert all(r.get('verified') for r in jobs),jobs
