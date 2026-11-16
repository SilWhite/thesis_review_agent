"""Apply the final one-file abstract-boundary correction with drift checks."""
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timezone

root = Path('/data01/amax/thesis_review_formula_20261112')
live = Path('/data01/amax/thesis_review_agent')
name = 'app/checkers/tree_builder.py'
old_receipt = json.loads((root / 'live-backup-20261112T034703Z/receipt.json').read_text())
expected_before = old_receipt['files'][name]['after']
expected_after = (root / 'keyword-tested.sha256').read_text().split('  ', 1)[0]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(live / name) == expected_before, 'Live code changed since prior deployment'
assert sha(root / name) == expected_after, 'Tested code changed'
backup = root / ('keyword-backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir()
shutil.copy2(live / name, backup / 'tree_builder.py')
with tempfile.NamedTemporaryFile(dir=(live / name).parent, prefix='.keyword-update-', delete=False) as temp:
    path = Path(temp.name)
    temp.write((root / name).read_bytes())
shutil.copymode(live / name, path)
os.replace(path, live / name)
assert sha(live / name) == expected_after
receipt = {'backup': str(backup), 'before': expected_before, 'after': expected_after}
(backup / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt))
