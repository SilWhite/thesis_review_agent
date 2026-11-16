"""Install the tested files only if the live files still match the captured baseline."""
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

test_root = Path('/data01/amax/thesis_review_validation_20261111')
live_root = Path('/data01/amax/thesis_review_agent')
files = ['app/checkers/deterministic_checker.py', 'app/checkers/layout_checker.py',
         'app/checkers/semantic_checker.py', 'app/checkers/tree_builder.py',
         'app/review.py', 'app/workflow.py']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


baseline = {}
for line in (test_root / 'source-baseline.sha256').read_text().splitlines():
    expected, name = line.split('  ', 1)
    baseline[str(Path(name).relative_to(test_root))] = expected
tested = {}
for line in (test_root / 'logic-final.sha256').read_text().splitlines():
    expected, name = line.split('  ', 1)
    tested[name] = expected
for name in files:
    if digest(live_root / name) != baseline[name]:
        raise SystemExit(f'Live file changed since baseline; no files installed: {name}')
    if not (test_root / name).is_file():
        raise SystemExit(f'Missing tested file; no files installed: {name}')
    if digest(test_root / name) != tested.get(name):
        raise SystemExit(f'Tested file changed since validation; no files installed: {name}')

stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup = test_root / ('live-backup-' + stamp)
backup.mkdir()
receipt = {'backup': str(backup), 'files': {}}
for name in files:
    source = live_root / name
    saved = backup / name
    saved.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, saved)
    receipt['files'][name] = {'before': digest(saved), 'after': digest(test_root / name)}
(backup / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')

installed = []
try:
    for name in files:
        target = live_root / name
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.review-update-', delete=False) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write((test_root / name).read_bytes())
        shutil.copymode(target, tmp_path)
        os.replace(tmp_path, target)
        installed.append(name)
    for name in files:
        if digest(live_root / name) != receipt['files'][name]['after']:
            raise RuntimeError(f'Installed hash mismatch: {name}')
except Exception:
    for name in installed:
        shutil.copy2(backup / name, live_root / name)
    raise
print(json.dumps(receipt, ensure_ascii=False))
