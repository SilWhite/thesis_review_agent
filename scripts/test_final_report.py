"""Human decisions update every final-report section, preserving original evidence."""
import sys,json,copy,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
from app.final_report import report_digest,build_final_report
from app.review import markdown

fixture={'mode':'local','verdict':'存在重大问题','summary':'REMOVED_ISSUE old summary',
 'priority_actions':['REMOVED_ISSUE old priority'],
 'findings':[
  {'rule_id':2,'severity':'major','issue':'REMOVED_ISSUE','suggestion':'REMOVED_SUGGESTION','quote':'REMOVED_QUOTE','locations':[]},
  {'rule_id':2,'severity':'minor','issue':'保留的问题','suggestion':'保留的建议','quote':'保留的原文','locations':[]},
  {'rule_id':24,'severity':'minor','issue':'另一条问题','suggestion':'另一条建议','quote':'另一条原文','locations':[]}],
 'rule_matrix':[{'rule_id':2,'status':'发现问题','findings_count':2,'note':'REMOVED_ISSUE'},
                {'rule_id':24,'status':'发现问题','findings_count':1},
                {'rule_id':25,'status':'无法可靠判断','findings_count':0,'note':'仍需查看图片'}],
 'limitations':['参考规范需核对。']}
original=copy.deepcopy(fixture)
r=build_final_report(fixture,[0])
assert fixture==original and r['verdict']=='需修改' and len(r['findings'])==2
assert [f['source_finding_index'] for f in r['findings']]==[1,2]
assert r['rule_matrix'][0]['findings_count']==1
assert 'REMOVED_' not in json.dumps(r,ensure_ascii=False) and 'REMOVED_' not in markdown(r)
r=build_final_report(fixture,[0,1,2])
assert not r['findings'] and r['verdict']=='信息不足'
assert r['rule_matrix'][0]['status']=='问题提示已划除' and r['rule_matrix'][2]['status']=='无法可靠判断'
assert build_final_report({**fixture,'findings':[],'rule_matrix':[],'verdict':'信息不足'},[])['verdict']=='信息不足'
assert len(build_final_report(fixture,[])['findings'])==3
failed=copy.deepcopy(fixture);failed['rule_matrix'][0].update(status='执行失败',note='第9页读取失败。')
assert '第9页读取失败' in build_final_report(failed,[0,1])['rule_matrix'][0]['note']

with tempfile.TemporaryDirectory() as directory:
 app=create_app(Settings(data_dir=Path(directory)))
 store=app.state.store
 job='job_'+'a'*32;other='job_'+'b'*32;pending='job_'+'c'*32
 for name,status in [(job,'partial'),(other,'completed'),(pending,'running')]:
  folder=store.folder('jobs',name)
  store.write(folder,'state.json',{'id':name,'status':status,'created_at':'2026-11-13'})
  store.write(folder,'report.json',fixture)
  (folder/'report.md').write_text(markdown(fixture),encoding='utf-8')
 before=(store.folder('jobs',job)/'report.json').read_bytes(),(store.folder('jobs',job)/'report.md').read_bytes()
 with TestClient(app) as client:
  url=f'/api/v1/jobs/{job}'
  decisions=client.get(url+'/review-decisions').json()
  assert decisions=={'source_report_sha256':report_digest(fixture),'excluded_findings':[],'revision':0}
  body={**decisions,'excluded_findings':[0]}
  saved=client.post(url+'/review-decisions',json=body);assert saved.status_code==200
  body=saved.json()
  assert client.get(url+'/review-decisions').json()['excluded_findings']==[0]
  assert client.get(f'/api/v1/jobs/{other}/review-decisions').json()['excluded_findings']==[]
  response=client.post(url+'/final-report',json=body);assert response.status_code==200,response.text
  final=response.json();assert final['report']['findings'][0]['source_finding_index']==1
  body['revision']=final['revision']
  downloaded=client.get(final['download_url']);assert downloaded.status_code==200
  assert 'REMOVED_' not in downloaded.text and '最终报告' in downloaded.text
  old_download=downloaded.content
  all_removed=client.post(url+'/final-report',json={**body,'excluded_findings':[0,1,2]}).json()
  body['revision']=all_removed['revision']
  assert not all_removed['report']['findings'] and all_removed['download_url']!=final['download_url']
  assert client.get(final['download_url']).content==old_download
  assert client.get(final['download_url'].replace(job,other)).status_code==404
  for indices in ([3],[-1],[0,0],[True],['0'],[0.5]):
   assert client.post(url+'/final-report',json={**body,'excluded_findings':indices}).status_code in (400,422),indices
  assert client.post(url+'/final-report',json={**body,'source_report_sha256':'0'*64}).status_code==409
  newest=client.post(url+'/review-decisions',json={**body,'excluded_findings':[1]});assert newest.status_code==200
  assert client.post(url+'/review-decisions',json=body).status_code==409
  assert client.get(url+'/review-decisions').json()['excluded_findings']==[1]
  store.update_job(pending,status='running')
  assert client.post(f'/api/v1/jobs/{pending}/final-report',json=body).status_code==409
  assert before==((store.folder('jobs',job)/'report.json').read_bytes(),(store.folder('jobs',job)/'report.md').read_bytes())
print('Final report: filtering, summaries, matrix, stable evidence indices, persistence, immutable snapshots and API validation passed')
