import urllib.request
import json
import time

url = "http://127.0.0.1:8122/v1/chat/completions"
data = {
    "model": "Qwen3-8B-IT",
    "messages": [
        {"role": "user", "content": "你好，请用一句话介绍你自己。"}
    ],
    "max_tokens": 100
}
req = urllib.request.Request(
    url,
    data=json.dumps(data).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

start_t = time.time()
print("Sending request to Qwen3-8B-IT on Single GPU...")
with urllib.request.urlopen(req, timeout=60) as resp:
    res = json.loads(resp.read().decode("utf-8"))
    print(f"Response in {time.time() - start_t:.2f}s:")
    print("Content:", res["choices"][0]["message"]["content"])
