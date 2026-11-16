"""Save a reproducible parser audit without calling a model."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--implementation', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('papers', type=Path, nargs='+')
args = parser.parse_args()
sys.path.insert(0, str(args.implementation.resolve()))
from app.checkers import build_document_tree_from_pdf, DeterministicChecker, SemanticChecker

records = []
for paper in args.papers:
    tree = build_document_tree_from_pdf(paper, paper.name)
    formulas = [f for c in tree.chapters for f in c.formulas]
    r12, a12 = DeterministicChecker()._check_rule_12_formula_number(tree)
    r13, a13 = SemanticChecker()._run_task_4_formula_symbols(tree, 'mock')
    r19, a19 = DeterministicChecker()._check_rule_19_reference_incomplete(tree)
    record = {
        'paper': str(paper), 'sha256': hashlib.sha256(paper.read_bytes()).hexdigest(),
        'pages': tree.total_pages, 'chapters': len(tree.chapters),
        'body_paragraphs': len(tree.all_body_paragraphs), 'references': len(tree.references),
        'reference_entries': [{'id': r.id_str, 'pages': getattr(r, 'source_pages', []) or [r.page_num], 'text': r.raw_text} for r in tree.references],
        'abstract_cn': [{'pages': getattr(p, 'source_pages', []) or [p.page], 'text': p.text} for p in tree.abstract_cn],
        'abstract_en': [{'pages': getattr(p, 'source_pages', []) or [p.page], 'text': p.text} for p in tree.abstract_en],
        'formulas': [{'page': f.page, 'number': f.num_str, 'text': f.text,
                      'structured': getattr(f, 'structured_text', ''),
                      'quality': getattr(f, 'extraction_status', 'legacy')} for f in formulas],
        'corrupt_formulas': sum('\ufffd' in f.text for f in formulas),
        'unreliable_formulas': sum(getattr(f, 'extraction_status', 'legacy') in ('partial', 'unreadable') for f in formulas),
        'rule12': {'audit': a12.model_dump(), 'findings': [f.model_dump() for f in r12]},
        'rule13': {'audit': a13[0].model_dump(), 'findings': [f.model_dump() for f in r13]},
        'rule19': {'audit': a19.model_dump(), 'findings': [f.model_dump() for f in r19]},
    }
    records.append(record)
    args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: record[key] for key in ('paper', 'pages', 'chapters', 'references', 'corrupt_formulas')}, ensure_ascii=False), flush=True)
