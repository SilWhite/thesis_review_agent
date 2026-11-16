from pathlib import Path
import json,requests,time
root=Path('/data01/amax/thesis_review_chai_20261112');job=json.loads((root/'live-job.json').read_text())['job'];base='http://127.0.0.1:8088';last=None
for _ in range(240):
 response=requests.get(base+'/api/v1/jobs/'+job,timeout=30);response.raise_for_status();state=response.json()
 if last!=state['status']:
  print(job,state['status'],state.get('stage'),flush=True);last=state['status']
 if state['status'] in ['completed','partial','failed','interrupted']:break
 time.sleep(5)
assert state['status'] in ['completed','partial'],state
response=requests.get(base+'/api/v1/jobs/'+job+'/report',timeout=30);response.raise_for_status();report=response.json();(root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
assert {a['rule_id'] for a in report['rule_matrix']}==set(range(2,39))
counts={str(i):sum(f['rule_id']==i for f in report['findings']) for i in [2,24,31,32]}
assert counts=={'2':21,'24':1,'31':0,'32':0},counts
f2=[(i,f) for i,f in enumerate(report['findings']) if f['rule_id']==2];assert all(l.get('bbox') and l.get('verified') for i,f in f2 for l in f['locations'])
i,f=f2[0]
for location in [0,1]:
 image=requests.get(base+f'/api/v1/jobs/{job}/evidence/{i}/{location}',timeout=30);image.raise_for_status();assert image.content.startswith(b'\x89PNG');(root/f'live-evidence-{location}.png').write_bytes(image.content)
receipt={'job':job,'status':state['status'],'counts':counts,'all_37_items':True,'all_R2_evidence_verified':True,'evidence_endpoint':'HTTP 200 PNG'};(root/'live-receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt),flush=True)
