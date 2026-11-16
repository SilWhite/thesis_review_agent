"""Formula-specific checks independent of a running model."""
import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.checkers.document_model import ThesisDocumentTree, ChapterData, FormulaData
from app.checkers.formula_symbols import symbols, assigned_outputs, has_definition, declared_element_families
from app.checkers.semantic_checker import SemanticChecker
from app.checkers.formula_extraction import stitch_numbered_rows


assert symbols('w = W_{e} + W_{p}') == {'w', 'W_{e}', 'W_{p}'}
assert 'i' not in symbols('L_{1}(U) = ∑ _{i} log P(u_{i})')
assert 'σ' not in symbols('L_{1}(U) = ∑ _{i} log P(u_{i})')
assert not {'s', 't'} & symbols('max δ, s.t. |δ| ≤ ε')
assert 'i' not in symbols('p = ∏ m i=1 P(p_{i})')
assert 'd_{k}' in symbols('a = Q / _{√d}_{k}')
assert 'd' not in symbols('a = Q / _{√d}_{k}')
assert assigned_outputs('h_{l}=transformer_block(h_{l-1})') == {'h'}
assert has_definition('W_{e}', '其中 W_{e} 表示词嵌入矩阵。')
assert not has_definition('W_{p}', '其中 W_{e} 表示词嵌入矩阵。')
assert declared_element_families('给定输入语料 U={u_{1},...,u_{n}}。') == {'u'}


def row(index, x, y, text, size=12):
    box = (x, y - size, x + len(text) * size / 2, y + 2)
    span = {'text': text, 'font': 'Times', 'size': size, 'origin': (x, y), 'bbox': box}
    return {'b_idx': index, 'text': text, 'lines': [{'spans': [span], 'bbox': box}],
            'bbox': box, 'max_font_sz': size, 'in_table': False}


parts = [row(0, 200, 100, 'Accuracy ='), row(1, 310, 93, 'TP+TN', 9),
         row(2, 300, 107, 'TP+TN+FP+FN', 9), row(3, 490, 100, '(1.1)'),
         row(4, 200, 135, 'q = x + y'), row(5, 200, 170, 'z = x (1.2)')]
combined = stitch_numbered_rows(parts, re.compile(r'\(\d+\.\d+\)\s*$'))
first = next(p for p in combined if '(1.1)' in p['text'])
assert 'TP+TN+FP+FN' in first['text']
assert any(p['text'] == 'q = x + y' for p in combined)


def check(formula):
    chapter = ChapterData(title='方法', level=1, page=1, formulas=[formula])
    tree = ThesisDocumentTree(filename='test', chapters=[chapter])
    return SemanticChecker()._run_task_4_formula_symbols(tree, 'mock')


f = FormulaData(text='w = W_e + W_p', has_number=True,
                structured_text='w = W_{e} + W_{p}', definition_context='其中 W_{e} 表示词嵌入矩阵。')
findings, audits = check(f)
assert len(findings) == 1 and 'W_{p}' in findings[0].issue and 'W_{e}' not in findings[0].issue
f.definition_context += 'W_{p} 表示位置嵌入矩阵。'
assert not check(f)[0]

f = FormulaData(text='x = \ufffd + y', has_number=True, context_text='y 表示输入。')
findings, audits = check(f)
assert not findings and audits[0].status == '无法可靠判断'
print('Formula structure and unreadable-input tests passed')
