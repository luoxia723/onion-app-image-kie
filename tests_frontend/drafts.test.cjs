const {test}=require('node:test');const assert=require('node:assert/strict');
const vm=require('node:vm');const fs=require('node:fs');const path=require('node:path');const {webcrypto}=require('node:crypto');
function context(request){
 const ctx=vm.createContext({crypto:webcrypto,structuredClone,TextEncoder,URLSearchParams,setTimeout:(fn,ms)=>{const timer=setTimeout(fn,ms);timer.unref();return timer},clearTimeout,
  window:{addEventListener(){}},document:{addEventListener(){},querySelector(){return null}},
  DEF_CTA:"立即体验",PLACEMENTS:[],
  S:{view:'form',draftId:'a'.repeat(32),draftRevision:1,draftSequence:1,draft:{image_form:'单图',t1:'本窗口最新输入'},formDrafts:{},drafts:[]},
  request,save(){},toast(){},R(){return null},report(){}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/js/views.js'),'utf8'),ctx);
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/js/drafts.js'),'utf8'),ctx);vm.runInContext('toast=()=>{}',ctx);return ctx;
}
test('另一窗口已修改草稿时，本窗口另存而不是覆盖或丢弃',async()=>{
 const calls=[];let first=true;
 const ctx=context(async(url,method,body)=>{
  calls.push({url,method,body});
  if(method==='PUT'&&first){first=false;const e=new Error('conflict');e.status=409;throw e}
  if(method==='GET'||method===undefined)return url==='/drafts'?{drafts:[]}:{draft:{t1:'其他窗口输入'},revision:2};
  return{revision:1};
 });
 await vm.runInContext('persistDraft()',ctx);
 const writes=calls.filter(c=>c.method==='PUT');assert.equal(writes.length,2);assert.notEqual(writes[0].url,writes[1].url);
 assert.equal(writes[1].body.draft.t1,'本窗口最新输入');assert.equal(ctx.S.draft.t1,'本窗口最新输入');
});
test('删除活动草稿后继续输入会创建新的草稿标识',()=>{
 const ctx=context(async()=>({}));ctx.S.draftId=null;
 vm.runInContext('scheduleDraftSave();clearTimeout(draftTimer)',ctx);
 assert.match(ctx.S.draftId,/^[a-f0-9]{32}$/);
});

function editor(request=async url=>url==='/bootstrap'?{product:{text:'产品资料',revision:2},form_defaults:{}}:{drafts:[]}){
 const listeners={};
 const ctx=vm.createContext({crypto:webcrypto,structuredClone,TextEncoder,URLSearchParams,setTimeout:(fn,ms)=>{const timer=setTimeout(fn,ms);timer.unref();return timer},clearTimeout,
  window:{addEventListener(name,fn){listeners[name]=fn}},history:{replaceState(){}},
  document:{addEventListener(){},querySelector(selector){return selector==='#main'?{scrollTop:0}:null}},mockRequest:request});
 for(const name of ['views','drafts','app']){
  const source=fs.readFileSync(path.join(__dirname,'../frontend/js/'+name+'.js'),'utf8');
  vm.runInContext(name==='app'?source.replace('\nboot();','\n'):source,ctx);
 }
 const run=code=>vm.runInContext(code,ctx);
 run('request=(...args)=>mockRequest(...args);render=()=>{};toast=()=>{};loadDraft(defParams())');
 return{ctx,run,listeners};
}
test('输入框聚焦时删除按钮按下不触发失焦，一次点击就发送DELETE',async()=>{
 const calls=[];const {ctx,run}=editor(async(url,method)=>{calls.push({url,method});return{drafts:[]}});
 run('S.draftId="active";S.draft.t1="正在编辑";S.drafts=[{id:"active",name:"草稿",draft:{image_form:"单图"}}]');
 const html=run('draftListHtml()'),button=html.match(/<button[^>]*aria-label="删除草稿"[^>]*>/)[0];
 let prevented=false;ctx.event={preventDefault(){prevented=true}};
 assert.match(button,/onmousedown="([^"]+)"/);
 run(button.match(/onmousedown="([^"]+)"/)[1]);
 if(!prevented)await run('persistDraft()');
 await run(button.match(/onclick="([^"]+)"/)[1]);
 assert.equal(prevented,true);assert.deepEqual(calls.filter(c=>c.method).map(c=>c.method),['DELETE']);
});
test('删除当前草稿后默认表单不另存，真正输入后才创建新草稿',async()=>{
 const calls=[];const {run}=editor(async(url,method)=>{calls.push({url,method});return{drafts:[],revision:1}});
 run('S.draftId="old";S.draft.t1="旧文案"');await run('removeDraft("old")');
 run('scheduleDraftSave();clearTimeout(draftTimer)');await run('persistDraft()');
 assert.equal(run('S.draftId'),null);assert.equal(calls.filter(c=>c.method==='PUT').length,0);
 run('S.draft.t1="新文案";scheduleDraftSave();clearTimeout(draftTimer)');await run('persistDraft()');
 assert.match(run('S.draftId'),/^[a-f0-9]{32}$/);assert.equal(calls.filter(c=>c.method==='PUT').length,1);
});
test('连续新建任务不落盘空表单，包括触碰已记忆的默认配置',async()=>{
 const calls=[];const {run}=editor(async(url,method)=>{
  calls.push({url,method});return url==='/bootstrap'?{product:{text:'产品资料',revision:2},form_defaults:{'三图':{channel:'应用商店',pids:['store']}}}:{drafts:[],revision:1};
 });
 run('S.draft.image_form="三图"');await run('newTask()');await run('newTask()');
 run('scheduleDraftSave();clearTimeout(draftTimer)');await run('persistDraft()');
 assert.equal(run('S.draftId'),null);assert.equal(calls.filter(c=>c.method==='PUT').length,0);
 assert.equal(run('S.draft.channel'),'应用商店');assert.equal(run('S.draft.image_form'),'三图');
 run('S.draft.s1="新短句";scheduleDraftSave();clearTimeout(draftTimer)');await run('persistDraft()');
 assert.equal(calls.filter(c=>c.method==='PUT').length,1);
});
test('新建任务复用已有空草稿，不复用有文案或正在编辑任务的草稿',async()=>{
 const opened=[];const {ctx,run}=editor();ctx.opened=opened;
 run('openDraft=async id=>opened.push(id);S.drafts=[{id:"copy",draft:{channel:"",t1:"标题"}},{id:"editing",editing_task_id:"task",draft:{channel:""}},{id:"empty",draft:{channel:"",image_form:"单图"}}]');
 await run('newTask()');await run('newTask()');assert.deepEqual(opened,['empty','empty']);
});
test('草稿副标题显示渠道和形式，无渠道时只显示待填写',()=>{
 const {run}=editor();run('S.drafts=[{id:"a",name:"A",draft:{channel:"应用商店",image_form:"三图"}},{id:"b",name:"B",draft:{channel:"信息流"}},{id:"c",name:"C",draft:{image_form:"单图"}}]');
 const html=run('draftListHtml()');assert(html.includes('应用商店 · 三图'));assert(html.includes('class="t2">信息流</div>'));assert(html.includes('class="t2">待填写</div>'));
});
test('列表读取完整草稿，保留渠道与非首行文案搜索，并可查到搜索外的空草稿',async()=>{
 const calls=[];const {run}=editor(async url=>{calls.push(url);return{drafts:[
  {id:'copy',name:'标题',draft:{channel:'应用商店',image_form:'单图',t2:'第二行搜索词'}},
  {id:'empty',name:'未命名草稿',draft:{channel:'',image_form:'单图'}},
 ]}});
 run('S.q="第二行搜索词"');await run('refreshDraftList()');
 assert.deepEqual(calls,['/drafts']);const html=run('draftListHtml()');
 assert(html.includes('应用商店 · 单图'));assert(!html.includes('未命名草稿'));assert.equal(run('S.drafts.length'),2);
});
test('已有空草稿输入文案后再新建，先保存当前内容再判断能否复用',async()=>{
 let stored={id:'empty',name:'未命名草稿',revision:1,draft:{channel:'',image_form:'单图'}};
 const {run}=editor(async(url,method,body)=>{
  if(method==='PUT'){stored={...stored,...body,revision:2};return{revision:2}}
  if(url==='/drafts')return{drafts:[stored]};
  if(url==='/drafts/empty')return stored;
  return{product:{text:'',revision:0},form_defaults:{}};
 });
 run('S.drafts=[{id:"empty",draft:{channel:"",image_form:"单图"}}];S.draftId="empty";S.draft.t1="刚输入的标题"');
 await run('newTask()');assert.equal(stored.draft.t1,'刚输入的标题');assert.equal(run('S.draft.t1'),'');assert.equal(run('S.draftId'),null);
});
test('空表单不会盖过其他形式中已填写的文案',async()=>{
 const {run}=editor();run('S.draft.image_form="三图";S.formDrafts={"单图":{t1:"保留的标题"}};scheduleDraftSave();clearTimeout(draftTimer)');
 assert.match(run('S.draftId'),/^[a-f0-9]{32}$/);
 const opened=[];const other=editor();other.ctx.opened=opened;
 other.run('openDraft=async id=>opened.push(id);S.drafts=[{id:"has-copy",draft:{channel:"",image_form:"三图"},form_drafts:{"单图":{t1:"保留的标题"}}}]');
 await other.run('newTask()');assert.deepEqual(opened,[]);
});
test('重新打开工作台时按最近任务形式读取服务端记忆的渠道配置',async()=>{
 const {ctx,run}=editor(async url=>url==='/bootstrap'?{
  placements:[],assets:{ips:[],logos:[],fonts:[],styles:[]},product:{text:'产品资料',revision:2},
  form_defaults:{'单图':{channel:'信息流'},'三图':{channel:'应用商店',pids:['store']}},
 }:{drafts:[]});
 ctx.location={hash:''};ctx.setInterval=()=>0;
 run('refresh=async()=>{S.summaries=[{image_form:"三图"}]}');await run('boot()');
 assert.equal(run('S.draft.image_form'),'三图');assert.equal(run('S.draft.channel'),'应用商店');assert.equal(run('S.draftId'),null);
});

test('删除当前草稿提供撤销，按新ID PUT恢复内存中的最新文案和其他形式内容',async()=>{
 const calls=[];let restored;
 const {ctx,run}=editor(async(url,method,body)=>{
  calls.push({url,method,body});if(url==='/drafts/old'&&!method)return{draft:{t1:'已保存内容'},revision:1};
  if(method==='PUT'){restored={id:url.split('/').at(-1),...body,revision:1};return restored}
  if(url==='/drafts')return{drafts:restored?[restored]:[]};return{};
 });ctx.setTimeout=()=>1;ctx.clearTimeout=()=>{};
 run('S.draftId="old";S.draft.t1="尚未自动保存的内容";S.formDrafts={"三图":{s1:"保留句子"}}');
 await run('removeDraft("old")');assert.equal(run('S.undo.draft.draft.t1'),'尚未自动保存的内容');
 run('openDraft=async id=>{S.draftId=id}');await run('undoDel()');
 const write=calls.find(c=>c.method==='PUT');assert(write);assert.notEqual(write.url,'/drafts/old');assert.equal(write.body.revision,0);
 assert.equal(write.body.draft.t1,'尚未自动保存的内容');assert.equal(write.body.form_drafts['三图'].s1,'保留句子');assert.equal(run('S.undo'),null);assert.equal(run('S.draftId'),restored.id);
});
test('自动保存只更新草稿列表、状态和标题，不重画品牌行',async()=>{
 let redraws=0;const writes=[];const {ctx,run}=editor(async()=>({drafts:[],revision:1}));ctx.redraw=()=>redraws++;
 ctx.document.querySelector=selector=>['#draft-list','#draft-status','#title'].includes(selector)?{set innerHTML(value){writes.push(selector)},set textContent(value){writes.push(selector)},classList:{toggle(){}}}:null;
 run('render=redraw;S.draftId="saved";S.draft.t1="标题"');await run('persistDraft()');assert.equal(redraws,0);assert(writes.includes('#draft-list'));assert(writes.includes('#draft-status'));
});
