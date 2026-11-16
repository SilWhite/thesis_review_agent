import requests
import time

BASE_URL = "http://127.0.0.1:8088"
doc_id = "doc_44e1ef56ef524e9b942f68cd93e82a0a"

print(f"Submitting review for user paper {doc_id}...")
job = requests.post(
    f"{BASE_URL}/api/v1/jobs",
    json={
        "document_ids": [doc_id],
        "policy_ids": [],
        "model_mode": "local",
        "language": "zh-CN",
        "material_type": "paper",
        "degree": "master"
    }
).json()
print("Submitted job:", job)

job_id = job["id"]
for i in range(120):
    time.sleep(2)
    state = requests.get(f"{BASE_URL}/api/v1/jobs/{job_id}").json()
    print(f"[{i*2}s] Status: {state['status']}, stage: {state.get('stage')}")
    if state["status"] in ("completed", "partial", "failed"):
        if state["status"] == "failed":
            print("FAILED with error:", state.get("error"))
        else:
            print("SUCCESS!")
            report = requests.get(f"{BASE_URL}/api/v1/jobs/{job_id}/report").json()
            print("Verdict:", report.get("verdict"))
            print("Findings:", len(report.get("findings", [])))
            for f in report.get("findings", [])[:3]:
                print(" -", f.get("dimension"), f.get("issue"))
        break
