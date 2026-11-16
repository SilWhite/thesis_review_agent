"""Layout classifications must spare graphics while retaining real paragraph defects."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.documents.models import (
    ThesisDocumentTree,
    ChapterData,
    ParagraphData,
    PageData,
)
from app.review.checks.layout import LayoutChecker

checker = LayoutChecker()
for flag in ("is_table_cell", "is_caption", "is_formula", "is_footnote"):
    para = ParagraphData(
        "p",
        "正文描述" * 250,
        1,
        line_count=40,
        ratio_of_page=0.8,
        last_line_text="。",
        **{flag: True}
    )
    tree = ThesisDocumentTree("test", all_body_paragraphs=[para])
    assert not checker._check_rule_30_long_paragraph(tree)[0], flag
    assert not checker._check_rule_32_orphan_character(tree)[0], flag
para = ParagraphData(
    "p", "正文描述" * 250, 1, line_count=40, ratio_of_page=0.8, last_line_text="。"
)
tree = ThesisDocumentTree("test", all_body_paragraphs=[para])
assert checker._check_rule_30_long_paragraph(tree)[0]
assert checker._check_rule_32_orphan_character(tree)[0]
for blank, expected in [((200, 650), True), ((200, 220), False)]:
    p1 = PageData(
        1, 600, 800, paragraphs=[para], content_height_ratio=0.8, largest_blank=blank
    )
    p2 = PageData(2, 600, 800, paragraphs=[para], content_height_ratio=0.8)
    tree = ThesisDocumentTree(
        "test", chapters=[ChapterData("第一章", 1, 1, end_page=3)], pages=[p1, p2]
    )
    assert bool(checker._check_rule_29_blank_space(tree)[0]) == expected
print("Layout defect/graphics/continuous-blank controls passed")
