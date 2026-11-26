/* Edits are durable drafts; they never mutate the prompt that made an image. */
let promptTimer=null,promptWrite=Promise.resolve(),previewEpoch=0;
function promptStatus(text){S.promptStatus=text;const e=$('#prompt-draft-status');if(e)e.textContent=text}
function schedulePromptDraft(){clearTimeout(promptTimer);promptStatus('正在保存草稿');promptTimer=setTimeout(()=>persistPromptDraft().catch(report),550)}
async function persistPromptDraft(){
 clearTimeout(promptTimer);const d=S.promptDraft;if(!d?.dirty)return promptWrite;
 const task=S.cur,body={att:d.att,editor_id:DRAFT_EDITOR,sequence:++d.sequence,text:d.value},id=d.id;
 const write=promptWrite.catch(()=>{}).then(()=>request('/tasks/'+task+'/prompt-drafts/'+id,'PUT',body));promptWrite=write;
 try{await write;if(S.promptDraft===d&&d.value===body.text){d.dirty=false;promptStatus('草稿已保存，尚未生成')}}catch(e){promptStatus('保存失败，内容仍在当前窗口');throw e}
}
async function discardPromptDraft(){
 clearTimeout(promptTimer);await promptWrite.catch(()=>{});const d=S.promptDraft,s=curPvSlot();if(!s)return;
 await request('/tasks/'+S.cur+'/prompt-drafts/'+s.id,'DELETE',{att:s.att,editor_id:DRAFT_EDITOR,sequence:(d?.sequence||0)+1});
 S.promptDraft=null;S.pvEditing=false;promptStatus('显示当前图片的实际提示词');render();
}
async function openPv(id,att=null){
 const token=++previewEpoch,tid=S.cur,epoch=viewEpoch;
 const current=()=>token===previewEpoch&&tid===S.cur&&epoch===viewEpoch;
 await persistPromptDraft();if(!current())return;if(!S.pv)window._pvFrom=trapRef(document.activeElement)||`[data-slot="${id}"]`;
 S.pv=id;S.pvPanel='prompt';S.pvEditing=false;S.previewStale=false;S.pvOriginal=false;S.pvDetails=null;S.promptDraft=null;S.pvCompare=false;render();
 try{
  const s=await request('/tasks/'+tid+'/image-details/'+id+'?editor='+encodeURIComponent(DRAFT_EDITOR)+(att?'&v='+att:''));
  if(!current()||S.pv!==id)return;
  if(T().ri!==s.round_index){const t=await request('/tasks/'+tid+'?view=1&round='+s.round_index);if(!current())return;installTask(t);T().ri=s.round_index}
  S.pvDetails=s;S.promptStatus=s.is_historical?'历史版本，只读':s.edit_draft?'草稿已保存，尚未生成':'当前图片的实际提示词';
  if(s.edit_draft&&!s.is_historical)S.promptDraft={id,att:s.att,value:s.edit_draft.text,dirty:false,sequence:s.edit_draft.editor_id===DRAFT_EDITOR?s.edit_draft.sequence:0};
  render();$('#pvx')?.focus();
 }catch(e){if(current()){S.pv=null;render();report(e)}}
}
function pvChk(){const s=curPvSlot();if(!s||s.is_historical)return;const previous=S.promptDraft;
 S.promptDraft={id:s.id,att:s.att,value:$('#pvPrompt').value,sequence:previous?.sequence||0,dirty:true};schedulePromptDraft();const b=$('#pvReset');if(b)b.style.display='';
 const banner=$('.prompt-draft-banner');if(banner)banner.hidden=false;
 const redo=$('#pvredo');if(redo&&typeof imageRetry==='function'){const retry=imageRetry(R(),s);if(!retry.query&&!retry.blocked)redo.textContent='用编辑稿'+retry.label}
}

function pvResetP(){const s=curPvSlot();if(!s||s.is_historical)return;$('#pvPrompt').value=s.orig;pvChk()}
async function closePv(){previewEpoch++;await persistPromptDraft();S.pv=null;S.pvDetails=null;S.promptDraft=null;S.pvCompare=false;render();document.querySelector(window._pvFrom||'#main')?.focus({preventScroll:true})}
async function pvRedo(){
 const s=curPvSlot();if(!s||s.is_historical)return;if(R()?.generation_disabled||s.generation_disabled)return toast('此制作流程已停用，请按新规则重新制作');const retry=imageRetry(R(),s);
 if(retry.blocked)return openPv(retry.head.id);
 if(retry.query){await resumeImage(s.id);return closePv()}
 if(R()?.params?.ximalaya_suite){await action('regenerate',{image_id:s.id,expected_att:s.att});return closePv()}
 if(s.production_mode==='local_resize'){await action('regenerate',{image_id:s.id,expected_att:s.att});return closePv()}
 await persistPromptDraft();await action('regenerate',{image_id:s.id,expected_att:s.att,prompt:$('#pvPrompt').value});S.promptDraft=null;await closePv();
}
function comparePrevious(){S.pvCompare=!S.pvCompare;render()}
window.addEventListener('beforeunload',event=>{
 const d=S.promptDraft;if(!d?.dirty)return;const body=JSON.stringify({att:d.att,editor_id:DRAFT_EDITOR,sequence:d.sequence+1,text:d.value});
 if(new TextEncoder().encode(body).length>=60000){event.preventDefault();event.returnValue='';return}
 if(new TextEncoder().encode(body).length<60000)fetch('/api/tasks/'+S.cur+'/prompt-drafts/'+d.id,{method:'PUT',headers:{'Content-Type':'application/json','X-Onion-Request':'1'},body,keepalive:true}).catch(()=>{});
});

async function choosePromptDraft(editor){
 if(!editor)return;await persistPromptDraft();const s=curPvSlot();
 const details=await request('/tasks/'+S.cur+'/image-details/'+s.id+'?v='+s.att+'&editor='+encodeURIComponent(DRAFT_EDITOR));
 const selected=details.edit_drafts.find(d=>d.editor_id===editor);if(!selected)return;
 S.pvDetails=details;S.promptDraft={id:s.id,att:s.att,value:selected.text,sequence:details.edit_drafts.find(d=>d.editor_id===DRAFT_EDITOR)?.sequence||0,dirty:true};
 await persistPromptDraft();render();
}
