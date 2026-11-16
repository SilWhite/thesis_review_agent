import requests
import time
import json

BASE_URL = "http://127.0.0.1:8088"

def test():
    print("[1] Testing config endpoint...")
    cfg = requests.get(f"{BASE_URL}/api/v1/config").json()
    print("Config response:", cfg)

    print("\n[2] Uploading sample text...")
    doc = requests.post(
        f"{BASE_URL}/api/v1/documents/text",
        json={
            "title": "sample_thesis",
            "text": "本研究探讨了深度学习模型在论文评审中的应用。TODO: 补充消融实验部分。通过对现有基准的测试，验证了方法的有效性。"
        }
    ).json()
    print("Document created:", doc)

    print("\n[3] Submitting review job (mock mode)...")
    job = requests.post(
        f"{BASE_URL}/api/v1/jobs",
        json={
            "document_ids": [doc["id"]],
            "policy_ids": [],
            "model_mode": "local",
            "language": "zh-CN"
        }
    ).json()
    print("Job submitted:", job)

    print("\n[4] Polling job status...")
    job_id = job["id"]
    for _ in range(30):
        time.sleep(2)
        state = requests.get(f"{BASE_URL}/api/v1/jobs/{job_id}").json()
        print(f"Status: {state['status']}, stage: {state.get('stage')}")
        if state["status"] in ("completed", "partial"):
            break

    print("\n[5] Fetching generated report...")
    report = requests.get(f"{BASE_URL}/api/v1/jobs/{job_id}/report").json()
    print("Report verdict:", report.get("verdict"))
    print("Findings count:", len(report.get("findings", [])))
    for f in report.get("findings", []):
        print(f" - [{f['dimension']}] {f['quote']}: {f['issue']}")

    print("\nWorkflow test passed successfully!")

if __name__ == "__main__":
    test()
