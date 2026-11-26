const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
function setup(){
 const round={id:'r1',planning_status:'running',stopped:false,sel:{},pending_placements:[],params:{pids:['oppo'],sets:1,ip:'none'},slots:[
  {id:'one',first_id:'one',pid:'oppo',set:1,idx:1,state:'queued',plan_ready:false},
  {id:'two',first_id:'one',pid:'oppo',set:1,idx:2,state:'queued',plan_ready:false}]};
 const task={id:'task',pkg:'任务',ri:0,rounds:[round],pkgs:[]};
 const ctx=vm.createContext({document:{addEventListener(){},querySelector(){return null}},PLACEMENTS:[{id:'oppo',platform:'OPPO',name:'双图',image_count:2,target_width:474,target_height:768}],IPS:[],VLAB:{queued:'等待中',generating:'生成中',stopped:'已停止'},S:{view:'pick',tab:'all',pf:'all',cur:'task',tasks:[task]},blocked:()=>false});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/js/views.js'),'utf8'),ctx);
 ctx.round=round;vm.runInContext('imgOf=()=>""',ctx);return ctx;
}
test('规划等待直接显示看样台，顶栏收纳真实阶段和可离开页面的边界',()=>{
 const ctx=setup(),html=vm.runInContext('viewHead()',ctx),pick=vm.runInContext('viewPick()',ctx);
 assert(html.includes('正在规划画面'));
 assert(html.includes('phase-dot'));
 assert(html.includes('可以切换任务或关闭网页'));
 assert(html.includes('保持本机服务运行'));
 assert(pick.includes('pick-workbench'));assert(pick.includes('data-slot="one"'));assert(pick.includes('data-slot="two"'));
 assert(!pick.includes('work-status'));assert(!pick.includes('wait-spinner'));
});
test('规划中的占位图与等待图 1 区分显示',()=>{
 const ctx=setup();let html=vm.runInContext('cellHtml(R(),R().slots[0],132)',ctx);
 assert(html.includes('规划中'));
 ctx.round.slots.forEach(s=>s.plan_ready=true);ctx.round.planning_status='done';ctx.round.slots[0].state='generating';
 html=vm.runInContext('cellHtml(R(),R().slots[1],132)',ctx);assert(html.includes('等图 1'));assert(html.includes('cell wait'));
});
test('全部排队时头部仍显示阶段和完成数量',()=>{
 const ctx=setup(),html=vm.runInContext('viewHead()',ctx);
 assert(html.includes('正在规划画面'));
 assert(html.includes('0 / 2'));
});
test('停止后仍有已提交图片时不谎称所有任务结束',()=>{
 const ctx=setup();ctx.round.stopped=true;ctx.round.planning_status='stopped';ctx.round.slots[0].state='generating';ctx.round.slots[1].state='stopped';
 const html=vm.runInContext('viewHead()',ctx);assert(html.includes('已提交图片仍在生成'));assert(html.includes('已停止后续'));
});
test('全部完成时不再显示后台运行提示',()=>{
 const ctx=setup();ctx.round.planning_status='done';ctx.round.slots.forEach(s=>s.state='done');
 const html=vm.runInContext('viewHead()',ctx);assert(!html.includes('可以切换任务或关闭网页'));
});
test('连接失效时不继续承诺任务正在后台执行',()=>{
 const ctx=setup();ctx.S.connectionLost=true;
 const html=vm.runInContext('viewWorkStatus(R())',ctx);
 assert(html.includes('暂时无法连接本机服务'));
 assert(html.includes('当前显示上次进度'));
 assert(!html.includes('wait-spinner'));
 assert(!html.includes('后台会继续'));
});
test('图 1 与分支明确显示不同重出范围，有原任务号时只恢复查询',()=>{
 const ctx=setup();ctx.round.planning_status='done';ctx.round.slots.forEach(s=>s.state='done');
 let retry=vm.runInContext('imageRetry(R(),R().slots[0])',ctx);assert.equal(retry.label,'重出图 1 及后续图');
 retry=vm.runInContext('imageRetry(R(),R().slots[1])',ctx);assert.equal(retry.label,'重出本张');assert(retry.note.includes('继续引用'));
 ctx.round.slots[1].state='failed';ctx.round.slots[1].kie_recovery_action='resume';
 const html=vm.runInContext('cellHtml(R(),R().slots[1],132)',ctx);assert(html.includes('resumeImage'));assert(!html.includes('onclick="redo('));
 retry=vm.runInContext('imageRetry(R(),R().slots[1])',ctx);assert.equal(retry.label,'恢复查询');
});
test('图 1 失败时分支按钮只定位图 1，不隐式重出整套',()=>{
 const ctx=setup();ctx.round.slots[0].state='failed';ctx.round.slots[1].state='blocked_first_failed';
 const html=vm.runInContext('cellHtml(R(),R().slots[1],132)',ctx);assert(html.includes('查看图 1'));assert(html.includes("openPv('one')"));assert(!html.includes('onclick="redo('));
});
