const {test}=require('node:test');const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../frontend/js/app.js'),'utf8');const refresh=source.slice(source.indexOf('async function refresh()'),source.indexOf('function searchTasks('));
function setup(request){const counts={render:0,timers:0,saved:0};const ctx=vm.createContext({loading:false,lastRefreshAt:0,viewEpoch:0,refreshFailures:0,
 S:{cur:'task',view:'pick',summaries:[],queue:{running:0},connectionLost:false},T:()=>({ri:0,loaded_round:0,revision:3}),request,installTask(){},syncPreviewState(){},
 persistPromptDraft:async()=>{counts.saved++},render(){counts.render++},softRender(){counts.render++},updTimers(){counts.timers++},toast(){},report(){},$:()=>null});
 vm.runInContext(refresh,ctx);return {ctx,counts}}
test('任务被另一窗口删除时返回列表，不误报服务断线',async()=>{
 const {ctx,counts}=setup(async url=>{if(url.startsWith('/tasks?'))return{tasks:[],queue:{running:0}};const e=new Error('deleted');e.status=404;throw e});
 await vm.runInContext('refresh()',ctx);assert.equal(ctx.S.cur,null);assert.equal(ctx.S.connectionLost,false);assert.equal(counts.saved,1);
});
test('摘要与修订号均未变化时不重建页面',async()=>{
 const {ctx,counts}=setup(async url=>url.startsWith('/tasks?')?{tasks:[],queue:{running:0}}:{unchanged:true});
 await vm.runInContext('refresh()',ctx);assert.equal(counts.render,0);assert.equal(counts.timers,1);
});
