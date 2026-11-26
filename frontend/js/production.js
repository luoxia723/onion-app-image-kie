/* Presentation of frozen run state. Tabs never submit a generation request. */
function productionStages(run){return isSharedCanvasRun(run)?[['plan','来源与计划'],['progress','制作进度'],['results','成品'],['packages','图包记录']]:[['baseline','基准图'],['progress','制作进度'],['results','成品'],['packages','图包记录']]}
function productionStage(run){
 const choices=productionStages(run).map(([key])=>key);
 if(S.learningStageRun===run.id&&choices.includes(S.learningStage))return S.learningStage;
 if(isSharedCanvasRun(run)&&run.suite?.status==='not_started')return 'plan';
 if(run.status==='completed')return 'results';
 if(run.suite?.status&&run.suite.status!=='not_started')return 'progress';
 return isSharedCanvasRun(run)?'plan':'baseline';
}
function setLearningStage(stage){
 const run=LEARNING_RUNS.current;if(!run||!productionStages(run).some(([key])=>key===stage))return;
 S.learningStage=stage;S.learningStageRun=run.id;S.learningImagePreview=null;render();
 document.getElementById('learning-stage-'+stage)?.focus({preventScroll:true});document.getElementById('main')?.scrollTo?.(0,0);
}
function productionSelectStage(run,stage){S.learningStageRun=run.id;S.learningStage=stage}
function viewProductionHead(){
 const run=LEARNING_RUNS.current;if(!run)return '<header class="head" id="head"><h1>正在读取任务</h1></header>';
 const type=isSharedCanvasRun(run)?'多尺寸适配':'学习机整套',done=(run.outputs||[]).filter(o=>o.status==='done').length;
 return `<header class="head pick-head production-head" id="head"><div class="pick-heading"><h1>${esc(run.name||run.params?.t1||type)}</h1><span class="type-pill">${type}</span><span class="status-pill ${run.busy?'running':run.status==='completed'?'completed':['failed','interrupted'].includes(run.status)||!isSharedCanvasRun(run)&&run.baseline?.status==='done'&&!learningBaselineApproved(run)?'attention':'ready'}">${esc(learningRunStatusLabel(run))}</span><span class="page-context">${run.mode==='real'?'真实制作':'历史模拟'}${run.outputs?.length?' · '+done+'/'+run.outputs.length+'张':''}</span></div><button onclick="backFromLearningRun()">返回任务列表</button></header>`;
}
function viewProductionStart(){
 const disabled=S.submitting||S.navigationPending||LEARNING_RUNS.actionBusy||!!S.uploadingPurpose;
 return `<div class="learning-run-start"><button class="primary" id="learning-start-real" ${disabled?'disabled':''} onclick="startLearningRun()">${learningConcept(S.draft)?'查看并确认概念图':'生成基准图'}</button><p class="field-help">${learningConcept(S.draft)?'确认概念图和文案后开始扩整套。':'基准图完成后，确认它再扩整套。'}</p></div>`;
}
async function confirmAndExpandLearningRun(){
 if(LEARNING_RUNS.confirmingSuite||LEARNING_RUNS.actionBusy)return;
 const run=LEARNING_RUNS.current;if(!run||isSharedCanvasRun(run)||learningRunBusy(run))return;
 LEARNING_RUNS.confirmingSuite=true;
 try{await learningRunAction('confirm');if(LEARNING_RUNS.current?.id===run.id&&learningBaselineApproved(LEARNING_RUNS.current)&&!learningRunBusy())await learningRunAction('expand')}
 finally{LEARNING_RUNS.confirmingSuite=false}
}
function productionSuiteReady(run){return run.suite?.status==='completed'&&run.suite.baseline_version===run.baseline?.version&&learningRunOutputsReady(run)}
function productionExpandButton(run,busy,id='learning-run-expand'){
 const rows=[...(run.masters||[]),...(run.outputs||[])],complete=productionSuiteReady(run);
 const needsReview=rows.some(needsKieReceiptReview);
 const label=complete?'这一套已完成':needsReview?'等待回执核对'
  :rows.some(row=>kieRecoveryAction(row)==='resume')?'恢复整套查询'
  :['failed','interrupted','completed'].includes(run.suite?.status)?'恢复未完成图片'
  :isSharedCanvasRun(run)?'生成共用母版':'扩展整套';
 return `<button class="primary" id="${id}" ${busy||!learningBaselineApproved(run)||complete||needsReview?'disabled':''} onclick="learningRunAction('expand')">${label}</button>`;
}
function viewProductionBaseline(run,busy){
 const baseline=run.baseline||{},versions=learningVersions(baseline,run.baseline_versions),selectedVersion=S.learningBaselineVersion??baseline.version,selected=versions.find(v=>v.version===selectedVersion)||baseline,approved=learningBaselineApproved(run),current=selectedVersion===baseline.version;
 return `<div class="learning-baseline-layout"><section class="card learning-baseline-preview"><div class="section-heading"><h2>${run.concept?'上传的概念图':'基准图'}</h2><div class="row">${versions.length?`<select aria-label="基准图版本" onchange="setLearningBaselineVersion(this.value)">${versions.map(v=>`<option value="${v.version}" ${v.version===selectedVersion?'selected':''}>第${v.version}版${v.version===baseline.version?' · 当前':''}</option>`).join('')}</select>`:''}<span class="aspect-tag">${esc(baseline.aspect_ratio||'16:9')}</span></div></div><div class="learning-baseline-stage">${selected.image_url?learningImageButton(selected,'基准图第'+selected.version+'版','baseline','baseline'):`<div class="learning-run-placeholder" role="status"><b>${kieRecoveryStatus(baseline)||(['generating','queued'].includes(baseline.status)?'正在制作基准图…':baseline.status==='failed'?'基准图需要处理':'基准图尚未生成')}</b><span>生成后先查看这张图，确认之前不会扩展整套。</span></div>`}</div>${baseline.error?`<p class="inline-error" role="alert">${esc(baseline.error)}</p>`:''}${run.outputs?.some(o=>o.image_url&&o.baseline_version!==baseline.version)?'<p class="inline-warning">已有成品来自之前的基准版本，继续保留；再次确认并扩套后才会制作新一套。</p>':''}${viewLearningActualPrompt(run,selected,'baseline','baseline')}<details class="baseline-source-details"><summary>基准图来源与制作方式</summary>${viewLearningBaselineSource(run)||'<p class="field-help">本批次生成并保存的视觉依据。</p>'}<button id="learning-run-from-baseline" ${run.mode!=='real'||busy||!approved||!current?'disabled':''} onclick="makeLearningRunFromBaseline()">沿用基准图按新规则制作</button>${run.mode==='real'&&typeof openMasterCanvasFromLearningBaseline==='function'?`<button ${busy||!approved||!current?'disabled':''} onclick="openMasterCanvasFromLearningBaseline()">制作多尺寸母版</button>`:''}</details></section><section class="card learning-baseline-summary"><h2>确认本套视觉</h2><dl><div><dt>推广文案</dt><dd>${esc(run.params?.t1||'—')}</dd></div><div><dt>CTA</dt><dd>${esc(run.params?.cta||'无')}</dd></div><div><dt>输出</dt><dd>${run.params?.pids?.length||0}个版位 / ${run.outputs?.length||run.counts?.output_count||0}张PNG</dd></div></dl><p class="field-help">${approved?'基准图当前版本已确认，后续版位沿用同一套视觉。':'这张图确定整套角色、画风和场景，确认后才会制作其他版位。'}</p>${!current?'<p class="inline-error">正在查看历史基准图，切回当前版本后才能确认。</p>':''}<button class="primary" id="learning-run-confirm" ${busy||approved||!current||baseline.status!=='done'||!baseline.image_url?'disabled':''} ${approved||needsKieReceiptReview(baseline)?'hidden':''} onclick="confirmAndExpandLearningRun()">确认此图并扩展整套</button><div ${approved?'':'hidden'}>${productionExpandButton(run,busy)}</div>${current&&needsKieReceiptReview(baseline)?viewLearningKieRecovery(run,'baseline',baseline,busy):''}<button id="learning-run-baseline" ${run.concept||needsKieReceiptReview(baseline)?'hidden':''} ${busy?'disabled':''} onclick="learningRunAction('baseline')">${kieRecoveryAction(baseline)==='resume'?'恢复基准图查询':baseline.version?'重新生成基准图':'生成基准图'}</button><p class="field-help">旧版本保留。${run.mode==='simulation'?'本批为演练图片，不调用模型。':''}</p></section></div>`;
}
function productionMasterType(master){return ({pure:'纯画面',visual_only:'纯画面',copy:'正文，无CTA',copy_cta:'正文＋CTA'})[master.content_mode]||master.group_id||'母版'}
function toggleProductionMaster(id){S.learningExpandedMaster=S.learningExpandedMaster===id?null:id;render()}
function productionVisualLabel(row){
 const kie=kieRecoveryStatus(row);if(kie)return kie;
 const review=row.visual_review;
 if(row.status==='processing'&&review){
  if(review.status==='repairing')return '正在修复文字';
  if(review.status==='reviewing_repair')return 'Luna 正在复审';
  if(review.status==='reviewing')return 'Luna 正在审核';
 }
 return LEARNING_IMAGE_STATUS[row.status]||row.status;
}
function viewProductionVisual(kind,row,busy,current){
 const review=row.visual_review;if(!review)return '';
 const buttons=[],held=row.status==='visual_hold'&&current&&!needsKieReceiptReview(row);
 const action=(name,label)=>`<button ${busy?'disabled':''} onclick="resolveLearningVisual('${kind}',${learningRunJs(row.id)},'${name}')">${label}</button>`;
 if(held&&review.can_accept)buttons.push(action('accept','确认无误，继续制作'));
 if(held&&review.can_repair)buttons.push(action('repair','确认有问题，修复文字'));
 if(held&&review.can_recompose)buttons.push(action('recompose','重新构图本组'));
 if(held)buttons.push(action('retry','重试 Luna 审核'));
 if(current&&review.can_clean_lettering)buttons.push(action('clean_lettering','确认字形问题并清修本组'));
 const state={approved:review.approved_by==='human'?'人工复核通过':review.repaired?'Nano Banana 修复 · Luna 通过':'Luna 审核通过',
  reviewing:'Luna 正在审核',repairing:'Nano Banana 正在修复',reviewing_repair:'Luna 正在复审',
  unavailable:'Luna 审核未完成',needs_review:'待核对文字'}[review.status];
 const labels={pass:'通过',repair:'发现问题',review:'有疑点',unavailable:'接口暂不可用'};
 const assessments=[['初审',review.first],['独立复核',review.verification],['修复后初审',review.after],['修复后复核',review.after_verification]];
 const focal=[review.before_focus,review.after_focus].filter(Boolean).map(item=>
  `<details open><summary>疑字局部复核 · ${esc(labels[item.verdict]||item.verdict)}</summary>${item.checks.filter(check=>check.text).map(check=>`<p class="field-help">读到「${esc(check.text)}」</p>`).join('')}</details>`).join('');
 const brush=[review.before_brush,review.after_brush].filter(Boolean).map(item=>
  `<details open><summary>原图笔触复核 · ${esc(labels[item.verdict]||item.verdict)}</summary><p class="field-help">${esc(item.detail||'可重试复核')}</p></details>`).join('');
 return `<div class="learning-visual-review"><h4>文字审核</h4><p class="field-help">${esc(state||'')}</p>${held&&review.can_repair?'<p class="field-help">确认问题后将发起一次 Nano Banana 修复。</p>':''}<div class="learning-detail-actions">${buttons.join('')}${review.original_url?`<a href="${esc(review.original_url)}" target="_blank" rel="noopener">查看审核原图</a>`:''}${review.repair_url?`<a href="${esc(review.repair_url)}" target="_blank" rel="noopener">查看修复图</a>`:''}</div>${focal}${brush}${assessments.filter(([,item])=>item).map(([label,item])=>`<details ${held?'open':''}><summary>${label} · ${esc(labels[item.verdict]||item.verdict)}</summary>${item.body?`<p class="field-help">${esc(item.body)}</p>`:''}${item.issues?.length?`<ul>${item.issues.map(issue=>`<li>${esc(issue.where)} ${esc(issue.detail)}</li>`).join('')}</ul>`:''}</details>`).join('')}</div>`;
}
function viewProductionProgress(run,busy){
 const outputs=run.outputs||[],done=outputs.filter(o=>o.status==='done').length,masters=run.masters||[],complete=masters.filter(m=>m.status==='done').length;
 return `<div class="learning-progress-layout"><div><section class="card production-progress"><div class="section-heading"><h2>整体进度</h2><span>${done}/${outputs.length}张成品</span></div><progress value="${done}" max="${Math.max(1,outputs.length)}" aria-label="成品完成进度"></progress><p class="field-help">显示实际完成数量，不估算剩余时间。</p></section><section class="card production-masters"><div class="section-heading"><h2>母版制作</h2><span class="field-help">共${masters.length}组 · ${complete}组完成</span></div><div class="workspace-table-scroll"><table class="workspace-table"><thead><tr><th>画面与画幅</th><th>状态</th><th>操作</th></tr></thead><tbody>${masters.map(m=>`<tr><td>${esc(productionMasterType(m))}<small class="workspace-progress">${esc(m.aspect_ratio||'')} · ${esc(m.group_id||m.id)}${m.concept_route?' · '+esc(learningConceptRouteLabel(m.concept_route)):''}</small></td><td><span class="status-pill ${m.status==='done'?'completed':m.query_required||['failed','interrupted','visual_hold'].includes(m.status)?'attention':'running'}">${esc(productionVisualLabel(m))}</span></td><td><button class="link-button" aria-expanded="${S.learningExpandedMaster===m.id}" onclick="toggleProductionMaster(${learningRunJs(m.id)})">查看记录</button>${m.image_url?`<button class="link-button" onclick="openLearningImage(${learningRunJs(m.image_url)},${learningRunJs('母版 '+(m.group_id||m.id))},'master',${learningRunJs(m.id)},${m.version})">查看图片</button>`:''}${viewProductionMasterActions(run,m,busy)}</td></tr>${S.learningExpandedMaster===m.id?`<tr><td colspan="3"><div class="production-master-detail">${m.error?`<p class="inline-error">${esc(m.error)}</p>`:''}${viewLearningActualPrompt(run,m,'master',m.id,true)}</div></td></tr>`:''}`).join('')}</tbody></table></div></section></div><aside class="card production-task-summary"><h2>任务信息</h2><p class="status-pill ${learningBaselineApproved(run)?'completed':'attention'}">${isSharedCanvasRun(run)?'来源图已固定':learningBaselineApproved(run)?'当前基准图已确认':'等待确认基准图'}</p>${run.baseline?.image_url?`<img src="${esc(run.baseline.image_url)}" alt="本批视觉来源" loading="lazy">`:''}<p class="field-help">${outputs.length}张成品 · ${run.mode==='real'?'真实制作':'历史模拟'}</p><button onclick="setLearningStage('results')">查看已有${done}张成品</button>${productionExpandButton(run,busy,'learning-progress-resume')}<p class="field-help">${busy?'当前制作结束后可恢复，成功结果保留。':'恢复继续未完成分支，已有远端任务沿原请求查询。'}</p><p class="field-help">可离开此页面；请保持本机服务运行。</p></aside></div>`;
}
function setLearningOutputFilter(value){if(!['all','issues','done'].includes(value))return;S.learningOutputFilter=value;render()}
function productionOutputHasIssue(output){return ['failed','blocked','interrupted','visual_hold'].includes(output.status)||output.query_required||output.logo_refresh_pending||output.background_repair_pending}
function viewLearningReviewToolbar(run,busy){
 const total=run.outputs?.length||0;
 const versions=learningReadyVersions(run),ready=Object.keys(versions).length;
 const selected=Object.keys(reviewedDeliveryVersions(learningDeliveryScope(run),versions)).length;
 const all=ready>0&&selected===ready,exportReady=learningRunOutputsReady(run)&&selected===total;
 return `<div class="delivery-review-toolbar learning-review-toolbar">
  <span class="delivery-review-count" role="status">已选 ${selected} / ${total} 张</span><div class="row delivery-review-tools">
   <button id="learning-select-all" ${!ready||busy?'disabled':''} title="应用到本批次所有已完成图片" onclick="setLearningDeliveryReview(${!all})">${all?'取消全选':ready===total?'全选':'全选已完成'}</button>
   <button class="primary" id="learning-run-package" ${busy||!exportReady?'disabled':''} title="${exportReady?'导出当前选中的整套成品':'选中全部成品后可导出'}" onclick="packageLearningRun()">${run.mode==='simulation'?'导出演练图包':'导出整套'}</button>
  </div>
 </div>`;
}
function viewProductionResults(run,busy){
 const outputs=run.outputs||[],filter=S.learningOutputFilter||'all',visible=outputs.filter(o=>filter==='all'||filter==='issues'&&productionOutputHasIssue(o)||filter==='done'&&o.status==='done');
 return `<section class="learning-run-results" id="learning-run-results" tabindex="-1"><div class="section-heading"><h2>按渠道审核成品</h2><label>渠道 <select aria-label="筛选成品渠道" onchange="filterLearningRunChannel(this.value)"><option value="">全部渠道</option>${[...new Set(outputs.map(o=>o.platform||o.channel||'其他渠道'))].map(channel=>`<option value="${esc(channel)}" ${S.learningRunChannel===channel?'selected':''}>${esc(channel)}</option>`).join('')}</select></label></div><div class="workspace-tabs result-status-tabs" role="tablist" aria-label="成品状态">${[['all','全部',outputs.length],['issues','待处理',outputs.filter(productionOutputHasIssue).length],['done','已完成',outputs.filter(o=>o.status==='done').length]].map(([key,label,n])=>`<button role="tab" aria-selected="${filter===key}" onclick="setLearningOutputFilter('${key}')">${label} <small>${n}</small></button>`).join('')}</div>${viewLearningReviewToolbar(run,busy)}<div class="learning-channel-groups">${viewLearningOutputGroups(run,visible,busy,learningBaselineApproved(run))||`<div class="card learning-run-placeholder">${outputs.some(o=>o.image_url)?'当前范围没有图片，可调整渠道或状态筛选。':isSharedCanvasRun(run)?'生成共用母版并适配后，成品会显示在这里。':'确认基准图并扩展后，成品会显示在这里。'}</div>`}</div></section>${viewProductionDelivery(run,busy)}`;
}
function viewProductionOutputRetry(run,output,busy,approved,current,prefix='learning-output'){
 if(!productionOutputHasIssue(output)||!current)return '';
 if(needsKieReceiptReview(output))return viewLearningKieRecovery(run,'output',output,busy,prefix);
 const disabled=busy||!approved?'disabled':'';
 if(learningLogoRefreshPending(output))return `<button class="primary" ${busy?'disabled':''} onclick="refreshLearningRunLogos()">重试Logo更新</button>`;
 if(output.recovery_action==='retired_flow')return `<button class="primary" ${busy||!approved?'disabled':''} onclick="configureLearningRunAgain()">按新规则重新配置</button>`;
 if(output.background_repair_pending)return `<button class="primary" ${busy?'disabled':''} onclick="repairLearningOutputBackground(${learningRunJs(output.id)})">${learningBackgroundRepairLabel(output)}</button>`;
 if(output.status==='visual_hold')return prefix==='learning-detail'?'':`<button class="primary" onclick="openLearningImage('', '文字审核', 'output', ${learningRunJs(output.id)}, ${output.version})">查看文字审核</button>`;
 if(output.status==='blocked'){
  const master=(run.masters||[]).find(row=>row.id===output.master_id);
  if(needsKieReceiptReview(master))return `<button onclick="openLearningImage('', '母版 KIE 回执', 'master', ${learningRunJs(master.id)}, ${master.version})">查看母版回执</button>`;
  if(master?.status==='visual_hold')return viewProductionMasterActions(run,master,busy);
  return productionExpandButton(run,busy,prefix+'-resume-'+encodeURIComponent(output.id));
 }
 return `<button class="primary" ${disabled} onclick="learningRunAction('regenerate',${learningRunJs(output.id)})">${kieRecoveryAction(output)==='resume'?'恢复本图查询':'重新生成本图'}</button>`;
}
function viewProductionOutputRegenerate(run,output,busy,approved,current,prefix='learning-output'){
 if(productionOutputHasIssue(output))return '';
 return `<button id="${prefix}-regenerate-${esc(encodeURIComponent(output.id))}" class="learning-output-regenerate" ${busy||!approved||!current||output.status!=='done'?'disabled':''} onclick="learningRunAction('regenerate',${learningRunJs(output.id)})">重出本图</button>`;
}
function viewProductionOutputBackground(run,output,busy,current){
 if(productionOutputHasIssue(output)||!learningBackgroundCanRepair(output)&&!learningBackgroundCanAdjust(output))return '';
 return `<button class="learning-background-action" ${busy||!current?'disabled':''} onclick="repairLearningOutputBackground(${learningRunJs(output.id)}${learningBackgroundCanAdjust(output)?',true':''})">${learningBackgroundRepairLabel(output)}</button>`;
}
function viewProductionDetailActions(run,output,busy,current){
 return `<div class="learning-detail-actions">${viewProductionOutputRetry(run,output,busy,learningBaselineApproved(run),current,'learning-detail')}${current?viewReviewLogoButton(output,'switchLearningReviewLogo',busy):''}${viewProductionOutputRegenerate(run,output,busy,learningBaselineApproved(run),current,'learning-detail')}${viewProductionOutputBackground(run,output,busy,current)}</div><p class="field-help">${current?'重出只更新本图，旧版本和图包保留。':'历史版本只读，切回当前版本后操作。'}</p>`;
}
function viewProductionImageActions(run,kind,current,selected){
 const busy=learningRunBusy(run)||LEARNING_RUNS.actionBusy,isCurrent=selected.version===current.version;
 if(kind==='output')return viewProductionDetailActions(run,current,busy,isCurrent);
 if(needsKieReceiptReview(current))return isCurrent?viewLearningKieRecovery(run,kind,current,busy,'detail'):'';
 if(kind==='master'&&isSharedCanvasRun(run)&&current.status!=='visual_hold')return viewSharedMasterRetry(run,current,!isCurrent);
 if(kind==='baseline'&&!isSharedCanvasRun(run)&&!run.concept)return `<div class="learning-detail-actions"><button ${busy||!isCurrent?'disabled':''} onclick="learningRunAction('baseline')">${kieRecoveryAction(current)==='resume'?'恢复基准图查询':'重新生成基准图'}</button></div><p class="field-help">${isCurrent?'新基准图需要重新确认，已有成品保留。':'历史版本只读，切回当前版本后操作。'}</p>`;
 return '';
}
function viewProductionMasterActions(run,master,busy){
 if(needsKieReceiptReview(master))return viewLearningKieRecovery(run,'master',master,busy,'progress');
 if(master.status==='visual_hold'){
  const pure=master.concept_route==='pure';
  return `<button class="primary" onclick="openLearningImage('', '${pure?'纯画面审核':'母版文字审核'}', 'master', ${learningRunJs(master.id)}, ${master.version})">${master.visual_review?.status==='unavailable'?'恢复审核':pure?'查看画面审核':'复核文字'}</button>`;
 }
 if(isSharedCanvasRun(run))return viewSharedMasterRetry(run,master);
 if(!master.query_required&&!['failed','interrupted'].includes(master.status))return '';
 return `<div class="master-recovery">${productionExpandButton(run,busy,'learning-master-recover-'+encodeURIComponent(master.id))}<small>继续未完成分支，已有成品保留。</small></div>`;
}
function viewProductionOutput(run,output,busy,approved){
 const versions=learningVersions(output,output.versions),selectedVersion=S.learningOutputVersions?.[output.id]??output.version,selected=versions.find(v=>v.version===selectedVersion)||output,current=selectedVersion===output.version;
 const label=(output.platform||'')+' '+(output.name||'')+' · '+output.width+'×'+output.height+(output.image_index>1?' · 图'+output.image_index:'');
 const regenerate=viewProductionOutputRegenerate(run,output,busy,approved,current);
 const backgroundMore=viewProductionOutputBackground(run,output,busy,current);
 const tags=[output.concept_route?learningConceptRouteLabel(output.concept_route):'',typeof output.main_copy_required==='boolean'?(output.main_copy_required?'有正文':'无正文'):'',typeof output.cta_required==='boolean'?(output.cta_required?'有CTA':'无CTA'):'',selected.logo_template?.asset_id?logoVariantLabel(selected.logo_template.asset_id):typeof output.logo_required==='boolean'?(output.logo_required?'有Logo':'无Logo'):''].filter(Boolean);
 return `<article class="card learning-output-card" data-review-wide="${Number(output.width)>=2*Number(output.height)}" style="--review-ratio:${(Number(output.width)||1)/(Number(output.height)||1)}"><div class="learning-output-heading"><div class="learning-output-label">${viewLearningDeliveryReview(run,selected,current&&!busy)}<h3>${esc(label)}</h3></div><span class="status-pill ${output.status==='done'?'completed':productionOutputHasIssue(output)?'attention':'running'}">${esc(productionVisualLabel(output))}</span></div><div class="learning-output-image ${selected.image_url?'':'without-image'}" ${selected.image_url?`style="aspect-ratio:${Number(output.width)||1}/${Number(output.height)||1}"`:''}>${selected.image_url?learningImageButton(selected,label+' · 第'+selectedVersion+'版','output',output.id):`<div class="learning-run-placeholder">${output.status==='generating'?'正在制作…':output.recovery_action==='retry_export'?'图片已生成，等待压缩导出':productionOutputHasIssue(output)?'本图需要处理':'等待母版与尺寸处理'}</div>`}</div>${tags.length?`<p class="output-content-tags">${tags.map(t=>`<span>${t}</span>`).join('')}</p>`:''}${output.error?`<p class="errtx">${esc(output.error)}</p>`:''}<div class="learning-output-actions">${viewProductionOutputRetry(run,output,busy,approved,current)}${versions.length?`<label>版本<select aria-label="${esc(label)}版本" onchange="setLearningOutputVersion(${learningRunJs(output.id)},this.value)">${versions.map(v=>`<option value="${v.version}" ${v.version===selectedVersion?'selected':''}>第${v.version}版${v.version===output.version?' · 当前':''}</option>`).join('')}</select></label>`:''}<button id="learning-output-detail-${esc(encodeURIComponent(output.id))}" onclick="openLearningImage(${learningRunJs(selected.image_url||'')},${learningRunJs(label)},'output',${learningRunJs(output.id)},${Number(selected.version)||0})">查看详情</button>${current?viewReviewLogoButton(output,'switchLearningReviewLogo',busy):''}${regenerate}${backgroundMore}</div><p class="field-help">${selected.baseline_version?(isSharedCanvasRun(run)?'来源快照第':'基准图第')+selected.baseline_version+'版 · ':''}${learningLogoRefreshPending(output)?'本图为本机Logo更新待恢复，不需要生图':current?'单张重出只更新本图':'正在查看历史版本'}</p>${output.background_repair_pending||learningBackgroundCanRepair(output)||learningBackgroundCanAdjust(output)?viewLearningBackgroundRepairHint(output,run):''}</article>`;
}
function viewProductionDelivery(run,busy){
 const ordinary=isSharedCanvasRun(run)&&run.target_kind==='ordinary';
 if(ordinary)return '';
 return `<section class="card learning-run-delivery"><div class="learning-logo-template-action"><h3>应用已保存的Logo位置模板</h3><button id="learning-refresh-logos" ${busy||!learningRunLogoOutputsReady(run)?'disabled':''} onclick="refreshLearningRunLogos()">${run.outputs.some(learningLogoRefreshPending)?'重试Logo更新':'应用当前Logo模板（不生图）'}</button><p class="field-help">用当前模板重新定位并自动选色，直接更新有 Logo 的成品。</p></div></section>`;
}
function viewProductionPackages(run){return `<section class="card production-packages"><div class="section-heading"><h2>图包记录</h2><button onclick="setLearningStage('results')">返回成品</button></div>${run.packages?.length?run.packages.map(pkg=>`<article class="production-package"><div><h3>图包 v${String(pkg.version).padStart(3,'0')}</h3><p>${pkg.image_count}张 · ${pkg.logo_asset_id?logoVariantLabel(pkg.logo_asset_id):'按各图配置'}${pkg.archive_layout==='channel-placement-v1'?' · 按渠道分目录':''}</p></div><a class="button-link" href="${esc(pkg.download_url)}" download>下载图包</a></article>`).join(''):'<div class="workspace-empty"><h3>还没有保存的图包</h3><p>全部成品完成后，可从成品页保存整套图包。</p></div>'}</section>`}
function viewProductionSharedPlan(run,busy){
 const groups=run.crop_plan||[],outputs=new Map((run.outputs||[]).map(o=>[o.id,o]));
 return `<div class="shared-plan-layout"><section class="card shared-plan-source">${viewSharedCanvasSource(run,busy,productionSuiteReady(run),false)}</section><section class="card shared-plan-groups"><div class="section-heading"><h2>共用母版方案</h2><span>${groups.length}组母版 · 预计新增${run.counts?.expected_new_calls??groups.length}次图片调用</span></div>${groups.map((g,i)=>{const source=(run.source_images||[]).find(s=>s.image_index===g.source_index),box=g.content_safe_box||g.shared_keep_box||[0,0,1,1];return `<section class="shared-plan-group"><div class="section-heading"><h3>母版${i+1} · ${esc(g.aspect_ratio)}</h3><span class="field-help">来源图${g.source_index||1}</span></div><div class="shared-plan-canvas" style="aspect-ratio:${esc(g.aspect_ratio.replace(':','/'))}">${source?.image_url?`<img src="${esc(source.image_url)}" alt="构图来源示意" style="inset:auto;left:${box[0]*100}%;top:${box[1]*100}%;width:${(box[2]-box[0])*100}%;height:${(box[3]-box[1])*100}%">`:''}<div class="shared-safe-box" style="left:${box[0]*100}%;top:${box[1]*100}%;width:${(box[2]-box[0])*100}%;height:${(box[3]-box[1])*100}%"><span>文字与主视觉共同保留区</span></div></div><p class="field-help">构图范围示意，未进行自动内容检测。Logo在尺寸处理后叠加。</p><dl class="shared-copy">${Object.entries(g.allowed_text||{}).map(([key,value])=>`<div><dt>${({t1:'正文',subtitle:'副标题',cta:'CTA'})[key]||'文字'}</dt><dd>${esc(value)}</dd></div>`).join('')||'<div><dt>内容</dt><dd>纯画面，无广告正文和CTA</dd></div>'}</dl><table class="workspace-table"><thead><tr><th>目标渠道与版位</th><th>输出尺寸</th></tr></thead><tbody>${g.target_ids.map(id=>{const o=outputs.get(id)||{};return `<tr><td>${esc([o.platform,o.name].filter(Boolean).join(' · ')||id)}</td><td>${o.width||'—'}×${o.height||'—'}</td></tr>`}).join('')}</tbody></table></section>`}).join('')}${viewSharedCanvasPlan(run)}</section></div>`;
}
function viewProductionRun(){
 const run=LEARNING_RUNS.current;if(!run||run.id!==S.learningRunId)return '<section class="card" role="status">正在读取制作任务…</section>';
 const stage=productionStage(run),busy=learningRunBusy(run)||LEARNING_RUNS.actionBusy,error=LEARNING_RUNS.error||run.error;
 const stageViews={baseline:viewProductionBaseline,plan:viewProductionSharedPlan,progress:viewProductionProgress,
  results:viewProductionResults,packages:viewProductionPackages};
 const tabs=productionStages(run).map(([key,title])=>`<button role="tab" id="production-tab-${key}" aria-selected="${stage===key}" ${stage===key?`aria-controls="learning-stage-${key}"`:''} onclick="setLearningStage('${key}')">${title}${key==='results'?'<small>'+run.outputs.filter(o=>o.status==='done').length+'</small>':''}</button>`).join('');
 return `<div class="learning-run-page">
  ${run.mode==='simulation'?'<div class="learning-simulation-banner" role="note"><b>历史模拟记录</b><span>仅验证操作和尺寸，未调用规划或生图模型。</span></div>':''}
  ${error?`<div class="learning-run-error" role="alert">${esc(error)} <button onclick="refreshLearningRun()">重新读取状态</button></div>`:''}
  <nav class="task-stage-tabs workspace-tabs" role="tablist" aria-label="制作阶段">${tabs}</nav>
  <section id="learning-stage-${stage}" role="tabpanel" aria-labelledby="production-tab-${stage}" tabindex="-1">${stageViews[stage](run,busy)}</section>
  ${viewLearningImageDetails(run)}
 </div>`;
}

function setOrdinaryPreviewPanel(panel){if(!['prompt','references','processing'].includes(panel))return;S.pvPanel=panel;render()}
function editOrdinaryPreviewPrompt(){const s=curPvSlot();if(!s||s.is_historical||s.production_mode==='local_resize'||S.previewStale)return;S.pvEditing=true;S.pvPanel='prompt';render();document.getElementById('pvPrompt')?.focus()}
async function copyOrdinaryActualPrompt(){
 const text=curPvSlot()?.prompt;if(typeof text!=='string'||!text.trim())return toast('此版本没有已保存的实际提示词');
 try{await navigator.clipboard.writeText(text);toast('实际提示词已复制')}
 catch{const field=document.getElementById('pvActualPrompt');field?.focus();if(field&&document.createRange&&window.getSelection){const range=document.createRange();range.selectNodeContents(field);const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range)}toast('无法自动复制，已选择实际提示词，请手动复制')}
}
function reviewZoomButton(frameId){
 return `<button type="button" class="review-zoom" aria-controls="${frameId}" aria-pressed="false" onclick="toggleImageReviewSize(this)">100%</button>`;
}
function toggleImageReviewSize(button){
 const frame=document.getElementById(button.getAttribute('aria-controls'));
 if(!frame)return;
 const fullSize=frame.classList.toggle('is-full-size');
 frame.tabIndex=fullSize?0:-1;
 frame.scrollTo(0,0);
 button.setAttribute('aria-pressed',String(fullSize));
 button.textContent=fullSize?'适应窗口':'100%';
}
function viewXimalayaReviewStrip(slots,currentId){
 return `<nav class="review-filmstrip" aria-label="本套图片">${slots.map(slot=>{
  const placement=plOf(slot.pid),source=slot.image_url||slot.review_image_url,size=psz(placement);
  return `<button type="button" class="review-thumb" aria-current="${slot.id===currentId}" ${source?'':'disabled'} onclick="openPv('${slot.id}')"><span>${source?`<img src="${esc(source)}" alt="" loading="lazy">`:'待生成'}</span><small>${size}</small></button>`;
 }).join('')}</nav>`;
}
function viewProductionOrdinaryPreview(){
 const r=R(),s=curPvSlot();
 if(!s)return `<div class="mask review-mask" id="m-preview"><div class="pv production-image-dialog" role="dialog" aria-modal="true" aria-label="正在加载预览" id="pv"><div class="l"><p role="status">正在读取图片…</p></div><div class="r"><div class="pv-panel-top"><h2>图片详情</h2><button class="x" id="pvx" onclick="closePv()" aria-label="关闭">×</button></div></div></div></div>`;
 const p=plOf(s.pid),retry=imageRetry(r,s),xima=ximalayaIds(r.params),suite=xima.includes(s.pid);
 const selected=!!r.sel[selectionKey(s.pid,s.set)];
 const slots=r.slots.filter(x=>suite?x.set===s.set&&xima.includes(x.pid):x.pid===s.pid)
  .sort((a,b)=>suite?xima.indexOf(a.pid)-xima.indexOf(b.pid):a.set-b.set||a.idx-b.idx);
 const index=slots.findIndex(x=>x.id===s.id),summary=slots[index],panel=S.pvPanel||'prompt';
 const available=slot=>!suite||slot.image_url||slot.review_image_url;
 const previous=slots.slice(0,index).findLast(available),next=slots.slice(index+1).find(available);
 const candidate=suite&&s.state!=='done'&&!s.is_historical&&summary?.att===s.att&&!s.files_cleared?summary.review_image_url:'';
 const original=s.original_image_url,delivery=imgOf(s);
 const versions=(s.history||[]).filter(v=>v.image_url);
 const comparison=S.pvCompare&&versions.length>1;
 const visual=s.files_cleared?'':S.pvOriginal?original:delivery||candidate||original;
 const canEdit=!suite&&!r.generation_disabled&&!s.generation_disabled&&!s.is_historical&&s.production_mode!=='local_resize'&&!S.previewStale&&!needsKieReceiptReview(s);
 const draft=S.promptDraft?.id===s.id?S.promptDraft:null;
 const image=s.files_cleared?'<p>此版本文件已清理，文字记录保留。</p>':comparison?`<div class="compare-images">${versions.slice(-2).map(v=>`<figure><img src="${esc(v.image_url)}" alt="图片第${v.att}版"><figcaption>图片第${v.att}版</figcaption></figure>`).join('')}</div>`:visual?`<img id="pvImg" src="${esc(visual)}" alt="${esc(pname(p))} · ${psz(p)}">`:`<p role="status">${esc(waitLabel(r,s))}</p>`;
 const message=s.ximalaya_review?.message||s.msg;
 const state=suite?`<div class="review-status"><b>${esc(ximalayaStatus(r,s))}</b>${message?`<p>${esc(message)}</p>`:''}</div>`:'';
 const actionsWithContext=needsKieReceiptReview(s)&&!s.is_historical?viewOrdinaryKieRecovery(r,s,'detail'):suite&&s.state!=='done'?(s.is_historical||S.previewStale||r.generation_disabled?'':`<div class="review-recovery">${viewXimalayaRecovery(r,s)}</div>`):`<div class="production-preview-actions" id="pvRetryScope">${r.generation_disabled||s.generation_disabled?`<button class="primary" id="pv-new-generation" ${s.is_historical?'disabled':''} onclick="editRedo()">按新规则重新制作</button>`:`<button class="primary" id="pvredo" ${retry.disabled||s.is_historical||S.previewStale?'disabled':''} onclick="pvRedo()">${draft&&!retry.query?'用编辑稿':''}${esc(retry.label)}</button>`}<p class="pv-scope">${esc(retry.note|| (retry.query?'沿用原任务查询，不重新提交。':s.idx===1&&p.image_count>1?'重出图1会更新本套全部图片，原版本和图包保留。':'只更新本图，旧版本和图包保留。'))}</p>${typeof masterCanvasOrdinarySource==='function'?`<button id="master-canvas-ordinary" ${s.is_historical||S.previewStale||masterCanvasOrdinarySource(s.id).error?'disabled':''} onclick="openMasterCanvasFromOrdinary('${s.id}')">制作多尺寸母版</button>`:''}</div>`;
 return `<div class="mask review-mask" id="m-preview" onclick="if(event.target===this)closePv()"><div class="pv production-image-dialog" role="dialog" aria-modal="true" aria-label="大图预览" id="pv">
 <div class="l">
  <div class="preview-image-tools">
   <button id="pvprev" aria-label="上一张" title="上一张（←）" ${previous?`onclick="openPv('${previous.id}')"`:'disabled'}>←</button>
   <span id="pvCounter">${index+1} / ${slots.length}</span>
   <button id="pvnext" aria-label="下一张" title="下一张（→）" ${next?`onclick="openPv('${next.id}')"`:'disabled'}>→</button>
   <span class="review-tools-spacer"></span>
   ${original?`<button aria-pressed="${!S.pvOriginal&&!S.pvCompare}" onclick="S.pvOriginal=false;S.pvCompare=false;render()">${delivery?'成品':'原图'}</button><button id="pvsource" aria-pressed="${!!S.pvOriginal}" onclick="togglePvOriginal()">生成原图</button>`:''}
   ${versions.length>1?`<button aria-pressed="${!!S.pvCompare}" onclick="comparePrevious()">版本对比</button>`:''}
   ${visual&&!comparison?reviewZoomButton('pv-review-frame'):''}
  </div>
  <div id="pv-review-frame" class="pv-image-frame review-image-frame" role="region" aria-label="图片预览，放大后可滚动查看">
   ${image}
  </div>
  <div class="review-stage-footer">
   <div class="preview-image-facts"><span id="pvkind">${candidate?'审核预览 · 无 Logo':s.preview_kind==='raw'?'待处理原图':S.pvOriginal?'生成原图':'成品预览'}</span><span>${psz(p)}</span>${s.state==='done'&&visual&&!comparison?`<a href="${esc(visual)}" download>下载这张图片</a>`:''}</div>
   ${suite?viewXimalayaReviewStrip(slots,s.id):''}
  </div>
 </div>
 <section class="r"><div class="pv-panel-top"><div class="pvtitle" id="pvTitle">${esc(pname(p))}<small>第${s.set}套 · 图${s.idx} · ${psz(p)}</small></div><button class="x" id="pvx" onclick="closePv()" aria-label="关闭">×</button></div><div class="pv-version-row"><label for="imageVersion">图片版本</label><select id="imageVersion" onchange="openPv('${s.id}',+this.value)">${(s.history||[{att:s.att}]).slice().reverse().map(v=>`<option value="${v.att}" ${v.att===s.att?'selected':''}>第${v.att}版${v.att===(s.history||[]).at(-1)?.att?' · 当前':v.files_cleared?' · 文件已清理':' · 历史'}</option>`).join('')}</select></div>
${s.delivery_eligible===false&&!candidate?'<div class="inline-warning" id="pvwhy">当前图片未通过交付规格，请按新规则重新制作。</div>':''}${s.is_historical?'<p class="field-help">历史版本只读。切回当前版本后才能编辑和重出。</p>':''}${S.previewStale?'<p class="inline-error">当前版本已更新，请重新读取后再操作。</p>':''}${suite?(s.is_historical?'':viewXimalayaDeliveryReview(r,s,!S.previewStale,'pv-review')):`<button class="pv-select ${selected?'checked':''}" id="pvsel" aria-pressed="${selected}" ${!s.is_historical&&s.state==='done'?'':'disabled'} onclick="toggleSel(${s.set},true,'${s.pid}')"><span class="pv-check" aria-hidden="true">✓</span>${selected?'已选中 · 取消选择':'选这一套'}</button>`}${state}
${!s.is_historical&&!S.previewStale?viewReviewLogoButton(s,'switchOrdinaryReviewLogo',S.logoReviewPending||S.exportBusy):''}
${actionsWithContext}
<nav class="workspace-tabs preview-detail-tabs" role="tablist" aria-label="图片详情分类">${[['prompt','实际提示词'],['references','参考素材'],['processing','处理记录']].map(([key,label])=>`<button role="tab" aria-selected="${panel===key}" onclick="setOrdinaryPreviewPanel('${key}')">${label}</button>`).join('')}</nav><section ${panel==='prompt'?'':'hidden'}><div class="pv-prompt-heading"><h4>实际提示词</h4><button class="link-button" onclick="copyOrdinaryActualPrompt()">复制提示词</button></div><pre class="actual-prompt-text" id="pvActualPrompt" tabindex="0">${esc(s.prompt||'此版本未保存提示词')}</pre><div class="prompt-draft-banner" ${draft?'':'hidden'}>有已保存的编辑草稿，尚未生成。</div>${canEdit?`<button id="pv-edit-prompt" onclick="editOrdinaryPreviewPrompt()">编辑提示词</button>`:''}<div class="prompt-editor" ${S.pvEditing&&canEdit?'':'hidden'}><div class="row"><span id="prompt-draft-status" role="status">${esc(S.promptStatus||'编辑稿尚未生成')}</span><button class="link-button" onclick="discardPromptDraft()">放弃草稿</button></div>${s.logo_fixed_rule?`<div class="fixed-logo-rule"><b>Logo固定规则</b><p>${esc(s.logo_fixed_rule)}</p><small>验收时可切换黑字标准版和白字反白版。</small></div>`:''}${s.canvas_fixed_rule?`<div class="fixed-canvas-rule"><b>画幅固定规则</b><p>${esc(s.canvas_fixed_rule)}</p><small>编辑提示词时保留该段，人物和文案按本版位安全区排布。</small></div>`:''}${s.edit_drafts?.length>1?`<label>已保存的编辑草稿<select onchange="choosePromptDraft(this.value)"><option value="">选择草稿</option>${s.edit_drafts.map((d,i)=>`<option value="${esc(d.editor_id)}">草稿${i+1} · ${esc(d.text.slice(0,16))}</option>`).join('')}</select></label>`:''}<textarea class="prompt" id="pvPrompt" aria-label="编辑提示词草稿" maxlength="30000" ${canEdit?'':'readonly'} oninput="pvChk()">${esc(draft?.value??s.prompt??'')}</textarea><button class="link-button" id="pvReset" onclick="pvResetP()">恢复默认提示词</button></div></section><section ${panel==='references'?'':'hidden'}><h4>实际参考素材</h4><div class="refs" id="pvRefs">${refsOf(r,s).map(ref=>`<div class="ref ${ref.bad?'bad':''}" data-ref="${ref.k}"><div>${ref.src?`<img src="${esc(ref.src)}" alt="${esc(ref.name)}" loading="lazy">`:''}</div><span>${esc(ref.name)}</span></div>`).join('')||'<p class="field-help">没有保存可查看的参考图。</p>'}</div></section><section ${panel==='processing'?'':'hidden'}><h4>处理记录</h4><p class="field-help">${esc(s.delivery_eligible===false?'当前图片未通过交付规格，请按新规则重新制作':s.natural_processing?'已按固定安全区从完整自然画布裁成目标尺寸；请查看人物和文字完整性':s.preview_kind==='raw'?'当前显示生成原图。':'以本版本保存的实际成品为准；规格通过不代表自动视觉审核。')}</p>${s.msg?`<p class="field-help">${esc(s.msg)}</p>`:''}<button ${s.files_cleared?'disabled':''} onclick="pinImageVersion()">${s.pinned?'取消保留此版本':'保留此版本'}</button></section></section></div></div>`;
}
