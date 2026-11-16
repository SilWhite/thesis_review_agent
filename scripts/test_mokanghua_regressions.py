"""Regression evidence from the user's 141-page Mo thesis, plus real defect controls."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.checkers import build_document_tree_from_pdf, DeterministicChecker, LayoutChecker
from app.checkers.formula_symbols import symbols

paper = Path(sys.argv[1])
tree = build_document_tree_from_pdf(paper, paper.name)
assert len(tree.references) == 188, len(tree.references)
assert [r.id_str for r in tree.references] == [str(i) for i in range(1, 189)]
for page in (51, 61, 64, 65, 79, 85, 88, 111, 113, 117, 118):
    assert any(p.is_table_cell for p in tree.pages[page-1].paragraphs), page
assert any(p.is_figure_text for p in tree.pages[24].paragraphs)
assert not any(f.page in (61, 79, 88) and not f.has_number for c in tree.chapters for f in c.formulas)
numbers = {f.num_str for c in tree.chapters for f in c.formulas}
assert {'2-1', '2-2', '2-3', '2-4', '2-5', '2-6', '5-9'} <= numbers
assert not DeterministicChecker()._check_rule_12_formula_number(tree)[0]
layout, _ = LayoutChecker().check_all(tree)
assert not [f for f in layout if f.rule_id in (30, 31, 32, 34)], [(f.rule_id, f.quote) for f in layout if f.rule_id in (30,31,32,34)]
refs, _ = DeterministicChecker()._check_rule_19_reference_incomplete(tree)
assert not [f for f in refs if f.block_id in ('ref_5', 'ref_27', 'ref_160', 'ref_163', 'ref_164', 'ref_165')]
assert any(f.block_id == 'ref_168' and '年份' in f.issue for f in refs)
assert 'NT' in symbols('t = LLM(Q, NT, P_{g})')
assert not {'L', 'M', 'N'} & symbols('t = LLM(Q, NT, P_{g})')
assert 'P_{sys}' in symbols('a = F(P_{sys}, x)')
print('Mo thesis regression passed:', tree.total_pages, 'pages;', len(numbers), 'formula numbers;', len(tree.references), 'references')
