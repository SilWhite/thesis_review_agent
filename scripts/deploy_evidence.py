"""Deploy the seven frozen, server-tested files with drift checks and backups."""
import hashlib,json,os,shutil,tempfile,sys
from pathlib import Path
from datetime import datetime,timezone
root=Path('/data01/amax/thesis_review_evidence_20261112')
source=root/'final'; live=Path('/data01/amax/thesis_review_agent')
manifest=json.loads((source/'release-tested.json').read_text())
sha=lambda p: hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
for name, digest in manifest.items():
 target=live/name;target.resolve().relative_to(live.resolve())
 old=root/'app_before'/Path(name).relative_to('app')
 assert sha(target)==sha(old),f'Live drift: {name}'
 assert sha(source/name)==digest,f'Untested source: {name}'
if '--check' in sys.argv:
 print('Deployment preflight passed:',len(manifest));sys.exit(0)
backup=root/('live-backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));backup.mkdir()
receipt={'backup':str(backup),'files':{}}
for name,digest in manifest.items():
 target=live/name
 receipt['files'][name]={'before':sha(target),'after':digest}
 if target.exists():
  saved=backup/name;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,saved)
(backup/'receipt.json').write_text(json.dumps(receipt,indent=2))
installed=[]
try:
 for name in manifest:
  target=live/name
  with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.mok-update-',delete=False) as f:
   temp=Path(f.name);f.write((source/name).read_bytes())
  temp.chmod(target.stat().st_mode & 0o777 if target.exists() else 0o644)
  os.replace(temp,target);installed.append(name)
 assert all(sha(live/name)==digest for name,digest in manifest.items())
except Exception:
 for name in installed:
  if receipt['files'][name]['before'] is None:(live/name).unlink()
  else:shutil.copy2(backup/name,live/name)
 raise
(root/'deploy-receipt.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
