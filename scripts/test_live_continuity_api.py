"""Verify deployed PDF parsing and reporting against labeled cross-page cases."""
import json
import time
from pathlib import Path
import requests

base = 'http://127.0.0.1:8088'
with Path('tests/fixtures/cross_page.pdf').open('rb') as source:
    response = requests.post(base + '/api/v1/documents',
        files={'file': ('系统回归测试_公式与跨页.pdf', source, 'application/pdf')}, timeout=30)
response.raise_for_status()
document_id = response.json()['id']
response = requests.post(base + '/api/v1/jobs', json={'document_ids': [document_id], 'model_mode': 'mock'}, timeout=30)
response.raise_for_status()
job = response.json()['id']
for _ in range(60):
    state = requests.get(base + '/api/v1/jobs/' + job, timeout=30).json()
    if state['status'] in ('partial', 'completed', 'failed'):
        break
    time.sleep(1)
assert state['status'] == 'partial', state
response = requests.get(base + '/api/v1/jobs/' + job + '/report', timeout=30)
response.raise_for_status()
report = response.json()
assert {r['rule_id'] for r in report['rule_matrix']} == set(range(2, 39))
findings = report['findings']
for rid in (12, 13, 19):
    selected = [f for f in findings if f['rule_id'] == rid]
    assert len(selected) == 1, (rid, selected)
assert 'q' in next(f['quote'] for f in findings if f['rule_id'] == 12)
assert 'm' in next(f['issue'] for f in findings if f['rule_id'] == 13)
assert '[2]' in next(f['issue'] for f in findings if f['rule_id'] == 19)
receipt = {'job': job, 'status': state['status'], 'rules': 37, 'labeled_pdf_checks': 'passed'}
Path('live-continuity-api-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(receipt, ensure_ascii=False))
