import sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.schemas import Finding,EvidenceLocation,Assessment
from app.checkers.document_model import ThesisDocumentTree,PageData,ParagraphData
from app.evidence import attach_evidence,render_evidence_page
from app.review import validate_evidence,markdown
p=ParagraphData('p','开始文字，共同的重复内容在这里。后续文字。',1,bbox=(70,100,500,130))
tree=ThesisDocumentTree('x.pdf',pages=[PageData(1,600,800,paragraphs=[p])])
f=Finding(rule_id=2,quote='共同的重复内容',issue='重复',suggestion='核对',locations=[EvidenceLocation(page=1,quote=p.text)])
attach_evidence(tree,[f]);assert f.locations[0].verified and f.locations[0].highlight_texts==['共同的重复内容']
a=Assessment(verdict='需修改',summary='test',findings=[f],priority_actions=[])
validate_evidence(a,[{'id':'unrelated','text':'不相关文字','location':'第 1 页'}]);assert not f.block_id
assert f.status=='supported'
bad=Finding(rule_id=2,quote='不存在的原句',issue='test',suggestion='test',locations=[EvidenceLocation(page=1,quote='不存在的原句')])
a.findings=[bad];validate_evidence(a,[{'id':'unrelated','text':'不相关文字','page':1}]);assert not bad.block_id and bad.status=='pending_verification'
assert '共同的重复内容' in markdown({'findings':[f.model_dump()]})
# Read an existing PDF; never alter it while making the preview.
source=Path('tests/fixtures/cross_page.pdf')
original=source.read_bytes();png=render_evidence_page(source,{'page':1,'bbox':[70,100,500,150]})
assert png.startswith(b'\x89PNG') and source.read_bytes()==original
Path('evidence-preview-test.png').write_bytes(png)
print('Evidence location, false-location rejection and read-only PDF preview tests passed')
