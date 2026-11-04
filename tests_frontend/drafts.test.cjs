const {test}=require('node:test');const assert=require('node:assert/strict');
const vm=require('node:vm');const fs=require('node:fs');const path=require('node:path');const {webcrypto}=require('node:crypto');
function context(request){
 const ctx=vm.createContext({crypto:webcrypto,structuredClone,TextEncoder,setTimeout,clearTimeout,
  window:{addEventListener(){}},document:{querySelector(){return null}},
  S:{view:'form',draftId:'a'.repeat(32),draftRevision:1,draftSequence:1,draft:{image_form:'单图',t1:'本窗口最新输入'},formDrafts:{},drafts:[]},
  request,save(){},toast(){},R(){return null},report(){}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/js/drafts.js'),'utf8'),ctx);return ctx;
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
