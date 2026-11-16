import hashlib,json,os,shutil,tempfile
from pathlib import Path
from datetime import datetime,timezone
root=Path('/data01/amax/thesis_review_mok_20261112');name='app/checkers/deterministic_checker.py'
source=root/'deterministic-fixed.py';final=root/'final';live=Path('/data01/amax/thesis_review_agent')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
receipt=json.loads((root/'deploy-receipt.json').read_text());assert sha(live/name)==receipt['files'][name]['after']
shutil.copy2(source,final/name)
import subprocess
subprocess.run(['/home/amax/anaconda3/envs/qwen3/bin/python','scripts/rule_case_matrix.py',str(root/'rule-matrix-release.json')],cwd=final,check=True,stdout=(root/'rule-matrix-release.log').open('w'))
backup=root/('followup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));backup.mkdir();shutil.copy2(live/name,backup/'deterministic_checker.py')
update={'file':name,'before':sha(live/name),'after':sha(source),'backup':str(backup)}
with tempfile.NamedTemporaryFile(dir=(live/name).parent,delete=False) as f:
 temp=Path(f.name);f.write(source.read_bytes())
temp.chmod(0o644);os.replace(temp,live/name)
manifest=json.loads((final/'mok-tested.json').read_text());manifest[name]=sha(source);(final/'mok-tested.json').write_text(json.dumps(manifest,indent=2))
(root/'followup-receipt.json').write_text(json.dumps(update,indent=2));print(json.dumps(update))
