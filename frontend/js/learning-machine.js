/* Learning-machine configuration and offline-only plan preview. */
let LEARNING_MACHINE={config:null,loading:false,error:'',templates:{},revision:null};
let ORDINARY_LOGOS={config:null,loading:false,error:'',templates:{},revision:null};
function logoEditorCategory(){return S.logoTemplateCategory||'学习机'}
function logoEditorStore(){return logoEditorCategory()==='学习机'?LEARNING_MACHINE:ORDINARY_LOGOS}
function learningLogoPlacements(){return (logoEditorStore().config?.placements||[]).filter(p=>logoEditorCategory()==='学习机'||p.category===logoEditorCategory())}
function logoPlacementAssets(p){return ((p?.category==='应用商店'||p?.category==='信息流'?ORDINARY_LOGOS:LEARNING_MACHINE).config?.logo_assets)||LEARNING_MACHINE.config?.logo_assets||[]}
function logoWorkingTemplates(){return logoEditorStore().templates}
function logoCategoryTabs(){return `<div class="logo-category-tabs workspace-tabs" role="tablist" aria-label="Logo模板类型">${['应用商店','信息流','学习机'].map(category=>`<button role="tab" aria-selected="${logoEditorCategory()===category}" onclick="setLogoTemplateCategory('${category}')">${category}</button>`).join('')}</div>`}
async function loadOrdinaryLogoConfig(force=false){
 if(ORDINARY_LOGOS.loading||ORDINARY_LOGOS.config&&!force)return;
 ORDINARY_LOGOS.loading=true;ORDINARY_LOGOS.error='';
 try{installOrdinaryLogoConfig(await request('/logo-templates'))}catch(e){ORDINARY_LOGOS.error=e.message;throw e}finally{ORDINARY_LOGOS.loading=false}
}
function installOrdinaryLogoConfig(config){
 if(!config||!Array.isArray(config.placements)||!Array.isArray(config.logo_assets))throw Error('普通广告Logo配置格式不完整');
 ORDINARY_LOGOS.config=config;ORDINARY_LOGOS.revision=config.revision;ORDINARY_LOGOS.error='';ORDINARY_LOGOS.templates={};
 for(const p of config.placements)if(learningLogoRequired(p))ORDINARY_LOGOS.templates[p.id]=constrainLearningLogo(p,p.logo_template);
}
async function setLogoTemplateCategory(category){
 if(!['应用商店','信息流','学习机'].includes(category)||S.learningLogoSaving)return;
 if(S.learningLogoDirty&&(category==='学习机')!==(logoEditorCategory()==='学习机'))return toast('请先保存当前类型的Logo模板，或重新读取已保存配置');
 S.logoTemplateCategory=category;S.learningLogoQuery='';S.logoTemplatePlatform='';S.logoDirectoryPage=1;S.learningLogoPid=learningLogoPlacements()[0]?.id;S.learningLogoError='';save(false);render();
 try{if(category==='学习机')await loadLearningMachineConfig();else await loadOrdinaryLogoConfig();S.learningLogoPid=learningLogoPlacements()[0]?.id;save(false);render()}catch(e){S.learningLogoError=e.message;render()}
}

function learningLogoAsset(id){return (logoEditorStore().config?.logo_assets||LEARNING_MACHINE.config?.logo_assets||[]).find(a=>(a.id||a.asset_id)===id)}
function learningLogoRequired(p){if(typeof p.logo_required==='boolean')return p.logo_required;return p.content_modules?.logo===true||p.content_modules?.logo_policy==='required'||p.logo_policy==='required'}
function learningLogoPlacement(){return learningLogoPlacements().find(p=>p.id===S.learningLogoPid)||learningLogoPlacements()[0]}
function logoCanvasSize(p){return {width:Number(p.target_width||p.size?.[0]||1),height:Number(p.target_height||p.size?.[1]||1)}}
function constrainLearningLogo(p,value){
 const assets=logoPlacementAssets(p),asset=assets.find(a=>(a.id||a.asset_id)===value.asset_id)||assets[0],size=logoCanvasSize(p);
 if(!asset)return {asset_id:'',x:0,y:0,width:.15};
 const safeRatio=Math.min(...assets.map(a=>a.width/a.height)),maxWidth=Math.min(1,size.height/size.width*safeRatio);
 const finite=(v,d)=>Number.isFinite(Number(v))?Number(v):d;
 const width=Math.min(maxWidth,Math.max(Math.min(.01,maxWidth),finite(value.width,.15)));
 const height=width*size.width/safeRatio/size.height;
 return {asset_id:asset.id||asset.asset_id,x:Math.max(0,Math.min(1-width,finite(value.x,.025))),y:Math.max(0,Math.min(1-height,finite(value.y,.03))),width};
}
function installLearningMachineConfig(config,{keepWorking=false}={}){
 if(!config||!Array.isArray(config.placements)||!Array.isArray(config.logo_assets))throw new Error('学习机配置格式不完整');
 invalidateLearningPreview();
 LEARNING_MACHINE.config=config;LEARNING_MACHINE.revision=config.revision;LEARNING_MACHINE.error='';
 const mapped=config.placements.map(p=>{
  const old=PLACEMENTS.find(q=>q.id===p.id)||{},modules=p.content_modules||p.modules||old.learning_rule?.modules||{};
  const logo=learningLogoRequired(p),cta=modules.cta??modules.download_button??p.cta_required??p.cta_policy==='required';
  return {...old,...p,category:'学习机',image_form:'单图',image_count:Number(p.image_count||p.output_count||old.image_count||1),target_width:logoCanvasSize(p).width,target_height:logoCanvasSize(p).height,enabled:true,
   learning_rule:{...old.learning_rule,modules:{...modules,logo,cta}},logo_policy:logo?'required':'forbidden',cta_policy:cta?'required':'forbidden',rule_summary:'PNG · '+(logo?'有Logo':'无Logo')+' · '+(cta?'有CTA':'无CTA')};
 });
 PLACEMENTS=[...PLACEMENTS.filter(p=>p.category!=='学习机'),...mapped];UNAVAILABLE_PLACEMENTS=UNAVAILABLE_PLACEMENTS.filter(p=>p.category!=='学习机');
 const working={};for(const p of config.placements)if(learningLogoRequired(p)){
  const saved=p.logo_template||config.logo_templates?.[p.id]||{};
  working[p.id]=constrainLearningLogo(p,keepWorking&&LEARNING_MACHINE.templates[p.id]||saved);
 }
 LEARNING_MACHINE.templates=working;
 if(learningForm(S.draft)){normalizeLearningDraft(S.draft,!!S.learningAutoSelectAll);filterFormPlacements(S.draft)}
}
async function loadLearningMachineConfig(force=false){
 if(LEARNING_MACHINE.loading)return;
 if(LEARNING_MACHINE.config&&!force)return LEARNING_MACHINE.config;
 LEARNING_MACHINE.loading=true;LEARNING_MACHINE.error='';
 try{const config=await request('/learning-machine/config');installLearningMachineConfig(config,{keepWorking:!!S.learningLogoDirty&&!force});return config}
 catch(e){LEARNING_MACHINE.error=e.message||'读取学习机配置失败';throw e}
 finally{LEARNING_MACHINE.loading=false;if(S.view==='learning-logo'||learningForm(S.draft))render()}
}
async function openLearningLogoConfig(category){
 if(S.submitting||S.navigationPending)return;
 await persistDraft();S.view='learning-logo';S.learningLogoError='';
 if(!S.learningLogoDirty)S.logoTemplateCategory=category||S.logoTemplateCategory||(learningForm(S.draft)?'学习机':'应用商店');save(false);render();
 try{if(logoEditorCategory()==='学习机')await loadLearningMachineConfig();else await loadOrdinaryLogoConfig();if(!learningLogoPlacements().some(p=>p.id===S.learningLogoPid))S.learningLogoPid=learningLogoPlacements()[0]?.id;save(false);render()}catch(e){S.learningLogoError=e.message;render()}
}
function closeLearningLogoConfig(){if(typeof openWorkspacePage==='function')return openWorkspacePage('tasks');S.view='form';save(false);render()}
function chooseLearningLogoPlacement(id){if(!learningLogoPlacements().some(p=>p.id===id))return;S.learningLogoPid=id;S.learningLogoError='';save(false);render()}
function setLearningLogoValue(key,value){if(S.learningLogoSaving)return;const p=learningLogoPlacement();if(!p||!learningLogoRequired(p)||!['x','y','width'].includes(key)||value==='')return;
 invalidateLearningPreview();logoWorkingTemplates()[p.id]=constrainLearningLogo(p,{...logoWorkingTemplates()[p.id],[key]:Number(value)/100});S.learningLogoDirty=true;updateLearningLogoPreview();
}
function syncLearningLogoField(key,field){const p=learningLogoPlacement(),t=p&&logoWorkingTemplates()[p.id];if(t&&field)field.value=(t[key]*100).toFixed(2)}
function updateLearningLogoPreview(){
 const p=learningLogoPlacement(),t=p&&logoWorkingTemplates()[p.id],logo=document.getElementById('learning-logo-image');if(!p||!t||!logo)return;
 logo.style.left=t.x*100+'%';logo.style.top=t.y*100+'%';logo.style.width=t.width*100+'%';
 const status=document.getElementById('learning-logo-save-status');if(status)status.textContent='有未保存的修改';
 for(const key of ['x','y','width']){const field=document.getElementById('learning-logo-'+key);if(field&&field!==document.activeElement)field.value=(t[key]*100).toFixed(2)}
 const pixels=document.getElementById('learning-logo-pixels');if(pixels){const size=logoCanvasSize(p);pixels.textContent=`位置 ${Math.round(t.x*size.width)}, ${Math.round(t.y*size.height)} px · 宽 ${Math.round(t.width*size.width)} px`}
}
function startLearningLogoDrag(event){
 if(event.button!==0||S.learningLogoSaving)return;const p=learningLogoPlacement(),board=document.getElementById('learning-logo-board');if(!p||!learningLogoRequired(p)||!board)return;
 event.preventDefault();const original={...logoWorkingTemplates()[p.id]},box=board.getBoundingClientRect(),pointer=event.pointerId,target=event.currentTarget;
 if(target.setPointerCapture)target.setPointerCapture(pointer);
 function move(e){if(e.pointerId!==pointer)return;invalidateLearningPreview();logoWorkingTemplates()[p.id]=constrainLearningLogo(p,{...original,x:original.x+(e.clientX-event.clientX)/box.width,y:original.y+(e.clientY-event.clientY)/box.height});S.learningLogoDirty=true;updateLearningLogoPreview()}
 function end(e){if(e.pointerId!==pointer)return;target.removeEventListener('pointermove',move);target.removeEventListener('pointerup',end);target.removeEventListener('pointercancel',end)}
 target.addEventListener('pointermove',move);target.addEventListener('pointerup',end);target.addEventListener('pointercancel',end);
}
async function saveLearningLogoTemplates(){
 const store=logoEditorStore(),learning=store===LEARNING_MACHINE;
 if(S.learningLogoSaving||!store.config)return;S.learningLogoSaving=true;S.learningLogoError='';render();
 try{const templates=store.config.placements.filter(learningLogoRequired).map(p=>({placement_id:p.id,...constrainLearningLogo(p,store.templates[p.id])}));
  const config=await request(learning?'/learning-machine/logo-templates':'/logo-templates','PUT',{revision:store.revision,templates});
  if(learning)installLearningMachineConfig(config);else installOrdinaryLogoConfig(config);S.learningLogoDirty=false;toast('Logo模板已保存，后续新制作使用对应版位配置');
 }catch(e){S.learningLogoError=e.status===409?'配置已在其他窗口更新，请重新读取后核对修改。':e.message;}
 finally{S.learningLogoSaving=false;render()}
}
async function reloadLearningLogoTemplates(){if(S.learningLogoSaving)return;try{if(logoEditorCategory()==='学习机')await loadLearningMachineConfig(true);else await loadOrdinaryLogoConfig(true);S.learningLogoDirty=false;S.learningLogoError=''}catch(e){S.learningLogoError=e.message}render()}
function learningLogoDirectoryRows(placements){
 if(!placements.length)return '<p class="field-help" role="status">没有匹配的版位</p>';
 const selected=learningLogoPlacement()?.id;
 return placements.map(q=>`<button class="${q.id===selected?'active':''}" data-logo-placement="${esc(q.id)}" onclick="chooseLearningLogoPlacement('${q.id}')"><b>${esc(q.platform+' · '+(q.name||''))}</b><span>${logoCanvasSize(q).width}×${logoCanvasSize(q).height} · ${learningLogoRequired(q)?(q.category==='学习机'?'有Logo':'位置模板'):'固定无Logo'}${learningMaskTemplate(q)?' · 底部遮罩':''}</span></button>`).join('');
}
function matchingLearningLogoPlacements(query){
 const q=String(query||'').trim().toLowerCase();
 return learningLogoPlacements().filter(p=>(!S.logoTemplatePlatform||p.platform===S.logoTemplatePlatform)&&[p.platform,p.name,logoCanvasSize(p).width+'×'+logoCanvasSize(p).height].join(' ').toLowerCase().includes(q));
}
function filterLearningLogoPlacements(query){
 S.learningLogoQuery=query;S.logoDirectoryPage=1;
 const list=document.getElementById('learning-logo-directory-list');
 if(list)list.innerHTML=viewLogoDirectoryResults(matchingLearningLogoPlacements(query));
}
function viewLogoDirectoryResults(placements){
 const pages=Math.max(1,Math.ceil(placements.length/8));S.logoDirectoryPage=Math.max(1,Math.min(S.logoDirectoryPage||1,pages));
 const page=S.logoDirectoryPage;
 return learningLogoDirectoryRows(placements.slice((page-1)*8,page*8))+`<nav class="logo-directory-pagination" aria-label="Logo版位分页"><button ${page<=1?'disabled':''} onclick="turnLogoDirectoryPage(-1)">上一页</button><span>第 ${page} / ${pages} 页</span><button ${page>=pages?'disabled':''} onclick="turnLogoDirectoryPage(1)">下一页</button></nav>`;
}
function turnLogoDirectoryPage(direction){S.logoDirectoryPage=(S.logoDirectoryPage||1)+direction;const list=document.getElementById('learning-logo-directory-list');if(list){list.innerHTML=viewLogoDirectoryResults(matchingLearningLogoPlacements(S.learningLogoQuery));list.scrollTo?.(0,0)}}
function setLogoTemplatePlatform(value){S.logoTemplatePlatform=value;S.learningLogoQuery='';S.logoDirectoryPage=1;const matches=matchingLearningLogoPlacements('');if(!matches.some(p=>p.id===S.learningLogoPid))S.learningLogoPid=matches[0]?.id;save(false);render()}
function learningMaskTemplate(p){
 const template=p?.mask_template;if(!template||template.enabled!==true)return null;
 const preset=(LEARNING_MACHINE.config?.mask_presets||[]).find(item=>item.id===template.preset_id)||{},mask={...preset,...template},height=Number(mask.height_fraction),opacity=Number(mask.max_opacity);
 if(!Number.isFinite(height)||height<=0||height>1||!Number.isFinite(opacity)||opacity<0||opacity>1||mask.curve!=='linear'||!/^#[0-9a-f]{6}$/i.test(mask.color||''))return null;
 return {...mask,height_fraction:height,max_opacity:opacity};
}
function viewLearningMaskOverlay(p){
 const mask=learningMaskTemplate(p);if(!mask)return '';
 const height=logoCanvasSize(p).height,start=(1-mask.height_fraction)*100,end=(1-1/height)*100,rgb=[1,3,5].map(offset=>parseInt(mask.color.slice(offset,offset+2),16)).join(',');
 return `<div class="learning-logo-mask-overlay" aria-label="代码叠加的底部遮罩" style="background:linear-gradient(to bottom,rgba(${rgb},0) ${start}%,rgba(${rgb},${mask.max_opacity}) ${end}%)"></div>`;
}
function viewLearningMaskNote(p){
 const mask=learningMaskTemplate(p);if(!mask)return '';
 return `<p class="field-help learning-mask-note"><b>底部遮罩由代码叠加，审核和导出一致。</b><span>底部高度 ${(mask.height_fraction*100).toFixed(1)}% · 最大不透明度 ${(mask.max_opacity*100).toFixed(1)}% · 线性渐变</span></p>`;
}
function viewLearningLogoConfig(){
 const store=logoEditorStore();if(!store.config)return logoCategoryTabs()+`<section class="card learning-logo-loading"><h2>读取${esc(logoEditorCategory())}Logo模板</h2><p role="status">${esc(S.learningLogoError||store.error||'正在读取配置…')}</p><button onclick="reloadLearningLogoTemplates()">重新读取</button></section>`;
 const placements=learningLogoPlacements(),p=learningLogoPlacement(),required=p&&learningLogoRequired(p),t=p&&store.templates[p.id],size=p&&logoCanvasSize(p),query=(S.learningLogoQuery||'').toLowerCase();
 const filtered=matchingLearningLogoPlacements(query);
 const bg=S.learningLogoBg||'light',asset=t&&learningLogoAsset(bg==='dark'?'learning.logo.white-app':'learning.logo.black');
 return logoCategoryTabs()+`<div class="learning-logo-page"><section class="card learning-logo-directory"><h2>版位模板</h2><p class="field-help">${placements.length}个版位 · ${placements.filter(learningLogoRequired).length}个可配置模板</p><input type="search" id="learning-logo-search" aria-label="搜索Logo版位" placeholder="搜索渠道、版位或尺寸" value="${esc(S.learningLogoQuery||'')}" oninput="filterLearningLogoPlacements(this.value)"><select aria-label="筛选Logo渠道" onchange="setLogoTemplatePlatform(this.value)"><option value="">全部渠道</option>${[...new Set(placements.map(p=>p.platform))].map(platform=>`<option value="${esc(platform)}" ${S.logoTemplatePlatform===platform?'selected':''}>${esc(platform)}</option>`).join('')}</select><div class="learning-logo-list" id="learning-logo-directory-list">${viewLogoDirectoryResults(filtered)}</div></section>
 <div class="learning-logo-workspace"> <section class="card learning-logo-save"><div><b id="learning-logo-save-status" role="status">${S.learningLogoDirty?'有未保存的修改':'当前配置已保存'}</b>${S.learningLogoError?`<p class="errtx" role="alert">${esc(S.learningLogoError)}</p>`:''}</div><button onclick="reloadLearningLogoTemplates()" ${S.learningLogoSaving?'disabled':''}>重新读取已保存配置</button><button class="primary" onclick="saveLearningLogoTemplates()" ${S.learningLogoSaving?'disabled':''}>${S.learningLogoSaving?'正在保存…':'保存当前类型Logo模板'}</button></section><section class="card learning-logo-editor"><div class="section-heading"><div><h2>${esc(p?.platform||'')} · ${size?.width||0}×${size?.height||0}</h2><p class="field-help">${esc(p?.name||'')} · ${required?'拖动Logo，或输入位置和宽度；素材始终等比。':'此版位固定无Logo，不提供启用选项。'}</p></div><div class="config-segments"><button class="${bg==='light'?'active':''}" onclick="S.learningLogoBg='light';render()">浅色预览</button><button class="${bg==='dark'?'active':''}" onclick="S.learningLogoBg='dark';render()">深色预览</button></div></div>
 ${required?`<div class="learning-logo-controls">${[['x','左侧位置'],['y','顶部位置'],['width','Logo宽度']].map(([key,label])=>`<label for="learning-logo-${key}">${label}<div><input type="number" id="learning-logo-${key}" min="0" max="100" step="0.1" value="${(t[key]*100).toFixed(2)}" oninput="setLearningLogoValue('${key}',this.value)" onblur="syncLearningLogoField('${key}',this)"><span>%</span></div></label>`).join('')}</div><p class="field-help" id="learning-logo-pixels">位置 ${Math.round(t.x*size.width)}, ${Math.round(t.y*size.height)} px · 宽 ${Math.round(t.width*size.width)} px</p>`:''}
 <div class="learning-logo-board-wrap"><div class="learning-logo-board ${bg}" id="learning-logo-board" style="aspect-ratio:${size?.width||1}/${size?.height||1};--logo-preview-ratio:${(size?.width||1)/(size?.height||1)}" aria-label="${esc(p?.platform||'')}Logo与遮罩预览"><div class="learning-logo-safearea"><span>人物 / 正文保留区（示意）</span></div>${required&&asset?`<img id="learning-logo-image" class="learning-logo-image" src="${esc(asset.url)}" alt="${esc(asset.label)}" draggable="false" style="left:${t.x*100}%;top:${t.y*100}%;width:${t.width*100}%" onpointerdown="startLearningLogoDrag(event)">`:'<span class="learning-logo-none">固定无Logo</span>'}${viewLearningMaskOverlay(p)}</div></div>${viewLearningMaskNote(p)}

 <p class="field-help">模板保存位置和大小，成品按落点背景自动选黑字或反白。${store===LEARNING_MACHINE?'Logo 有无由版位固定。':''}</p>${p?.sample_url?`<details class="learning-logo-reference"><summary>查看对应样图位置参考</summary><img src="${esc(p.sample_url)}" alt="${esc(p.platform)}对应版位样图"><p class="field-help">${esc(p.sample_note||"样图含原有Logo，只用于核对位置与大小，不是本次叠加结果。")}</p></details>`:''}</section>
</div></div>`;
}
async function previewLearningSuite(){
 if(S.submitting||S.navigationPending||S.uploadingPurpose)return;if(S.learningLogoDirty)return toast('Logo模板还有未保存的修改，请先进入配置页保存。');normalizeLearningDraft(S.draft);S.tried=true;const issue=formIssue(S.draft);
 if(issue){focusLearningFormIssue(issue);return}
 S.submitting=true;S.learningPreviewError='';let previewReady=false;render();
 try{await persistDraft();const params=structuredClone(S.draft);params.cta=String(params.cta||'').trim()||LEARNING_DEFAULT_CTA;
  S.learningPreview=await request('/learning-machine/preview','POST',{params});if(S.learningPreview.params&&typeof S.learningPreview.params==='object'){Object.assign(S.draft,structuredClone(S.learningPreview.params));save();await persistDraft()}toast(learningConcept(S.draft)?'扩版方案已更新':'配置已保存；基准图尚未生成，需要查看确认后才扩展整套');previewReady=true;
 }catch(e){S.learningPreviewError=e.message;report(e)}finally{S.submitting=false;render();if(previewReady&&S.view==='form'){const panel=document.getElementById('learning-plan-preview');panel?.focus({preventScroll:true});panel?.scrollIntoView({behavior:'auto',block:'start'})}}
}
function learningPromptMissingInputs(entry){
 const values=Array.isArray(entry?.missing_inputs)?entry.missing_inputs:[];
 const names=values.map(value=>typeof value==='string'?value:String(value?.name||value?.key||value?.field||value?.code||value?.id||value?.message||'待配置内容'));
 if(entry?.unsupported_model_ratio&&!names.includes('unsupported_model_ratio'))names.push('unsupported_model_ratio');
 return [...new Set(names)].filter(name=>!['feature_label','extra_heading','extra_description'].includes(name));
}
function viewLearningPromptMissing(entry){
 const missing=learningPromptMissingInputs(entry);if(!missing.length)return '';
 const labels={scene_plan:'画面方案将在生成基准图时确定',unsupported_model_ratio:'当前模型不支持此比例，请调整模型或画幅配置'};
 return `<div class="learning-prompt-pending" role="status"><b>模板待配置</b><ul>${missing.map(name=>`<li>${esc(labels[name]||('待配置：'+name))}</li>`).join('')}</ul><p>可先保存并审核固定模板；这些信息不会新增为当前主表单必填项，也不会触发生图。</p></div>`;
}
function learningMasterReusesBaseline(master){return master?.reuse_baseline===true||master?.source_kind==='confirmed_baseline_reuse'||master?.image_generation_required===false}
function viewLearningPromptCounts(plan){
 const prompt=plan.prompt_plan,counts=prompt?.counts||{},entries=Array.isArray(prompt?.masters)?prompt.masters:null;
 const number=value=>value!==undefined&&value!==null&&Number.isInteger(Number(value))&&Number(value)>=0?Number(value):null;
 const masters=number(counts.master_count??plan.master_count??entries?.length),planned=number(counts.planned_image_calls??plan.planned_image_calls);
 const newMasters=number(counts.image_model_master_calls??(entries?.length?entries.filter(master=>!learningMasterReusesBaseline(master)).length:planned===null?masters:Math.max(0,planned-1)));
 const calls=planned??(newMasters===null?null:newMasters+1),reused=number(counts.baseline_reused_master_count??(masters===null||newMasters===null?undefined:Math.max(0,masters-newMasters)));
 const background=number(counts.background_image_calls);
 if(masters===null||calls===null||newMasters===null)return '';
 return `<div class="learning-prompt-counts" aria-label="预计母版及首轮调用"><span>预计 <b>${masters}</b> 组母版</span><span>首轮图片模型调用 <b>${calls}</b> 次</span><small>1张基准图＋${newMasters}张新母版${reused?'；'+reused+'组直接复用基准图':''}${background>0?'；另含'+background+'次条件背景扩展':''}；仅为计划，不含重出或额外修补，当前未调用模型。</small></div>`;
}
function viewLearningFixedPrompts(plan){
 const promptPlan=plan.prompt_plan;if(!promptPlan)return '';
 const baseline=promptPlan.baseline||{},masters=Array.isArray(promptPlan.masters)?promptPlan.masters:[];
 const placements=master=>(master.placement_ids||[]).map(id=>{const p=plOf(id);return p?`${p.platform} · ${p.name} · ${psz(p)}`:String(id)});
 return `<details class="learning-fixed-prompts" id="learning-fixed-prompts"><summary>查看固定提示词 · 1张基准图＋${masters.length}组母版</summary><p class="field-help">这是离线固定模板审核。所有需要图生图的母版都参照同一张已确认的基准图独立生成，不依次引用上一组母版；标记为复用的分组直接采用基准图，不调用图片模型。开始制作后会先等待基准图确认；配置预览本身不会提交模型。</p><p class="field-help">正文和CTA按版位固定规则处理；Logo与底部遮罩由代码叠加。</p><section class="learning-prompt-template" aria-label="基准图固定提示词"><h4>基准图 · 固定模板</h4>${viewLearningPromptMissing(baseline)}<pre id="learning-baseline-prompt" tabindex="0" aria-label="基准图完整固定提示词">${esc(baseline.prompt||'固定模板尚未载入')}</pre></section><div class="learning-master-prompts">${masters.map((master,index)=>`<details class="learning-prompt-template"><summary>母版 ${String(index+1).padStart(2,'0')} · ${esc(master.aspect_ratio||'比例待配置')} · ${esc(master.id||master.group_id||'')} · ${learningMasterReusesBaseline(master)?'复用基准图，不调用模型':'图生图'}${learningPromptMissingInputs(master).length?' · 待配置':''}</summary><p class="field-help">适配 ${(master.placement_ids||[]).length} 个版位 · ${Number.isFinite(Number(master.delivery_count))?Number(master.delivery_count):(master.output_ids||[]).length} 张交付图</p><ul class="learning-prompt-placement-list">${placements(master).map(name=>`<li>${esc(name)}</li>`).join('')}</ul>${viewLearningPromptMissing(master)}<pre id="learning-master-prompt-${index+1}" tabindex="0" aria-label="母版${index+1}完整固定提示词">${esc(master.prompt||(learningMasterReusesBaseline(master)?'直接复用已确认基准图，本组不调用图片模型。':'固定模板尚未载入'))}</pre></details>`).join('')}</div></details>`;
}
function viewLearningFramingWorkflow(plan){
 if(!plan.prompt_plan?.framing_node)return '';
 return `<section class="learning-framing-workflow" aria-label="扩图工作流"><h4>扩图工作流</h4><p>主视觉约束图生图 → 小误差轻裁／大误差AI自然延展 → 精确导出 → 查看人物完整性</p><p class="field-help">整个人物、动作和关键道具一起缩小并重排。普通组在保留区内每侧留10%，超宽组留12%；文字另留4%。主视觉约束由代码编译进每组提示词；补边占比8%以内本机轻裁，超过8%按计划增加AI自然延展。成图完整性由你查看确认。</p></section>`;
}
function learningConceptRouteLabel(route){
 return ({direct:'原图适配',background:'GPT 扩背景',reflow:'GPT 重新排版',add_cta:'GPT 加按钮并排版',remove_cta:'GPT 去按钮并排版',pure:'GPT 去字并重排构图'})[route]||'';
}
function viewLearningConceptPlan(plan){
 const groups=new Map(),counts=plan.prompt_plan.counts,source=plan.params.concept;
 for(const row of plan.outputs){
  if(!groups.has(row.concept_route))groups.set(row.concept_route,[]);
  groups.get(row.concept_route).push(row);
 }
 return `<section class="card learning-plan-preview" id="learning-plan-preview" tabindex="-1"><div class="section-heading"><h3>扩版方案</h3><span>${plan.output_count} 张成品</span></div><p class="field-help">${groups.get('direct')?.length||0} 张预计原图适配 · 预计 GPT ${counts.image_model_master_calls} 次制作母版，另有 ${counts.background_image_calls} 次条件补背景。文字清修由实际审核决定。</p>${[...groups].sort(([a],[b])=>Number(b==='direct')-Number(a==='direct')).map(([route,rows])=>`<details ${route==='direct'?'open':''}><summary>${esc(learningConceptRouteLabel(route))} · ${rows.length} 张</summary><div class="adaptation-plan-table"><table><thead><tr><th>版位</th><th>尺寸</th><th>处理</th></tr></thead><tbody>${rows.map(row=>`<tr><td>${esc(row.platform)} ${esc(row.name)}</td><td>${esc(row.target_size)}</td><td>${esc(row.method)}${route==='direct'?`<details><summary>查看原图裁切</summary><img class="concept-crop-preview" src="/api/uploads/${esc(encodeURIComponent(source.id))}" alt="原图裁切预览" style="aspect-ratio:${row.width}/${row.height}"></details>`:''}</td></tr>`).join('')}</tbody></table></div></details>`).join('')}</section>`;
}
function viewLearningPlanPreview(){
 const p=S.learningPreview;if(!p)return S.learningPreviewError?`<p class="errtx" role="alert">${esc(S.learningPreviewError)}</p>`:'';
 if(p.params?.concept)return viewLearningConceptPlan(p);
 const outputs=p.outputs||p.rows||p.plan?.outputs||[],base=p.baseline||p.plan?.baseline||{},placementCount=Array.isArray(p.placements)?p.placements.length:S.draft.pids.length,visual=p.visual_config||p.params?.learning_visual_config||p.normalized_params?.learning_visual_config||S.draft.learning_visual_config||{};
 return `<section class="card learning-plan-preview" id="learning-plan-preview" tabindex="-1" aria-label="学习机整套计划预览"><div class="section-heading"><h3>配置流程预览</h3><span class="simulation-note">仅配置 · 基准图待生成</span></div>${viewLearningPromptCounts(p)}<ol class="learning-preview-steps"><li><b>1 · 配置</b><span>文案、版位与本套视觉配置。</span></li><li><b>2 · 生成并查看基准图</b><span>${esc(base.ratio||base.aspect_ratio||'16:9')} · 先看真实基准图，不满意可重新生成。</span></li><li><b>3 · 确认后扩展整套</b><span>${placementCount}个版位、${p.output_count||outputs.length||totalOf(S.draft)}张目标图等待用户确认基准图，不会自动开始。</span></li></ol><section class="learning-baseline-review" aria-label="基准图确认阶段"><div class="learning-baseline-placeholder" role="status"><b>基准图待生成</b><span>这里目前没有真实图片，配置预览不代表基准图已生成或已确认。</span></div><p class="field-help" id="learning-baseline-stage-note">配置预览不会生成图片。生成基准图后进入制作页查看，确认后再扩展整套。</p></section><dl class="learning-frozen-visual" aria-label="本套冻结视觉配置">${[['IP / 角色',visual.ip_name||'未配置'],['画风',visual.style_name||'未配置'],['字体参考',visual.font_name||'未配置']].map(([label,value])=>`<div><dt>${label}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl><p class="field-help">这套角色、画风和字体已固定，重复预览沿用。Logo使用已保存的版位模板；固定提示词可先审核；开始制作后保存实际提示词、图片和版本。</p>${viewLearningFramingWorkflow(p)}${viewLearningFixedPrompts(p)}${outputs.length?`<details><summary>查看逐版位计划</summary><div class="adaptation-plan-table"><table><thead><tr><th>版位</th><th>尺寸</th><th>处理</th></tr></thead><tbody>${outputs.map(o=>`<tr><td>${esc(o.platform||o.channel||plOf(o.placement_id||o.id)?.platform||'')} ${esc(o.name||'')}</td><td>${esc(Array.isArray(o.size)?o.size.join('×'):o.size||o.target_size||((o.target_width||o.width||'')+'×'+(o.target_height||o.height||'')))}</td><td>${esc(o.method||o.processing_mode||'基准图扩展 → 精确尺寸 → Logo图层')}</td></tr>`).join('')}</tbody></table></div></details>`:''}</section>`;
}
