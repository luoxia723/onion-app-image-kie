const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const {webcrypto}=require('node:crypto');const root=path.join(__dirname,'..');
function setup(request=async()=>({drafts:[]})){
 const ctx=vm.createContext({structuredClone,crypto:webcrypto,TextEncoder,setTimeout,clearTimeout,
  document:{addEventListener(){},querySelector(){return {disabled:false,scrollTop:0,focus(){}}},querySelectorAll(){return []}},
  window:{addEventListener(){}},history:{replaceState(){}},mockRequest:request});
 for(const f of ['views','drafts','prompt-drafts','app']){
  let s=fs.readFileSync(path.join(root,'frontend/js/'+f+'.js'),'utf8');if(f==='app')s=s.replace('\nboot();','\n');vm.runInContext(s,ctx);
 }
 vm.runInContext('request=(...args)=>mockRequest(...args);render=()=>{};softRender=()=>{};save=()=>{};toast=()=>{};report=()=>{};formIssue=()=>null;updSum=()=>{}',ctx);
 return {ctx,run:s=>vm.runInContext(s,ctx)};
}
test('提交期间锁定配置，失败后恢复编辑并保留原草稿',async()=>{
 let release;const {ctx,run}=setup(async()=>{throw Error('提交失败')});
 ctx.waitSave=()=>new Promise(r=>release=r);
 run('CFG={planningKey:true,simulation:true};S.draftId="draft";S.draft.t1="原标题";persistDraft=waitSave');
 const pending=run('startGen()');
 assert.equal(run('S.submitting'),true);
 run('setF("t1","等待期间修改")');assert.equal(run('S.draft.t1'),'原标题');
 release();await pending;
 assert.equal(run('S.submitting'),false);assert.equal(run('S.draftId'),'draft');
 run('setF("t1","失败后修改")');assert.equal(run('S.draft.t1'),'失败后修改');
});
test('任务请求乱序返回时，只打开最后点击的任务',async()=>{
 const waiting={};const {run}=setup(url=>new Promise(r=>waiting[url]=r));
 run('persistDraft=async()=>{};persistPromptDraft=async()=>{}');
 const a=run('openTask("A")');await new Promise(r=>setImmediate(r));
 const b=run('openTask("B")');await new Promise(r=>setImmediate(r));
 waiting['/tasks/B?view=1']({id:'B',rounds:[{}],loaded_round:0});await b;
 waiting['/tasks/A?view=1']({id:'A',rounds:[{}],loaded_round:0});await a;
 assert.equal(run('S.cur'),'B');
 assert.equal(run('S.navigationPending'),false);
});
test('打开新任务期间旧表单不可修改，请求失败后解除加载锁',async()=>{
 let reject;const {run}=setup(()=>new Promise((r,j)=>reject=j));
 run('persistDraft=async()=>{};persistPromptDraft=async()=>{};S.draft.t1="原草稿"');
 const pending=run('openTask("missing")');await new Promise(r=>setImmediate(r));
 run('setF("t1","切换期间输入")');assert.equal(run('S.draft.t1'),'原草稿');assert.equal(run('S.navigationPending'),true);
 reject(Error('not found'));await assert.rejects(pending);assert.equal(run('S.navigationPending'),false);
});
test('同张图片的版本请求乱序返回时，保持最后选择的版本',async()=>{
 const waiting={};const {run}=setup(url=>new Promise(r=>waiting[url.split('&v=')[1]]=r));
 run('S.cur="T";S.tasks=[{id:"T",ri:0,rounds:[{}]}]');
 const a=run('openPv("image",1)');await new Promise(r=>setImmediate(r));
 const b=run('openPv("image",2)');await new Promise(r=>setImmediate(r));
 waiting[2]({att:2,round_index:0});await b;waiting[1]({att:1,round_index:0,is_historical:true});await a;
 assert.equal(run('S.pvDetails.att'),2);
});
test('搜索副标题时保留后台匹配的摘要，不再二次过滤丢弃',()=>{
 const {run}=setup();run('S.q="副标题独有词";S.summaries=[{is_summary:true,id:"task",name:"主标题",pkg:"APP",category:"attention",round_count:1}];summaryRow=t=>"MATCH:"+t.id');
 assert.equal(run('taskList()'),'MATCH:task');
});
test('草稿列表可以展开到第51份，摘要无需携带全部资料',()=>{
 const {run}=setup();run('S.drafts=Array.from({length:51},(_,i)=>({id:String(i),name:"草稿"+i,draft:{image_form:"单图"}}))');
 assert(!run('draftListHtml()').includes('草稿50'));
 run('showMoreDrafts();showMoreDrafts()');assert(run('draftListHtml()').includes('草稿50'));
});

test('跨渠道旧配置提交时移除channel字段，保留全部所选版位',async()=>{
 const calls=[];const {run}=setup(async(url,method,body)=>{calls.push({url,method,body});if(url==='/tasks')return{id:'new',rounds:[{slots:[],params:body.params}]};return{drafts:[]}});
 run('CFG={planningKey:true,simulation:true};S.draft.channel=["应用商店","信息流"];S.draft.pids=["huawei","weibo"];persistDraft=async()=>{}');await run('startGen()');
 const submitted=calls.find(c=>c.url==='/tasks');assert(!Object.hasOwn(submitted.body.params,'channel'));assert.deepEqual(Array.from(submitted.body.params.pids),['huawei','weibo']);
});
test('任务直接删除并能撤销，无浏览器确认，任务摘要同步移除',async()=>{
 const calls=[];const {ctx,run}=setup(async(url,method)=>{calls.push({url,method});return{id:'task',rounds:[{}],summary:{id:'task',name:'任务'}}});
 ctx.confirm=()=>{throw Error('不应调用confirm')};ctx.setTimeout=()=>1;ctx.clearTimeout=()=>{};
 run('S.cur="task";S.tasks=[{id:"task",rounds:[{}]}];S.summaries=[{id:"task"}]');await run('delTask("task")');
 assert.equal(run('S.tasks.length'),0);assert.equal(run('S.summaries.length'),0);assert.equal(run('S.undo.id'),'task');assert.equal(calls[0].method,'DELETE');
 await run('undoDel()');assert.equal(run('S.cur'),'task');assert.equal(run('S.view'),'pick');assert.equal(run('S.undo'),null);assert.equal(calls[1].url,'/tasks/task/restore');
});
test('打开任务期间主区域用骨架，失败或较旧请求结束不残留加载状态',async()=>{
 let reject;const {run}=setup(()=>new Promise((resolve,fail)=>reject=fail));run('persistDraft=async()=>{};persistPromptDraft=async()=>{}');
 const pending=run('openTask("loading")');await new Promise(setImmediate);
 assert.equal(run('S.openingTask'),'loading');assert(run('viewPick()').includes('pick-skeleton'));assert(!run('viewHead()').includes('正在打开，请稍候'));
 reject(Error('offline'));await assert.rejects(pending);assert.equal(run('S.openingTask'),null);
});

test('单一任务列表保留生成中、待挑选和历史任务，不按旧分组重复展示',()=>{
 const {run}=setup();run('S.summaries=[{is_summary:true,id:"a",name:"生成中",category:"running",status:"正在处理",done:0,total:1},{is_summary:true,id:"b",name:"待挑选",category:"attention",status:"待挑选",done:1,total:1},{is_summary:true,id:"c",name:"已保存",category:"history",status:"已保存 v001",done:1,total:1}];S.q=""');
 const html=run('taskList()');for(const id of ['a','b','c'])assert.equal((html.match(new RegExp('data-task="'+id+'"','g'))||[]).length,1);
 assert(!html.includes('>历史<'));assert(!html.includes('>待挑选与处理<'));assert(html.includes('>任务<'));
});
