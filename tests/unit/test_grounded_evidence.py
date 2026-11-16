import sys, pickle, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.review.checks.semantic import SemanticChecker
from app.documents.models import *
from app.evidence.locating import attach_evidence

p = ParagraphData(
    "p", "本文比较卷积网络和注意力网络的优点与局限。然后列举四种同类算法作为例子。", 1
)
s = SemanticChecker()
calls = []


def replies(*args):
    calls.append(args[0])
    return (
        {"findings": [{"rule_id": 7, "quote": p.text, "issue": "列举"}]}
        if len(calls) == 1
        else {"findings": []}
    ), None


s._call_llm = replies
assert not s._grounded_review(7, [p], "test", "local")[0] and len(calls) == 2
print("Context recheck and semantic evidence-offset controls passed")
