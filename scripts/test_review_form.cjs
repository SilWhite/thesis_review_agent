const fs=require('fs'),vm=require('vm'),assert=require('assert');
const elements=new Map(),calls=[];
function el(selector){if(!elements.has(selector))elements.set(selector,{value:'',files:[],hidden:true,disabled:false,dataset:{}});return elements.get(selector);}
const context={document:{querySelector:el,querySelectorAll:()=>[]},setTimeout:()=>{},
 FormData:class{append(){}},ReviewEvidence:{},fetch:async(url,options={})=>{
  calls.push({url,body:options.body&&typeof options.body==='string'?JSON.parse(options.body):null});
  const result=url.endsWith('/review-decisions')?{revision:(JSON.parse(options.body).revision||0)+1}:url.endsWith('/documents')?(options.method?{id:'doc_test'}:[]):url.endsWith('/jobs')?(options.method?{id:'job_test'}:[]):{};
  return {ok:true,json:async()=>result};
 }};
vm.createContext(context);
const source=fs.readFileSync('app/static/app.js','utf8');
vm.runInContext(source.slice(0,source.lastIndexOf('init().catch')),context);
(async()=>{
 el('#files').files=[{name:'paper.pdf'}];el('#policies').files=[];
 el('#prompt').value='重点查看实验数据划分';el('#material').value='thesis';el('#degree').value='master';el('#language').value='zh-CN';
 vm.runInContext('modelAvailable=true',context);
 await el('#review-form').onsubmit({preventDefault(){}});
 const submit=calls.find(c=>c.url==='/api/v1/jobs'&&c.body);
 assert(submit&&submit.body.custom_prompt==='重点查看实验数据划分'&&submit.body.model_mode==='local');
 assert(!calls.some(c=>c.url.includes('/documents/text')));
 calls.length=0;el('#files').files=[];
 await el('#review-form').onsubmit({preventDefault(){}});
 assert.equal(calls.length,0);assert(el('#toast').textContent.includes('上传论文'));
 vm.runInContext('globalThis.state={jobId:"one",digest:"hash",excluded:new Set([0]),queue:Promise.resolve(),pending:0}',context);
 const first=vm.runInContext('saveReviewSelection(state)',context);
 vm.runInContext('state.excluded.add(1)',context);
 const second=vm.runInContext('saveReviewSelection(state)',context);
 await Promise.all([first,second]);
 const writes=calls.filter(c=>c.url.endsWith('/review-decisions'));
 assert.deepEqual(writes.map(c=>c.body.excluded_findings),[[0],[0,1]]);
 assert.deepEqual(writes.map(c=>c.body.revision),[0,1]);
 const html=fs.readFileSync('app/static/index.html','utf8');
 assert.equal((html.match(/<textarea/g)||[]).length,1);
 assert(html.includes('id="prompt" rows="6"')&&!html.includes('value="mock"')&&!html.includes('id="text"'));
 assert(!/DEMO|本地演示版|论文留在本机|填入测试材料/.test(html));
 console.log('Production form: focus field, local engine, no text upload, required file, serialized per-job decisions passed');
})().catch(e=>{console.error(e);process.exitCode=1});
