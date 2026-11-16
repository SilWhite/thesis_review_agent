import json
from collections import Counter
from pathlib import Path

job_dir = Path("/data01/amax/thesis_review_agent/data/jobs/job_449b878ed246428b8c43c0bae527ccff")
report = json.loads((job_dir / "report.json").read_text(encoding="utf-8"))

print("Verdict:", report.get("verdict"))
print("Summary:", report.get("summary"))
findings = report.get("findings", [])
print(f"Total findings: {len(findings)}")

counts = Counter(f["rule_id"] for f in findings)
print("\nFindings by rule ID:")
for r_id, count in sorted(counts.items()):
    sample = next(f for f in findings if f["rule_id"] == r_id)
    print(f"  Rule {r_id} ({count} issues): {sample.get('issue', '')[:80]} | Sample quote: {sample.get('quote', '')[:40]}")
