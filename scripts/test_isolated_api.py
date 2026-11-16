"""End-to-end test against the isolated local server, using mock semantic mode."""
import json
import time
from pathlib import Path
import requests

base = 'http://127.0.0.1:18089'
with Path('xuhuiwen_thesis.pdf').open('rb') as paper:
    response = requests.post(base + '/api/v1/documents', files={'file': ('xuhuiwen_thesis.pdf', paper, 'application/pdf')}, timeout=30)
response.raise_for_status()
doc = response.json()['id']
response = requests.post(base + '/api/v1/jobs', json={'document_ids': [doc], 'model_mode': 'mock', 'degree': 'master'}, timeout=30)
response.raise_for_status()
job = response.json()['id']
for _ in range(60):
    state = requests.get(base + '/api/v1/jobs/' + job, timeout=30).json()
    if state['status'] in ('completed', 'partial', 'failed'): break
    time.sleep(1)
assert state['status'] in ('completed', 'partial'), state
response = requests.get(base + '/api/v1/jobs/' + job + '/report', timeout=30)
response.raise_for_status()
report = response.json()
ids = {item['rule_id'] for item in report['rule_matrix']}
assert ids == set(range(2, 39)), ids
print(json.dumps({'job': job, 'status': state['status'], 'rules': len(ids),
                  'findings': len(report['findings'])}, ensure_ascii=False))
