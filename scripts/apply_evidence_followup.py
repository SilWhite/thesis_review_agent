import hashlib,json,os,shutil,tempfile
from pathlib import Path
from datetime import datetime,timezone
root=Path('/data01/amax/thesis_review_evidence_20261112');live=Path('/data01/amax/thesis_review_agent');source=root/'final_v2'
before=json.loads((root/'final/release-tested.json').read_text());after=json.loads((source/'release-tested.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert all(sha(live/name)==digest for name,digest in before.items())
assert all(sha(source/name)==digest for name,digest in after.items())
# Never interrupt a user review while applying this small presentation update.
for path in (live/'data/jobs').glob('*/state.json'):
 state=json.loads(path.read_text())
 assert state['status'] not in ('queued','running'),f'Active review: {state["id"]}'
changed=[name for name in after if before[name]!=after[name]]
backup=root/('followup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));backup.mkdir()
receipt={'backup':str(backup),'files':{}}
for name in changed:
 saved=backup/name;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(live/name,saved)
 receipt['files'][name]={'before':before[name],'after':after[name]}
for name in changed:
 with tempfile.NamedTemporaryFile(dir=(live/name).parent,delete=False) as f:
  temp=Path(f.name);f.write((source/name).read_bytes())
 temp.chmod((live/name).stat().st_mode&0o777);os.replace(temp,live/name)
assert all(sha(live/name)==digest for name,digest in after.items())
(root/'installed-manifest.json').write_text(json.dumps(after,indent=2));(root/'followup-receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
