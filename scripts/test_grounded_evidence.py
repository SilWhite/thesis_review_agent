import sys,pickle,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.checkers.semantic_checker import SemanticChecker
from app.checkers.document_model import *
from app.evidence import attach_evidence
p=ParagraphData('p','本文比较卷积网络和注意力网络的优点与局限。然后列举四种同类算法作为例子。',1)
s=SemanticChecker();calls=[]
def replies(*args):
 calls.append(args[0]);return ({'findings':[{'rule_id':7,'quote':p.text,'issue':'列举'}]} if len(calls)==1 else {'findings':[]}),None
s._call_llm=replies
assert not s._grounded_review(7,[p],'test','local')[0] and len(calls)==2
path=next(Path('F:/auto-review/occurrence_audit').glob('*刘潇潇.pkl'),None)
if path:
 tree=pickle.loads(path.read_bytes());p=next(p for p in tree.all_body_paragraphs if 'VM-Unet[109]' in p.text)
 begin=p.text.index('VM-Unet[109]');quote=p.text[begin:begin+80].replace('  ',' ')
 s._call_llm=lambda *args:({'findings':[{'rule_id':7,'quote':quote,'issue':'test'}]},None)
 fs,_=s._grounded_review(7,[p],'test','local');assert fs and fs[0].locations[0].text_offset is not None
 attach_evidence(tree,fs)
 assert fs[0].locations[0].page==23 and fs[0].locations[0].verified and fs[0].locations[0].bbox
 print('Cross-page semantic quote resolves to physical page 23')
print('Context recheck and semantic evidence-offset controls passed')
