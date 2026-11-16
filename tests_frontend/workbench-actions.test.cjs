const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function setup(){
 const timers=new Map(),calls=[],listeners={};
 let timerId=0;
 const ctx=vm.createContext({
  document:{addEventListener(name,fn){(listeners[name]??=[]).push(fn)},querySelector(){return null}},window:{addEventListener(){}},
  setTimeout(callback,delay){timers.set(++timerId,{callback,delay});return timerId},clearTimeout(id){timers.delete(id)},calls,
 });
 for(const name of ['views','workspace','production','app']){
  const source=fs.readFileSync(path.join(__dirname,'../frontend/js/'+name+'.js'),'utf8');
  vm.runInContext(name==='app'?source.replace('\nboot();','\n'):source,ctx);
 }
 vm.runInContext(`
  PLACEMENTS=['first','second','third'].map(id=>({id,platform:id,name:'单图',image_count:1,target_width:720,target_height:1559}));
  S.cur='task';S.view='pick';
  S.tasks=[{id:'task',ri:0,rounds:[{id:'round',params:{pids:['first','second','third']},sel:{},slots:PLACEMENTS.map(placement=>({id:placement.id,pid:placement.id,set:1,idx:1,state:'done'}))}]}];
  render=()=>{};softRender=()=>{};report=()=>{};toast=()=>{};
  action=async(name,data)=>{calls.push({name,...data});if(name==='adopt')R().sel[selectionKey(data.placement_id,data.set)]=data.adopted;return T()};
  pickPlacement(R());
 `,ctx);
 return{ctx,timers,calls,listeners,run:code=>vm.runInContext(code,ctx)};
}

test('单套勾选、取消、预览勾选和批量勾选都不切换版位',async()=>{
 const {run,timers,calls}=setup();
 await run('toggleSel(1,false,"first")');assert.equal(calls[0].name,'adopt');
 assert.equal(calls[0].placement_id,'first');assert.equal(run('S.pickPid'),'first');assert.equal(timers.size,0);
 await run('toggleSel(1,false,"first")');assert.equal(timers.size,0);
 await run('toggleSel(1,true,"first")');assert.equal(timers.size,0);
 run('action=async(name,data)=>{for(const group of data.sets)R().sel[selectionKey(group.placement_id,group.set)]=data.adopted}');
 await run('selectVisible(true)');assert.equal(run('S.pickPid'),'first');assert.equal(timers.size,0);
 await run('clearVisibleSelection()');
 assert.equal(run('S.pickPid'),'first');assert.equal(timers.size,0);
});

test('下一版位按钮沿目录顺序切换，包括生成中的版位，到最后禁用',()=>{
 const {run}=setup();run('R().slots[1].state="generating"');
 let html=run('viewSelectionFooter()');assert(!html.includes('auto-next'));assert(!html.includes('勾完自动跳到下一版位'));
 assert.match(html,/id="next-placement"[^>]*onclick="setPickPlacement\('second'\)"/);
 run(html.match(/id="next-placement"[^>]*onclick="([^"]+)"/)[1]);assert.equal(run('S.pickPid'),'second');
 html=run('viewSelectionFooter()');run(html.match(/id="next-placement"[^>]*onclick="([^"]+)"/)[1]);
 assert.equal(run('S.pickPid'),'third');assert.match(run('viewSelectionFooter()'),/id="next-placement"[^>]*disabled/);
});

test('方向键上下切换版位，到边界保持原位',()=>{
 const {run,listeners}=setup();let prevented=0;
 const key=key=>listeners.keydown.forEach(fn=>fn({key,target:{closest(){return null}},preventDefault(){prevented++}}));
 key('ArrowUp');assert.equal(run('S.pickPid'),'first');
 key('ArrowDown');assert.equal(run('S.pickPid'),'second');
 key('ArrowDown');key('ArrowDown');assert.equal(run('S.pickPid'),'third');
 key('ArrowUp');assert.equal(run('S.pickPid'),'second');assert.equal(prevented,5);
});

test('输入控件、可编辑内容、大图、配置弹层和配置页中方向键不换版位',()=>{
 for(const state of ['S.pv="image"','S.cfgOpen=true','S.view="form"','S.navigationPending=true']){
  const {run,listeners}=setup();run(state);let prevented=false;
  listeners.keydown.forEach(fn=>fn({key:'ArrowDown',target:{closest(){return null}},preventDefault(){prevented=true}}));
  assert.equal(run('S.pickPid'),'first',state);assert.equal(prevented,false,state);
 }
 for(const control of ['input','textarea','select','[contenteditable]']){
  const {run,listeners}=setup();let prevented=false;
  listeners.keydown.forEach(fn=>fn({key:'ArrowDown',target:{closest(selector){return selector.split(',').includes(control)?{}:null}},preventDefault(){prevented=true}}));
  assert.equal(run('S.pickPid'),'first',control);assert.equal(prevented,false,control);
 }
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
test('普通图包导出只在能力允许和用户明确选择时传Logo版本，不触发生图',async()=>{
 const {ctx,run}=setup(),requests=[];ctx.capture=(...args)=>{requests.push(args);return Promise.resolve({filename:'variant.zip'})};
 run('request=capture;refresh=async()=>{};R().delivery={incomplete_sets:0,ready_sets:1,can_export:true,has_changes:false,matching_version:"v001"};R().logo_export_capability={editable:true,asset_ids:["learning.logo.black","learning.logo.white-app"]}');
 run('setOrdinaryExportLogo("learning.logo.white-app")');assert(run('viewSelectionFooter()').includes('id="save-selected"'));
 await run('dlAll(false)');assert.equal(requests[1][2].logo_asset_id,'learning.logo.white-app');assert(requests.every(args=>args[0].includes('package')));
 requests.length=0;run('R().logo_export_capability={editable:false,reason:"旧图片已将Logo画入内容，不能直接替换"}');
 assert.equal(run('ordinaryLogoExportValue(R())'),'');assert(run('viewSelectionFooter()').includes('旧图片已将Logo画入内容，不能直接替换'));assert.match(run('viewSelectionFooter()'),/id="ordinary-export-logo"[^>]*disabled/);
 await run('dlAll(false)');assert(!Object.hasOwn(requests[1][2],'logo_asset_id'));
});

test('轮询后可定位原来的套图复选框和版位目录焦点',()=>{
 const {run}=setup();
 assert.equal(run('trapRef({dataset:{sel:"first::1"}})'),'[data-sel="first::1"]');
 assert.equal(run('trapRef({dataset:{pickPlacement:"first"}})'),'[data-pick-placement="first"]');
});
