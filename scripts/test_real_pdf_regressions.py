"""Known parser failures observed in the authorized Xu thesis PDF."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.checkers import build_document_tree_from_pdf

pdf = Path(sys.argv[1])
t = build_document_tree_from_pdf(pdf, pdf.name)
assert t.abstract_cn[-1].text.endswith('务上的表现接近甚至超过了商用未开源模型。')
assert any(len(p.source_pages) > 1 for p in t.abstract_cn)
assert t.abstract_cn[0].text.startswith('近年来')
assert t.abstract_en[-1].text.endswith('available proprietary models in action decision-making and value identification tasks.')
assert len(t.references) == 92, len(t.references)
assert sum(ref.id_str == '27' for ref in t.references) == 1
assert all(ref.id_str != '663' for ref in t.references)
ref26 = next(ref for ref in t.references if ref.id_str == '26')
assert 'Value Orientations and Understanding' in ref26.raw_text
formulas = [f for ch in t.chapters for f in ch.formulas]
assert {'3.4', '3.5', '4.7'} <= {f.num_str for f in formulas}
assert all('\ufffd' not in f.text for f in formulas)
f23 = next(f for f in formulas if f.num_str == '2.3')
assert 'softmax' in f23.structured_text and '作为语言模型' not in f23.text
f24 = next(f for f in formulas if f.num_str == '2.4')
assert '∑' in f24.structured_text and 'σ' not in f24.structured_text
print('Real PDF extraction regression passed')
