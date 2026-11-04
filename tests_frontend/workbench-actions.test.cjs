const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function setup(){
 const timers=new Map(),saved=new Map(),calls=[];
 let timerId=0;
 const ctx=vm.createContext({
  document:{addEventListener(){},querySelector(){return null}},window:{addEventListener(){}},
  localStorage:{setItem(key,value){saved.set(key,value)},getItem(key){return saved.get(key)??null}},
  setTimeout(callback,delay){timers.set(++timerId,{callback,delay});return timerId},clearTimeout(id){timers.delete(id)},calls,
 });
 for(const name of ['views','app']){
  const source=fs.readFileSync(path.join(__dirname,'../frontend/js/'+name+'.js'),'utf8');
  vm.runInContext(name==='app'?source.replace('\nboot();','\n'):source,ctx);
 }
 vm.runInContext(`
  PLACEMENTS=['first','second','third'].map(id=>({id,platform:id,name:'单图',image_count:1,target_width:720,target_height:1559}));
  S.cur='task';S.view='pick';S.autoNext=true;
  S.tasks=[{id:'task',ri:0,rounds:[{id:'round',params:{pids:['first','second','third']},sel:{},slots:PLACEMENTS.map(placement=>({id:placement.id,pid:placement.id,set:1,idx:1,state:'done'}))}]}];
  render=()=>{};softRender=()=>{};report=()=>{};toast=()=>{};
  action=async(name,data)=>{calls.push({name,...data});if(name==='adopt')R().sel[selectionKey(data.placement_id,data.set)]=data.adopted;return T()};
  pickPlacement(R());
 `,ctx);
 return{ctx,timers,saved,calls,run:code=>vm.runInContext(code,ctx)};
}

test('勾选成功后400毫秒跳过已选版位，定位下一待选版位',async()=>{
 const {run,timers,calls}=setup();run('R().sel["second::1"]=true');
 await run('toggleSel(1,false,"first")');
 assert.equal(calls[0].name,'adopt');assert.equal(calls[0].placement_id,'first');
 assert.equal(run('S.pickPid'),'first');assert.equal(timers.size,1);
 const timer=[...timers.values()][0];assert.equal(timer.delay,400);timer.callback();
 assert.equal(run('S.pickPid'),'third');
});

test('开关写入localStorage，关闭时取消待执行跳转',async()=>{
 const {run,timers,saved}=setup();await run('toggleSel(1,false,"first")');assert.equal(timers.size,1);
 run('setAutoNext(false)');assert.equal(saved.get('onion.pick.autoNext'),'false');assert.equal(timers.size,0);
 await run('toggleSel(1,false,"second")');assert.equal(timers.size,0);
 run('setAutoNext(true)');assert.equal(saved.get('onion.pick.autoNext'),'true');
});

test('首次启动默认开启自动跳转，重新启动读取已保存的关闭偏好',()=>{
 const initial=setup();initial.run('S.autoNext=false;request=()=>new Promise(()=>{});boot()');assert.equal(initial.run('S.autoNext'),true);
 const restored=setup();restored.saved.set('onion.pick.autoNext','false');
 restored.run('request=()=>new Promise(()=>{});boot()');assert.equal(restored.run('S.autoNext'),false);
});

test('取消勾选、请求失败和预览内勾选都不自动跳转',async()=>{
 const {run,timers}=setup();run('R().sel["first::1"]=true');await run('toggleSel(1,false,"first")');assert.equal(timers.size,0);
 run('action=async()=>{throw Error("offline")}');await run('toggleSel(1,false,"first")');assert.equal(timers.size,0);
 run('action=async(name,data)=>{R().sel[selectionKey(data.placement_id,data.set)]=data.adopted}');
 await run('toggleSel(1,true,"first")');assert.equal(timers.size,0);
});

test('手动换版位和跨任务导航取消跳转，换轮或打开弹层不误跳',async()=>{
 for(const mutation of ['setPickPlacement("third")','beginNavigation()','R().id="another-round"','S.pv="image"','S.view="form"']){
  const {run,timers}=setup();await run('toggleSel(1,false,"first")');const callback=[...timers.values()][0].callback;
  run(mutation);const placement=run('S.pickPid');callback();assert.equal(run('S.pickPid'),placement,mutation);
 }
});

test('只有尚在生成的版位时不跳转，批量勾选复用同一延时规则',async()=>{
 const {run,timers}=setup();run('R().slots[1].state="generating";R().sel["third::1"]=true');
 await run('toggleSel(1,false,"first")');[...timers.values()][0].callback();assert.equal(run('S.pickPid'),'first');
 run('R().slots[1].state="done";action=async(name,data)=>{for(const group of data.sets)R().sel[selectionKey(group.placement_id,group.set)]=data.adopted}');
 await run('selectVisible(true)');[...timers.values()].at(-1).callback();assert.equal(run('S.pickPid'),'second');
});

test('生成失败补齐和保存只提交原有接口参数',async()=>{
 const {run,calls}=setup();await run('repairSet("second",1)');await run('addVariant("first")');await run('stopRest()');
 assert.deepEqual(calls.map(call=>call.name),['repair-set','add-variant','stop']);
 assert.equal(calls[0].placement_id,'second');assert.equal(calls[0].set,1);
 const requests=[];
 const context=setup();
 context.ctx.capture=(...args)=>{requests.push(args);return Promise.resolve({filename:'v001.zip'})};
 context.run('request=capture;R().delivery={incomplete_sets:1};refresh=async()=>{}');
 await context.run('dlAll(true)');
 assert(requests[0][0].endsWith('&ready_only=1'));assert.equal(requests[1][2].ready_only,true);
});

test('轮询后可定位原来的套图复选框和版位目录焦点',()=>{
 const {run}=setup();
 assert.equal(run('trapRef({dataset:{sel:"first::1"}})'),'[data-sel="first::1"]');
 assert.equal(run('trapRef({dataset:{pickPlacement:"first"}})'),'[data-pick-placement="first"]');
});
