"""Inspect response structure for the real abstract comparison without dumping the paper."""
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.checkers import build_document_tree_from_pdf

pdf = Path(sys.argv[1])
t = build_document_tree_from_pdf(pdf, pdf.name)
prompt = f"请审查规则4：中英文摘要内容是否对齐一致，有无漏译误译；有问题时 findings 的 rule_id 必须是 4。\n【中文摘要】：\n{' '.join(p.text for p in t.abstract_cn)}\n\n【英文摘要】：\n{' '.join(p.text for p in t.abstract_en)}"
payload = {'model': 'Qwen3.8-27B', 'temperature': .1, 'messages': [
    {'role':'system','content':'你是资深研究生学位论文评审专家。只输出JSON对象，格式为 {"findings": []}。'},
    {'role':'user','content':prompt}], 'response_format':{'type':'json_object'}, 'max_tokens':1500}
req = Request('http://127.0.0.1:8122/v1/chat/completions', data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
with urlopen(req, timeout=180) as r: data = json.load(r)
choice=data['choices'][0]
msg=choice.get('message',{})
print(json.dumps({'input_chars':len(prompt), 'finish_reason':choice.get('finish_reason'),
                  'message_keys':list(msg), 'content_length':len(msg.get('content') or ''),
                  'content_prefix':(msg.get('content') or '')[:160],
                  'reasoning_length':len(msg.get('reasoning_content') or '')}, ensure_ascii=False))
