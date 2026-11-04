const {test}=require('node:test');const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');const path=require('node:path');
function setup(request){
 const image={id:'x'.repeat(32),att:2,prompt:'当前图片实际提示词'};
 const ctx=vm.createContext({setTimeout,clearTimeout,TextEncoder,DRAFT_EDITOR:'window-one',window:{addEventListener(){}},document:{querySelector(){return null}},$:()=>null,
 S:{cur:'task',promptDraft:{id:image.id,att:2,value:'手动修改\n无需固定格式',sequence:0,dirty:true}},request,curPvSlot:()=>image,report(){},render(){}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/js/prompt-drafts.js'),'utf8'),ctx);return {ctx,image};
}
test('保存提示词草稿不会覆盖成图实际提示词，也不会调用生图',async()=>{
 const calls=[];const {ctx,image}=setup(async(...args)=>{calls.push(args);return {}});
 await vm.runInContext('persistPromptDraft()',ctx);
 assert.equal(image.prompt,'当前图片实际提示词');assert.equal(calls.length,1);assert.equal(calls[0][1],'PUT');
 assert(calls[0][0].includes('/prompt-drafts/'));assert.equal(calls[0][2].text,'手动修改\n无需固定格式');assert.equal(ctx.S.promptDraft.dirty,false);
});
test('草稿保存失败时保留本窗口内容与未保存标记',async()=>{
 const {ctx}=setup(async()=>{throw new Error('offline')});
 await assert.rejects(vm.runInContext('persistPromptDraft()',ctx));assert.equal(ctx.S.promptDraft.value,'手动修改\n无需固定格式');assert.equal(ctx.S.promptDraft.dirty,true);
});
