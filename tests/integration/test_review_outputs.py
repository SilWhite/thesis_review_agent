"""Compare full parser outputs and model request text with the expected results."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import dataclasses, hashlib, json, runpy, tempfile
from app.documents import (
    build_document_tree_from_pdf,
    build_document_tree_from_docx,
    build_document_tree_from_blocks,
)
from app.review.engine import NegativeChecklistReviewer
from app.review.checks.semantic import SemanticChecker
from app.schemas import ReviewRequest

ROOT = Path(__file__).resolve().parents[2]


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


rows = {}
with tempfile.TemporaryDirectory() as d:
    for name, source in runpy.run_path(str(ROOT / "tests/fixtures/review_cases.py"))[
        "cases"
    ](Path(d)):
        if isinstance(source, list):
            tree = build_document_tree_from_blocks(source, name)
        elif source.suffix == ".pdf":
            tree = build_document_tree_from_pdf(source, name)
        else:
            tree = build_document_tree_from_docx(source, name)
        prompts = []
        checker = SemanticChecker()

        def reply(prompt, mode):
            prompts.append(prompt)
            return {"findings": []}, None

        checker._call_llm = reply
        findings, audits = checker.check_all(tree, "local")
        assessment = NegativeChecklistReviewer().assess(
            ReviewRequest(document_ids=["synthetic"], model_mode="mock"),
            [],
            [],
            tree=tree,
        )
        rows[name] = {
            "tree": digest(dataclasses.asdict(tree)),
            "assessment": digest(assessment.model_dump()),
            "semantic": digest(
                [[f.model_dump() for f in findings], [a.model_dump() for a in audits]]
            ),
            "prompts": digest(sorted(prompts)),
            "calls": len(prompts),
        }
expected = json.loads((ROOT / "tests/fixtures/expected_review.json").read_text())
assert rows.keys() == expected.keys()
for name, actual in rows.items():
    for field, value in actual.items():
        assert value == expected[name][field], (
            name,
            field,
            value,
            expected[name][field],
        )
print(
    "Six review cases: full trees, assessments, semantic states and exact prompts unchanged"
)
