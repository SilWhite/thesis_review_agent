"""A model may clear a symbol candidate only with a quote present in the source."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.checkers.document_model import ThesisDocumentTree, ChapterData, FormulaData
from app.checkers.semantic_checker import SemanticChecker

for quote, cleared in [('上下文说明为历史记录 H。', True), ('H 表示历史上下文，这是编造的句子。', False)]:
    formula = FormulaData('q=m+H', False, definition_context='上下文说明为历史记录 H。')
    tree = ThesisDocumentTree('test', chapters=[ChapterData('test', 1, 1, formulas=[formula])])
    checker = SemanticChecker()
    checker._call_llm = lambda *args: ({'findings':[{'index':0, 'symbol':'H','quote':quote}]}, None)
    findings, audit = checker._run_task_4_formula_symbols(tree, 'local')
    assert len(findings) == 1  # The genuine missing input m survives.
    assert ('H' not in findings[0].issue) == cleared
print('Formula verification source-quote controls passed')
