import urllib.request
import json
import time

url = "http://127.0.0.1:8122/v1/chat/completions"
data = {
    "model": "Qwen3.8-27B",
    "temperature": 0.1,
    "messages": [
        {"role": "system", "content": "你是资深研究生学位论文评审专家。只输出严格符合要求的JSON对象，格式形如：{\"findings\": [{\"rule_id\": 3, \"quote\": \"原文片段\", \"issue\": \"具体问题\", \"suggestion\": \"修改建议\"}]}。"},
        {"role": "user", "content": "请检查这段文字：'本研究探讨了深度学习模型在论文评审中的应用。TODO: 补充消融实验部分。'"}
    ],
    "response_format": {"type": "json_object"},
    "max_tokens": 500
}

req = urllib.request.Request(
    url,
    data=json.dumps(data).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - t0
        print(f"Elapsed: {elapsed:.2f}s, Response status: {resp.status}")
        content = res["choices"][0]["message"]["content"]
        print("Raw content:", content)
        parsed = json.loads(content)
        print("Parsed JSON successfully:", parsed)
except Exception as e:
    import traceback
    traceback.print_exc()
