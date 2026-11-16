import hashlib,json,os,shutil,tempfile,subprocess
from pathlib import Path
from datetime import datetime,timezone
root=Path('/data01/amax/thesis_review_mok_20261112');final=root/'final';live=Path('/data01/amax/thesis_review_agent');name='app/checkers/formula_symbols.py';source=root/'formula-symbols-fixed.py'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((final/'mok-tested.json').read_text());assert sha(live/name)==manifest[name]
shutil.copy2(source,final/name)
for script in ['test_formula_recovery.py','test_formula_verification.py','test_page_continuity.py']:
 subprocess.run(['/home/amax/anaconda3/envs/qwen3/bin/python','scripts/'+script],cwd=final,check=True)
subprocess.run(['/home/amax/anaconda3/envs/qwen3/bin/python','scripts/rule_case_matrix.py',str(root/'rule-matrix-release.json')],cwd=final,check=True,stdout=(root/'rule-matrix-release.log').open('w'))
backup=root/('symbol-followup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));backup.mkdir();shutil.copy2(live/name,backup/'formula_symbols.py')
receipt={'before':sha(live/name),'after':sha(source),'file':name,'backup':str(backup)}
with tempfile.NamedTemporaryFile(dir=(live/name).parent,delete=False) as f:
 temp=Path(f.name);f.write(source.read_bytes())
temp.chmod(0o644);os.replace(temp,live/name)
manifest[name]=sha(source);(final/'mok-tested.json').write_text(json.dumps(manifest,indent=2));(root/'symbol-followup-receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
