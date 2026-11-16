const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {loadScripts}=require('./helpers/workbench.cjs');

function setup(request){
 const counts={render:0,timers:0,saved:0},calls=[];
 const ctx=vm.createContext({document:{addEventListener(){},querySelector(){return null},querySelectorAll(){return[]}},
  window:{addEventListener(){}},mockRequest:async(...args)=>{calls.push(args);return request(...args)},
  counts,setTimeout,clearTimeout});
 loadScripts(ctx,['views','app']);
 const run=source=>vm.runInContext(source,ctx);
 run(`request=(...args)=>mockRequest(...args);
  S={cur:'task',view:'pick',summaries:[],queue:{running:0},connectionLost:false,
     tasks:[{id:'task',ri:0,loaded_round:0,revision:3,rounds:[{params:{pids:[]},slots:[],sel:{}}]}]};
  persistPromptDraft=async()=>{counts.saved++};
  render=softRender=()=>{counts.render++};updTimers=()=>{counts.timers++};toast=report=()=>{};`);
 return {run,counts,calls};
}

test('任务被另一窗口删除时保存编辑并返回列表，不误报服务断线',async()=>{
 const {run,counts}=setup(async url=>{if(url.startsWith('/tasks?'))return{tasks:[],queue:{running:0}};const e=new Error('deleted');e.status=404;throw e});
 await run('refresh()');
 assert.equal(run('S.cur'),null);assert.equal(run('S.connectionLost'),false);assert.equal(run('S.view'),'form');
 assert.equal(counts.saved,1);assert.equal(run('loading'),false);
});

test('摘要与修订号未变时发送条件读取且不重建页面',async()=>{
 const {run,counts,calls}=setup(async url=>url.startsWith('/tasks?')?{tasks:[],queue:{running:0}}:{unchanged:true});
 await run('refresh()');
 assert.equal(calls[1][0],'/tasks/task?view=1&round=0&revision=3');
 assert.equal(counts.render,0);assert.equal(counts.timers,1);assert.equal(run('T().revision'),3);
});

test('菜单打开时安装新任务进度但保持操作中的菜单',async()=>{
 const {run,counts}=setup(async url=>url.startsWith('/tasks?')?{tasks:[{id:'task',revision:4}],queue:{running:1}}:
  {id:'task',ri:0,loaded_round:0,revision:4,rounds:[{params:{pids:[]},slots:[{id:'new',state:'done'}],sel:{}}]});
 run('S.menu="task"');await run('refresh()');
 assert.equal(counts.render,0);assert.equal(run('S.menu'),'task');assert.equal(run('T().revision'),4);
 assert.equal(run('T().rounds[0].slots[0].id'),'new');assert.equal(run('S.summaries[0].revision'),4);
});

test('学习机Logo配置页只轮询摘要，不加载旧任务详情或改变配置页',async()=>{
 const {run,calls}=setup(async()=>({tasks:[],queue:{running:0}}));
 run('S.view="learning-logo"');await run('refresh()');
 assert.equal(calls.length,1);assert(calls[0][0].startsWith('/tasks?summary=1'));
 assert.equal(run('S.view'),'learning-logo');assert.equal(run('T().revision'),3);
});

test('轮询失败后释放并发锁，连续失败显示断线，恢复成功后清除',async()=>{
 let offline=true;
 const {run,counts}=setup(async url=>{if(offline)throw new Error('offline');return url.startsWith('/tasks?')?{tasks:[],queue:{running:0}}:{unchanged:true}});
 await run('refresh()');assert.equal(run('S.connectionLost'),false);assert.equal(run('loading'),false);
 await run('refresh()');assert.equal(run('S.connectionLost'),true);assert.equal(run('loading'),false);
 offline=false;await run('refresh()');assert.equal(run('S.connectionLost'),false);assert.equal(run('refreshFailures'),0);
 assert(counts.render>0);
});
