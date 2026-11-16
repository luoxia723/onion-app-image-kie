/* Explicit source/version selection for multi-size shared canvases. Creation is local. */
function masterCanvasOrdinarySource(imageId){
 const round=R(),image=round?.slots?.find(row=>row.id===imageId),preview=S.pv&&typeof curPvSlot==='function'?curPvSlot():null;
 if(!image)return {error:'请先打开当前制作轮次的图片'};
 if(preview?.id===imageId&&(preview.is_historical||preview.att!==image.att||S.previewStale))return {error:'请先切回当前图片版本，再制作多尺寸母版'};
 const spec=round.placement_rules?.[image.pid]||plOf(image.pid),count=Number(spec?.image_count);
 const images=round.slots.filter(row=>row.pid===image.pid&&row.set===image.set).sort((a,b)=>a.idx-b.idx);
 if(!Number.isInteger(count)||count<1||images.length!==count||images.some((row,index)=>row.idx!==index+1||row.state!=='done'||row.delivery_eligible===false||row.files_cleared||!Number.isInteger(row.att)||row.att<1))return {error:'请先完成当前版位这一套的全部图片并通过规格检查'};
 return {source:{kind:'ordinary',task_id:S.cur,image_ids:images.map(row=>row.id),atts:Object.fromEntries(images.map(row=>[row.id,row.att])),use_raw:false},targetKind:'ordinary',count,
  rawAvailable:!round.generation_disabled&&images.every(row=>!!row.original_image_url),expectedMode:typeof round.simulation==='boolean'?(round.simulation?'simulation':'real'):null,
  title:(spec.platform||'当前渠道')+' · 第'+image.set+'套 · 完整'+count+'张',returnFocusId:'master-canvas-set-'+image.pid+'-'+image.set,previews:images.map(row=>({url:row.image_url||'',raw_url:row.original_image_url||'',label:'图'+row.idx+' · 第'+row.att+'版'}))};
}
function masterCanvasTargets(kind,count){return PLACEMENTS.filter(placement=>placement.enabled!==false&&(kind==='learning'?placement.category==='学习机':placement.category!=='学习机'&&Number(placement.image_count)===count))}
function showMasterCanvasDialog(data,defaults=null){
 const targets=masterCanvasTargets(data.targetKind,data.count),allowed=new Set(targets.map(placement=>placement.id));
 const selected=(defaults||targets.map(placement=>placement.id)).filter(id=>allowed.has(id));
 S.masterCanvasDialog={...structuredClone(data),targets:structuredClone(targets),pids:selected,key:crypto.randomUUID(),busy:false,error:''};
 S.learningImagePreview=null;render();document.getElementById('master-canvas-title')?.focus();
}
async function openMasterCanvasFromOrdinary(imageId){
 if(S.submitting||S.navigationPending)return;const data=masterCanvasOrdinarySource(imageId);if(data.error)return toast(data.error);
 const epoch=viewEpoch;if(S.pv&&typeof closePv==='function')await closePv();else await persistPromptDraft();if(epoch!==viewEpoch)return;
 showMasterCanvasDialog(data);
}
function openMasterCanvasFromLearningBaseline(){
 const run=LEARNING_RUNS.current;if(!run||learningRunBusy(run)||LEARNING_RUNS.actionBusy||isSharedCanvasRun(run))return;
 if(!learningBaselineApproved(run)||(S.learningBaselineVersion??run.baseline.version)!==run.baseline.version)return toast('请先查看并确认当前基准图');
 showMasterCanvasDialog({source:{kind:'learning',run_id:run.id,baseline:true,baseline_version:run.baseline.version},targetKind:'learning',count:1,expectedMode:run.mode,title:'已确认基准图 · 第'+run.baseline.version+'版',returnFocusId:'master-canvas-learning-baseline',previews:[{url:run.baseline.image_url,label:'基准图第'+run.baseline.version+'版'}]},run.params.pids);
}
function openMasterCanvasFromLearningOutput(outputId,version){
 const run=LEARNING_RUNS.current;if(!run||learningRunBusy(run)||LEARNING_RUNS.actionBusy)return;
 if(isSharedCanvasRun(run)&&run.target_kind==='ordinary')return toast('请从原普通任务的完整套图建立多尺寸计划');
 const output=(run.outputs||[]).find(row=>row.id===outputId);
 if(!output||output.status!=='done'||Number(version)!==output.version)return toast('请先切回当前已完成的图片版本');
 showMasterCanvasDialog({source:{kind:'learning',run_id:run.id,output_ids:[output.id],versions:{[output.id]:output.version}},targetKind:'learning',count:1,expectedMode:run.mode,title:(output.platform||output.channel||'当前渠道')+' · '+output.width+'×'+output.height+' · 第'+output.version+'版',returnFocusId:'learning-output-detail-'+encodeURIComponent(output.id),previews:[{url:output.image_url,label:'当前成品第'+output.version+'版'}]});
}
function closeMasterCanvasDialog(){if(S.masterCanvasDialog?.busy)return;const focusId=S.masterCanvasDialog?.returnFocusId;S.masterCanvasDialog=null;render();if(focusId)document.getElementById(focusId)?.focus({preventScroll:true})}
function setMasterCanvasTarget(id){
 const dialog=S.masterCanvasDialog;if(!dialog||dialog.busy||!dialog.targets.some(placement=>placement.id===id))return;
 dialog.pids=dialog.pids.includes(id)?dialog.pids.filter(value=>value!==id):[...dialog.pids,id];dialog.key=crypto.randomUUID();dialog.error='';render();
}
function setMasterCanvasTargets(all){const dialog=S.masterCanvasDialog;if(!dialog||dialog.busy)return;dialog.pids=all?dialog.targets.map(placement=>placement.id):[];dialog.key=crypto.randomUUID();dialog.error='';render()}
function setMasterCanvasUseRaw(value){const dialog=S.masterCanvasDialog;if(!dialog||dialog.busy||dialog.source.kind!=='ordinary'||!dialog.rawAvailable)return;dialog.source.use_raw=!!value;dialog.key=crypto.randomUUID();dialog.error='';render()}
async function createMasterCanvasRun(){
 const dialog=S.masterCanvasDialog;if(!dialog||dialog.busy)return;if(!dialog.pids.length){dialog.error='请选择至少一个目标版位';render();return}
 dialog.busy=true;dialog.error='';render();const epoch=viewEpoch;
 try{const run=await request('/master-canvases','POST',{source:structuredClone(dialog.source),target_kind:dialog.targetKind,pids:[...dialog.pids],idempotency_key:dialog.key});
  if(epoch!==viewEpoch||S.masterCanvasDialog!==dialog)return;
  if(run.kind!=='shared_canvas_adaptation')throw new Error('共用母版计划数据不完整，请刷新后核对');
  if(dialog.expectedMode&&run.mode!==dialog.expectedMode)throw new Error('新计划模式与来源不一致，已停止；请刷新核对');
  installLearningRun(run);S.masterCanvasDialog=null;S.cur=null;S.view='learning-run';S.pv=null;S.pvDetails=null;S.learningImagePreview=null;S.learningOutputVersions={};S.learningBaselineVersion=null;S.learningBaselineExpanded=true;S.learningRunChannel='';S.learningStage='plan';S.learningStageRun=run.id;S.learningOutputFilter='all';
  save(false);render();toast('多尺寸计划已建立，尚未调用图片模型；请查看调用数和裁切计划后生成共用母版');
 }catch(error){if(epoch===viewEpoch&&S.masterCanvasDialog===dialog){dialog.error=error.message;if(error.status&&error.status<500)dialog.key=crypto.randomUUID()}}
 finally{dialog.busy=false;if(epoch===viewEpoch)render()}
}
function viewMasterCanvasDialog(){
 const dialog=S.masterCanvasDialog;if(!dialog)return '';
 const groups=new Map();for(const placement of dialog.targets){if(!groups.has(placement.platform))groups.set(placement.platform,[]);groups.get(placement.platform).push(placement)}
 return `<div class="mask master-canvas-modal" role="dialog" aria-modal="true" aria-label="制作多尺寸共用母版" onclick="if(event.target===this)closeMasterCanvasDialog()"><div class="master-canvas-dialog"><header><h2 id="master-canvas-title" tabindex="-1">制作多尺寸母版</h2><button class="x" ${dialog.busy?'disabled':''} aria-label="关闭多尺寸计划" onclick="closeMasterCanvasDialog()">×</button></header><p class="field-help">来源：${esc(dialog.title)}。保留原图片，先创建计划，不自动提交图片模型。</p>${dialog.previews?.length?`<div class="master-canvas-source-previews">${dialog.previews.map(image=>`<figure>${(dialog.source.use_raw?image.raw_url||image.url:image.url)?`<img src="${esc(dialog.source.use_raw?image.raw_url||image.url:image.url)}" alt="${esc(image.label)}">`:''}<figcaption>${esc(image.label)}</figcaption></figure>`).join('')}</div>`:''}${dialog.source.kind==='ordinary'&&dialog.rawAvailable?`<label class="master-canvas-raw-choice"><input type="checkbox" ${dialog.source.use_raw?'checked':''} ${dialog.busy||!dialog.rawAvailable?'disabled':''} onchange="setMasterCanvasUseRaw(this.checked)"><span>使用模型原始画布<small>原始画布仍需按目标规格重新适配；新共用母版重构后再按目标导出。</small></span></label>`:''}<div class="master-canvas-target-heading"><b>选择目标版位 · ${dialog.pids.length}/${dialog.targets.length}</b><div><button ${dialog.busy?'disabled':''} onclick="setMasterCanvasTargets(true)">全选</button><button ${dialog.busy?'disabled':''} onclick="setMasterCanvasTargets(false)">清空</button></div></div><div class="master-canvas-targets">${[...groups].map(([channel,placements])=>`<section><h3>${esc(channel)}</h3>${placements.map(placement=>`<label><input type="checkbox" id="master-canvas-target-${esc(encodeURIComponent(placement.id))}" ${dialog.pids.includes(placement.id)?'checked':''} ${dialog.busy?'disabled':''} onchange="setMasterCanvasTarget(${learningRunJs(placement.id)})"><span>${esc(placement.name)} · ${placement.target_width}×${placement.target_height}${Number(placement.image_count)>1?' · '+placement.image_count+'张':''}</span></label>`).join('')}</section>`).join('')}</div>${dialog.error?`<p class="errtx" role="alert">${esc(dialog.error)}</p>`:''}<footer><p>创建后查看预计调用数和裁切方案，再明确生成共用母版。</p><button ${dialog.busy?'disabled':''} onclick="closeMasterCanvasDialog()">取消</button><button class="primary" id="create-master-canvas-plan" ${dialog.busy||!dialog.pids.length?'disabled':''} onclick="createMasterCanvasRun()">${dialog.busy?'正在建立计划…':'建立多尺寸计划'}</button></footer></div></div>`;
}
function viewSharedCanvasSource(run,busy,suiteDone,suiteNeedsQuery){
 const source=run.baseline||{},approved=learningBaselineApproved(run),expanded=S.learningBaselineExpanded??!run.outputs?.some(output=>output.image_url),sourceCount=run.source_summary?.image_count;
 const images=Array.isArray(run.source_images)&&run.source_images.length?run.source_images:source.image_url?[{image_index:1,image_url:source.image_url}]:[];
 return `<section class="card learning-run-baseline shared-canvas-source ${expanded?'expanded':'compact'}"><div class="section-heading"><div><h2>1 · 来源图与共用母版</h2><p class="field-help">使用已选择的来源图，保留原图片和旧任务；不另生一张无文案基准图。</p></div><button id="learning-baseline-toggle" aria-expanded="${expanded}" onclick="setLearningBaselineExpanded(${!expanded})">${expanded?'收起来源图':'查看来源图'}</button></div>${expanded?`<div class="shared-canvas-source-images">${images.map(image=>`<figure><button class="learning-image-button" onclick="openLearningImage(${learningRunJs(image.image_url)},${learningRunJs('来源图'+image.image_index+(image.width&&image.height?' · '+image.width+'×'+image.height:''))})"><img src="${esc(image.image_url)}" alt="来源图${image.image_index}"></button><figcaption>来源图${image.image_index}${image.width&&image.height?' · '+image.width+'×'+image.height:''}${image.source_contains_logo?' · 原图含Logo':''}</figcaption></figure>`).join('')||'<div class="learning-run-placeholder">来源图尚未就绪，请重新读取状态。</div>'}</div>`:''}${Number.isInteger(sourceCount)&&sourceCount>1?`<p class="field-help">完整${sourceCount}张来源按各自剧情分别适配，不混用另一张图的文案。</p>`:''}${run.source_summary?.copy_basis==='frozen_task_copy'?'<p class="shared-canvas-copy-note">文案采用原任务冻结的确认文字，不根据图片OCR猜测。若图片曾手工改字，请先核对下方母版文案再生成。</p>':''}<div class="learning-run-actions"><button class="primary" id="learning-run-expand" ${busy||!approved||suiteDone?'disabled':''} onclick="learningRunAction('expand')">${suiteDone?'共用母版与成品已完成':suiteNeedsQuery?'恢复已有母版查询':['failed','interrupted','completed'].includes(run.suite?.status)?'恢复未完成适配':'生成共用母版'}</button></div><p class="field-help">先生成完整自然母版，再按各目标尺寸裁出，Logo最后按规则叠加。</p></section>`;
}
function viewSharedCanvasPlan(run){
 const plans=Array.isArray(run.crop_plan)?run.crop_plan:[],counts=run.counts||{},calls=Number.isInteger(counts.expected_new_calls)?counts.expected_new_calls:Number.isInteger(counts.planned_image_calls)?counts.planned_image_calls:null;
 const targetName=id=>{const output=(run.outputs||[]).find(row=>row.id===id||row.placement_id===id);return output?[output.platform||output.channel||'',output.name||'',output.width&&output.height?output.width+'×'+output.height:''].filter(Boolean).join(' · '):id};
 const box=value=>Array.isArray(value)&&value.length===4&&value.every(Number.isFinite)?value.map(number=>Number((number*100).toFixed(1))+'%').join(' / '):'未提供';
 const textLabels={t1:'正文',t2:'副标题',mainTitle:'主标题',subtitle:'副标题',cta:'CTA'};
 const copy=plan=>Object.entries(plan.allowed_text||{}).map(([key,value])=>`<b>${esc(textLabels[key]||key)}</b>：${esc(typeof value==='string'?value:JSON.stringify(value))}`).join('<br>');
 return `<section class="card shared-canvas-plan"><div class="section-heading"><h2>共用母版计划</h2><span>${Number.isInteger(counts.master_count)?counts.master_count+'组母版':''}${calls!==null?' · 预计新增'+calls+'次图片模型调用':''}</span></div><p class="field-help">创建计划不调用模型；点击“生成共用母版”后才开始。裁切坐标只说明几何保留范围，成图仍需查看人物、文字和背景。</p>${plans.length?`<details><summary>查看各母版文案、目标尺寸与裁切范围</summary><div class="shared-canvas-plan-table"><table><thead><tr><th>母版 / 画幅</th><th>来源图</th><th>确认文案</th><th>目标版位</th><th>共同保留框<br>左 / 上 / 右 / 下坐标</th></tr></thead><tbody>${plans.map(plan=>`<tr><td>${esc(plan.id||'')}<br>${esc(plan.aspect_ratio||'')}</td><td>${Number.isInteger(plan.source_index)?'图'+plan.source_index:''}</td><td>${copy(plan)||'无广告文字'}</td><td>${(plan.target_ids||[]).map(id=>esc(targetName(id))).join('<br>')}</td><td>${esc(box(plan.shared_keep_box))}</td></tr>`).join('')}</tbody></table></div></details>`:''}</section>`;
}
document.addEventListener('keydown',event=>{
 if(!S.masterCanvasDialog)return;
 if(event.key==='Escape'){event.preventDefault();closeMasterCanvasDialog();return}
 if(event.key==='Tab'){const controls=[...document.querySelectorAll('.master-canvas-modal input,.master-canvas-modal button')].filter(control=>!control.disabled&&(!control.getClientRects||control.getClientRects().length));if(!controls.length)return;
  const first=controls[0],last=controls.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
 }
});
