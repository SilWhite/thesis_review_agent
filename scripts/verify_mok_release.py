from pathlib import Path
import json,hashlib,zipfile
root=Path('/data01/amax/thesis_review_mok_20261112');live=Path('/data01/amax/thesis_review_agent')
manifest=json.loads((root/'final/mok-tested.json').read_text())
with zipfile.ZipFile(root/'verified-release.zip') as z:
 for name,digest in manifest.items():
  assert hashlib.sha256((live/name).read_bytes()).hexdigest()==digest,name
  assert hashlib.sha256(z.read(name)).hexdigest()==digest,('zip',name)
rows=json.loads((root/'rule-matrix-release.json').read_text());assert len(rows)==64 and all(r['correct'] for r in rows)
print(json.dumps({'installed_files':len(manifest),'archive_matches':True,'rule_cases_passed':len(rows)}))
