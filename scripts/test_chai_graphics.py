"""The user's new real PDF: chart labels excluded, neighbouring prose retained."""
import sys,json,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.checkers import build_document_tree_from_pdf,DeterministicChecker,LayoutChecker
from app.evidence import attach_evidence
p=Path(sys.argv[1]);t=build_document_tree_from_pdf(p,p.name)
assert t.total_pages==91 and len(t.chapters)==5 and len(t.references)==93
assert sum(len(c.figures) for c in t.chapters)==67
body=re.sub(r'\s+','',t.body_text_only)
for text in ['PTM数据集','奖励模型训练阶段']:
 labels=[p for p in t.pages[26].paragraphs if p.text==text]
 assert labels and all(p.is_figure_text for p in labels),text
for text in ['图1-5所示','图3-1所示','图3-3所示','图3-5所示','图4-5所示','本节建立的中医数据集由两大部分组成']:
 assert text in body,text
for number in [32,33,35,37,38,39,40,42,65]:
 assert any(p.is_figure_text for p in t.pages[number-1].paragraphs),number
D,L=DeterministicChecker(),LayoutChecker();f2,_=D._check_rule_2_duplicate_sentences(t);f31,_=L._check_rule_31_short_paragraphs(t);f32,_=L._check_rule_32_orphan_character(t)
assert not f31 and not f32
assert not any(not re.search(r'[A-Za-z\u4e00-\u9fff]',f.quote) for f in f2)
assert f2 # Genuine prose candidates are still checked.
attach_evidence(t,f2);assert all(l.verified and l.bbox for f in f2 for l in f.locations)
f24,_=D._check_rule_24_figures_tables_unreferenced(t);assert len(f24)==1 and '2-6' in f24[0].quote
record={'paper':p.name,'pages':t.total_pages,'chapters':5,'references':93,'figure_captions':67,'R2':len(f2),'R31':len(f31),'R32':len(f32),'R24':len(f24),'all_R2_locations_verified':True,'figure_labels_and_adjacent_prose':'passed'}
if len(sys.argv)>2:Path(sys.argv[2]).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(record,ensure_ascii=False))
