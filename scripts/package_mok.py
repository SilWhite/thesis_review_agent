from pathlib import Path
import zipfile,hashlib,json,shutil
root=Path.cwd()
changed=['app/checkers/document_model.py','app/checkers/tree_builder.py','app/checkers/layout_regions.py','app/checkers/formula_symbols.py','app/checkers/deterministic_checker.py','app/checkers/layout_checker.py','app/checkers/semantic_checker.py']
manifest={s:hashlib.sha256((root/s).read_bytes()).hexdigest() for s in changed}
(root/'mok-tested.json').write_text(json.dumps(manifest,indent=2))
with zipfile.ZipFile('F:/auto-review/mok-candidate.zip','w',zipfile.ZIP_DEFLATED) as z:
 for pattern in ['app/**/*.py','scripts/*.py','tests/fixtures/cross_page.pdf']:
  for p in root.glob(pattern):z.write(p,p.relative_to(root))
 z.write(root/'mok-tested.json','mok-tested.json')
shutil.copy2(next(Path('F:/auto-review/test_papers/cnki_new').glob('*莫康华.pdf')),'F:/auto-review/mokanghua.pdf')
print('Frozen',len(manifest),'changed files')
