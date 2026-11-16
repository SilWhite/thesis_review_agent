from pathlib import Path
import json,hashlib,shutil,subprocess,sys,time,requests
root=Path('/data01/amax/thesis_review_chai_20261112');live=Path('/data01/amax/thesis_review_agent');candidate=root/'candidate'
tests=json.loads((root/'cpu-test-receipt.json').read_text());assert len(tests)==15 and all(t['returncode']==0 for t in tests)
assert all(r['correct'] for r in json.loads((root/'rule-matrix.json').read_text()))
manifest=json.loads((candidate/'manifest.json').read_text());base=json.loads((candidate/'baseline-manifest.json').read_text())
assert all(hashlib.sha256((candidate/p).read_bytes()).hexdigest()==h for p,h in manifest.items())
assert all(hashlib.sha256((live/p).read_bytes()).hexdigest()==h for p,h in base.items())
active=[j for j in requests.get('http://127.0.0.1:8088/api/v1/jobs',timeout=30).json() if j['status'] in ['queued','running']];assert not active,active

def models():
 result=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:args=(p/'cmdline').read_bytes().split(b'\0')
  except OSError:continue
  if any(Path(a.decode(errors='ignore')).name=='llama-server' for a in args):result.append(int(p.name))
 return sorted(result)
before=models();changed=[]
for relative,sha in manifest.items():
 if not relative.startswith('app/'):continue
 target=live/relative
 if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==sha:continue
 temporary=target.with_name(target.name+'.chai-new');shutil.copy2(candidate/relative,temporary);temporary.replace(target);changed.append(relative)
restart=subprocess.run([sys.executable,str(candidate/'scripts/restart_mok_web.py')],cwd=live,capture_output=True,text=True);assert restart.returncode==0,restart.stderr
assert before==models()
assert all(hashlib.sha256((live/p).read_bytes()).hexdigest()==h for p,h in manifest.items() if p.startswith('app/'))
receipt={'changed':changed,'backup':str(root/'app_before'),'model_before':before,'model_after':models(),'restart':restart.stdout,'installed_hashes':{p:h for p,h in manifest.items() if p.startswith('app/')}}
(root/'deploy-receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps({'changed':changed,'health':restart.stdout,'model_unchanged':True}),flush=True)
old='job_cfd6efb0f3a44b54a7c2e3aa4bb2bb1f';req=json.loads((live/'data/jobs'/old/'request.json').read_text());response=requests.post('http://127.0.0.1:8088/api/v1/jobs',json=req,timeout=30);response.raise_for_status();job=response.json()['id'];(root/'live-job.json').write_text(json.dumps({'previous':old,'job':job}));print('submitted',job,flush=True)
