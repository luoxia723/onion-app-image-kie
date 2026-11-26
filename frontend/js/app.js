/* Persistent state comes only from the local service. */
const SETS_MIN=1,SETS_MAX=20,DEF_CTA='立即体验';
const DEF_BASE='https://api.kie.ai',DEF_UP='https://kieai.redpandaai.co';
const VLAB={queued:'等待中',waiting_first:'等待中',generating:'生成中',done:'已完成',failed:'失败',blocked_first_failed:'失败',stopped:'已停止'};
let PLACEMENTS=[],UNAVAILABLE_PLACEMENTS=[],ASSETS={},IPS=[],LOGO={},FONTS=[],STYLES=[];
let CFG={kie:false,path:'',base:DEF_BASE,up:DEF_UP,simulation:true},CONN={};
let S={tasks:[],cur:null,view:'form',draft:defParams(),tab:'all',pf:'all',pv:null,miss:false,cfgOpen:false,tried:false,drafts:[],draftId:null,draftSequence:0,draftRevision:0};
let lastRefreshAt=0;
let storage={used_bytes:0},busy=false,loading=false,pollTimer,searchTimer,viewEpoch=0,refreshFailures=0;

async function request(path,method='GET',body){
  const response=await fetch('/api'+path,{method,headers:method==='GET'?{}:{'Content-Type':'application/json','X-Onion-Request':'1'},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok){const error=new Error(data.message_zh||'操作未完成，请重试');error.status=response.status;throw error}
  return data;
}
function report(error){toast(error.message||'操作未完成，请重试')}
window.addEventListener('unhandledrejection',event=>{event.preventDefault();report(event.reason)});
function applySettings(s){if(s.image_models)IMAGE_MODEL_OPTIONS=s.image_models.map(m=>[m.id,m.name]);CFG={imageModel:s.image_model,imageModels:s.image_models,kie:s.key_configured,path:s.output_dir,base:s.kie_base_url,up:s.kie_upload_base_url,simulation:s.simulation,planningKey:s.planning_key_configured,planningBase:s.planning_base_url,planningModel:s.planning_model}}
function save(autosave=true){
  const p=new URLSearchParams();if(S.cur)p.set('task',S.cur);p.set('view',S.view);
  if(['form','learning-logo'].includes(S.view)&&S.draftId)p.set('draft',S.draftId);
  if(S.view==='learning-logo'&&S.learningLogoPid)p.set('logo',S.learningLogoPid);
  if(S.view==='learning-logo'&&S.logoTemplateCategory)p.set('logoCategory',S.logoTemplateCategory);
  if(S.view==='learning-run'&&S.learningRunId)p.set('run',S.learningRunId);
  history.replaceState(null,'','#'+p.toString());if(autosave)scheduleDraftSave();
}
function cfgSave(){}
function updTimers(){document.querySelectorAll('[data-t0]').forEach(e=>{const n=Math.max(0,Math.floor((Date.now()-Number(e.dataset.t0))/1000));e.textContent=Math.floor(n/60)+':'+String(n%60).padStart(2,'0')})}
function allRun(){return S.tasks.flatMap(t=>t.rounds.flatMap(r=>r.slots))}
function head1(r,s){return s.idx>1?r.slots.find(x=>x.id===s.first_id):null}
function blocked(r,s){return s.state==='blocked_first_failed'}


function imgOf(s){return s.image_url||''}




function taskStatus(t){
  const r=t.rounds[t.ri],d=r.delivery,done=r.slots.filter(s=>s.state==='done').length;
  if(t.background_running&&!r.slots.some(s=>s.state==='queued'||s.state==='generating'))return['d-run','上一轮仍在完成'];
  if(tRun(t))return['d-run',workStatus(r).title];
  if(d?.last_version&&!d.has_changes&&d.can_export)return['d-ok','已保存 '+d.last_version];
  if(r.stopped)return['d-wait',done?'待挑选':'已停止'];
  if(d?.incomplete_sets)return['d-err',d.incomplete_sets+' 套待处理 · '+d.ready_sets+' 套可保存'];
  if(done)return['d-wait',d?.can_export?'可保存图包':'待挑选'];
  return['d-err',r.planning_status==='failed'?'规划失败':'失败 '+r.slots.filter(s=>isFail(r,s)).length];
}
function gb(bytes){return(bytes/1024**3).toFixed(3)+' GB'}
function storHtml(){return`<b id="storused">${gb(storage.used_bytes)}</b><button id="cleanbtn" style="flex:none" onclick="cleanNow()">清理暂存文件</button><span class="sfree ok" id="storfree">${S.freed!=null?'已释放 '+gb(S.freed):''}</span>`}
async function cleanNow(){const preview=await request('/storage/preview');if(!preview.files){toast('没有可清理的暂存文件，历史和原图均保留');return}const result=await request('/storage','POST',{});S.freed=result.freed_bytes;storage=await request('/storage');const e=$('#stor');if(e)e.innerHTML=storHtml();toast('已清理暂存文件，历史记录与图片保留')}
async function openCfg(){if(typeof openWorkspacePage==='function')return openWorkspacePage('settings');if(S.submitting)return toast('正在提交配置，请稍候');window._cfgFrom=cfgRef(document.activeElement);CONN={};S.freed=null;const [settings,st]=await Promise.all([request('/settings'),request('/storage')]);applySettings(settings);storage=st;S.cfgOpen=true;render();$('#plankey')?.focus()}
async function saveCfg(){
 if(busy||S.settingsSaving)return;
 const epoch=viewEpoch,view=S.view,form=$('#workspace-settings-form');
 const data={image_model:$('#cfgimagemodel').value,kie_api_key:$('#kiekey').value,simulation:$('#cfgimagemode').value==='simulation',planning_api_key:$('#plankey').value,planning_base_url:$('#planbase').value,planning_model:$('#planmodel').value,output_dir:$('#cfgpath').value,kie_base_url:$('#kbase').value,kie_upload_base_url:$('#kup').value};
 busy=true;S.settingsSaving=true;if(form)form.disabled=true;const button=$('#cfgsave');if(button)button.disabled=true;
 try{
  const result=await request('/settings','PUT',data);applySettings(result);
  if(epoch!==viewEpoch||S.view!==view)return;
  S.settingsSaving=false;S.cfgOpen=false;render();
  if(S.view!=='settings')cfgBack();else{const status=document.getElementById('settings-save-state');if(status)status.textContent='已保存'}
  toast(CFG.simulation?'已保存 · 模拟预览':'已保存 · 真实生图已启用');
 }catch(e){if(epoch===viewEpoch)report(e)}finally{busy=false;S.settingsSaving=false;if(form?.isConnected)form.disabled=false;if(button?.isConnected)button.disabled=false}
}
function imageKeyEntered(){if($('#kiekey').value.trim())$('#cfgimagemode').value='real'}
async function testConn(){const key=$('#kiekey').value,epoch=viewEpoch,button=$('#kietest');button.disabled=true;try{const result=await request('/settings/test','POST',{kie_api_key:key,kie_base_url:$('#kbase').value});if(epoch!==viewEpoch||$('#kietest')!==button||!S.cfgOpen&&S.view!=='settings')return;CONN.kie=result.key_status==='connected'?'ok':'bad';$('#kiest').textContent=result.message_zh;$('#kiest').className=result.key_status==='connected'?'ok':'ng'}finally{if(button?.isConnected)button.disabled=false}}
async function testPlanning(){
  const data={planning_api_key:$('#plankey').value,planning_base_url:$('#planbase').value,planning_model:$('#planmodel').value};
  const button=$('#plantest');button.disabled=true;$('#planst').textContent='正在测试…';
  try{const result=await request('/settings/test-planning','POST',data);if(!S.cfgOpen&&S.view!=='settings'||$('#plantest')!==button)return;$('#planst').textContent=result.message_zh;$('#planst').className=result.key_status==='connected'?'ok':'ng'}finally{button.disabled=false}
}
function connTx(k){return CONN[k]==='ok'?'<div class="ok">● 已连接</div>':CONN[k]==='bad'?'<div class="ng">连接失败</div>':''}
async function chooseFolder(){const r=await request('/folders/choose','POST',{});if(r.path&&$('#cfgpath'))$('#cfgpath').value=r.path}
function installTask(t){
 const old=S.tasks.find(x=>x.id===t.id);if(t.loaded_round===undefined&&old&&old.ri<t.rounds.length)t.ri=old.ri;
 const i=S.tasks.findIndex(x=>x.id===t.id);if(i<0)S.tasks.push(t);else S.tasks[i]=t;
 if(t.summary){S.summaries=S.summaries||[];const j=S.summaries.findIndex(x=>x.id===t.id);if(j<0)S.summaries.unshift(t.summary);else S.summaries[j]=t.summary}
}
async function refresh(){if(typeof WORKSPACE!=='undefined'&&WORKSPACE_PAGES.includes(S.view))return refreshWorkspacePage();if(S.view==='learning-run'&&typeof refreshLearningRun==='function')return refreshLearningRun();if(loading)return;loading=true;lastRefreshAt=Date.now();const epoch=viewEpoch,query=S.q||'',previous=JSON.stringify([S.summaries,S.queue]),wasDisconnected=!!S.connectionLost;let detailChanged=false;try{
 let cursor='',summaries=[],queue;
 do{const r=await request('/tasks?summary=1&q='+encodeURIComponent(query)+'&cursor='+cursor);summaries.push(...r.tasks);cursor=r.next_cursor||'';queue=r.queue}while(cursor);
 if(epoch!==viewEpoch||query!==(S.q||''))return;
 if(typeof refreshLearningRunsList==='function')await refreshLearningRunsList().catch(()=>{});
 S.searchPending=false;S.summaries=summaries;S.queue=queue;S.connectionLost=false;refreshFailures=0;
 if(S.cur&&!['form','learning-logo','learning-run'].includes(S.view)){
  const old=T(),index=old?.ri;
  let r;try{r=await request('/tasks/'+S.cur+'?view=1'+(index!==undefined?'&round='+index:'')+(old&&old.loaded_round===index?'&revision='+old.revision:''))}catch(e){if(e.status!==404)throw e;await persistPromptDraft();S.cur=null;S.pv=null;S.promptDraft=null;S.view='form';render();toast('任务已在其他窗口删除，已返回列表；撤销删除后可恢复编辑');return}
  if(epoch!==viewEpoch)return;if(!r.unchanged){installTask(r);syncPreviewState();detailChanged=true}
 }
 if(!detailChanged&&!wasDisconnected&&previous===JSON.stringify([S.summaries,S.queue])){updTimers();return}
 if(!S.ren&&!S.menu){if(S.view==='form'){const list=$('.tasks');if(list&&!S.menu)list.innerHTML=taskList()||'<li class="empty-list">还没有任务</li>';const q=$('#queue-overview');if(q)q.textContent=queueText()}else softRender()}
}catch(e){refreshFailures++;if(refreshFailures>=2){S.connectionLost=true;softRender()}if(!S.summaries?.length)report(e)}finally{loading=false;if(query!==(S.q||''))refresh()}}
function searchTasks(q){S.q=q;S.searchPending=true;S.draftSearching=true;S.draftLimit=20;updateDraftList();clearTimeout(searchTimer);searchTimer=setTimeout(()=>{refresh();refreshDraftList().catch(report)},180)}
function beginNavigation(taskId=null){if(S.submitting){toast('正在提交配置，请稍候');return null}S.pickMore=false;S.menu=null;S.openingTask=taskId;const epoch=++viewEpoch;S.navigationPending=true;render();return epoch}
function finishNavigation(epoch){if(epoch===viewEpoch){S.navigationPending=false;S.openingTask=null;render()}}
async function newTask(){return newDraft()}
async function openTask(id){
 const epoch=beginNavigation(id);if(epoch===null)return;try{
 await persistDraft();await persistPromptDraft();if(epoch!==viewEpoch)return;
 const t=await request('/tasks/'+id+'?view=1');if(epoch!==viewEpoch)return;
 installTask(t);S.pv=null;S.pvDetails=null;S.promptDraft=null;S.cur=id;t.ri=t.loaded_round;S.view='pick';S.ordinaryStage='results';S.tab='all';S.pf='all';S.editing=null;S.draftId=null;save(false);render();$('#main').scrollTop=0;
 }finally{finishNavigation(epoch)}
}
async function go(v){
  if(S.submitting)return toast('正在提交配置，请稍候');
  if(v==='form')return editTaskDraft();if(!R())return;
  await persistDraft();S.view=v;S.pickMore=false;S.draftId=null;S.miss=false;save(false);render();$('#main').scrollTop=0;
}
function editRedo(){return editTaskDraft()}
async function startGen(){if(busy||S.navigationPending||S.uploadingPurpose)return;
  if(learningForm(S.draft))return previewLearningSuite();
  if((S.draft.pids||[]).some(id=>plOf(id)?.category==='学习机'))return toast('学习机请单独选择渠道，先保存基准图与整套配置。');
  if(!CFG.planningKey){toast('请先配置画面规划 API');return openCfg()}
  if(!CFG.simulation&&!CFG.kie)return openCfg();
  S.tried=true;const issue=formIssue(S.draft);if(issue){if(issue.field==='styleq')S.visualOpen=true;render();const field=document.getElementById(issue.field);if(field){field.scrollIntoView({block:'center'});field.focus()}return}
  const params=JSON.parse(JSON.stringify(S.draft));if(Array.isArray(params.channel))delete params.channel;delete params.logo_asset_id;params.sets=Number(params.sets);params.image_model=params.image_model||CFG.imageModel;
  busy=true;S.submitting=true;render();
  const fingerprint=JSON.stringify(params);
  const idem=S.submitKey&&S.submitFingerprint===fingerprint?S.submitKey:crypto.randomUUID();S.submitKey=idem;S.submitFingerprint=fingerprint;
  try{
    await persistDraft();const submittedDraft=S.draftId;
    const editing=S.editing&&S.cur===S.editing;
    const t=await request(editing?'/tasks/'+S.cur+'/rounds':'/tasks','POST',{params,idempotency_key:idem,draft_id:submittedDraft});
    S.draftId=null;installTask(t);S.cur=t.id;T().ri=T().rounds.length-1;S.editing=null;S.view='pick';S.submitKey=null;S.tab='all';S.pf='all';save();render();$('#main').scrollTop=0;refreshDraftList().catch(report);
    if(t.recovered_submission)toast('已恢复上次提交，未重复生成');else if(t.added_image_count===0)toast('配置未变，没有重复生成');else if(t.added_image_count)toast('只补充 '+t.added_image_count+' 张，已有结果已保留');
  }catch(e){if(e.status&&e.status<500)S.submitKey=null;report(e)}finally{busy=false;S.submitting=false;render()}
}
async function action(name,data={}){const t=await request('/tasks/'+S.cur+'/'+name,'POST',{round:T().ri,...data});installTask(t);softRender();return t}
async function changeSelection(name,data){
  if(S.selectionBusy){softRender();return false}
  S.selectionBusy=true;softRender();
  try{await action(name,data);return true}catch(e){report(e);return false}finally{S.selectionBusy=false;softRender()}
}
async function toggleSel(n,inPv,pid){
  pid=pid||curPvSlot()?.pid||R().params.pids[0];
  const adopted=!R().sel[selectionKey(pid,n)];
  await changeSelection('adopt',{set:n,placement_id:pid,adopted});
}
function setPickPlacement(pid,filter='all'){
  S.pickPid=pid;S.pf=filter;render();
  $('.sample-stage')?.scrollTo({top:0});$('#sets')?.scrollTo({left:0,top:0});
  document.querySelector(`[data-pick-placement="${pid}"]`)?.scrollIntoView({block:'nearest'});
}
function updatePlacementScroll(){
  const list=$('.dir-list'),previous=$('#dir-prev'),next=$('#dir-next');
  if(!list||!previous||!next)return;
  previous.disabled=list.scrollLeft<=1;
  next.disabled=list.scrollLeft+list.clientWidth>=list.scrollWidth-1;
}
function scrollPlacementDirectory(direction){
  const list=$('.dir-list');
  if(list)list.scrollBy({left:direction*Math.max(160,list.clientWidth*.7),behavior:'smooth'});
}
function locatePickIssue(){
  const r=R();if(!r)return;
  const issues=new Set(setsOf(r).filter(group=>attentionSet(r,group)).map(group=>group.pid));
  const ids=pickPlacementIds(r),current=pickPlacement(r),index=ids.indexOf(current);
  if(ximalayaSlots(r).some(s=>isFail(r,s)))issues.add(ximalayaIds(r.params)[0]);
  const order=[...ids.slice(index+1),...ids.slice(0,index+1)];
  const target=S.pf!=='bad'&&issues.has(current)?current:order.find(pid=>issues.has(pid));
  if(!target)return;
  setPickPlacement(target,'bad');
  $('#sample-filter-bad')?.focus({preventScroll:true});
}
async function selectVisible(adopted){
  const sets=selectionScope(R()).map(g=>({placement_id:g.pid,set:g.n}));
  if(sets.length)await changeSelection('adopt-bulk',{sets,adopted});
}
async function clearVisibleSelection(){
  const r=R(),sets=selectionScope(r).filter(g=>selectedSet(r,g)).map(g=>({placement_id:g.pid,set:g.n}));
  if(sets.length)await changeSelection('adopt-bulk',{sets,adopted:false});
}
async function repeatOrdinaryImage(id){
 if(S.ordinaryImageActionPending||S.submitting||S.navigationPending||S.localProcessing)return;
 const r=R(),slot=r?.slots.find(row=>row.id===id);if(r?.generation_disabled||!slot||slot.state!=='done'||slot.delivery_eligible===false)return;
 const retry=imageRetry(r,slot);if(retry.disabled)return;
 if(retry.blocked)return retry.head&&openPv(retry.head.id);
 S.ordinaryImageActionPending=true;render();
 try{if(retry.query)await resumeImage(id);else await action('regenerate',{image_id:id,...(Number.isInteger(slot.att)?{expected_att:slot.att}:{})})}
 catch(error){report(error)}finally{S.ordinaryImageActionPending=false;render()}
}
async function redo(id){await action('regenerate',{image_id:id});render()}
async function resumeImage(id){await action('resume',{image_id:id});render()}
function confirmKieNotAccepted(){
 return window.confirm('请确认当前 KIE 账号的任务记录中没有受理这次请求。确认后将提交一次新的生图请求。');
}
async function reconcileOrdinaryKie(id,version,taskId=null){
 const r=R(),slot=r?.slots.find(row=>row.id===id);
 if(S.ordinaryImageActionPending||!slot||slot.att!==version||r.generation_disabled)return;
 if(taskId===null&&!confirmKieNotAccepted())return;
 if(taskId!==null&&!taskId.trim())return toast('请填写 KIE 任务号');
 const epoch=viewEpoch;S.ordinaryImageActionPending=true;
 try{
  await action(taskId===null?'retry-confirmed-submission':'attach-kie-receipt',
   {image_id:id,expected_att:version,...(taskId===null?{confirmed_unaccepted:true}:{task_id:taskId.trim()})});
  if(epoch===viewEpoch&&S.pv===id)await closePv();
  if(epoch===viewEpoch)toast(taskId===null?'已提交重出':'已接回 KIE 任务，后台继续取图');
 }catch(error){if(epoch===viewEpoch)report(error)}
 finally{S.ordinaryImageActionPending=false;if(epoch===viewEpoch)render()}
}
async function retryXimalayaImage(id,method){
 const r=R(),slot=r?.slots.find(row=>row.id===id);
 if(!slot||!ximalayaIds(r.params).includes(slot.pid)||S.ordinaryImageActionPending)return;
 if(method==='retry-confirmed-submission')return reconcileOrdinaryKie(id,slot.att);
 S.ordinaryImageActionPending=true;
 const task=S.cur;
 try{
  await action(method,{image_id:id,expected_att:slot.att});
  if(S.cur===task&&S.pv===id)await closePv();
 }catch(error){report(error)}
 finally{S.ordinaryImageActionPending=false;render()}
}
async function downloadXimalayaSuite(number){
 const r=R();if(S.exportBusy||S.logoReviewPending||!r?.params.ximalaya_suite)return;
 const items=ximalayaSlots(r).filter(s=>s.set===number),versions=ximalayaReadyVersions(items);
 const reviewed_versions=reviewedDeliveryVersions(ximalayaReviewScope(r,number),versions);
 if(!items.length||Object.keys(reviewed_versions).length!==items.length)return toast('请先选中本套的全部成品');
 const task=S.cur,round=T().ri,epoch=viewEpoch;
 S.exportBusy=true;render();
 try{
  const pkg=await request('/tasks/'+task+'/packages','POST',{round,suite_number:number,reviewed_versions});
  if(epoch!==viewEpoch)return;
  downloadLink(pkg.download_url);await refresh();toast('整套图包已保存');
 }catch(error){report(error)}finally{S.exportBusy=false;render()}
}
async function switchOrdinaryReviewLogo(id,att,assetId,sha256){
 if(S.logoReviewPending||S.exportBusy||S.navigationPending)return;
 const epoch=viewEpoch;S.logoReviewPending=true;
 try{
  await persistPromptDraft();
  if(epoch!==viewEpoch)return;
  render();
  await action('review-logo',{image_id:id,expected_att:att,expected_sha256:sha256,asset_id:assetId});
  if(epoch===viewEpoch){
   if(S.pv===id){S.pvOriginal=false;S.pvCompare=false}
   syncPreviewState();
  }
 }catch(error){if(epoch===viewEpoch)report(error)}
 finally{S.logoReviewPending=false;if(epoch===viewEpoch)render()}
}
async function stopRest(){await action('stop');render()}




function togglePvOriginal(){S.pvOriginal=!S.pvOriginal;S.pvCompare=false;render()}
function openMenu(id){S.menu=S.menu===id?null:id;render();positionTaskMenu();$('.tmenu button:not(:disabled)')?.focus()}
function closeTaskMenu(){const id=S.menu;S.menu=null;render();document.querySelector(`[data-menu-task="${id}"]`)?.focus({preventScroll:true})}
function renStart(id){S.menu=null;S.ren=id;S.renV=null;render();$('#renin').focus();$('#renin').select()}
async function renOk(){if(!S.ren||window._rnd)return;const id=S.ren,name=S.renV;S.ren=null;S.renV=null;if(name?.trim()){try{installTask(await request('/tasks/'+id,'PATCH',{name}))}catch(e){report(e)}}render()}
function renEnd(){S.ren=null;S.renV=null;render()}
async function dupFrom(id){const r=await request('/tasks/'+id+'/duplicate','POST',id===S.cur?{round:T().ri}:{});r.params.direction='';return newDraft(r.params)}
function dupTask(){return dupFrom(S.cur)}
async function delTask(id){await request('/tasks/'+id,'DELETE',{});S.menu=null;S.undo={id,cur:S.cur===id};S.tasks=S.tasks.filter(t=>t.id!==id);S.summaries=S.summaries?.filter(t=>t.id!==id);if(S.cur===id){S.cur=null;S.view='form'}render();clearTimeout(window._undoT);window._undoT=setTimeout(()=>{S.undo=null;render()},300000)}
async function undoDel(){
 const u=S.undo;if(!u)return;
 if(u.draft){
  const id=draftId();await request('/drafts/'+id,'PUT',{draft:u.draft.draft,form_drafts:u.draft.form_drafts||{},editing_task_id:u.draft.editing_task_id,editing_round:u.draft.editing_round,revision:0,editor_id:DRAFT_EDITOR,sequence:1});
  await refreshDraftList();clearTimeout(window._undoT);S.undo=null;if(u.cur)await openDraft(id);else render();
 }else{installTask(await request('/tasks/'+u.id+'/restore','POST',{}));clearTimeout(window._undoT);S.undo=null;if(u.cur){S.cur=u.id;S.view='pick'}save();render()}
}
function pkZip(pk){return pk.zip}
function downloadLink(url){const a=document.createElement('a');a.href=url;a.download='';document.body.append(a);a.click();a.remove()}
async function dlAll(readyOnly=false){
  const r=R();if(!r||S.exportBusy||S.logoReviewPending||S.selectionBusy||onlyXimalaya(r.params))return;
  const proof={};
  if(r.params.ximalaya_suite){
   const root=ximalayaIds(r.params)[0],slots=ximalayaSlots(r);
   for(const number of new Set(slots.map(s=>s.set))){
    const key=selectionKey(root,number);
    if(!r.sel[key]||readyOnly&&r.delivery?.incomplete_keys?.includes(key))continue;
    const items=slots.filter(s=>s.set===number);
    const selected=reviewedDeliveryVersions(ximalayaReviewScope(r,number),ximalayaReadyVersions(items));
    if(Object.keys(selected).length!==items.length)return toast('请先在喜马拉雅套图中选中当前成品');
    Object.assign(proof,selected);
   }
  }
  S.pickMore=false;S.exportBusy=true;render();
  const tid=S.cur,round=T().ri,skipped=readyOnly?r.delivery.incomplete_sets:0;
  try{const p=await request('/tasks/'+tid+'/packages','POST',{round,ready_only:readyOnly,...(r.params.ximalaya_suite?{reviewed_versions:proof}:{})});
  await refresh();toast('已保存到本机：'+p.filename+(skipped?'；'+skipped+' 套待处理图片未纳入':''));
  }catch(e){report(e)}finally{S.exportBusy=false;render()}
}
function redl(id){const p=T().pkgs.find(p=>p.id===id);if(p)downloadLink('/api/tasks/'+S.cur+'/packages/'+p.id)}
async function openFolder(){await request('/tasks/'+S.cur+'/open-folder','POST',{})}
async function uploadReference(purpose){
  if(S.submitting||S.navigationPending||S.uploadingPurpose)return;
  if(S.draft.references.some(r=>r.purpose===purpose))return toast('每种用途最多上传 1 张参考图');
  const input=document.createElement('input');input.type='file';input.accept='image/png,image/jpeg,image/webp';
  input.onchange=async()=>{const f=input.files[0];if(f)await addReference(f,purpose)};input.click();
}
function previewImageDrop(event){
 if(!Array.from(event.dataTransfer?.types||[]).includes('Files'))return;
 event.preventDefault();
 event.currentTarget.classList.toggle('is-dragging',!event.currentTarget.disabled);
}
function leaveImageDrop(event){
 if(!event.currentTarget.contains(event.relatedTarget))event.currentTarget.classList.remove('is-dragging');
}
async function dropImageFile(event,purpose){
 event.preventDefault();
 event.currentTarget.classList.remove('is-dragging');
 if(event.currentTarget.disabled||S.submitting||S.navigationPending||S.uploadingPurpose)return;
 const files=event.dataTransfer?.files;
 if(!files?.length)return;
 if(files.length!==1)return toast('每次拖入一张图片');
 const file=files[0];
 if(file.type&&!['image/png','image/jpeg','image/webp'].includes(file.type))return toast('请选择 PNG、JPG 或 WebP 图片');
 if(purpose==='learning_concept')return addLearningConcept(file);
 return addReference(file,purpose);
}
function setLearningConceptOrigin(upload){
 if(S.submitting||S.navigationPending||S.uploadingPurpose||!learningForm(S.draft)||learningConcept(S.draft)===upload)return;
 if(upload){S.draft.concept={button_text:''};normalizeLearningDraft(S.draft,true);S.learningAutoSelectAll=true}
 else delete S.draft.concept;
 S.learningPlacementsOpen=false;invalidateLearningPreview();save();render();
}
function setLearningConceptButton(text){
 if(!learningConcept(S.draft)||S.submitting)return;
 S.draft.concept.button_text=text;
 S.draft.cta=text.trim()||LEARNING_DEFAULT_CTA;
 invalidateLearningPreview();save();updSum();
}
function uploadLearningConcept(){
 if(S.submitting||S.navigationPending||S.uploadingPurpose||!learningConcept(S.draft))return;
 const picker=document.createElement('input');picker.type='file';picker.accept='image/png,image/jpeg,image/webp';
 picker.onchange=()=>{if(picker.files[0])addLearningConcept(picker.files[0])};picker.click();
}
async function addLearningConcept(file){
 if(S.submitting||S.navigationPending||S.uploadingPurpose||!learningConcept(S.draft))return;
 if(file.size>10*1024*1024)return toast('图片不能超过 10MB');
 const draft=S.draft,source=draft.concept;S.uploadingPurpose='learning_concept';render();
 try{
  const bytes=new Uint8Array(await file.arrayBuffer());let binary='';
  for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
  const result=await request('/uploads','POST',{purpose:'learning_concept',name:file.name,data:btoa(binary)});
  if(S.draft!==draft||draft.concept!==source||!learningConcept(draft))return;
  draft.concept={id:result.id,name:result.name,width:result.width,height:result.height,button_text:'',source_path:result.path};
  if(source.id)draft.t1='';
  normalizeLearningDraft(draft);invalidateLearningPreview();save();
 }catch(error){if(S.draft===draft)report(error)}
 finally{S.uploadingPurpose=null;render()}
}
async function referencePreview(file){
  const bitmap=await createImageBitmap(file),canvas=document.createElement('canvas'),scale=Math.min(1,120/bitmap.width,90/bitmap.height);
  canvas.width=Math.round(bitmap.width*scale);canvas.height=Math.round(bitmap.height*scale);
  canvas.getContext('2d').drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();
  return canvas.toDataURL('image/jpeg',0.55);
}
async function addReference(file,purpose){
  const learningOnly=learningForm(S.draft);
  if(S.submitting||S.navigationPending||S.uploadingPurpose)return;
  if(S.draft.references.some(r=>r.purpose===purpose))return toast('每种用途最多上传 1 张参考图');
  if(file.size>10*1024*1024)return toast('参考图不能超过 10MB');
  const draft=S.draftId;
  let pending;
  S.uploadingPurpose=purpose;render();
  try{
    const preview=await referencePreview(file),bytes=new Uint8Array(await file.arrayBuffer());let binary='';
    for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
    const r=await request('/uploads','POST',{name:file.name,note:'',purpose,data:btoa(binary)});
    if(draft!==S.draftId)return;
    if(S.draft.references.some(x=>x.id===r.id))return toast('这张图片已在其他上传位使用');
    pending={draft,id:r.id};
    S.referencePointsPending=S.referencePointsPending||{};S.referencePointsPending[purpose]=pending;
    invalidateLearningPreview();S.draft.references.push({...r,purpose,preview,points:[]});S.referenceMode=true;S.visualOpen=true;save();pending.draft=S.draftId;
  }catch(e){report(e)}finally{S.uploadingPurpose=null;render()}
  if(!pending)return;
  if(learningOnly){if(S.referencePointsPending?.[purpose]===pending)delete S.referencePointsPending[purpose];delete S.draft.learning_visual_config;save();render();return}
  try{
    const result=await request('/references/points','POST',{id:pending.id,purpose});
    if(S.referencePointsPending?.[purpose]!==pending||pending.draft!==S.draftId||S.submitting||S.navigationPending)return;
    const ref=S.draft.references.find(r=>r.id===pending.id&&r.purpose===purpose);
    if(ref){ref.points=result.points;save()}
  }catch{}finally{
    if(S.referencePointsPending?.[purpose]===pending){delete S.referencePointsPending[purpose];render()}
  }
}
function setReferenceMode(reference){
  if(S.submitting||S.navigationPending||S.uploadingPurpose)return;
  invalidateLearningPreview();S.referenceMode=reference;
  if(!reference){S.draft.references=[];S.referencePointsPending={}}
  save();render();
}
function removeReference(i){if(S.submitting||S.navigationPending)return;invalidateLearningPreview();delete S.referencePointsPending?.[S.draft.references[i].purpose];S.draft.references.splice(i,1);S.referenceMode=!!S.draft.references.length;save();render()}
function setReferenceNote(i,value){if(S.submitting||S.navigationPending)return;invalidateLearningPreview();S.draft.references[i].note=value;save();updSum()}
function addReferencePoint(i){
  if(S.submitting||S.navigationPending||S.referencePointsPending?.[S.draft.references[i].purpose])return;
  invalidateLearningPreview();const ref=S.draft.references[i];ref.points=ref.points||[];if(ref.points.length>=6)return;
  ref.points.push('');save();render();document.getElementById(`ref-point-${ref.purpose}-${ref.points.length-1}`)?.focus();
}
function setReferencePoint(i,j,value){if(S.submitting||S.navigationPending)return;invalidateLearningPreview();S.draft.references[i].points[j]=value;save()}
function removeReferencePoint(i,j){if(S.submitting||S.navigationPending)return;invalidateLearningPreview();S.draft.references[i].points.splice(j,1);save();render()}
document.addEventListener('click',e=>{if(S.menu&&!e.target.closest('.tmenu,.more')){S.menu=null;render()}});
window.addEventListener('resize',updateWorkbenchPosition);
async function retryPlanning(){await action('retry-planning');render()}
async function repairSet(pid,n){await action('repair-set',{placement_id:pid,set:n});render()}
async function addVariant(pid){await action('add-variant',{placement_id:pid});render()}
function locateIncomplete(){const key=R()?.delivery?.incomplete_keys?.[0];if(key){setPickPlacement(key.split('::')[0]);document.querySelector(`[data-sel="${key}"]`)?.closest('.set')?.scrollIntoView({block:'center',inline:'center'})}}
async function boot(){
 try{
  const [b,s,d]=await Promise.all([request('/bootstrap'),request('/settings'),request('/drafts')]);
  PLACEMENTS=b.placements;UNAVAILABLE_PLACEMENTS=b.unavailable_placements||[];ASSETS=b.assets;IPS=ASSETS.ips;LOGO=ASSETS.logos.find(a=>/standard/.test(a.id))||ASSETS.logos[0];FONTS=ASSETS.fonts;STYLES=ASSETS.styles;FORM_DEFAULTS=b.form_defaults||{};S.planner=b.planner;S.product=b.product;S.drafts=d.drafts;applySettings(s);
  const hash=new URLSearchParams(location.hash.slice(1)),wanted=hash.get('view');
  if(typeof loadLearningMachineConfig==='function')await loadLearningMachineConfig().catch(()=>{});
  S.draft.image_form=Object.keys(FORM_DEFAULTS).at(-1)||'单图';
  if(typeof openWorkspacePage==='function'){
   S.view='tasks';S.cur=null;
   if(WORKSPACE_PAGES.includes(wanted))await openWorkspacePage(wanted);
   else if(wanted==='learning-run'&&hash.get('run'))await openLearningRun(hash.get('run'));
   else if(wanted==='learning-logo'){if(hash.get('draft'))await openDraft(hash.get('draft'));S.learningLogoPid=hash.get('logo')||undefined;const category=hash.get('logoCategory');if(['应用商店','信息流','学习机'].includes(category))S.logoTemplateCategory=category;await openLearningLogoConfig()}
   else if(hash.get('draft'))await openDraft(hash.get('draft'));
   else if(hash.get('task')){await openTask(hash.get('task'));if(wanted==='form')await editTaskDraft();else if(wanted==='dl')await go('dl')}
   else if(wanted==='form')await newDraft();
   else await openWorkspacePage(WORKSPACE_PAGES.includes(wanted)?wanted:'tasks');
  }else{S.cur=hash.get('task');S.view=['form','pick','dl'].includes(wanted)?wanted:'form';await refresh();if(hash.get('draft'))await openDraft(hash.get('draft'));else if(T()&&S.view==='form')await editTaskDraft();else if(!T())await newDraft()}
  render();pollTimer=setInterval(()=>{const gap=document.hidden?15000:S.view==='learning-run'&&typeof learningRunBusy==='function'&&learningRunBusy()?1200:S.queue?.running||S.queue?.queued||S.queue?.planning?2500:8000;if(Date.now()-lastRefreshAt>=gap)refresh()},1000);
 }catch(e){$('#app').textContent=/Failed to fetch|Load failed|NetworkError/i.test(e.message||'')?'无法连接本机服务，请重新启动工作台。':'工作台页面加载失败，请刷新重试。';report(e)}
}
boot();

async function pauseQueue(on){await action(on?'pause':'continue');render()}
function queueText(){const q=S.queue;if(q?.blocked_reason)return q.blocked_reason;if(q?.maintenance)return '正在进行本机数据维护，队列暂缓提交';return q&&(q.running||q.queued||q.waiting)?'出图中 '+q.running+' · 排队 '+(q.queued+q.waiting)+(q.paused?' · 已暂停':''):''}

function syncPreviewState(){
 const s=curPvSlot();if(!s||s.is_historical)return;
 const current=R()?.slots.find(x=>x.id===s.id);if(!current)return;
 if(current.att!==s.att){if(!s.history.some(v=>v.att===current.att))s.history.push({att:current.att,state:current.state,image_url:current.image_url});S.previewStale=true;promptStatus('图片已在其他窗口更新，编辑草稿保留在本版本');const b=$('#pvredo');if(b)b.disabled=true;return}
 const changed=s.state!==current.state||s.image_url!==current.image_url;
 for(const key of ['state','stage','reason_code','msg','image_url','original_image_url','preview_kind','delivery_eligible','sha256','delivery_logo_asset_id','logo_review_switchable'])s[key]=current[key];
 const version=s.history.find(row=>row.att===s.att);if(version)version.image_url=s.image_url;
 if(changed&&!S.promptDraft?.dirty)render();
 const retry=imageRetry(R(),s),b=$('#pvredo');if(b){b.disabled=retry.disabled;b.textContent=retry.label}
}
