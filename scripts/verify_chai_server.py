import json,zipfile,hashlib,shutil,subprocess,sys,time
from pathlib import Path
root=Path('/data01/amax/thesis_review_chai_20261112');root.mkdir(exist_ok=True);live=Path('/data01/amax/thesis_review_agent');candidate=root/'candidate'
zipfile.ZipFile('/tmp/thesis_chai_release.zip').extractall(candidate)
base=json.loads((candidate/'baseline-manifest.json').read_text())
assert all(hashlib.sha256((live/p).read_bytes()).hexdigest()==h for p,h in base.items()),'Live source changed since baseline'
if not (root/'app_before').exists():shutil.copytree(live/'app',root/'app_before')
manifest=json.loads((candidate/'manifest.json').read_text());assert all(hashlib.sha256((candidate/p).read_bytes()).hexdigest()==h for p,h in manifest.items())
def document(job):
 req=json.loads((live/'data/jobs'/job/'request.json').read_text());return live/'data/documents'/req['document_ids'][0]/'source.pdf'
chai=document('job_cfd6efb0f3a44b54a7c2e3aa4bb2bb1f');liu=document('job_b5730a1f2a6c47e6b6858a6354b01c74');han=document('job_c93410e283c547b1bd51a163ac8cd5cd');mo=document('job_d8130ce82ef3455ba9bc2ae5500ee496')
tests=[['test_graphic_text_boundaries.py'],['test_review_regressions.py'],['test_layout_region_controls.py'],['test_structure_and_citations.py'],['test_embedded_fragments.py'],['test_page_continuity.py'],['test_formula_recovery.py'],['test_evidence.py'],['test_evidence_api.py'],['test_duplicate_occurrences.py'],['test_toc_transitions.py'],['rule_case_matrix.py',str(root/'rule-matrix.json')],['test_chai_graphics.py',str(chai),str(root/'real-paper-regression.json')],['test_latest_theses.py',str(liu),str(han),str(root/'previous-theses-regression.json')],['test_mokanghua_regressions.py',str(mo)]]
records=[]
for name,*args in tests:
 result=subprocess.run([sys.executable,str(candidate/'scripts'/name),*args],cwd=candidate,capture_output=True,text=True)
 records.append({'script':name,'returncode':result.returncode,'output':result.stdout[-2000:],'stderr':result.stderr[-2000:]})
 (root/'cpu-test-receipt.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
 print(name,result.returncode,flush=True);assert result.returncode==0,records[-1]
print('All candidate checks passed; original PDF SHA256 '+hashlib.sha256(chai.read_bytes()).hexdigest(),flush=True)
