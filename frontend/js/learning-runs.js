/* Learning runs use their own API/state; ordinary task rounds stay independent. */
let LEARNING_RUNS={items:[],current:null,loading:false,error:'',actionBusy:false,actionKeys:{},backgroundKeys:{},masterKeys:{},lastListAt:0};
const LEARNING_IMAGE_STATUS={not_generated:'待开始',waiting_for_baseline_confirmation:'等待确认基准图',queued:'等待中',generating:'制作中',processing:'尺寸与图层处理中',done:'已完成',failed:'需要处理',interrupted:'已中断',blocked:'等待来源母版恢复'};
const LEARNING_RUN_STATUS={configured:'待生成基准图',generating_baseline:'正在生成基准图',waiting_for_confirmation:'待确认基准图',baseline_confirmed:'基准图已确认',generating_suite:'正在制作整套',completed:'整套已完成',failed:'需要处理',interrupted:'制作已中断'};
function learningRunPath(id,suffix=''){return '/learning-machine/runs/'+encodeURIComponent(id)+suffix}
function isSharedCanvasRun(run){return run?.kind==='shared_canvas_adaptation'}
function learningRunStatusLabel(run){return isSharedCanvasRun(run)&&['configured','waiting_for_confirmation','baseline_confirmed'].includes(run.status)?'来源图已就绪 · 待生成共用母版':isSharedCanvasRun(run)&&run.status==='generating_suite'?'共用母版制作中':LEARNING_RUN_STATUS[run.status]||run.status}
function learningRunBusy(run=LEARNING_RUNS.current){return !!run&&(run.busy===true||['generating_baseline','generating_suite'].includes(run.status))}
function learningRunJs(value){return esc(JSON.stringify(String(value)))}
function learningRunMode(run){return run.mode==='real'?'真实制作':'模拟制作 · 不调用模型'}
function learningBaselineApproved(run){const b=run.baseline||{},a=run.approval;return b.status==='done'&&!!a?.confirmed&&a.baseline_version===b.version&&a.mode===run.mode&&a.sha256===b.sha256}
function learningRunOutputsReady(run){const outputs=run.outputs||[];return outputs.length>0&&(!run.counts?.output_count||outputs.length===run.counts.output_count)&&outputs.every(output=>output.status==='done')}
function applyLearningRunQueue(run){
 if(!run?.queue||typeof run.queue!=='object'||Array.isArray(run.queue))return;
 S.queue=run.queue;const summary=document.getElementById('queue-overview');if(summary&&typeof queueText==='function')summary.textContent=queueText();
}
function installLearningRun(run){
 if(!run||typeof run.id!=='string')throw new Error('学习机任务数据不完整');
 if(run.id===LEARNING_RUNS.current?.id&&Number.isInteger(run.revision)&&Number.isInteger(LEARNING_RUNS.current.revision)&&run.revision<LEARNING_RUNS.current.revision)return;
 LEARNING_RUNS.current=run;const index=LEARNING_RUNS.items.findIndex(x=>x.id===run.id);
 if(index<0)LEARNING_RUNS.items.unshift(run);else LEARNING_RUNS.items[index]=run;
 LEARNING_RUNS.error='';S.learningRunId=run.id;applyLearningRunQueue(run);
 for(const output of run.outputs||[]){const scope=run.id+':'+output.id,record=LEARNING_RUNS.backgroundKeys[scope];if(record&&!output.background_repair_pending&&output.status==='done'&&(record.accepted||record.source_version!==output.version))delete LEARNING_RUNS.backgroundKeys[scope]}
 for(const master of run.masters||[]){const scope=run.id+':'+master.id,record=LEARNING_RUNS.masterKeys[scope];if(record&&!master.query_required&&['done','failed','interrupted'].includes(master.status)&&(record.accepted||record.source_version!==master.version))delete LEARNING_RUNS.masterKeys[scope]}
}
async function refreshLearningRunsList(){
 const result=await request('/learning-machine/runs');LEARNING_RUNS.items=result.runs||[];LEARNING_RUNS.lastListAt=Date.now();
 const sidebar=document.getElementById('learning-run-sidebar');if(sidebar)sidebar.innerHTML=viewLearningRunList();return LEARNING_RUNS.items;
}
async function openLearningRun(id){
 const epoch=beginNavigation();if(epoch===null)return;
 try{await persistDraft();await persistPromptDraft();if(epoch!==viewEpoch)return;
  const run=await request(learningRunPath(id));if(epoch!==viewEpoch)return;
  installLearningRun(run);S.cur=null;S.view='learning-run';S.pv=null;S.learningImagePreview=null;
  S.learningOutputVersions={};S.learningBaselineVersion=null;S.learningBaselineExpanded=null;S.learningRunChannel='';S.learningStage=null;S.learningStageRun=run.id;S.learningOutputFilter='all';save(false);render();document.getElementById('main')?.scrollTo?.(0,0);
 }catch(error){report(error)}finally{finishNavigation(epoch)}
}
async function refreshLearningRun(){
 if(LEARNING_RUNS.loading||S.view!=='learning-run'||!S.learningRunId)return;
 LEARNING_RUNS.loading=true;lastRefreshAt=Date.now();const epoch=viewEpoch,id=S.learningRunId;
 const revision=LEARNING_RUNS.current?.id===id?LEARNING_RUNS.current.revision:null;
 const path=learningRunPath(id)+(Number.isInteger(revision)?'?revision='+revision:'');
 const listDue=Date.now()-LEARNING_RUNS.lastListAt>=(document.hidden?15000:8000);
 try{const [run,list]=await Promise.all([request(path),listDue?request('/learning-machine/runs').catch(()=>null):null]);if(epoch!==viewEpoch||S.view!=='learning-run'||S.learningRunId!==id)return;
  if(list){LEARNING_RUNS.items=list.runs||LEARNING_RUNS.items;LEARNING_RUNS.lastListAt=Date.now();const sidebar=document.getElementById('learning-run-sidebar');if(sidebar)sidebar.innerHTML=viewLearningRunList()}
  if(run.unchanged){applyLearningRunQueue(run);const recovered=LEARNING_RUNS.error||S.connectionLost;LEARNING_RUNS.error='';S.connectionLost=false;if(recovered)softRender();else updTimers();return}
  const changed=run.revision!==LEARNING_RUNS.current?.revision||LEARNING_RUNS.error||S.connectionLost;
  installLearningRun(run);S.connectionLost=false;if(changed)softRender();else updTimers();
 }catch(error){if(epoch===viewEpoch&&S.view==='learning-run'&&S.learningRunId===id){LEARNING_RUNS.error=error.message;S.connectionLost=true;softRender()}}
 finally{LEARNING_RUNS.loading=false}
}
async function startLearningRun(mode='simulation'){
 if(S.submitting||S.navigationPending||LEARNING_RUNS.actionBusy||S.uploadingPurpose)return;
 if(mode!=='simulation'&&mode!=='real')return;
 if(!learningForm(S.draft))return;
 if(S.learningLogoDirty)return toast('请先保存Logo模板');
 S.tried=true;normalizeLearningDraft(S.draft);const issue=formIssue(S.draft);
 if(issue){focusLearningFormIssue(issue);return}
 if(mode==='real'&&(!CFG.kie||!CFG.planningKey)){toast('真实制作需要配置规划和生图Key');return openCfg()}
 const params=structuredClone(S.draft);params.image_model=params.image_model||CFG.imageModel;
 const fingerprint=JSON.stringify({params,mode});
 if(S.learningCreateFingerprint!==fingerprint){S.learningCreateKey=crypto.randomUUID();S.learningCreateFingerprint=fingerprint}
 LEARNING_RUNS.actionBusy=true;S.submitting=true;render();
 try{await persistDraft();const run=await request('/learning-machine/runs','POST',{params,mode,idempotency_key:S.learningCreateKey});
  if(run.mode!==mode)throw new Error('制作模式与请求不一致，已停止提交，请刷新后核对');
  installLearningRun(run);S.learningCreateKey=null;S.learningCreateFingerprint=null;S.cur=null;S.view='learning-run';S.learningOutputVersions={};S.learningBaselineVersion=null;S.learningBaselineExpanded=null;S.learningRunChannel='';S.learningImagePreview=null;
  productionSelectStage(run,'baseline');save(false);render();
  const key='initial-baseline:'+run.id;
  LEARNING_RUNS.actionKeys[key]=LEARNING_RUNS.actionKeys[key]||crypto.randomUUID();
  const started=await request(learningRunPath(run.id,'/baseline'),'POST',{idempotency_key:LEARNING_RUNS.actionKeys[key]});
  if(S.view==='learning-run'&&S.learningRunId===run.id)installLearningRun(started);
  toast(mode==='real'?'基准图已提交，完成后请先查看确认':'正在本机生成演练基准图，不调用模型');
 }catch(error){LEARNING_RUNS.error=error.message;report(error)}
 finally{LEARNING_RUNS.actionBusy=false;S.submitting=false;render()}
}
async function makeLearningRunFromBaseline(){
 const run=LEARNING_RUNS.current;if(!run||isSharedCanvasRun(run)||LEARNING_RUNS.actionBusy||learningRunBusy(run))return;
 const baseline=run.baseline||{};
 if(!learningBaselineApproved(run)||(S.learningBaselineVersion??baseline.version)!==baseline.version)return toast('请先查看并确认当前基准图后再沿用');
 const scope='from-baseline:'+run.id+':'+baseline.version;
 const body={idempotency_key:LEARNING_RUNS.actionKeys[scope]||(LEARNING_RUNS.actionKeys[scope]=crypto.randomUUID())};
 const epoch=viewEpoch;LEARNING_RUNS.actionBusy=true;LEARNING_RUNS.error='';render();
 try{const next=await request(learningRunPath(run.id,'/from-baseline'),'POST',body);
  if(epoch!==viewEpoch||S.view!=='learning-run'||S.learningRunId!==run.id)return;
  if(next.mode!==run.mode||next.baseline?.sha256!==baseline.sha256||!learningBaselineApproved(next))throw new Error('沿用的基准图记录不一致，请刷新后核对');
  delete LEARNING_RUNS.actionKeys[scope];installLearningRun(next);S.cur=null;S.learningOutputVersions={};S.learningBaselineVersion=null;S.learningBaselineExpanded=false;S.learningRunChannel='';S.learningImagePreview=null;
  productionSelectStage(next,'baseline');save(false);toast('已沿用确认基准图，旧批次保留；请点击扩展整套按新规则制作');
 }catch(error){if(epoch===viewEpoch){LEARNING_RUNS.error=error.message;report(error);if(error.status&&error.status<500)delete LEARNING_RUNS.actionKeys[scope]}}
 finally{LEARNING_RUNS.actionBusy=false;if(epoch===viewEpoch)render()}
}
async function learningRunAction(action,outputId=null){
 if(!['baseline','confirm','expand','regenerate'].includes(action))return;
 const run=LEARNING_RUNS.current;if(!run||LEARNING_RUNS.actionBusy||learningRunBusy(run))return;
 if(isSharedCanvasRun(run)&&['baseline','confirm'].includes(action))return toast('本批使用已选择的来源图，无需重新生成或确认基准图');
 const baseline=run.baseline||{},selected=S.learningBaselineVersion??baseline.version;
 const approved=learningBaselineApproved(run);
 if(action==='confirm'&&(baseline.status!=='done'||selected!==baseline.version))return toast('请先查看当前已完成的基准图');
 if(action==='expand'&&!approved)return toast('请先确认当前基准图');
 if(action==='expand'&&run.suite?.status==='completed'&&run.suite.baseline_version===baseline.version&&learningRunOutputsReady(run))return toast('这一版基准图的整套已经完成，可单独重出某张图片');
 const output=outputId&&(run.outputs||[]).find(x=>x.id===outputId);
 if(action==='regenerate'&&!output)return;
 if(action==='regenerate'&&output.logo_refresh_pending)return toast('本图等待本机Logo更新，请使用“重试Logo更新”，不需要重新生图');
 if(action==='regenerate'&&output.background_repair_pending)return toast('本图已有背景适配任务，请先恢复背景查询，避免重新提交');
 if(action==='regenerate'&&S.learningOutputVersions?.[outputId]&&S.learningOutputVersions[outputId]!==output.version)return toast('请切回本图当前版本后重出');
 if(action==='regenerate'&&!approved)return toast('请先确认当前基准图');
 const suffix=action==='baseline'?'/baseline':action==='confirm'?'/confirm':action==='expand'?'/expand':'/outputs/'+encodeURIComponent(outputId)+'/regenerate';
 const version=action==='regenerate'?output.version:baseline.version;
 const scope=run.id+':'+action+':'+(outputId||'')+':'+version;
 const body=action==='confirm'?{baseline_version:baseline.version}:{idempotency_key:LEARNING_RUNS.actionKeys[scope]||(LEARNING_RUNS.actionKeys[scope]=crypto.randomUUID())};
 if(action==='regenerate')body.expected_version=output.version;
 if((action==='baseline'&&baseline.query_required)||(action==='regenerate'&&output.query_required))body.resume=true;
 LEARNING_RUNS.actionBusy=true;LEARNING_RUNS.error='';render();const epoch=viewEpoch;let focusResults=false;
 try{const next=await request(learningRunPath(run.id,suffix),'POST',body);
  if(epoch!==viewEpoch||S.view!=='learning-run'||S.learningRunId!==run.id)return;
  delete LEARNING_RUNS.actionKeys[scope];installLearningRun(next);if(action==='baseline'){S.learningBaselineVersion=null;S.learningBaselineExpanded=true;productionSelectStage(next,'baseline')}
  if(action==='expand'){S.learningBaselineExpanded=false;productionSelectStage(next,'progress');focusResults=true}
  if(action==='regenerate'){delete (S.learningOutputVersions||{})[outputId];productionSelectStage(next,'results')}
  if(action==='confirm')toast('基准图已确认，可以扩展整套');
 }catch(error){if(epoch===viewEpoch){LEARNING_RUNS.error=error.message;report(error);if(error.status&&error.status<500)delete LEARNING_RUNS.actionKeys[scope]}}
 finally{LEARNING_RUNS.actionBusy=false;if(epoch===viewEpoch){render();if(focusResults){const results=document.getElementById('learning-stage-progress');results?.focus({preventScroll:true});results?.scrollIntoView({block:'start',behavior:'auto'})}}}
}
async function packageLearningRun(){
 const run=LEARNING_RUNS.current;if(!run||LEARNING_RUNS.actionBusy||learningRunBusy(run))return;
 if(!learningRunOutputsReady(run))return toast('请先完成所有版位再保存图包');
 LEARNING_RUNS.actionBusy=true;LEARNING_RUNS.error='';render();const epoch=viewEpoch;
 const logo=learningExportLogoValue(run);
 try{const pkg=await request(learningRunPath(run.id,'/package'),'POST',logo?{logo_asset_id:logo}:{});if(epoch!==viewEpoch||S.learningRunId!==run.id)return;
  const next=await request(learningRunPath(run.id));if(epoch!==viewEpoch||S.learningRunId!==run.id)return;
  installLearningRun(next);if(pkg.download_url)downloadLink(pkg.download_url);toast(run.mode==='real'?'图包已保存':'演练图包已保存，内容为模拟图片');
 }catch(error){if(epoch===viewEpoch){LEARNING_RUNS.error=error.message;report(error)}}finally{LEARNING_RUNS.actionBusy=false;if(epoch===viewEpoch)render()}
}
function learningExportLogoValue(run=LEARNING_RUNS.current){return run?canonicalLogoVariant(S.learningExportLogoByRun?.[run.id]):''}
function learningLogoRefreshPending(output){return output.logo_refresh_pending===true&&['failed','interrupted'].includes(output.status)}
function learningRunLogoOutputsReady(run){const outputs=run.outputs||[],known=outputs.filter(output=>output.logo_refresh_supported!==false&&(output.logo_required===true||learningLogoRefreshPending(output)));return known.length?known.every(output=>output.status==='done'||learningLogoRefreshPending(output)):outputs.some(output=>typeof output.logo_required!=='boolean')&&learningRunOutputsReady(run)}
function setLearningExportLogo(value){
 const run=LEARNING_RUNS.current,selected=value?canonicalLogoVariant(value):'';if(!run||LEARNING_RUNS.actionBusy||value&&!selected)return;
 S.learningExportLogoByRun=S.learningExportLogoByRun||{};S.learningExportLogoByRun[run.id]=selected;render();
}
async function refreshLearningRunLogos(){
 const run=LEARNING_RUNS.current;if(!run||LEARNING_RUNS.actionBusy||learningRunBusy(run))return;
 if(isSharedCanvasRun(run)&&run.target_kind==='ordinary')return;
 if(S.learningLogoDirty)return toast('请先保存Logo模板，再应用到图片');
 if(!learningRunLogoOutputsReady(run))return toast('请先完成有Logo的图片，再应用模板；无Logo版位不添加');
 const scope='refresh-logos:'+run.id+':'+run.revision,key=LEARNING_RUNS.actionKeys[scope]||(LEARNING_RUNS.actionKeys[scope]=crypto.randomUUID());
 const epoch=viewEpoch;LEARNING_RUNS.actionBusy=true;LEARNING_RUNS.error='';render();
 try{const next=await request(learningRunPath(run.id,'/refresh-logos'),'POST',{idempotency_key:key});
  if(epoch!==viewEpoch||S.view!=='learning-run'||S.learningRunId!==run.id)return;
  delete LEARNING_RUNS.actionKeys[scope];installLearningRun(next);S.learningOutputVersions={};S.learningImagePreview=null;toast('正在本机应用已保存的Logo模板，不调用生图模型');
 }catch(error){if(epoch===viewEpoch){LEARNING_RUNS.error=error.message;report(error);if(error.status&&error.status<500)delete LEARNING_RUNS.actionKeys[scope]}}
 finally{LEARNING_RUNS.actionBusy=false;if(epoch===viewEpoch)render()}
}
function viewLearningLogoExport(run,busy){
 return `<div class="logo-export-control learning-logo-export"><label for="learning-export-logo">导出Logo<select id="learning-export-logo" ${busy?'disabled':''} onchange="setLearningExportLogo(this.value)">${logoVariantOptions(learningExportLogoValue(run),'按各图配置')}</select></label><small>只作用于本次图包；固定无Logo版位不添加。</small></div>`;
}
function learningBackgroundPadding(output){const value=output.processing?.sizing?.padding_percent??output.processing?.padding_percent;return typeof value==='number'&&Number.isFinite(value)&&value>0&&value<=100?value:null}
function learningBackgroundAIRepaired(output){const processing=output.processing,sizing=processing?.sizing||processing;return sizing?.ai_repair_performed===true||processing?.ai_repair_performed===true||sizing?.method==='ai_background_expansion'||processing?.method==='ai_background_expansion'}
function learningBackgroundCanRepair(output){return learningBackgroundPadding(output)!==null&&!learningBackgroundAIRepaired(output)}
function learningBackgroundCanAdjust(output){return output.status==='done'&&!output.background_repair_pending&&learningBackgroundAIRepaired(output)}
function learningBackgroundRepairLabel(output){return output.background_repair_pending?(['generating','queued','processing'].includes(output.status)?output.recovery_action==='retry_export'?'正在压缩导出':'背景适配处理中':output.recovery_action==='retry_export'?'重新压缩并导出':output.query_required?'恢复背景适配查询':'重试背景适配'):learningBackgroundCanAdjust(output)?'再次调整背景（AI）':learningBackgroundPadding(output)>8?'AI自然扩展背景':'自然适配背景'}
function viewLearningBackgroundRepairHint(output,run=LEARNING_RUNS.current){
 if(output.recovery_action==='retired_flow')return '<p class="field-help learning-background-repair-hint">此制作流程已停用，请按新规则重新配置制作；已有图片保留。</p>';
 if(output.background_repair_pending&&output.recovery_action==='retry_export')return '<p class="field-help learning-background-repair-hint">使用已生成的图片重新压缩并导出，不调用AI；保持版位要求的精确尺寸。</p>';
 if(run?.mode==='simulation')return '<p class="field-help learning-background-repair-hint">本次为模拟演练，仅验证背景适配流程，不调用图片模型。</p>';
 if(output.background_repair_pending)return '<p class="field-help learning-background-repair-hint">沿用现有背景适配任务；状态不明时只恢复查询，不重复提交。</p>';
 if(learningBackgroundCanAdjust(output))return '<p class="field-help learning-background-repair-hint">将再次调用约一次图片模型调整背景与留白，允许少量细节变化；旧版本保留。</p>';
 const padding=learningBackgroundPadding(output);if(padding===null)return '';
 return `<p class="field-help learning-background-repair-hint">${padding>8?'延续场景并去除补边色条，会调用一次图片模型；允许少量细节变化。':'按现有记录进行本机轻量裁切去边，不调用图片模型。'}</p>`;
}
async function repairLearningOutputBackground(outputId,forceAi=false){
 const run=LEARNING_RUNS.current;if(!run||LEARNING_RUNS.actionBusy||learningRunBusy(run))return;
 const output=(run.outputs||[]).find(row=>row.id===outputId);if(output?.recovery_action==='retired_flow')return toast('此制作流程已停用，请按新规则重新配置制作');const pending=output?.background_repair_pending===true,force=forceAi===true&&!pending;
 if(!output||(force?!learningBackgroundCanAdjust(output):!learningBackgroundCanRepair(output)&&!pending))return toast('这张图片没有可用的背景适配记录');
 if(S.learningOutputVersions?.[outputId]&&S.learningOutputVersions[outputId]!==output.version)return toast('请切回本图当前版本再处理背景');
 const scope=run.id+':'+outputId;let record=LEARNING_RUNS.backgroundKeys[scope];
 if(pending&&typeof output.background_repair_key==='string'&&output.background_repair_key)record={key:output.background_repair_key,source_version:output.version};
 if(!record||(!pending&&(record.source_version!==output.version||record.force_ai!==force)))record={key:crypto.randomUUID(),source_version:output.version,force_ai:force};
 LEARNING_RUNS.backgroundKeys[scope]=record;const epoch=viewEpoch;LEARNING_RUNS.actionBusy=true;LEARNING_RUNS.error='';render();
 try{const next=await request(learningRunPath(run.id,'/repair-backgrounds'),'POST',{idempotency_key:record.key,output_ids:[outputId],...(force?{force_ai:true}:{})});
  if(epoch!==viewEpoch||S.view!=='learning-run'||S.learningRunId!==run.id)return;
  if(next.id!==run.id||next.mode!==run.mode)throw new Error('背景适配记录不一致，请刷新后核对');
  record.accepted=true;installLearningRun(next);delete (S.learningOutputVersions||{})[outputId];
  toast(output.recovery_action==='retry_export'?'正在本机重新压缩并导出，不调用AI':run.mode==='simulation'?'已提交本图模拟背景适配，不调用图片模型':pending?'已恢复背景适配任务':force?'已提交再次AI背景调整，旧版本保留':learningBackgroundPadding(output)>8?'已提交本图AI背景扩展，旧版本保留':'已提交本图本机背景适配，不调用图片模型');
 }catch(error){if(epoch===viewEpoch){LEARNING_RUNS.error=error.message;report(error);if(error.status&&error.status<500&&!output.background_repair_pending)delete LEARNING_RUNS.backgroundKeys[scope]}}
 finally{LEARNING_RUNS.actionBusy=false;if(epoch===viewEpoch)render()}
}
async function configureLearningRunAgain(){
 const run=LEARNING_RUNS.current;if(!run||LEARNING_RUNS.actionBusy||learningRunBusy(run))return;
 const params={...structuredClone(run.params),channel:'学习机',image_form:'单图',sets:1,references:[]};
 await newDraft(params);S.learningCreateMode='simulation';toast('已复制文案与版位，请确认画面设定后生成新基准图');
}
function backFromLearningRun(){if(S.submitting||LEARNING_RUNS.actionBusy)return;if(typeof openWorkspacePage==='function')return openWorkspacePage('tasks');viewEpoch++;S.view='form';S.learningRunId=null;S.learningImagePreview=null;save(false);render()}
function setLearningBaselineVersion(version){if(LEARNING_RUNS.current&&!isSharedCanvasRun(LEARNING_RUNS.current))productionSelectStage(LEARNING_RUNS.current,'baseline');S.learningBaselineVersion=Number(version);S.learningBaselineExpanded=true;render()}
function setLearningBaselineExpanded(value){if(value&&LEARNING_RUNS.current)productionSelectStage(LEARNING_RUNS.current,isSharedCanvasRun(LEARNING_RUNS.current)?'plan':'baseline');S.learningBaselineExpanded=!!value;render();document.getElementById('learning-baseline-toggle')?.focus({preventScroll:true})}
function setLearningOutputVersion(id,version){S.learningOutputVersions=S.learningOutputVersions||{};S.learningOutputVersions[id]=Number(version);render()}
function filterLearningRunChannel(channel){S.learningRunChannel=channel;render()}
function openLearningImage(url,label,kind=null,id=null,version=null){S.learningImagePreview={url,label,kind,id,version:Number(version)||null};render();document.getElementById('learning-image-close')?.focus()}
function closeLearningImage(){const url=S.learningImagePreview?.url;S.learningImagePreview=null;render();[...document.querySelectorAll('.learning-image-button')].find(button=>button.querySelector('img')?.getAttribute('src')===url)?.focus()}
function viewLearningRunList(){
 const query=(S.q||'').trim().toLowerCase(),runs=LEARNING_RUNS.items.filter(run=>!query||String(run.name||'').toLowerCase().includes(query));
 if(!runs.length)return '';
 return `<ul class="learning-run-list" aria-label="图片制作"><li class="gh fixed"><span>图片制作</span><span>${runs.length}</span></li>${runs.map(run=>`<li class="trow"><button class="task ${S.view==='learning-run'&&S.learningRunId===run.id?'on':''}" onclick="openLearningRun(${learningRunJs(run.id)})"><div><div class="t1">${esc(run.name||(isSharedCanvasRun(run)?'母版适配':'学习机任务'))}</div><div class="t2">${isSharedCanvasRun(run)?'母版适配 · ':''}${esc(learningRunStatusLabel(run))} · ${run.mode==='real'?'真实':'模拟'}${run.counts?.output_count?' · '+(run.counts.completed_outputs||0)+'/'+run.counts.output_count:''}</div></div></button></li>`).join('')}</ul>`;
}
function viewLearningRunStart(){return viewProductionStart()}

async function regenerateSharedCanvasMaster(masterId){
 const run=LEARNING_RUNS.current;if(!isSharedCanvasRun(run)||LEARNING_RUNS.actionBusy||learningRunBusy(run))return;
 if(!learningBaselineApproved(run))return toast('请先重新读取并核对来源图记录');
 const master=(run.masters||[]).find(row=>row.id===masterId);if(!master)return;
 const scope=run.id+':'+masterId;let record=LEARNING_RUNS.masterKeys[scope];
 if(master.query_required&&typeof master.regeneration_key==='string'&&master.regeneration_key)record={key:master.regeneration_key,source_version:master.version};
 if(!record||(!master.query_required&&record.source_version!==master.version))record={key:crypto.randomUUID(),source_version:master.version};
 LEARNING_RUNS.masterKeys[scope]=record;const epoch=viewEpoch;LEARNING_RUNS.actionBusy=true;LEARNING_RUNS.error='';render();
 try{const next=await request(learningRunPath(run.id,'/masters/'+encodeURIComponent(masterId)+'/regenerate'),'POST',{idempotency_key:record.key,expected_version:master.version});
  if(epoch!==viewEpoch||S.view!=='learning-run'||S.learningRunId!==run.id)return;
  if(next.id!==run.id||next.mode!==run.mode)throw new Error('母版更新记录不一致，请刷新后核对');
  record.accepted=true;installLearningRun(next);S.learningOutputVersions={};S.learningImagePreview=null;
  toast(master.query_required?'已恢复现有母版查询，未创建新的生图请求':run.mode==='simulation'?'正在演练重新扩展此母版，不调用图片模型':'已提交此组母版AI扩展，将更新组内全部尺寸，旧版本保留');
 }catch(error){if(epoch===viewEpoch){LEARNING_RUNS.error=error.message;report(error);if(error.status&&error.status<500&&!master.query_required)delete LEARNING_RUNS.masterKeys[scope]}}
 finally{LEARNING_RUNS.actionBusy=false;if(epoch===viewEpoch)render()}
}
function viewSharedMasterRetry(run,master,disabled=false){
 if(!isSharedCanvasRun(run))return '';
 return `<div class="shared-master-retry"><button ${disabled||learningRunBusy(run)||LEARNING_RUNS.actionBusy||!learningBaselineApproved(run)?'disabled':''} onclick="regenerateSharedCanvasMaster(${learningRunJs(master.id)})">${master.query_required?'恢复母版查询':'重新扩展此母版（AI）'}</button><small>${master.query_required?'沿用现有任务查询，不创建新的图片请求。':run.mode==='simulation'?'模拟演练，不调用模型；会更新本组全部尺寸。':'一次图片模型调用，更新此组全部尺寸；旧图和旧图包保留。'}</small></div>`;
}
function viewLearningRunHead(){return viewProductionHead()}

function learningVersions(current,history=[]){
 const versions=new Map();for(const item of history)if(Number.isInteger(item.version)&&item.version>0)versions.set(item.version,item);
 if(Number.isInteger(current?.version)&&current.version>0)versions.set(current.version,current);
 return [...versions.values()].sort((a,b)=>b.version-a.version);
}
function learningImageButton(image,label,kind=null,id=image?.id){return image?.image_url?`<button class="learning-image-button" onclick="openLearningImage(${learningRunJs(image.image_url)},${learningRunJs(label)},${learningRunJs(kind||'')},${learningRunJs(id||'')},${Number(image.version)||0})"><img src="${esc(image.image_url)}" alt="${esc(label)}" loading="lazy"></button>`:''}
function learningPromptElementId(kind,id,version,scope='page'){return 'learning-actual-prompt-'+scope+'-'+kind+'-'+encodeURIComponent(id)+'-v'+version}
function learningPromptVersion(run,kind,id,version){
 const current=kind==='baseline'?run.baseline:(kind==='master'?run.masters:run.outputs)?.find(row=>row.id===id);
 if(!current)return null;const history=kind==='baseline'?run.baseline_versions:current.versions;
 return learningVersions(current,history).find(row=>row.version===Number(version))||null;
}
async function copyLearningActualPrompt(kind,id,version,scope='page'){
 const row=LEARNING_RUNS.current&&learningPromptVersion(LEARNING_RUNS.current,kind,id,version),text=row?.prompt;
 if(typeof text!=='string'||!text.trim())return toast('这个版本尚未保存实际提示词');
 try{if(!globalThis.navigator?.clipboard?.writeText)throw new Error('clipboard_unavailable');await navigator.clipboard.writeText(text);toast('提示词已复制')}
 catch{
  const element=document.getElementById(learningPromptElementId(kind,id,version,scope));element?.focus();
  try{const selection=window.getSelection?.(),range=document.createRange?.();if(selection&&range&&element){range.selectNodeContents(element);selection.removeAllRanges();selection.addRange(range)}}catch{}
  toast('无法自动复制，请选中下方文本复制');
 }
}
function viewLearningProcessing(row){
 const sizing=row.processing?.sizing||row.processing;if(!sizing||typeof sizing!=='object')return '';
 const labels=[],percentage=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=100?Number(value.toFixed(2))+'%':null;
 const repaired=learningBackgroundAIRepaired(row);
 const sharedCanvas=sizing.method==='shared_canvas_crop'||sizing.source_box_scope==='generated_shared_canvas';
 if(repaired)labels.push('AI扩展背景','最终精确裁切适配');
 else if(sharedCanvas)labels.push('从生成的共用母版裁出');
 else if(sizing.method==='contain_full_source_color_gradient')labels.push('等比保全原图');
 else if(sizing.method==='fixed_crop_resize'&&!sizing.right_panel)labels.push('本机裁切适配');
 const panel=sizing.right_panel;
 if(panel)labels.push('左侧主画面 '+panel.artwork_width+'px','右侧纯色 '+panel.fill_width+'px');
 const compression=row.processing?.compression;
 if(compression)labels.push(compression.pixel_lossless?'PNG 无损编码':'PNG 已减色',Number((compression.bytes/1024).toFixed(1))+' KiB');
 const crop=percentage(sizing.crop_percent),padding=percentage(sizing.padding_percent);
 if(crop!==null&&!repaired)labels.push((sharedCanvas?'母版裁切 ':'裁切 ')+crop);if(padding!==null)labels.push((repaired||sharedCanvas?'后处理补边 ':'补背景 ')+padding);
 if(sizing.seam_review_required===true)labels.push('接缝待目视查看');
 if(sizing.content_detection==='not_performed')labels.push('未进行内容检测');
 else if(sizing.cv_detection_performed===false)labels.push('未进行自动内容检测');
 if(sizing.visual_review_required===true)labels.push('待目视检查人物与文字');
 if(sizing.ai_repair_performed===false&&!repaired)labels.push(sharedCanvas?'未追加AI补边调用':'未进行AI补图');
 return labels.length?`<p class="field-help learning-processing-note">处理记录：${esc(labels.join(' · '))}</p>`:'';
}
function viewLearningActualPrompt(run,row,kind,id=row.id,expanded=false,scope='page'){
 const version=Number(row.version)||0,text=version>0&&typeof row.prompt==='string'?row.prompt:'';
 const repaired=learningBackgroundAIRepaired(row),reused=!repaired&&(typeof row.reuse_baseline==='boolean'?row.reuse_baseline:/^(?:本分支)?直接复用.*基准图/.test(text));
 const sourceId=row.source_master_id,sourceLabel=sourceId?.replace(/^learning-master-/,'');
 const shared=isSharedCanvasRun(run),referenceName=shared?'来源图':'基准图';
 const title=kind==='baseline'?(shared?'来源图原提示词':'查看基准图提示词'):kind==='master'?(row.group_id||id)+' · 查看实际提示词':'查看实际提示词';
 const provenance=kind==='output'?(repaired?'本版本已进行AI自然扩展背景，下方为保存的实际执行提示词。':reused?'本图复用'+referenceName+'，未单独调用模型；以下为程序复用规则。':sourceId?.startsWith('single-')?'本版本为单张独立重出，未替换共享母版。':sourceId?'复用母版 '+sourceLabel+(row.source_master_version?' · 第'+row.source_master_version+'版':''):''):kind==='master'&&reused?'本组直接复用'+referenceName+'，未单独调用模型。':'';
 const parameters=[];if(run.params?.image_model&&!(shared&&kind==='baseline'))parameters.push('模型：'+run.params.image_model);
 if(row.aspect_ratio)parameters.push('生图画幅：'+row.aspect_ratio);
 if(Number(row.width)>0&&Number(row.height)>0)parameters.push((kind==='baseline'?referenceName+'像素：':'最终尺寸：')+row.width+'×'+row.height);
 if(typeof row.cta_required==='boolean')parameters.push(row.cta_required?'有CTA':'无CTA');
 if(typeof row.logo_required==='boolean')parameters.push(row.logo_required?'有Logo':'无Logo');
 return `<details class="learning-run-prompt learning-actual-prompt" ${expanded?'open':''}><summary>${esc(title)}</summary>${provenance?`<p class="field-help learning-prompt-source">${esc(provenance)}</p>`:''}${parameters.length?`<p class="field-help">${esc(parameters.join(' · '))}</p>`:''}${viewLearningProcessing(row)}${kind!=='baseline'?'<p class="field-help">生图使用母版画幅，成品的具体尺寸由后续代码裁切、缩放和图层处理。</p>':''}${run.mode==='simulation'?'<p class="field-help">本次为模拟演练，执行提示词没有发送给图片模型。</p>':''}${version>0&&row.status!=='done'?'<p class="field-help">此版本尚未完成，下面是当前保存的执行提示词。</p>':''}${text.trim()?`<button type="button" class="learning-prompt-copy" onclick="copyLearningActualPrompt('${kind}',${learningRunJs(id)},${version}${scope==='page'?'':','+learningRunJs(scope)})">复制完整提示词</button><pre id="${esc(learningPromptElementId(kind,id,version,scope))}" tabindex="0" aria-label="第${version}版完整实际提示词">${esc(text)}</pre>`:'<p class="field-help">本版本尚未保存实际提示词。</p>'}</details>`;
}
function learningOutputChannelGroups(outputs,filter=''){
 const groups=new Map();for(const output of outputs){const channel=output.platform||output.channel||'其他渠道';if(filter&&channel!==filter)continue;if(!groups.has(channel))groups.set(channel,[]);groups.get(channel).push(output)}
 return [...groups].map(([channel,items])=>({channel,outputs:items}));
}
function viewLearningOutputGroups(run,outputs,busy,approved){
 return learningOutputChannelGroups(outputs,S.learningRunChannel||'').map(group=>`<section class="learning-output-channel" data-learning-channel="${esc(group.channel)}"><div class="learning-channel-heading"><h3>${esc(group.channel)}</h3><span>${group.outputs.filter(output=>output.status==='done').length} / ${group.outputs.length} 张完成</span></div><div class="learning-output-grid">${group.outputs.map(output=>viewLearningOutput(run,output,busy,approved)).join('')}</div></section>`).join('');
}
function setLearningImageDetailVersion(version){
 const preview=S.learningImagePreview,run=LEARNING_RUNS.current;if(!preview||!run)return;
 const selected=learningPromptVersion(run,preview.kind,preview.id,Number(version));if(!selected)return toast('这个版本尚不可查看');
 preview.version=selected.version;preview.url=selected.image_url||'';
 if(preview.kind==='baseline')S.learningBaselineVersion=selected.version;
 if(preview.kind==='output'){S.learningOutputVersions=S.learningOutputVersions||{};S.learningOutputVersions[preview.id]=selected.version}
 render();document.getElementById('learning-image-version')?.focus();
}
function viewLearningImageDetails(run){
 const preview=S.learningImagePreview;if(!preview)return '';
 const current=preview.kind==='baseline'?run.baseline:(preview.kind==='master'?run.masters:run.outputs)?.find(row=>row.id===preview.id);
 const history=preview.kind==='baseline'?run.baseline_versions:current?.versions,versions=learningVersions(current,history);
 const selected=current&&learningPromptVersion(run,preview.kind,preview.id,preview.version);
 const title=selected?[preview.kind==='baseline'?(isSharedCanvasRun(run)?'来源图快照':'基准图'):selected.platform||selected.channel||'',preview.kind==='baseline'?'':selected.name||'成品','第'+selected.version+'版'].filter(Boolean).join(' · '):preview.label;
 const imageUrl=selected?selected.image_url:preview.url;
 return `<div class="mask learning-image-modal" role="dialog" aria-modal="true" aria-label="学习机图片详情" onclick="if(event.target===this)closeLearningImage()"><div class="learning-image-dialog"><div class="learning-image-detail-header"><h3>${esc(title)}</h3><button class="x" id="learning-image-close" aria-label="关闭图片详情" onclick="closeLearningImage()">×</button></div><div class="learning-image-detail-layout"><div class="learning-image-visual">${imageUrl?`<img src="${esc(imageUrl)}" alt="${esc(title)}"><a href="${esc(imageUrl)}" download>下载这张图片</a>`:'<div class="learning-run-placeholder">这版图片尚未完成，可查看已保存的提示词。</div>'}</div><section class="learning-image-info" aria-label="图片版本与实际提示词">${versions.length?`<label class="learning-detail-version">图片版本<select id="learning-image-version" onchange="setLearningImageDetailVersion(this.value)">${versions.map(row=>`<option value="${row.version}" ${row.version===preview.version?'selected':''}>第${row.version}版${row.version===current.version?' · 当前':''}</option>`).join('')}</select></label>`:''}${selected?.baseline_version?`<p class="field-help">${isSharedCanvasRun(run)?'来源快照记录：第':'来源：基准图第'}${selected.baseline_version}版</p>`:''}${selected?viewProductionImageActions(run,preview.kind,current,selected):''}${selected?viewLearningActualPrompt(run,selected,preview.kind,preview.id,true,'detail'):isSharedCanvasRun(run)?'<p class="field-help">这是冻结的来源图快照，未重新生图；原历史提示词请在来源任务中查看。</p>':'<p class="field-help">这张图片未保存可查看的提示词记录。</p>'}${selected&&preview.kind==='output'&&typeof openMasterCanvasFromLearningOutput==='function'&&!(isSharedCanvasRun(run)&&run.target_kind==='ordinary')?`<button id="master-canvas-learning-output" ${learningRunBusy(run)||selected.version!==current.version||selected.status!=='done'?'disabled':''} onclick="openMasterCanvasFromLearningOutput(${learningRunJs(preview.id)},${selected.version})">制作多尺寸母版</button>`:''}</section></div></div></div>`;
}
function viewLearningBaselineSource(run){
 const source=run.baseline_source;if(run.baseline?.inherited!==true||typeof source?.run_id!=='string'||!source.run_id)return '';
 const count=run.counts?.expected_new_calls,hasCount=Number.isInteger(count)&&count>=0;
 return `<div class="learning-baseline-source"><p><b>基准图沿用自 ${esc(source.run_id.slice(0,8))}${Number.isInteger(source.baseline_version)?' · 第'+source.baseline_version+'版':''}</b>${source.run_id!==run.id?`<button type="button" onclick="openLearningRun(${learningRunJs(source.run_id)})">查看来源批次</button>`:''}</p><span>基准图未重新生成；新的母版会按现行规则重新构图，旧批次保留。</span>${hasCount?`<span>本批预计新增 ${count} 次图片模型调用；点击扩展整套后才开始。</span>`:''}</div>`;
}
function viewLearningRun(){return viewProductionRun()}
function viewLearningOutput(run,output,busy,approved){return viewProductionOutput(run,output,busy,approved)}

document.addEventListener('keydown',event=>{
 if(!S.learningImagePreview||S.masterCanvasDialog)return;
 if(event.key==='Escape'){event.preventDefault();closeLearningImage();return}
 if(event.key==='Tab'){const controls=[...document.querySelectorAll('.learning-image-modal button,.learning-image-modal a[href],.learning-image-modal select,.learning-image-modal summary,.learning-image-modal [tabindex="0"]')].filter(control=>!control.disabled&&(!control.getClientRects||control.getClientRects().length));if(!controls.length)return;
  const first=controls[0],last=controls.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
 }
});
