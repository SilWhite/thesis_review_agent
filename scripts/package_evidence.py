from pathlib import Path
import zipfile,json,hashlib,shutil
root=Path.cwd()
names=['app/schemas.py','app/main.py','app/review.py','app/evidence.py','app/checkers/structure.py','app/checkers/illustration_citations.py','app/checkers/tree_builder.py','app/checkers/document_model.py','app/checkers/deterministic_checker.py','app/checkers/layout_checker.py','app/checkers/layout_regions.py','app/static/app.js','app/static/evidence.js','app/static/index.html']
manifest={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}
(root/'release-tested.json').write_text(json.dumps(manifest,indent=2))
with zipfile.ZipFile('F:/auto-review/evidence-release.zip','w',zipfile.ZIP_DEFLATED) as z:
 for pattern in ['app/**/*.py','app/static/*','scripts/*.py','scripts/*.cjs','tests/fixtures/cross_page.pdf']:
  for path in root.glob(pattern):
   if path.is_file():z.write(path,path.relative_to(root))
 z.write(root/'release-tested.json','release-tested.json')
for author,name in [('刘潇潇','liuxiaoxiao'),('韩葳','hanwei')]:
 shutil.copy2(next(Path('F:/auto-review/test_papers/cnki_new').glob('*'+author+'.pdf')),f'F:/auto-review/{name}.pdf')
print('Frozen',len(names),'files')
