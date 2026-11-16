from pathlib import Path
import json,hashlib,shutil,subprocess,sys,time,requests
root=Path('/data01/amax/thesis_review_occurrences_20261112');live=Path('/data01/amax/thesis_review_agent');candidate=root/'candidate'
assert all(r['correct'] for r in json.loads((root/'model-control-receipt.json').read_text()))
assert all(r['returncode']==0 for r in json.loads((root/'cpu-test-receipt.json').read_text()))
assert all(r['correct'] for r in json.loads((root/'rule-matrix.json').read_text()))
manifest=json.loads((candidate/'manifest.json').read_text());assert all(hashlib.sha256((candidate/p).read_bytes()).hexdigest()==h for p,h in manifest.items())
def models():
 result=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:args=(p/'cmdline').read_bytes().split(b'\0')
  except OSError:continue
  if any(Path(a.decode(errors='ignore')).name=='llama-server' for a in args):result.append(int(p.name))
 return sorted(result)
before=models();backup=root/('live-backup-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()));changed=[]
for relative,sha in manifest.items():
 if not relative.startswith('app/'):continue
 target=live/relative
 if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==sha:continue
 if target.exists():
  b=backup/relative;b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,b)
 target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(candidate/relative,target);changed.append(relative)
restart=subprocess.run([sys.executable,str(candidate/'scripts/restart_mok_web.py')],cwd=live,capture_output=True,text=True)
assert restart.returncode==0,restart.stderr
assert before==models(),(before,models())
assert all(hashlib.sha256((live/p).read_bytes()).hexdigest()==h for p,h in manifest.items() if p.startswith('app/'))
receipt={'changed':changed,'backup':str(backup),'restart':restart.stdout,'model_pids_before':before,'model_pids_after':models(),'installed_app_hashes':{p:h for p,h in manifest.items() if p.startswith('app/')}}
(root/'deploy-receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt),flush=True)
previous=['job_a99c5d28810e4005847deccb7ff511d1','job_b5730a1f2a6c47e6b6858a6354b01c74','job_d858c9abe76b4fd29cbb15aa338d14c5'];jobs=[]
for old in previous:
 request=json.loads((live/'data/jobs'/old/'request.json').read_text());request['model_mode']='local'
 response=requests.post('http://127.0.0.1:8088/api/v1/jobs',json=request,timeout=30);response.raise_for_status();job=response.json()['id'];jobs.append({'previous':old,'job':job});print('submitted',job,flush=True)
(root/'live-jobs.json').write_text(json.dumps(jobs,indent=2))
