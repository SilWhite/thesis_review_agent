"""Non-model smoke test of the running service with a clearly named test document."""
import json
import time
import requests

base = 'http://127.0.0.1:8088'
content = '第一章 绪论\n本文测试论文审查服务。我们在此构造测试材料。\n第二章 方法\n本章介绍测试方法和目标。'
r = requests.post(base + '/api/v1/documents/text', json={'title': '系统回归测试样例', 'text': content}, timeout=20)
r.raise_for_status()
doc = r.json()['id']
r = requests.post(base + '/api/v1/jobs', json={'document_ids': [doc], 'model_mode': 'mock'}, timeout=20)
r.raise_for_status()
job = r.json()['id']
for _ in range(60):
    state = requests.get(base + '/api/v1/jobs/' + job, timeout=20).json()
    if state['status'] in ('completed', 'partial', 'failed'): break
    time.sleep(1)
assert state['status'] == 'partial', state
report = requests.get(base + '/api/v1/jobs/' + job + '/report', timeout=20)
report.raise_for_status()
assert {x['rule_id'] for x in report.json()['rule_matrix']} == set(range(2, 39))
download = requests.get(base + '/api/v1/jobs/' + job + '/download', timeout=20)
download.raise_for_status()
download.encoding = 'utf-8'
assert '各项检查状态' in download.text
print(json.dumps({'job': job, 'status': state['status'], 'rules': 37}, ensure_ascii=False))
