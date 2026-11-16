from pathlib import Path
import json
for name in ['liuxiaoxiao','hanwei']:
 r=json.loads(Path(f'F:/auto-review/{name}-before.json').read_text(encoding='utf-8-sig'))
 print(name)
 for f in r['findings']:
  if f['rule_id'] in [19,24,29]:print(f['rule_id'],[x.get('page') for x in f.get('locations',[])],f['quote'],f['issue'])
