/* Drafts are persisted by the local service, never in browser storage. */
const DRAFT_EDITOR=crypto.randomUUID();
let draftTimer=null;
function draftId(){return crypto.randomUUID().replaceAll('-','')}
function draftPayload(){return{draft:structuredClone(S.draft),form_drafts:structuredClone(S.formDrafts||{}),editing_task_id:S.editing||null,
  editing_round:S.editing?R()?.id:null,revision:S.draftRevision||0,editor_id:DRAFT_EDITOR,sequence:++S.draftSequence}}
function showDraftStatus(text,error=false){S.draftStatus=text;const e=document.querySelector('#draft-status');if(e){e.textContent=text;e.classList.toggle('errtx',error)}}
function scheduleDraftSave(){
  if(S.view!=='form'||S.loadingDraft)return;
  clearTimeout(draftTimer);
  const defaults={...defParams(imageFormOf(S.draft)),product_facts:S.product?.text||'',facts_version:S.product?.revision||0};
  if(!S.draftId&&Object.entries(S.draft).every(([key,value])=>JSON.stringify(value)===JSON.stringify(defaults[key]))&&!Object.values(S.formDrafts||{}).some(pr=>['t1','t2','s1','s2','s3'].some(key=>pr[key]?.trim())))return;
  if(!S.draftId){S.draftId=draftId();S.draftRevision=0;S.draftSequence=0;save(false)}
  showDraftStatus('正在保存');
  draftTimer=setTimeout(()=>persistDraft().catch(e=>{showDraftStatus('保存失败，可重试',true);report(e)}),550);
}
async function persistDraft(){
  clearTimeout(draftTimer);
  if(S.view!=='form'||!S.draftId||S.loadingDraft)return;
  const id=S.draftId,body=draftPayload();
  let value;try{value=await request('/drafts/'+id,'PUT',body)}catch(e){if(S.draftId!==id)return;if(e.status===409){let latest;try{latest=await request('/drafts/'+id)}catch{}if(latest?.submitted_task_id)return latest;S.draftId=draftId();S.draftRevision=0;S.draftSequence=0;save(false);toast('草稿在另一窗口发生变化，本窗口内容已另存');return persistDraft()}throw e}
  if(S.draftId===id){S.draftRevision=Math.max(S.draftRevision||0,value.revision);if(JSON.stringify(S.draft)===JSON.stringify(body.draft)&&JSON.stringify(S.formDrafts||{})===JSON.stringify(body.form_drafts))showDraftStatus('草稿已保存')}
  await refreshDraftList();
  return value;
}
function updateDraftList(){const e=document.querySelector('#draft-list');if(e)e.innerHTML=draftListHtml()}
async function refreshDraftList(){
  const q=S.q||'',value=await request('/drafts');
  if(q!==(S.q||''))return;S.drafts=value.drafts||[];S.draftSearching=false;updateDraftList();
}
function showMoreDrafts(){S.draftLimit=(S.draftLimit||20)+20;updateDraftList()}
function draftListHtml(){
  if(S.draftSearching)return '<li class="tnone">正在搜索草稿…</li>';
  const drafts=(S.drafts||[]).filter(d=>JSON.stringify(d.draft).toLowerCase().includes((S.q||'').toLowerCase())),shown=drafts.slice(0,S.draftLimit||20);
  return drafts.length?`<li class="gh fixed"><span>草稿</span><span>${drafts.length}</span></li>`+shown.map(d=>`<li class="trow"><button class="task ${S.draftId===d.id?'on':''}" onclick="openDraft('${d.id}')"><span class="noimg draft-icon">✎</span><div><div class="t1">${esc(d.name)}</div><div class="t2">${esc(d.draft.channel?[d.draft.channel,d.draft.image_form].filter(Boolean).join(' · '):'待填写')}</div></div></button><button class="more" aria-label="删除草稿" onmousedown="event.preventDefault()" onclick="removeDraft('${d.id}')">×</button></li>`).join('')+(shown.length<drafts.length?`<li><button class="lnk draft-more" onclick="showMoreDrafts()">加载更多草稿（还有 ${drafts.length-shown.length} 份）</button></li>`:''):'';
}
async function openDraft(id){
  const epoch=beginNavigation();if(epoch===null)return;try{
  await persistDraft();if(epoch!==viewEpoch)return;
  const value=await request('/drafts/'+id);if(epoch!==viewEpoch)return;
  if(value.submitted_task_id)return openTask(value.submitted_task_id);
  let task=null,missingTask=false;
  if(value.editing_task_id){try{task=await request('/tasks/'+value.editing_task_id)}catch(e){if(e.status!==404)throw e;value.editing_task_id=null;missingTask=true}}
  if(epoch!==viewEpoch)return;
  S.loadingDraft=true;
  if(task){installTask(task);S.cur=task.id;const index=T().rounds.findIndex(r=>r.id===value.editing_round);if(index>=0)T().ri=index}else S.cur=null;
  loadDraft(value.draft);S.formDrafts=value.form_drafts||{};S.draftId=id;S.draftRevision=value.revision;
  S.draftSequence=value.editor_id===DRAFT_EDITOR?value.sequence:0;S.editing=value.editing_task_id||null;S.view='form';S.tried=false;
  S.loadingDraft=false;showDraftStatus('草稿已保存');save(false);render();document.querySelector('#main').scrollTop=0;if(missingTask)toast('原任务已清理，草稿可作为新任务继续');
  }finally{finishNavigation(epoch)}
}
async function removeDraft(id){
  if(S.submitting)return toast('正在提交配置，请稍候');
  if(S.draftId===id)clearTimeout(draftTimer);
  await request('/drafts/'+id,'DELETE',{});await refreshDraftList();
  if(S.draftId===id){S.draftId=null;S.cur=null;S.editing=null;loadDraft(defParams(imageFormOf(S.draft)));S.formDrafts={};S.view='form';showDraftStatus('')}save(false);render();
}
async function newDraft(params=null,editing=null){
  const epoch=beginNavigation();if(epoch===null)return;try{
  await persistDraft();if(epoch!==viewEpoch)return;
  if(!params){
    const empty=(S.drafts||[]).find(d=>!d.editing_task_id&&![d.draft,...Object.values(d.form_drafts||{})].some(pr=>pr.channel||['t1','t2','s1','s2','s3'].some(key=>pr[key]?.trim())));
    if(empty)return openDraft(empty.id);
    const b=await request('/bootstrap');if(epoch!==viewEpoch)return;S.product=b.product;FORM_DEFAULTS=b.form_defaults||{};params={...defParams(imageFormOf(S.draft)),product_facts:b.product.text||'',facts_version:b.product.revision||0};
  }
  S.cur=editing?.taskId||null;S.editing=S.cur;S.view='form';S.draftId=null;S.submitKey=null;S.submitFingerprint=null;S.draftRevision=0;S.draftSequence=0;
  loadDraft(params);S.formDrafts={};S.tried=false;S.tab='all';S.pf='all';
  showDraftStatus('');save();render();await persistDraft();if(epoch===viewEpoch)document.querySelector('#main').scrollTop=0;
  }finally{finishNavigation(epoch)}
}
async function editTaskDraft(){
  if(S.submitting)return toast('正在提交配置，请稍候');
  const t=T(),r=R();if(!t||!r)return;
  const previous=(S.drafts||[]).find(d=>d.editing_task_id===t.id&&d.editing_round===r.id);
  if(previous)return openDraft(previous.id);
  const epoch=beginNavigation();if(epoch===null)return;try{const copied=await request('/tasks/'+t.id+'/duplicate','POST',{round:t.ri});if(epoch!==viewEpoch)return;return newDraft(copied.params,{taskId:t.id})}finally{finishNavigation(epoch)}
}
window.addEventListener('beforeunload',event=>{
  if(S.view!=='form'||!S.draftId)return;
  const body=JSON.stringify(draftPayload());
  if(new TextEncoder().encode(body).length>=60000){event.preventDefault();event.returnValue='';return}
  if(new TextEncoder().encode(body).length<60000)fetch('/api/drafts/'+S.draftId,{method:'PUT',headers:{'Content-Type':'application/json','X-Onion-Request':'1'},body,keepalive:true}).catch(()=>{});
});
