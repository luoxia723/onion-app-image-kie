/* Persistent state comes only from the local service. */
const SETS_MIN=1,SETS_MAX=20,DEF_CTA='立即体验';
const DEF_BASE='https://api.kie.ai',DEF_UP='https://kieai.redpandaai.co';
const VLAB={queued:'等待中',waiting_first:'等待中',generating:'生成中',done:'已完成',failed:'失败',blocked_first_failed:'失败',stopped:'已停止'};
let PLACEMENTS=[],ASSETS={},IPS=[],LOGO={},FONTS=[],STYLES=[];
let CFG={kie:false,path:'',base:DEF_BASE,up:DEF_UP,simulation:true},CONN={};
let S={tasks:[],cur:null,view:'form',draft:defParams(),tab:'all',pf:'all',pv:null,miss:false,cfgOpen:false,tried:false,drafts:[],draftId:null,draftSequence:0,draftRevision:0};
let lastRefreshAt=0;
let storage={used_bytes:0},busy=false,loading=false,pollTimer,searchTimer,viewEpoch=0,refreshFailures=0;
let pickAdvanceTimer;

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
  if(S.view==='form'&&S.draftId)p.set('draft',S.draftId);
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
async function openCfg(){if(S.submitting)return toast('正在提交配置，请稍候');window._cfgFrom=cfgRef(document.activeElement);CONN={};S.freed=null;const [settings,st,product]=await Promise.all([request('/settings'),request('/storage'),request('/product')]);applySettings(settings);storage=st;S.product=product;S.cfgOpen=true;render();$('#plankey')?.focus()}
async function saveCfg(){if(busy)return;busy=true;try{
  const data={image_model:$('#cfgimagemodel').value,kie_api_key:$('#kiekey').value,simulation:$('#cfgimagemode').value==='simulation',planning_api_key:$('#plankey').value,planning_base_url:$('#planbase').value,planning_model:$('#planmodel').value,output_dir:$('#cfgpath').value,kie_base_url:$('#kbase').value,kie_upload_base_url:$('#kup').value};
  data.product_text=$('#product-facts').value;data.product_revision=S.product.revision;const result=await request('/settings','PUT',data);S.product=result.product||S.product;applySettings(result);$('#kiekey').value='';S.cfgOpen=false;render();cfgBack();toast(CFG.simulation?'已保存 · 模拟预览':'已保存 · 真实生图已启用');
}catch(e){report(e)}finally{busy=false}}
function imageKeyEntered(){if($('#kiekey').value.trim())$('#cfgimagemode').value='real'}
async function testConn(){const key=$('#kiekey').value;$('#kietest').disabled=true;try{const result=await request('/settings/test','POST',{kie_api_key:key,kie_base_url:$('#kbase').value});if(!S.cfgOpen)return;CONN.kie=result.key_status==='connected'?'ok':'bad';$('#kiest').textContent=result.message_zh;$('#kiest').className=result.key_status==='connected'?'ok':'ng'}finally{const b=$('#kietest');if(b)b.disabled=false}}
async function testPlanning(){
  const data={planning_api_key:$('#plankey').value,planning_base_url:$('#planbase').value,planning_model:$('#planmodel').value};
  const button=$('#plantest');button.disabled=true;$('#planst').textContent='正在测试…';
  try{const result=await request('/settings/test-planning','POST',data);if(!S.cfgOpen||$('#plantest')!==button)return;$('#planst').textContent=result.message_zh;$('#planst').className=result.key_status==='connected'?'ok':'ng'}finally{button.disabled=false}
}
function connTx(k){return CONN[k]==='ok'?'<div class="ok">● 已连接</div>':CONN[k]==='bad'?'<div class="ng">连接失败</div>':''}
async function chooseFolder(){const r=await request('/folders/choose','POST',{});if(r.path&&$('#cfgpath'))$('#cfgpath').value=r.path}
function installTask(t){
 const old=S.tasks.find(x=>x.id===t.id);if(t.loaded_round===undefined&&old&&old.ri<t.rounds.length)t.ri=old.ri;
 const i=S.tasks.findIndex(x=>x.id===t.id);if(i<0)S.tasks.push(t);else S.tasks[i]=t;
 if(t.summary){S.summaries=S.summaries||[];const j=S.summaries.findIndex(x=>x.id===t.id);if(j<0)S.summaries.unshift(t.summary);else S.summaries[j]=t.summary}
}
async function refresh(){if(loading)return;loading=true;lastRefreshAt=Date.now();const epoch=viewEpoch,query=S.q||'',previous=JSON.stringify([S.summaries,S.queue]),wasDisconnected=!!S.connectionLost;let detailChanged=false;try{
 let cursor='',summaries=[],queue;
 do{const r=await request('/tasks?summary=1&q='+encodeURIComponent(query)+'&cursor='+cursor);summaries.push(...r.tasks);cursor=r.next_cursor||'';queue=r.queue}while(cursor);
 if(epoch!==viewEpoch||query!==(S.q||''))return;
 S.searchPending=false;S.summaries=summaries;S.queue=queue;S.connectionLost=false;refreshFailures=0;
 if(S.cur&&S.view!=='form'){
  const old=T(),index=old?.ri;
  let r;try{r=await request('/tasks/'+S.cur+'?view=1'+(index!==undefined?'&round='+index:'')+(old&&old.loaded_round===index?'&revision='+old.revision:''))}catch(e){if(e.status!==404)throw e;await persistPromptDraft();S.cur=null;S.pv=null;S.promptDraft=null;S.view='form';render();toast('任务已在其他窗口删除，已返回列表；撤销删除后可恢复编辑');return}
  if(epoch!==viewEpoch)return;if(!r.unchanged){installTask(r);syncPreviewState();detailChanged=true}
 }
 if(!detailChanged&&!wasDisconnected&&previous===JSON.stringify([S.summaries,S.queue])){updTimers();return}
 if(!S.ren){if(S.view==='form'){const list=$('.tasks');if(list&&!S.menu)list.innerHTML=taskList()||'<li class="empty-list">还没有任务</li>';const q=$('#queue-overview');if(q)q.textContent=queueText()}else softRender()}
}catch(e){refreshFailures++;if(refreshFailures>=2){S.connectionLost=true;softRender()}if(!S.summaries?.length)report(e)}finally{loading=false;if(query!==(S.q||''))refresh()}}
function searchTasks(q){S.q=q;S.searchPending=true;S.draftSearching=true;S.draftLimit=20;updateDraftList();clearTimeout(searchTimer);searchTimer=setTimeout(()=>{refresh();refreshDraftList().catch(report)},180)}
function beginNavigation(){if(S.submitting){toast('正在提交配置，请稍候');return null}clearTimeout(pickAdvanceTimer);S.pickMore=false;const epoch=++viewEpoch;S.navigationPending=true;render();return epoch}
function finishNavigation(epoch){if(epoch===viewEpoch){S.navigationPending=false;render()}}
async function newTask(){return newDraft()}
async function openTask(id){
 const epoch=beginNavigation();if(epoch===null)return;try{
 await persistDraft();await persistPromptDraft();if(epoch!==viewEpoch)return;
 const t=await request('/tasks/'+id+'?view=1');if(epoch!==viewEpoch)return;
 installTask(t);S.pv=null;S.pvDetails=null;S.promptDraft=null;S.cur=id;t.ri=t.loaded_round;S.view='pick';S.tab='all';S.pf='all';S.editing=null;S.draftId=null;save(false);render();$('#main').scrollTop=0;
 }finally{finishNavigation(epoch)}
}
async function go(v){
  if(S.submitting)return toast('正在提交配置，请稍候');
  if(v==='form')return editTaskDraft();if(!R())return;
  await persistDraft();S.view=v;S.draftId=null;S.miss=false;save(false);render();$('#main').scrollTop=0;
}
function editRedo(){return editTaskDraft()}
async function startGen(){if(busy||S.navigationPending||S.uploadingPurpose)return;
  if(!CFG.planningKey){toast('请先配置画面规划 API');return openCfg()}
  if(!CFG.simulation&&!CFG.kie)return openCfg();
  S.tried=true;const issue=formIssue(S.draft);if(issue){render();const field=document.getElementById(issue.field);if(field){field.scrollIntoView({block:'center'});field.focus()}return}
  const params=JSON.parse(JSON.stringify(S.draft));params.sets=Number(params.sets);params.image_model=params.image_model||CFG.imageModel;
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
  const adopted=!R().sel[selectionKey(pid,n)],roundId=R().id,task=S.cur;
  clearTimeout(pickAdvanceTimer);
  const changed=await changeSelection('adopt',{set:n,placement_id:pid,adopted});
  if(changed&&adopted&&!inPv&&!S.pv&&S.cur===task&&R()?.id===roundId)schedulePickAdvance(pid);
}
function setPickPlacement(pid){clearTimeout(pickAdvanceTimer);S.pickPid=pid;S.pf='all';render();$('.sample-stage')?.scrollTo({top:0});$('#sets')?.scrollTo({left:0});document.querySelector(`[data-pick-placement="${pid}"]`)?.scrollIntoView({block:'nearest'})}
function setAutoNext(enabled){S.autoNext=enabled;localStorage.setItem('onion.pick.autoNext',String(enabled));if(!enabled)clearTimeout(pickAdvanceTimer)}
function schedulePickAdvance(pid){
  clearTimeout(pickAdvanceTimer);
  const round=R(),roundId=round.id,task=S.cur,epoch=viewEpoch;
  if(S.autoNext===false||S.view!=='pick'||S.navigationPending||pickPlacement(round)!==pid)return;
  const groups=setsOf(round);
  if(!groups.some(group=>group.pid===pid&&selectedSet(round,group)&&readySet(group)))return;
  pickAdvanceTimer=setTimeout(()=>{
    if(S.autoNext===false||S.view!=='pick'||S.navigationPending||S.cur!==task||R()?.id!==roundId||viewEpoch!==epoch||S.pv||pickPlacement(R())!==pid)return;
    const current=R(),sets=setsOf(current),order=current.params.pids,index=order.indexOf(pid);
    if(!sets.some(group=>group.pid===pid&&selectedSet(current,group)&&readySet(group)))return;
    const next=[...order.slice(index+1),...order.slice(0,index)].find(id=>!sets.some(group=>group.pid===id&&selectedSet(current,group)&&readySet(group))&&sets.some(group=>group.pid===id&&readySet(group)&&!selectedSet(current,group)));
    if(next)setPickPlacement(next);
  },400);
}
async function selectVisible(adopted){
  const roundId=R().id,task=S.cur,pid=pickPlacement(R());clearTimeout(pickAdvanceTimer);
  const sets=selectionScope(R()).map(g=>({placement_id:g.pid,set:g.n}));
  if(sets.length&&await changeSelection('adopt-bulk',{sets,adopted})&&adopted&&S.cur===task&&R()?.id===roundId)schedulePickAdvance(pid);
}
async function clearVisibleSelection(){
  clearTimeout(pickAdvanceTimer);
  const r=R(),sets=selectionScope(r).filter(g=>selectedSet(r,g)).map(g=>({placement_id:g.pid,set:g.n}));
  if(sets.length)await changeSelection('adopt-bulk',{sets,adopted:false});
}
async function redo(id){await action('regenerate',{image_id:id});render()}
async function resumeImage(id){await action('resume',{image_id:id});render()}
async function stopRest(){await action('stop');render()}




function togglePvOriginal(){S.pvOriginal=!S.pvOriginal;S.pvCompare=false;render()}
async function reprocessFrame(id){
  if(S.pv===id)await persistPromptDraft();await action('reprocess-frame',{image_id:id});S.pvOriginal=false;
  S.promptDraft=null;await openPv(id);toast('已在本机去框，请重新勾选；未调用生图');
}
async function fitImage(id){
  if(S.localProcessing)return;S.localProcessing=true;
  try{if(S.pv===id)await persistPromptDraft();await action('fit-image',{image_id:id});S.pvOriginal=false;
    S.promptDraft=null;await openPv(id);toast('已整图适配，保留全部内容；未调用生图');
  }finally{S.localProcessing=false}
}

function openMenu(id){S.menu=S.menu===id?null:id;render();$('.tmenu button')?.focus()}
function renStart(id){S.menu=null;S.ren=id;S.renV=null;render();$('#renin').focus();$('#renin').select()}
async function renOk(){if(!S.ren||window._rnd)return;const id=S.ren,name=S.renV;S.ren=null;S.renV=null;if(name?.trim()){try{installTask(await request('/tasks/'+id,'PATCH',{name}))}catch(e){report(e)}}render()}
function renEnd(){S.ren=null;S.renV=null;render()}
async function dupFrom(id){const r=await request('/tasks/'+id+'/duplicate','POST',id===S.cur?{round:T().ri}:{});r.params.direction='';return newDraft(r.params)}
function dupTask(){return dupFrom(S.cur)}
async function delTask(id){if(!confirm('删除此任务及候选图片？已保存到工作区的交付包保留。可在5分钟内撤销。'))return;await request('/tasks/'+id,'DELETE',{});S.menu=null;S.undo={id,cur:S.cur===id};S.tasks=S.tasks.filter(t=>t.id!==id);if(S.cur===id){S.cur=null;S.view='form'}render();clearTimeout(window._undoT);window._undoT=setTimeout(()=>{S.undo=null;render()},5000)}
async function undoDel(){const u=S.undo;if(!u)return;installTask(await request('/tasks/'+u.id+'/restore','POST',{}));clearTimeout(window._undoT);S.undo=null;if(u.cur){S.cur=u.id;S.view='pick'}save();render()}
function pkZip(pk){return pk.zip}
function downloadLink(url){const a=document.createElement('a');a.href=url;a.download='';document.body.append(a);a.click();a.remove()}
async function dlAll(readyOnly=false){
  if(S.exportBusy)return;S.exportBusy=true;render();
  const tid=S.cur,round=T().ri,skipped=readyOnly?R().delivery.incomplete_sets:0;
  try{await request('/tasks/'+tid+'/package-preview?round='+round+(readyOnly?'&ready_only=1':''));
  const p=await request('/tasks/'+tid+'/packages','POST',{round,ready_only:readyOnly});
  await refresh();toast('已保存到本机：'+p.filename+(skipped?'；'+skipped+' 套待处理图片未纳入':''));
  }catch(e){report(e)}finally{S.exportBusy=false;render()}
}
function redl(v){const p=T().pkgs.find(p=>p.v===v);if(p)downloadLink('/api/tasks/'+S.cur+'/packages/'+p.id)}
async function openFolder(){await request('/tasks/'+S.cur+'/open-folder','POST',{})}
async function uploadReference(purpose){
  if(S.submitting||S.navigationPending||S.uploadingPurpose)return;
  if(S.draft.references.some(r=>r.purpose===purpose))return toast('每种用途最多上传 1 张参考图');
  const input=document.createElement('input');input.type='file';input.accept='image/png,image/jpeg,image/webp';
  input.onchange=async()=>{const f=input.files[0];if(f)await addReference(f,purpose)};input.click();
}
async function referencePreview(file){
  const bitmap=await createImageBitmap(file),canvas=document.createElement('canvas'),scale=Math.min(1,120/bitmap.width,90/bitmap.height);
  canvas.width=Math.round(bitmap.width*scale);canvas.height=Math.round(bitmap.height*scale);
  canvas.getContext('2d').drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();
  return canvas.toDataURL('image/jpeg',0.55);
}
async function addReference(file,purpose){
  if(S.submitting||S.navigationPending||S.uploadingPurpose)return;
  if(S.draft.references.some(r=>r.purpose===purpose))return toast('每种用途最多上传 1 张参考图');
  if(file.size>10*1024*1024)return toast('参考图不能超过 10MB');
  const draft=S.draftId;
  S.uploadingPurpose=purpose;render();
  try{
    const preview=await referencePreview(file),bytes=new Uint8Array(await file.arrayBuffer());let binary='';
    for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
    const r=await request('/uploads','POST',{name:file.name,note:'',purpose,data:btoa(binary)});
    if(draft!==S.draftId)return;
    if(S.draft.references.some(x=>x.id===r.id))return toast('这张图片已在其他上传位使用');
    S.draft.references.push({...r,preview});S.referenceMode=true;S.visualOpen=true;save();
  }catch(e){report(e)}finally{S.uploadingPurpose=null;render()}
}
function setReferenceMode(reference){
  if(S.submitting||S.navigationPending||S.uploadingPurpose)return;
  S.referenceMode=reference;
  if(!reference)S.draft.references=[];
  save();render();
}
function removeReference(i){if(S.submitting||S.navigationPending)return;S.draft.references.splice(i,1);S.referenceMode=!!S.draft.references.length;save();render()}
function setReferenceNote(i,value){if(S.submitting||S.navigationPending)return;S.draft.references[i].note=value;save();updSum()}
document.addEventListener('click',e=>{if(S.menu&&!e.target.closest('.tmenu,.more')){S.menu=null;render()}});
window.addEventListener('resize',()=>setHH());
async function useLatestProduct(){if(S.submitting)return;const draft=S.draftId;const p=await request('/product');if(draft!==S.draftId||S.submitting||S.navigationPending)return;S.product=p;S.draft.product_facts=p.text;S.draft.facts_version=p.revision;save();render()}
async function retryPlanning(){await action('retry-planning');render()}
async function repairSet(pid,n){await action('repair-set',{placement_id:pid,set:n});render()}
async function addVariant(pid){await action('add-variant',{placement_id:pid});render()}
function locateIncomplete(){const key=R()?.delivery?.incomplete_keys?.[0];if(key){setPickPlacement(key.split('::')[0]);document.querySelector(`[data-sel="${key}"]`)?.closest('.set')?.scrollIntoView({block:'center',inline:'center'})}}
async function boot(){
 try{
  S.autoNext=localStorage.getItem('onion.pick.autoNext')!=='false';
  const [b,s,d]=await Promise.all([request('/bootstrap'),request('/settings'),request('/drafts?summary=1')]);
  PLACEMENTS=b.placements;ASSETS=b.assets;IPS=ASSETS.ips;LOGO=ASSETS.logos.find(a=>/standard/.test(a.id))||ASSETS.logos[0];FONTS=ASSETS.fonts;STYLES=ASSETS.styles;FORM_DEFAULTS=b.form_defaults||{};S.planner=b.planner;S.product=b.product;S.drafts=d.drafts;applySettings(s);
  const hash=new URLSearchParams(location.hash.slice(1));S.cur=hash.get('task');S.view=['form','pick','dl'].includes(hash.get('view'))?hash.get('view'):'form';
  await refresh();
  if(hash.get('draft')){S.view='pick';await openDraft(hash.get('draft'))}
  else if(T()&&S.view==='form')await editTaskDraft();
  else if(!T()){const last=S.drafts.find(d=>!d.editing_task_id);if(last){S.view='pick';await openDraft(last.id)}else await newDraft()}
  render();pollTimer=setInterval(()=>{const gap=document.hidden?15000:S.queue?.running||S.queue?.queued||S.queue?.planning?2500:8000;if(Date.now()-lastRefreshAt>=gap)refresh()},1000);
 }catch(e){$('#app').textContent=/Failed to fetch|Load failed|NetworkError/i.test(e.message||'')?'无法连接本机服务，请重新启动工作台。':'工作台页面加载失败，请刷新重试。';report(e)}
}
boot();

async function archiveTask(id,on){await request('/tasks/'+id+'/'+(on?'archive':'unarchive'),'POST',{});S.menu=null;await refresh();toast(on?'已归档，可在历史中查找':'已取消归档')}
async function pauseQueue(on){await action(on?'pause':'continue');render()}
function queueText(){const q=S.queue;if(q?.blocked_reason)return q.blocked_reason;if(q?.maintenance)return '正在进行本机数据维护，队列暂缓提交';return q&&(q.running||q.queued||q.waiting)?'出图中 '+q.running+' · 排队 '+(q.queued+q.waiting)+(q.paused?' · 已暂停':''):''}

function syncPreviewState(){
 const s=curPvSlot();if(!s||s.is_historical)return;
 const current=R()?.slots.find(x=>x.id===s.id);if(!current)return;
 if(current.att!==s.att){if(!s.history.some(v=>v.att===current.att))s.history.push({att:current.att,state:current.state,image_url:current.image_url});S.previewStale=true;promptStatus('图片已在其他窗口更新，编辑草稿保留在本版本');const b=$('#pvredo');if(b)b.disabled=true;return}
 const changed=s.state!==current.state;
 for(const key of ['state','stage','reason_code','msg','image_url','original_image_url','preview_kind','delivery_eligible'])s[key]=current[key];
 if(changed&&!S.promptDraft?.dirty)render();
 const retry=imageRetry(R(),s),b=$('#pvredo');if(b){b.disabled=retry.disabled;b.textContent=retry.label}
}
