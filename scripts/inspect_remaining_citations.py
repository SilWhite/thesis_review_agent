import json,pickle,sys,re
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from app.checkers.illustration_citations import references
records=json.loads(Path('F:/auto-review/evidence-after.json').read_text(encoding='utf-8'))
for r in records:
 print(r['author'])
 t=pickle.loads(Path('F:/auto-review/evidence-'+r['author']+'.pkl').read_bytes())
 for f in r['findings']:
  if f['rule_id']==24:
   print(f['issue'],f['quote'],f['locations'])
   key=f['quote'].split()[0]
   for page in t.pages:
    for p in page.paragraphs:
     if key in p.text:print('MATCH',page.page_num,'cap',p.is_caption,'table',p.is_table_cell,p.text[:160])
