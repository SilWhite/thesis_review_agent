"""Install only the frozen formula/continuity changes after backing up live files."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

root = Path('/data01/amax/thesis_review_formula_20261112')
live = Path('/data01/amax/thesis_review_agent')
files = ['app/checkers/document_model.py', 'app/checkers/tree_builder.py',
         'app/checkers/formula_extraction.py', 'app/checkers/formula_symbols.py',
         'app/checkers/page_continuity.py', 'app/checkers/deterministic_checker.py',
         'app/checkers/semantic_checker.py', 'app/checkers/layout_checker.py',
         'app/review.py', 'requirements.txt']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(name):
    return dict((path, value) for value, path in
                (line.split('  ', 1) for line in (root / name).read_text().splitlines()))


before = manifest('live-before.sha256')
tested = manifest('tested.sha256')
for name in files:
    target = live / name
    target.resolve().relative_to(live.resolve())
    expected = before.get(name)
    if target.exists() and (expected is None or sha(target) != expected):
        raise SystemExit(f'Live file changed; update stopped: {name}')
    if not target.exists() and expected is not None:
        raise SystemExit(f'Live file disappeared; update stopped: {name}')
    if sha(root / name) != tested.get(name):
        raise SystemExit(f'Tested file changed; update stopped: {name}')

if '--check' in sys.argv:
    print('Deployment preflight passed:', len(files), 'files')
    raise SystemExit(0)

import fontTools
assert fontTools.__version__ == '4.65.0', 'Required fontTools version is unavailable'
backup = root / ('live-backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir()
receipt = {'backup': str(backup), 'files': {}}
for name in files:
    target = live / name
    if target.exists():
        saved = backup / name
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, saved)
    receipt['files'][name] = {'before': before.get(name), 'after': sha(root / name)}
(backup / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')

installed = []
try:
    for name in files:
        target = live / name
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.formula-update-', delete=False) as temp:
            temporary = Path(temp.name)
            temp.write((root / name).read_bytes())
        if target.exists():
            shutil.copymode(target, temporary)
        else:
            temporary.chmod(0o644)
        os.replace(temporary, target)
        installed.append(name)
    assert all(sha(live / name) == tested[name] for name in files)
except Exception:
    for name in installed:
        if receipt['files'][name]['before'] is None:
            (live / name).unlink()
        else:
            shutil.copy2(backup / name, live / name)
    raise
print(json.dumps(receipt, ensure_ascii=False))
