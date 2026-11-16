import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.checkers import build_document_tree_from_pdf,DeterministicChecker,LayoutChecker
from app.evidence import attach_evidence
D=DeterministicChecker();L=LayoutChecker();records=[]
for key,path,starts,ends,count,fixed in [
 ('liu',Path(sys.argv[1]),[11,29,49,69,91,111],[27,48,68,89,109,113],210,{'124'}),
 ('han',Path(sys.argv[2]),[15,29,52,66,83,95,109],[28,51,65,82,94,108,111],196,{'5'})]:
 tree=build_document_tree_from_pdf(path,path.name)
 assert [c.page for c in tree.chapters]==starts,[(c.title,c.page) for c in tree.chapters]
 assert [c.end_page for c in tree.chapters]==ends
 assert len(tree.references)==count
 f29,a29=L._check_rule_29_blank_space(tree);assert not f29,f29
 f24,a24=D._check_rule_24_figures_tables_unreferenced(tree);assert not f24,[(f.quote,f.issue) for f in f24]
 f19,a19=D._check_rule_19_reference_incomplete(tree)
 assert not {f.block_id.removeprefix('ref_') for f in f19}&fixed
 assert all(r.segments for r in tree.references)
 attach_evidence(tree,f19)
 assert all(loc.verified and loc.bbox and loc.context for f in f19 for loc in f.locations)
 record={'paper':key,'chapters':[[c.title,c.page,c.end_page] for c in tree.chapters],'references':len(tree.references),'R29':len(f29),'R24':len(f24),'R19':len(f19)}
 records.append(record);print(json.dumps(record,ensure_ascii=False),flush=True)
Path(sys.argv[3]).write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
print('Latest two thesis regressions passed')
