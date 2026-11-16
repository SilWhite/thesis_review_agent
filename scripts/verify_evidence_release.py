import json,hashlib,zipfile
from pathlib import Path
root=Path('/data01/amax/thesis_review_evidence_20261112');live=Path('/data01/amax/thesis_review_agent')
manifest=json.loads((root/'installed-manifest.json').read_text())
with zipfile.ZipFile(root/'verified-release-v2.zip') as archive:
 for name,digest in manifest.items():
  assert hashlib.sha256((live/name).read_bytes()).hexdigest()==digest,name
  assert hashlib.sha256(archive.read(name)).hexdigest()==digest,name
rows=json.loads((root/'rule-matrix-v2.json').read_text());assert len(rows)==64 and all(r['correct'] for r in rows)
receipts=json.loads((root/'live-receipts.json').read_text());assert len(receipts)==2 and all(r['R24']==r['R29']==0 and r['evidence_image']=='passed' for r in receipts)
print(json.dumps({'installed_files':len(manifest),'archive_matches':True,'rule_cases':len(rows),'full_reviews':len(receipts)}))
