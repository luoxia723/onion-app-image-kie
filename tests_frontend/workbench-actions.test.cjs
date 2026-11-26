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
 assert.equal(requests.length,1);assert.equal(requests[0][0],'/tasks/task/packages');assert.equal(requests[0][1],'POST');assert.equal(requests[0][2].ready_only,true);
});
test('普通图包按成品直接保存，无需选择统一Logo款式',async()=>{
 const {ctx,run}=setup(),requests=[];ctx.capture=(...args)=>{requests.push(args);return Promise.resolve({filename:'current.zip'})};
 run('request=capture;refresh=async()=>{};R().delivery={incomplete_sets:0,ready_sets:1,can_export:true,has_changes:false,matching_version:"v001"}');
 const html=run('viewSelectionFooter()');assert(html.includes('已保存 v001'));assert(!html.includes('ordinary-export-logo'));
 await run('dlAll(false)');assert.equal(requests.length,1);assert(!Object.hasOwn(requests[0][2],'logo_asset_id'));assert.equal(requests[0][0],'/tasks/task/packages');
});

test('普通成品提供逐张切换 Logo，发送当前版本和款式校验值',async()=>{
 const {ctx,run,calls}=setup();ctx.persistPromptDraft=async()=>{};
 run('Object.assign(R().slots[0],{att:2,sha256:"current-rendition",delivery_logo_asset_id:"learning.logo.black",logo_review_switchable:true})');
 assert.match(run('cellHtml(R(),R().slots[0])'),/切换反白 Logo/);
 assert.doesNotMatch(run('cellHtml(R(),R().slots[1])'),/review-logo-action/);
 await run('switchOrdinaryReviewLogo("first",2,"learning.logo.white-app","current-rendition")');
 assert.deepEqual({...calls[0]},{name:'review-logo',image_id:'first',expected_att:2,
  expected_sha256:'current-rendition',asset_id:'learning.logo.white-app'});
});

test('喜马拉雅先选齐同套当前五张，重出后的版本需重新选择才可导出',async()=>{
 const {ctx,run,calls}=setup();
 ctx.capture=async(...args)=>{calls.push(args);return{download_url:'/set.zip'}};
 run(`R().params.ximalaya_suite=true;
      for(const p of PLACEMENTS)p.platform='喜马拉雅';
      Object.assign(PLACEMENTS[0],{target_width:1000,target_height:1000});
      Object.assign(PLACEMENTS[1],{target_width:1280,target_height:720});
      for(const slot of R().slots)Object.assign(slot,{att:1,image_url:'/img-'+slot.id});
      for(const [id,w,h] of [['fourth',1200,480],['fifth',720,1280]]){
        PLACEMENTS.push({id,platform:'喜马拉雅',name:'单图',image_count:1,target_width:w,target_height:h});
        R().params.pids.push(id);R().slots.push({id,pid:id,set:1,idx:1,state:'done',att:1,image_url:'/img-'+id});
      }
      Object.assign(R().slots[0],{state:'failed',att:1,ximalaya_review:{status:'unavailable',message:'审核暂未完成'}});
      R().slots[1].ximalaya_source='first';R().slots[1].dependency_ids=['first'];R().slots[1].state='blocked_first_failed';`);
 const waiting=run('viewPick()');assert.match(waiting,/等待首图通过审核/);assert.match(waiting,/重试审核/);
 assert.match(waiting,/id="ximalaya-download-1"[^>]*disabled/);
 await run('retryXimalayaImage("first","retry-ximalaya-review")');assert.equal(calls[0].expected_att,1);
 run('Object.assign(R().slots[0],{state:"done",ximalaya_review:{status:"approved"}});R().slots[1].state="done";request=capture;refresh=async()=>{};downloadLink=url=>calls.push(url)');
 assert.match(run('viewPick()'),/5 \/ 5 张完成/);
 await run('downloadXimalayaSuite(1)');assert.equal(calls.length,1);
 run('setXimalayaDeliveryReview(1,true,"first",1)');assert.match(run('viewPick()'),/已选 1 \/ 5 张/);
 run('setXimalayaDeliveryReview(1,true)');assert.match(run('viewPick()'),/已选 5 \/ 5 张/);
 assert.match(run('viewPick()'),/取消全选/);
 run('setXimalayaDeliveryReview(1,false)');assert.match(run('viewPick()'),/已选 0 \/ 5 张/);
 run('setXimalayaDeliveryReview(1,true);R().slots[0].att=2');
 assert.match(run('viewPick()'),/已选 4 \/ 5 张/);
 assert.match(run('viewPick()'),/id="ximalaya-download-1"[^>]*disabled/);
 run('setXimalayaDeliveryReview(1,true,"first",1)');await run('downloadXimalayaSuite(1)');assert.equal(calls.length,1);
 run('setXimalayaDeliveryReview(1,true,"first",2)');
 await run('downloadXimalayaSuite(1)');assert.equal(calls[1][2].suite_number,1);
 assert.deepEqual({...calls[1][2].reviewed_versions},{first:2,second:1,third:1,fourth:1,fifth:1});assert.equal(calls[2],'/set.zip');
});

test('喜马拉雅区分等待提交、正在提交、自动查询和回执待核对',()=>{
 const {run}=setup();
 run(`R().params.ximalaya_suite=true;
      Object.assign(R().slots[1],{ximalaya_source:'first',dependency_ids:['first'],state:'generating',stage:'awaiting_submit'});`);
 const card=()=>run('viewXimalayaImage(R(),R().slots[1],R().slots[0])');
 assert.match(card(),/等待同套提交回执/);
 assert.doesNotMatch(card(),/正在提交生成任务|恢复查询|确认未受理后重出/);
 run('R().slots[1].stage="submitting"');
 assert.match(card(),/正在提交生成任务/);
 run('Object.assign(R().slots[1],{state:"queued",stage:"query_retry"})');
 assert.match(card(),/后台继续查询原任务/);
 assert.doesNotMatch(card(),/恢复查询|确认未受理后重出/);
 run('Object.assign(R().slots[1],{state:"failed",submission_unverified:true})');
 assert.match(card(),/等待回执核对/);
 assert.match(card(),/href="https:\/\/kie\.ai\/logs"/);
 assert.match(card(),/确认未受理后重出/);
 assert.doesNotMatch(card(),/恢复查询/);
});

test('信息流成品目录合并喜马拉雅，双尺寸验收后可和普通版位一起保存',async()=>{
 const {ctx,run,calls}=setup();
 ctx.capture=async(...args)=>{calls.push(args);return{filename:'feed.zip'}};
 run(`const r=R();r.params.ximalaya_suite=true;
      Object.assign(PLACEMENTS[1],{platform:'喜马拉雅',target_width:1280,target_height:720});
      PLACEMENTS[2].platform='喜马拉雅';
      for(const s of r.slots)Object.assign(s,{image_url:'/img/'+s.id,att:1});
      r.slots[2].ximalaya_source='second';
      r.sel['first::1']=true;
      r.delivery={ready_sets:1,can_export:true,covered_placements:1};
      request=capture;refresh=async()=>{};`);
 assert.match(run('viewPick()'),/喜马拉雅套图/);
 assert.doesNotMatch(run('viewPick()'),/id="ximalaya-download-1"/);
 run('S.pickPid="second"');
 const gallery=run('viewPick()');
 assert.match(gallery,/2 \/ 2 张完成/);
 assert.doesNotMatch(gallery,/data-slot="first"/);
 await run('setXimalayaDeliveryReview(1,true)');
 assert.equal(calls[0].placement_id,'second');
 assert.deepEqual({...calls[0].reviewed_versions},{second:1,third:1});
 await run('dlAll()');
 assert.deepEqual({...calls[1][2].reviewed_versions},{second:1,third:1});
 assert(!('suite_number' in calls[1][2]));
 await run('setXimalayaDeliveryReview(1,false,"third",1)');
 assert.equal(calls[2].adopted,false);
});

test('回执待核对的尺寸仅在明确确认后提交同一版本的补跑请求',async()=>{
 const {ctx,run,calls}=setup();
 run('R().params.ximalaya_suite=true;plOf("second").platform="喜马拉雅";Object.assign(R().slots[1],{state:"failed",att:3,submission_unverified:true})');
 const retry='retryXimalayaImage("second","retry-confirmed-submission")';
 ctx.window.confirm=()=>false;
 await run(retry);
 assert.equal(calls.length,0);
 ctx.window.confirm=()=>true;
 await run(retry);
 assert.deepEqual({...calls[0]},{name:'retry-confirmed-submission',image_id:'second',expected_att:3,confirmed_unaccepted:true});
 assert.equal(calls.length,1);
});

test('普通卡片和进度页可接回 KIE 任务，发送版本及任务号',async()=>{
 const {ctx,run,calls}=setup();
 ctx.window.confirm=()=>{throw new Error('接回原任务不应提示重出')};
 run('Object.assign(R().slots[0],{state:"failed",att:3,submission_unverified:true})');
 for(const markup of [run('cellHtml(R(),R().slots[0])'),run('viewOrdinaryProgress()')]){
  assert.match(markup,/KIE 任务号/);
  assert.match(markup,/接回任务/);
  assert.match(markup,/确认未受理后重出/);
 }
 await run('reconcileOrdinaryKie("first",3," kie-previous-task ")');
 assert.deepEqual({...calls[0]},{name:'attach-kie-receipt',image_id:'first',expected_att:3,task_id:'kie-previous-task'});
});

test('无可用回执时各页面都提示核对或恢复备份',()=>{
 const {run}=setup();
 run('Object.assign(R().slots[0],{state:"failed",reason_code:"unknown",query_required:true,kie_recovery_action:"blocked"})');
 for(const markup of [run('cellHtml(R(),R().slots[0])'),run('viewOrdinaryProgress()'),run('viewXimalayaImage(R(),R().slots[0],R().slots[0])')]){
  assert.match(markup,/恢复包含回执的备份/);
  assert.doesNotMatch(markup,/恢复查询|确认未受理后重出|resumeImage\(/);
 }
});

test('轮询后可定位原来的套图复选框和版位目录焦点',()=>{
 const {run}=setup();
 assert.equal(run('trapRef({dataset:{sel:"first::1"}})'),'[data-sel="first::1"]');
 assert.equal(run('trapRef({dataset:{pickPlacement:"first"}})'),'[data-pick-placement="first"]');
});
