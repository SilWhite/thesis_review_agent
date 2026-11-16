"""Regression controls for distinct source occurrences and physical evidence."""

import sys, pickle
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.documents.models import *
from app.review.checks.deterministic import DeterministicChecker
from app.evidence.locating import attach_evidence

phrase = "这里是一段需要分别定位并且内容完全相同的测试句子"
p = ParagraphData("p", phrase + "。" + phrase + "。", 1, bbox=(50, 100, 500, 160))
lines = [
    TextLine(phrase + "。", (50, 100, 500, 120), 12, ""),
    TextLine(phrase + "。", (50, 140, 500, 160), 12, ""),
]
t = ThesisDocumentTree(
    "test",
    all_body_paragraphs=[p],
    pages=[PageData(1, 600, 800, lines=lines, paragraphs=[p])],
)
c = DeterministicChecker()
fs, _ = c._check_rule_2_duplicate_sentences(t)
attach_evidence(t, fs)
assert len(fs) == 1 and fs[0].locations[0].bboxes != fs[0].locations[1].bboxes
assert fs[0].locations[0].bboxes == [[50.0, 100.0, 500.0, 120.0]]
assert fs[0].locations[1].bboxes == [[50.0, 140.0, 500.0, 160.0]]
t.all_body_paragraphs = [p, p]
assert len(c._check_rule_2_duplicate_sentences(t)[0]) == 1
p2 = ParagraphData("other", p.text, 1, bbox=p.bbox)
t.all_body_paragraphs = [p, p2]
# Duplicate overlapping text layers must not create additional finding pairs.
fs, _ = c._check_rule_2_duplicate_sentences(t)
assert all(f.locations[0].block_id == f.locations[1].block_id for f in fs)
t.all_body_paragraphs = [
    ParagraphData("f1", phrase, 1, is_formula=True),
    ParagraphData("f2", phrase, 2, is_formula=True),
]
assert not c._check_rule_2_duplicate_sentences(t)[0]
print("Duplicate occurrence controls passed")
