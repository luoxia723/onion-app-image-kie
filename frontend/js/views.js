let FORM_DEFAULTS={};
const LEARNING_DEFAULT_CTA='点击下载';
const LOGO_VARIANT_CHOICES=[['learning.logo.black','黑字标准版'],['learning.logo.white-app','白字APP版']];
function canonicalLogoVariant(value){if(value==='logo.onion.standard.001')return 'learning.logo.black';if(value==='logo.onion.app.001')return 'learning.logo.white-app';return LOGO_VARIANT_CHOICES.some(([id])=>id===value)?value:''}
function logoVariantLabel(value){return LOGO_VARIANT_CHOICES.find(([id])=>id===canonicalLogoVariant(value))?.[1]||'按当前图片版本'}
function logoVariantOptions(selected,currentLabel='按图片当前版本'){return `<option value="" ${!selected?'selected':''}>${esc(currentLabel)}</option>`+LOGO_VARIANT_CHOICES.map(([id,label])=>`<option value="${id}" ${selected===id?'selected':''}>${label}</option>`).join('')}
let IMAGE_MODEL_OPTIONS=[['gpt-image-2-5-sunburst-image-to-image','GPT Image 2.5 Sunburst'],['gpt-image-2-image-to-image','GPT Image 2']];
function imageModelName(id){
  if(id==='gpt-image-2-5-sunburst-image-to-image')return 'Sunburst 2.5 · 1K';
  if(id==='gpt-image-2-image-to-image')return 'GPT Image 2 · 1K';
  return (IMAGE_MODEL_OPTIONS.find(model=>model[0]===id)||IMAGE_MODEL_OPTIONS[0])[1]+' · 1K';
}
function imageModelOptions(selected){return IMAGE_MODEL_OPTIONS.map(([id])=>`<option value="${id}" ${id===selected?'selected':''}>${esc(imageModelName(id))}</option>`).join('')}

const $=s=>document.querySelector(s);
function esc(s){return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}
function plOf(id){if(S.view!=='form'){const r=R();if(r?.placement_rules?.[id])return r.placement_rules[id]}return PLACEMENTS.find(p=>p.id===id)}
function pname(p){return p.platform+" "+p.name.replace(/\s*\d+×\d+/,"")}
function psz(p){return p.target_width+"×"+p.target_height}
function fnv(s){let h=0x811c9dc5;for(const c of s){h^=c.charCodeAt(0);h=Math.imul(h,16777619)>>>0}return h.toString(16).padStart(8,"0")}
function toast(t){const e=$("#toast");e.textContent=t;e.classList.add("on");clearTimeout(toast._t);toast._t=setTimeout(()=>e.classList.remove("on"),1800)}

function styleOfSet(pr,n){return pr.style==="random"?STYLES[(n*7)%STYLES.length].name:pr.style}
function fontOfSet(n){return FONTS[(n*5)%FONTS.length]}
function perSet(pr){return pr.pids.map(plOf).filter(Boolean).reduce((a,p)=>a+p.image_count,0)}
function totalOf(pr){return pr.pids.map(plOf).filter(Boolean).reduce((n,p)=>n+p.image_count*(learningForm(pr)?1:pr.variants_by_placement?.[p.id]??(+pr.sets||0)),0)}
function copyFor(pr,p,idx){return p.image_count===1?{main:pr.t1,sub:pr.t2}:{main:pr["s"+idx]||""}}

function T(){return (S.tasks||[]).find(t=>t.id===S.cur)}
function R(){const t=T();return t?t.rounds[t.ri]:null}
function P(){return S.view==="form"?S.draft:(R()?R().params:S.draft)}

function isFail(r,s){return s.state==='failed'||s.state==='blocked_first_failed'}
function chans(r){return[...new Set(r.params.pids.map(plOf).map(p=>p.platform))]}
function inTab(s){return S.tab==="all"||plOf(s.pid).platform===S.tab}
function setPf(r,g){const sl=g.sl.filter(inTab);if(sl.some(s=>isFail(r,s)||s.state==="stopped"))return"bad";if(sl.some(s=>s.state!=="done"))return"run";return r.sel[g.n]?"yes":"no"}
function missList(r){return(r.pending_placements||[]).map(x=>({pid:x.placement_id,set:x.set||'—',what:x.reason}))}
function missK(r){return r.pending_placements?.length||0}
function failMsg(r,s){return s.msg||'未返回图片'}
function sourceSlots(r,s){const ids=s.dependency_ids||(s.idx>1?[s.first_id]:[]);return ids.map(id=>r.slots.find(x=>x.id===id)).filter(Boolean)}
function waitingSource(r,s){return sourceSlots(r,s).find(x=>x.state!=='done'||x.delivery_eligible===false)}
function dependentImages(r,s){const ids=new Set([s.id]);let size;do{size=ids.size;for(const x of r.slots)if(sourceSlots(r,x).some(source=>ids.has(source.id)))ids.add(x.id)}while(ids.size!==size);return r.slots.filter(x=>ids.has(x.id))}

function tName(t){if(t.draft)return Array.from(((t.draft.image_form==='单图'?t.draft.t1:t.draft.s1)||'').trim()).slice(0,16).join('')||t.name||'未命名草稿';if(t.name)return t.name;const p=(t.rounds[0]||{}).params||{},multi=(p.pids||[]).some(id=>{const q=plOf(id);return q&&q.image_count>1});return Array.from(((multi?p.s1:p.t1)||t.pkg||"").trim()).slice(0,16).join("")||t.pkg}
function workStatus(r){
 const slots=r.slots||[],done=slots.filter(s=>s.state==='done').length,generating=slots.filter(s=>s.state==='generating').length,queued=slots.filter(s=>s.state==='queued').length;
 const planning=r.planning_status==='running'||!r.stopped&&!r.paused&&r.planning_status==='queued',active=generating>0||r.planning_status==='running'||!r.stopped&&!r.paused&&(planning||queued>0);
 const groups=new Map();for(const slot of slots){const key=slot.pid+'::'+slot.set;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(slot)}
 const planned=[...groups.values()].filter(group=>group.every(slot=>slot.plan_ready!==false)).length;
 const waitingFirst=slots.filter(slot=>slot.state==='queued'&&slot.plan_ready!==false&&waitingSource(r,slot)).length;
 let title=r.paused?(generating?'已暂停后续，已开始的图片仍在处理':r.planning_status==='running'?'已暂停后续，已开始的规划仍在完成':'已暂停后续提交'):r.stopped?(generating?'已停止后续，已提交图片仍在生成':'已停止后续'):planning?(r.planning_status==='queued'?'正在排队，等待画面规划':generating?'正在规划画面，并陆续生成图片':'正在规划画面'):generating?'正在生成图片':queued?'排队等待生图':'生成已结束';
 const currentWork=slots.filter(s=>['queued','generating'].includes(s.state));
 if(!r.paused&&!r.stopped&&!planning&&currentWork.length&&currentWork.every(s=>s.production_mode==='local_resize'))title=generating?'正在本机适配':'等待本机适配';
 const detail='画面 '+planned+' / '+groups.size+' 套就绪 · 图片 '+done+' / '+slots.length+' 张完成'+(generating?' · '+generating+' 张处理中':'')+(waitingFirst?' · '+waitingFirst+' 张等待图 1':'');
 return{active,planning,generating,queued,done,total:slots.length,title,detail,waitingFirst};
}
function waitLabel(r,s){
 if(s.state==='generating'&&s.production_mode==='local_resize')return'本机适配中';
 if(s.state==='generating')return({uploading:'正在上传参考图',submitting:'正在提交生成任务',generating:'正在生成',downloading:'正在下载',processing:'正在处理尺寸'})[s.stage]||'生成中';
 if(s.state==='queued'&&r.paused)return'已暂停后续';
 if(s.state==='queued'&&s.plan_ready===false)return r.planning_status==='queued'?'待规划':'规划中';
 if(s.state==='queued'&&s.production_mode&&waitingSource(r,s))return waitingSource(r,s).id===s.template_id?'等待首模板':'等待母版';
 if(s.state==='queued'&&s.production_mode==='local_resize')return'待本机适配';
 if(s.state==='queued'&&s.idx>1&&r.slots.find(x=>x.id===s.first_id)?.state!=='done')return'等待图 1';
 return s.state==='queued'?'排队中':VLAB[s.state]||'等待中';
}
function viewWorkStatus(r){
 const status=workStatus(r);
 if(S.connectionLost)return`<span class="work-phase disconnected" role="status" title="请检查启动服务的窗口，连接恢复后会自动更新。">暂时无法连接本机服务 · 当前显示上次进度</span>`;
 if(!status.active&&!r.stopped&&!r.paused)return'';
 return`<span class="work-phase" id="pctx" role="status" title="${esc(status.detail)}${status.active?'。可以切换任务或关闭网页；请保持本机服务运行，不要关闭启动窗口、关机或休眠。':''}">${status.active?'<span class="phase-dot" aria-hidden="true"></span>':''}${esc(status.title)}</span>`;
}
function tRun(t){const r=t.rounds[t.ri];return !!t.background_running||['queued','running'].includes(r.planning_status)||r.slots.some(s=>s.state==="generating"||(s.state==="queued"&&!blocked(r,s)))}
function tProg(t){if(tRun(t))return true;if(t.downloaded)return false;const r=t.rounds[t.ri];return r.slots.some(s=>s.state==="done")}
function tGroup(t){if(t.is_summary)return t.category==='running'?'prog':t.category==='history'?'old':'attention';if(tProg(t))return"prog";const d0=new Date();d0.setHours(0,0,0,0);const s=d0.getTime(),dt=t.date||Date.now(),wd=(d0.getDay()+6)%7;if(dt>=s)return"today";if(dt>=s-864e5)return"yday";if(dt>=s-wd*864e5)return"week";return"old"}
function tHit(t,q){if(t.is_summary)return[t.name,t.pkg,t.image_model,t.image_form].some(v=>v&&String(v).toLowerCase().includes(q));const p=(t.rounds[t.ri]||{}).params||{};return[tName(t),t.pkg,p.t1,p.t2,p.s1,p.s2,p.s3].some(v=>v&&String(v).toLowerCase().includes(q))}
function taskRow(t){if(t.is_summary)return summaryRow(t);const r=t.rounds[t.ri],[dc,st]=taskStatus(t),run=tRun(t),m=S.menu===t.id;
 if(S.ren===t.id)return`<li class="trow"><div class="task on ren"><input id="renin" aria-label="任务名" value="${esc(S.renV!=null?S.renV:tName(t))}" oninput="S.renV=this.value" onkeydown="if(event.key==='Enter')renOk();if(event.key==='Escape'){event.stopPropagation();renEnd()}" onblur="renOk()"></div></li>`;
 const meta=st+(r.delivery?.last_version&&st!=='已保存 '+r.delivery.last_version?' · 已保存 '+r.delivery.last_version+(r.delivery.has_changes?' · 勾选有变化，需重新保存':''):'');
 return`<li class="trow ${t.downloaded?"dl":""} ${m?"mopen":""}" oncontextmenu="event.preventDefault();openMenu('${t.id}')"><button class="task ${t.id===S.cur?"on":""}" data-task="${t.id}" onclick="openTask('${t.id}')"><div><div class="t1">${esc(tName(t))}</div><div class="t2" title="${esc(meta)}"><span class="dot ${dc}"></span><span class="tst">${esc(meta)}</span></div></div></button><button class="more" data-more="${t.id}" aria-label="更多操作" aria-haspopup="menu" aria-expanded="${m}" onclick="event.stopPropagation();openMenu('${t.id}')">⋯</button>${m?`<div class="tmenu" role="menu"><button role="menuitem" data-act="ren" onclick="renStart('${t.id}')">重命名</button><button role="menuitem" data-act="del" ${run?'disabled aria-disabled="true"':""} onclick="delTask('${t.id}')">删除</button>${run?'<div class="mhint">先停止后续</div>':""}</div>`:""}</li>`}
function taskList(){
 const q=(S.q||'').trim().toLowerCase();
 if(S.searchPending)return '<li class="tnone">正在搜索任务…</li>';
 const tasks=S.summaries||S.tasks.filter(t=>!q||tHit(t,q));
 if(q)return tasks.length?tasks.map(taskRow).join(''):'<li class="tnone">没有匹配的任务</li>';
 return tasks.length?`<li class="gh fixed"><span>任务</span><span>${tasks.length}</span></li>`+tasks.map(taskRow).join(''):'';
}

function toggleSidebar(){S.sidebarCollapsed=!S.sidebarCollapsed;render();document.querySelector('#sidebar-toggle')?.focus()}
function viewSide(){if(typeof viewWorkspaceSide==='function')return viewWorkspaceSide();return`<aside><button id="sidebar-toggle" class="sidebar-toggle" type="button" aria-label="${S.sidebarCollapsed?'展开任务栏':'收起任务栏'}" aria-expanded="${!S.sidebarCollapsed}" title="${S.sidebarCollapsed?'展开任务栏':'收起任务栏'}" onclick="toggleSidebar()"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M7 4l6 6-6 6"/></svg></button><div class="side-top"><div class="brandrow"><span class="proof-brand-plate"><img src="${LOGO.thumb}" alt="洋葱学园"></span><span class="proof-brand-name">广告图工作台</span></div><button id="newbtn" onclick="newTask()"><svg class="ui-icon" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 4v12M4 10h12"/></svg>新建任务</button><div class="tsearch"><input id="tq" type="search" placeholder="搜索任务或文案" aria-label="搜索任务" value="${esc(S.q||"")}" oninput="searchTasks(this.value)"></div></div>
<div class="sidebar-scroll"><ul id="draft-list" class="drafts" aria-label="草稿">${typeof draftListHtml==='function'?draftListHtml():''}</ul><div id="learning-run-sidebar">${typeof viewLearningRunList==='function'?viewLearningRunList():''}</div><ul class="tasks" aria-label="任务">${taskList()||((S.drafts||[]).length?'':'<li class="empty-list">还没有任务</li>')}</ul></div>${S.undo?`<div class="undo" id="undo" role="status"><span>${S.undo.draft?'已删除草稿 ·':'已删除 ·'}</span><button id="undobtn" onclick="undoDel()">撤销</button></div>`:""}
<div class="side-bot"><div id="queue-overview" class="queue-overview">${typeof queueText==='function'?esc(queueText()):''}</div><div class="side-settings"><button class="ghost" id="cfgbtn" onclick="openCfg()"><svg class="ui-icon" viewBox="0 0 20 20" aria-hidden="true"><path d="M3 5h14M3 10h14M3 15h14M7 3v4m6 1v4m-5 1v4"/></svg>设置</button>${CFG.simulation?'<span class="simulation-note">模拟预览</span>':""}</div></div></aside>`}
function stepsHtml(){const current=S.view==='form'?0:1;return`<div class="steps" role="tablist">${[['form','配置生成'],['pick','挑选保存']].map(([key,label],i)=>`<button class="step ${i===current?'on':i<current?'done':''}" ${key==='pick'&&!R()?'disabled':''} onclick="go('${key}')"><i>${i<current?'✓':i+1}</i>${label}</button>`).join('')}</div>`}
function viewHead(){
 if(typeof viewWorkspaceHead==='function'){const head=viewWorkspaceHead();if(head!==null)return head}
 if(S.view==='learning-run'&&typeof viewLearningRunHead==='function')return viewLearningRunHead();
 if(S.view==='learning-logo')return '<header class="head pick-head" id="head"><div class="pick-heading"><h1>Logo 模板</h1><span class="page-context">应用商店、信息流与学习机 · 按版位保存位置和大小</span></div><button class="ghost" onclick="closeLearningLogoConfig()">返回任务列表</button></header>';
 if(S.openingTask)return '<header class="head pick-head" id="head" aria-busy="true"><span class="skeleton skeleton-title" aria-label="正在加载任务"></span></header>';
 const t=T(),pr=P();
 if(S.view==='form')return `<header class="head pick-head config-head" id="head"><div class="pick-heading"><h1 id="page-title">${S.editing?'修改任务配置':'新建任务'}</h1><span class="page-context" id="title" tabindex="-1">${esc(tName({draft:pr}))}</span></div><div class="draft-status-wrap"><span class="config-draft-state" id="draft-status" role="status">${esc(S.draftId?S.draftStatus||'草稿自动保存':'草稿自动保存')}</span><button id="draft-retry" class="lnk" ${S.draftStatus?.includes('失败')?'':'hidden'} onclick="persistDraft().catch(report)">重试保存</button></div></header>`;

 if(['pick','dl'].includes(S.view)&&t){
  const round=R(),status=workStatus(round),complete=status.done===status.total,channel=round.params.channel||((round.params.pids||[]).length?plOf(round.params.pids[0])?.category:'');
  const queueActions=status.active||round.paused?`${!round.stopped?`<button onclick="pauseQueue(${!round.paused})">${round.paused?'继续队列':'暂停后续'}</button>`:''}<button id="stopbtn" ${round.stopped?'disabled':''} onclick="stopRest()">${round.stopped?'已停止后续':'停止后续提交'}</button>`:'';
  const rounds=t.rounds.length>1?`<label>修改记录<select id="roundSel" onchange="setRound(+this.value)">${t.rounds.map((entry,index)=>`<option value="${index}" ${index===t.ri?'selected':''}>${esc(roundLabel(entry,index,t.rounds.length))}</option>`).reverse().join('')}</select></label>`:'';
  return`<header class="head pick-head" id="head"><div class="pick-heading"><h1 id="title" tabindex="-1">${esc(tName(t))}</h1><span class="page-context">${esc([Array.isArray(channel)?'多渠道':channel,round.params.image_form].filter(Boolean).join(' · '))}</span><span class="pick-progress ${complete?'complete':'pending'}" id="progtx"><strong>${complete?status.total:status.done+' / '+status.total}</strong><span>${complete?'张已生成':'张完成'}</span></span>${typeof round.simulation==='boolean'?`<span class="mode-pill">${round.simulation?'模拟图片':'真实制作'}</span>`:''}${viewWorkStatus(round)}</div><div class="pick-head-actions"><button id="redo" onclick="editRedo()">修改配置</button>${queueActions}${t.pkgs.length?'<button class="resave-package" onclick="dlAll(false)">检查并重新保存</button>':''}<details class="pick-more" ${S.pickMore?'open':''} ontoggle="S.pickMore=this.open"><summary aria-label="任务更多操作">⋯</summary><div><button id="dup" onclick="dupTask()">复制为新任务</button>${t.pkgs.length?'<button onclick="go(\'dl\')">交付记录</button>':''}${rounds}</div></details></div></header>`;
 }
 return '<header class="head pick-head" id="head"></header>';
}
function setsBad(pr){const v=String(pr.sets).trim();return!/^\d+$/.test(v)||+v<SETS_MIN||+v>SETS_MAX}

const IMAGE_FORMS = {
  '单图': {count:1, fields:[['t1','主标题'],['t2','副标题']]},
  '双图': {count:2, fields:[['s1','句 1'],['s2','句 2']]},
  '三图': {count:3, fields:[['s1','句 1'],['s2','句 2'],['s3','句 3']]},
};
function learningForm(pr){return pr.channel==='学习机'&&imageFormOf(pr)==='单图'}
function invalidateLearningPreview(){S.learningPreview=null;S.learningPreviewError='';document.getElementById?.('learning-plan-preview')?.remove?.()}
function learningUpload(pr){return learningForm(pr)&&pr.learning_mode==='upload'}
function normalizeLearningDraft(pr,selectAll=false){
 if(!learningForm(pr))return pr;
 pr.learning_mode='generate';pr.learning_pipeline='baseline_then_suite';pr.sets=1;pr.variants_by_placement={};
 pr.noLogo=false;delete pr.logo_asset_id;delete pr.learning_source;pr.cta_enabled=true;pr.cta_overrides={};
 if(!String(pr.cta||'').trim()||pr.cta===DEF_CTA)pr.cta=LEARNING_DEFAULT_CTA;
 if(selectAll)pr.pids=formPlacements(pr).map(p=>p.id);
 return pr;
}
function setLearningMode(){
 if(S.submitting||S.navigationPending||!learningForm(S.draft))return;
 invalidateLearningPreview();normalizeLearningDraft(S.draft);save();render();
}
function selectLearningPlacements(all){if(S.submitting||S.navigationPending)return;invalidateLearningPreview();S.learningAutoSelectAll=!!all;S.draft.pids=all?formPlacements(S.draft).map(p=>p.id):[];filterFormPlacements(S.draft);save();render()}
function learningPlanKey(pr){return JSON.stringify({pids:pr.pids,source:pr.learning_source,feature_label:pr.feature_label,t1:pr.t1,t2:pr.t2,cta:pr.cta,cta_enabled:pr.cta_enabled,cta_overrides:pr.cta_overrides,extra_heading:pr.extra_heading,extra_description:pr.extra_description,logo_asset_id:pr.logo_asset_id})}
function currentLearningPlan(pr){return S.learningPlanKey===learningPlanKey(pr)?S.learningPlan:null}
function setSourceLayout(id){const source=S.draft.learning_source;if(!source||S.submitting)return;Object.assign(source,{layout_id:id,layout_confirmed:false,original_logo_asset_id:S.draft.logo_asset_id||'logo.onion.standard.001'});save();render()}
function confirmSourceLayout(checked){if(!S.draft.learning_source||S.submitting)return;S.draft.learning_source.layout_confirmed=checked;save();render()}
function viewSourceLayout(pr){
 const source=pr.learning_source;if(!source)return '';
 const options=PLACEMENTS.filter(p=>p.category==='学习机'&&Math.abs((source.width/source.height)/(p.target_width/p.target_height)-1)<=.015),known=source.known_sample;
 return `<div class="source-layout"><label>原图版式<select aria-label="原图版式" ${known?'disabled':''} onchange="setSourceLayout(this.value)"><option value="">未确认，按 AI 适配</option>${options.map(p=>`<option value="${p.id}" ${source.layout_id===p.id?'selected':''}>${esc(p.platform+' · '+p.name+' · '+psz(p))}</option>`).join('')}</select></label>${source.layout_id?`<img src="/api/learning-samples/${encodeURIComponent(source.layout_id)}" alt="对应版式样图">${known?'<p class="field-help">已匹配到已核对的原始样图。</p>':`<label class="inline-check"><input type="checkbox" ${source.layout_confirmed?'checked':''} onchange="confirmSourceLayout(this.checked)">确认原图构图、文案模块和 Logo 与样图一致</label>`}`:'<p class="field-help">按实际版式选择并核对样图后，可判断哪些尺寸能直接复用原图。未确认也可以继续，系统会使用 AI 适配。</p>'}</div>`;
}
function viewLearningAdaptation(pr){
 if(!learningUpload(pr)||!pr.learning_source)return '';
 const plan=currentLearningPlan(pr);
 if(!plan)return `<div id="learning-adaptation-plan"><p role="status" class="field-help">${S.learningPlanError?'适配计划读取失败，请重试。':'正在核对适配计划…'}${S.learningPlanError?'<button onclick="S.learningPlanAttempt=null;render()">重试</button>':''}</p></div>`;
 return `<div id="learning-adaptation-plan"><details class="adaptation-plan"><summary>逐版位适配计划 · ${plan.model_tasks} 张需 AI · ${plan.local_outputs} 张本机处理</summary><div class="adaptation-plan-table"><table><thead><tr><th>版位</th><th>处理方式</th><th>原因</th></tr></thead><tbody>${plan.rows.map(row=>`<tr><td>${esc(row.platform+' '+row.size)}<small>${esc(row.name)}</small></td><td>${({source_resize:'原图直接适配',local_resize:'母版适配后缩放',ai_edit:'AI 编辑一张'})[row.method]}</td><td>${esc(row.reason)}</td></tr>`).join('')}</tbody></table></div></details></div>`;
}
function viewLearningSource(pr){
 if(!learningForm(pr))return '';
 return '<p class="learning-flow-note">生成基准图 → 确认基准图并扩展整套</p>';
}
function copyFields(pr){
 return learningForm(pr)?[['t1','推广文案']]:IMAGE_FORMS[imageFormOf(pr)]?.fields||[];
}
function learningProduction(pr){
 if(!learningForm(pr))return '';
 return pr.pids.length?`先生成并查看 1 张基准图，确认后再完成 ${pr.pids.length} 个版位、${totalOf(pr)} 张成品。可先审核计划，再开始模拟或真实制作。`:'默认全选学习机版位，可按需要调整。';
}
function imageFormOf(pr){
  if(Object.hasOwn(pr,'image_form'))return IMAGE_FORMS[pr.image_form]?pr.image_form:'';
  const forms=[...new Set((pr.pids||[]).map(plOf).filter(Boolean).map(p=>p.image_form||Object.keys(IMAGE_FORMS).find(f=>IMAGE_FORMS[f].count===p.image_count)))];
  return forms.length===1?forms[0]:'';
}
function channelOptions(){return [...new Set([...PLACEMENTS.map(p=>p.category),'学习机'])]}
function channelForms(channel){if(channel==='学习机')return PLACEMENTS.some(p=>p.category==='学习机')?['单图']:[];return Object.keys(IMAGE_FORMS).filter(form=>PLACEMENTS.some(p=>(Array.isArray(channel)?channel.includes(p.category):p.category===channel)&&p.image_count===IMAGE_FORMS[form].count))}
function formPlacements(pr){if(learningForm(pr))return PLACEMENTS.filter(p=>p.category==='学习机');return PLACEMENTS.filter(p=>(Array.isArray(pr.channel)?pr.channel.includes(p.category):p.category===pr.channel)&&p.image_count===IMAGE_FORMS[imageFormOf(pr)]?.count)}
function defParams(form='单图'){return{channel:'',image_form:form,pids:[],t1:'',t2:'',s1:'',s2:'',s3:'',cta:DEF_CTA,cta_enabled:true,cta_overrides:{},sets:3,ip:'random',style:'random',font:'random',noLogo:false,references:[],...(FORM_DEFAULTS[form]||{})}}
function loadDraft(params){
  invalidateLearningPreview();
  S.learningReadPending=null;S.learningReadError='';
  S.learningPlan=null;S.learningPlanKey=null;S.learningPlanAttempt=null;S.learningPlanError=false;
  const form=imageFormOf(params)||'单图';
  S.draft={...defParams(form),pids:[],product_facts:'',facts_version:0,...structuredClone(params)};
  S.draft.image_form=imageFormOf(params)||(params.image_form!==undefined||params.pids?.length?'':form);
  if(!Object.hasOwn(params,'channel')){const channels=[...new Set(S.draft.pids.map(plOf).filter(Boolean).map(p=>p.category))];S.draft.channel=channels.length>1?channels:channels[0]||''}
  normalizeLearningDraft(S.draft);
  S.visualOpen=visualCustomized(S.draft);S.referenceMode=!!S.draft.references.length;S.learningPlacementsOpen=false;S.learningCreateMode='simulation';
  S.referencePointsPending={};
  S.formDrafts={};
  S.formError=null;
}
function setImageForm(form){
  if(S.submitting||S.navigationPending||!channelForms(S.draft.channel).includes(form)||form===imageFormOf(S.draft))return;
  invalidateLearningPreview();S.formDrafts=S.formDrafts||{};
  const previous=imageFormOf(S.draft);
  if(previous)S.formDrafts[previous]=structuredClone(S.draft);
  const shared={};
  for(const k of ['channel','cta','cta_enabled','sets','ip','style','font','noLogo','logo_asset_id','references','feature_note','feature_label','extra_heading','extra_description','learning_mode','learning_source','image_model','direction','product_facts','facts_version'])if(S.draft[k]!==undefined)shared[k]=structuredClone(S.draft[k]);
  S.draft={...(S.formDrafts[form]?structuredClone(S.formDrafts[form]):defParams(form)),...shared};
  filterFormPlacements(S.draft);
  S.tried=false;S.formError=null;save();render();
}
function filterFormPlacements(pr){
  const ids=formPlacements(pr).map(p=>p.id);
  pr.pids=pr.pids.filter(id=>ids.includes(id));
  for(const key of ['cta_overrides','variants_by_placement'])if(pr[key])for(const id of Object.keys(pr[key]))if(!pr.pids.includes(id))delete pr[key][id];
}
function setChannel(channel){
  if(S.submitting||S.navigationPending||channel===S.draft.channel)return;
  invalidateLearningPreview();const forms=channelForms(channel),form=imageFormOf(S.draft);
  S.draft.channel=channel;
  if(forms.length&&!forms.includes(form))setImageForm(forms[0]);
  for(const pr of [S.draft,...Object.values(S.formDrafts||{})]){pr.channel=channel;filterFormPlacements(pr)}
  if(channel==='学习机'){S.learningPlacementsOpen=false;S.draft.image_form='单图';normalizeLearningDraft(S.draft,true);S.learningAutoSelectAll=true;if(typeof loadLearningMachineConfig==='function')loadLearningMachineConfig().catch(report)}
  S.tried=false;save();render();
}
function setCtaOverride(id,mode,text){
  if(learningForm(S.draft))return;
  if(S.submitting||S.navigationPending||!S.draft.pids.includes(id))return;
  S.draft.cta_overrides=S.draft.cta_overrides||{};
  S.draft.cta_overrides[id]={mode,text:text??S.draft.cta_overrides[id]?.text??S.draft.cta??''};
  save();if(text===undefined)render();else updSum();
}
function formIssue(pr){
  const form=imageFormOf(pr);
  if(!pr.channel)return{field:'channel',message:'请选择渠道'};
  if(!form)return{field:'image-form',message:'请选择图片形式'};
  if(!pr.pids.length)return{field:'chans',message:'请选择版位'};
  if(learningUpload(pr)&&!pr.learning_source)return{field:'learning-source',message:'请上传要扩展的图片'};
  if(learningUpload(pr)&&S.learningReadPending)return{field:'learning-source',message:'正在读取文案，请稍候或选择手动填写'};
  if(!learningForm(pr)&&pr.noLogo&&pr.pids.some(id=>PLACEMENTS.find(p=>p.id===id)?.logo_policy==='required'))return{field:'nologo',message:'所选版位要求使用 Logo，请选择 Logo 或移除该版位'};
  if(pr.pids.some(id=>!formPlacements(pr).some(p=>p.id===id)))return{field:'chans',message:'所选版位与当前渠道、形式不一致，请重新选择'};
  for(const [key,label] of copyFields(pr))if(!(pr[key]||'').trim())return{field:'f-'+key,message:'请填写'+label};
  if(!learningForm(pr)&&setsBad(pr))return{field:'f-sets',message:'套数请填写 1–20 的整数'};
  if(!learningUpload(pr)&&pr.style&&pr.style!=='random'&&!STYLES.some(style=>style.name===pr.style)&&!(pr.references||[]).some(ref=>ref.purpose==='style')){
    return{field:'styleq',message:'原画风已从广告画风库下线，请重新选择'};
  }
  for(const pid of pr.pids)if(plOf(pid)?.cta_policy==='required'&&!placementCtaText(pr,pid).trim())return{field:'f-cta',message:plOf(pid).platform+' '+plOf(pid).name+' 要求按钮文字，请填写统一按钮或自定义文字'};
  if((pr.cta||'').length>12)return{field:'f-cta',message:'按钮文字最多 12 字'};
  for(const [id,value] of Object.entries(learningForm(pr)?{}:pr.cta_overrides||{}))if(value.mode==='custom'&&(!value.text.trim()||value.text.length>12))return{field:'cta-'+id,message:'版位按钮文字请填写 1–12 字'};
  const refs=pr.references||[];
  if(refs.some(r=>(r.note||'').length>200))return{field:'reference-options',message:'参考图说明最多 200 字'};
  if(refs.some(r=>r.points!==undefined&&(!Array.isArray(r.points)||r.points.length>6||r.points.some(p=>typeof p!=='string'||!p.trim()||[...p].length>16))))return{field:'reference-options',message:'参考图要点最多 6 条，每条 1–16 字'};
  if(new Set(refs.map(r=>r.purpose)).size!==refs.length)return{field:'reference-options',message:'每种用途最多上传 1 张参考图'};
  return null;
}
function formErr(pr){const e=formIssue(pr);return e?e.field==='f-sets'?'sets':e.field==='chans'?'pids':'copy':''}
function visualCustomized(pr){return !!((pr.references||[]).length||pr.ip&&!['random','full_random'].includes(pr.ip)||pr.style&&pr.style!=='random'||pr.noLogo||pr.font&&pr.font!=='random'||pr.feature_note)}
const REFERENCE_PURPOSES={style:'参考风格',composition:'参考排版',ui:'产品界面'};
function viewReferenceOptions(pr){return `<div class="reference-slots" id="reference-options" tabindex="-1">${Object.entries(REFERENCE_PURPOSES).map(([purpose,label])=>{
  const i=(pr.references||[]).findIndex(r=>r.purpose===purpose),r=pr.references?.[i];
  const pending=S.referencePointsPending?.[purpose],extracting=pending?.draft===S.draftId&&pending?.id===r?.id;
  const points=r?`<div class="points-tag-list">${extracting?'<span class="points-pending" role="status">提炼中…</span>':(r.points||[]).map((point,j)=>`<span class="point-tag"><input class="point-tag-text" id="ref-point-${purpose}-${j}" aria-label="${label}要点 ${j+1}" value="${esc(point)}" maxlength="16" size="${Math.max(2,[...point].length*2)}" oninput="setReferencePoint(${i},${j},this.value);this.size=Math.max(2,[...this.value].length*2)"><button type="button" class="point-tag-del" aria-label="删除${label}要点 ${j+1}" onclick="removeReferencePoint(${i},${j})">×</button></span>`).join('')}<button type="button" class="point-add-btn" ${extracting||(r.points||[]).length>=6?'disabled':''} onclick="addReferencePoint(${i})">＋ 添加要点</button></div>`:'';
  return `<section class="reference-slot ${r?'uploaded':''}" data-purpose="${purpose}"><div class="slot-heading"><h4>${label}</h4>${r?`<button ${S.uploadingPurpose?'disabled':''} onclick="removeReference(${i})" aria-label="移除${label}">移除</button>`:''}</div>${r?`<img class="reference-thumb" src="${esc(r.thumbnail_url||r.preview||'')}" alt="${esc(r.name)}">${points}<label class="slot-note">补充说明（选填）<textarea id="ref-note-${purpose}" maxlength="200" rows="2" oninput="setReferenceNote(${i},this.value)">${esc(r.note||'')}</textarea></label>`:`<button class="reference-upload" ${S.uploadingPurpose?'disabled':''} onclick="uploadReference('${purpose}')">${S.uploadingPurpose===purpose?'正在上传…':'＋ 上传图片'}</button>`}</section>`;
}).join('')}</div>`}
function viewVisualOptions(pr){
  const open=S.visualOpen??visualCustomized(pr),reference=!!(pr.references||[]).some(r=>r.purpose==='style'),fonts=typeof FONTS!=='undefined'?FONTS:[];
  const retiredStyle=pr.style&&pr.style!=='random'&&!STYLES.some(style=>style.name===pr.style);
  const summary=[reference?'参考画风':pr.style&&pr.style!=='random'?pr.style:'随机画风',pr.ip==='none'?'不用角色':['random','full_random',undefined].includes(pr.ip)?'随机角色':IPS.find(a=>a.id===pr.ip)?.label||'指定角色',learningForm(pr)?'同套视觉固定一次':pr.noLogo?'不加 Logo':pr.logo_asset_id?logoVariantLabel(pr.logo_asset_id):'按版位Logo模板'].join(' · ');
  const groups=[['标准形象',IPS.filter(a=>a.variant==='standard'||a.id.includes('.standard.'))],['学段与 Q 版',IPS.filter(a=>a.variant!=='standard'&&!a.id.includes('.standard.')&&a.stage!=='teacher'&&!a.id.includes('.teacher.'))],['老师角色',IPS.filter(a=>a.stage==='teacher'||a.id.includes('.teacher.'))]];
  return `<section class="card visual-options" id="visual-options" aria-labelledby="visual-options-title"><div class="section-heading"><h3 id="visual-options-title">画面设定</h3><span class="scene-summary" title="${esc(summary)}">${open?'':esc(summary)}</span><button aria-expanded="${open}" onclick="S.visualOpen=${!open};render()">${open?'收起':'定制'}</button></div>${open?`
    <div class="scene-mode"><div class="config-segments" role="group" aria-label="画面参考"><button class="${!S.referenceMode?'active':''}" aria-pressed="${!S.referenceMode}" ${S.uploadingPurpose?'disabled':''} onclick="setReferenceMode(false)">随机</button><button class="${S.referenceMode?'active':''}" aria-pressed="${!!S.referenceMode}" ${S.uploadingPurpose?'disabled':''} onclick="setReferenceMode(true)">按参考图</button></div></div>
    ${viewReferenceOptions(pr)}
    <div class="custom-controls"><label>IP<select id="ips" onchange="setF('ip',this.value,1)"><option value="random" ${pr.ip==='random'?'selected':''}>随机 IP</option><option value="full_random" ${pr.ip==='full_random'?'selected':''}>全随机（含不用 IP）</option><option value="none" ${pr.ip==='none'?'selected':''}>不用 IP</option>${groups.map(([label,items])=>`<optgroup label="${label}">${items.map(a=>`<option data-ip="${a.id}" value="${a.id}" ${pr.ip===a.id?'selected':''}>${esc(a.label)}</option>`).join('')}</optgroup>`).join('')}</select></label>
    <label>画风${reference?'<span class="style-locked" role="status">🔒 按参考图</span>':`<select id="styleq" onchange="setF('style',this.value,1)">${retiredStyle?`<option selected disabled>${esc(pr.style)}（已下线，请重选）</option>`:''}${['random',...STYLES.map(s=>s.name)].map(name=>`<option value="${esc(name)}" ${pr.style===name?'selected':''}>${name==='random'?'随机画风':esc(name)}</option>`).join('')}</select>`}</label>
    ${learningForm(pr)?'':`<label>Logo<select id="nologo" onchange="setLogoSelection(this.value)"><option value="none" ${pr.noLogo?'selected':''}>不用 Logo</option><option value="template" ${!pr.noLogo&&!pr.logo_asset_id?'selected':''}>按版位模板</option>${LOGO_VARIANT_CHOICES.map(([id,label])=>`<option value="${id}" ${!pr.noLogo&&canonicalLogoVariant(pr.logo_asset_id)===id?'selected':''}>${label}</option>`).join('')}</select><small class="field-help">按版位模板使用已保存款式和位置，也可统一指定款式；禁止Logo的版位不会添加</small></label>`}
    <label>标题字体<select id="f-font" onchange="setF('font',this.value,1)">${[['random','随机字体参考'],['none','不用字体参考'],...fonts.map(a=>[a.id,a.label])].map(([id,label])=>`<option value="${id}" ${(pr.font||'random')===id?'selected':''}>${esc(label)}</option>`).join('')}</select>${learningForm(pr)?'<small class="field-help">字体参考用于后续带文字的版位，基准图不排广告文字。</small>':!reference&&pr.style==='random'?'<small class="field-help">抽中内置参考风格时不使用字体参考</small>':''}</label></div>
    <label class="scene-note" for="f-feature">补充要求（选填）<textarea id="f-feature" maxlength="200" rows="2" oninput="setF('feature_note',this.value)">${esc(pr.feature_note||'')}</textarea></label>
    ${S.tried&&formIssue(pr)?.field==='reference-options'?`<div class="errtx">${esc(formIssue(pr).message)}</div>`:''}`:''}</section>`;
}
function placementCtaText(pr,id){
  if(learningForm(pr))return plOf(id)?.cta_policy==='required'?(String(pr.cta||'').trim()||LEARNING_DEFAULT_CTA):'';
  if(plOf(id)?.cta_policy==='forbidden')return '';
  const value=pr.cta_overrides?.[id]||{mode:'inherit'};
  return value.mode==='custom'?value.text:value.mode==='none'||pr.cta_enabled===false?'':pr.cta||'';
}
function placementCta(pr,p){
  if(learningForm(pr))return `<div class="placement-cta learning-cta"><span class="placement-cta-label" data-cta-label="${p.id}">${p.cta_policy==='required'?'使用CTA文案':'无CTA'}</span></div>`;
  const forbidden=p.cta_policy==='forbidden',value=forbidden?{mode:'none'}:pr.cta_overrides?.[p.id]||{mode:'inherit'},selected=pr.pids.includes(p.id),label=pname(p)+'按钮文字',text=placementCtaText(pr,p.id);
  return `<div class="placement-cta mode-${value.mode} ${text?'':'no-button'}">${value.mode==='custom'?`<span class="cta-custom-dot" aria-hidden="true">•</span><input id="cta-${p.id}" aria-label="${esc(label)}" maxlength="12" value="${esc(value.text||'')}" ${!selected?'disabled':''} oninput="setCtaOverride('${p.id}','custom',this.value)">`:`<span class="placement-cta-label" data-cta-label="${p.id}">${esc(text?'跟随统一':'无按钮')}</span>`}<select aria-label="${esc(label)}模式" ${!selected||forbidden?'disabled':''} onchange="setCtaOverride('${p.id}',this.value)">${[['inherit','跟随统一'],['custom','自定义'],['none','无按钮']].map(([mode,label])=>`<option value="${mode}" ${mode===value.mode?'selected':''}>${mode===value.mode?'✓ ':''}${label}</option>`).join('')}</select></div>`;
}
function summaryFormula(pr){
  if(learningForm(pr))return `${pr.pids.length} 个版位 · 1 套，共 ${totalOf(pr)} 张成品` ;
  if(!pr.channel)return '';
  const mixed=pr.variants_by_placement&&new Set(pr.pids.map(id=>pr.variants_by_placement[id]??+pr.sets)).size>1;
  return mixed?`${pr.pids.length} 版位 × 分别设置套数`:`${pr.pids.length} 版位 × ${esc(pr.sets)} 套${IMAGE_FORMS[imageFormOf(pr)]?.count>1?' × '+IMAGE_FORMS[imageFormOf(pr)].count+' 张':''}`;
}
function setLogoSelection(value){if(S.submitting||S.navigationPending||learningForm(S.draft))return;const selected=canonicalLogoVariant(value);if(!['none','template'].includes(value)&&!selected)return;S.draft.noLogo=value==='none';if(value==='template')delete S.draft.logo_asset_id;else if(selected)S.draft.logo_asset_id=selected;save();render()}
function toggleLearningPlacements(){
  if(!learningForm(S.draft)||S.submitting||S.navigationPending)return;
  S.learningPlacementsOpen=!S.learningPlacementsOpen;render();
}
function focusLearningFormIssue(issue){
  if(issue.field==='chans')S.learningPlacementsOpen=true;
  if(['styleq','reference-options','ips','f-font','f-feature'].includes(issue.field))S.visualOpen=true;
  render();const field=document.getElementById(issue.field==='chans'?'learning-placements-toggle':issue.field);
  field?.focus();field?.scrollIntoView?.({block:'center'});
}
function viewForm(){
  const pr=S.draft,form=imageFormOf(pr),definition=IMAGE_FORMS[form],placements=formPlacements(pr),multi=Array.isArray(pr.channel),grp={},forms=channelForms(pr.channel),blocked=S.submitting||S.navigationPending,unavailable=!forms.length;
  placements.forEach(p=>{const group=grp[p.category]=grp[p.category]||{};(group[p.platform]=group[p.platform]||[]).push(p)});
  const issue=S.tried?formIssue(pr):null;
  const pending=(typeof UNAVAILABLE_PLACEMENTS!=='undefined'?UNAVAILABLE_PLACEMENTS:[]).filter(p=>Array.isArray(pr.channel)?pr.channel.includes(p.category):p.category===pr.channel);
  const fi=(key,label)=>`<label class="copy-field" for="f-${key}"><span>${label}</span><input id="f-${key}" data-k="${key}" aria-label="${esc(label)}" required aria-required="true" aria-invalid="${issue?.field==='f-'+key}" value="${esc(pr[key]||'')}" class="${issue?.field==='f-'+key?'bad':''}" oninput="setF('${key}',this.value)">${issue?.field==='f-'+key?`<span class="errtx">${esc(issue.message)}</span>`:''}</label>`;
  return `<div class="form config-form${learningForm(pr)?' learning-config':''}"><fieldset class="form-fields config-main" ${blocked?'disabled':''}>
    <section class="card compose-card"><h2 class="config-section-title">文案与渠道</h2><div class="channel-row"><h3 id="channel-label">渠道</h3><div id="channel" class="config-segments" role="${multi?'group':'radiogroup'}" aria-labelledby="channel-label" tabindex="-1">${channelOptions().map(channel=>`<button role="${multi?'checkbox':'radio'}" aria-checked="${multi?pr.channel.includes(channel):pr.channel===channel}" class="${(multi?pr.channel.includes(channel):pr.channel===channel)?'active':''}" onclick="setChannel('${channel}')">${esc(channel)}</button>`).join('')}</div>${multi?'<span class="muted">沿用原任务</span>':''}${issue?.field==='channel'?`<span class="errtx">${esc(issue.message)}</span>`:''}</div>
    <fieldset class="channel-dependent" ${unavailable?'disabled':''}>
    ${forms.length>1?`<div class="format-row"><h3 id="image-form-label">形式</h3><div class="config-segments" role="radiogroup" aria-labelledby="image-form-label" id="image-form">${forms.map(f=>`<button role="radio" aria-checked="${f===form}" class="${f===form?'active':''}" onclick="setImageForm('${f}')">${f}</button>`).join('')}</div></div>`:''}
    ${viewLearningSource(pr)}${learningUpload(pr)?viewSourceLayout(pr):''}<div class="config-copy"><div class="copy-lines">${copyFields(pr).map(([k,label])=>fi(k,label)).join('')}${learningForm(pr)&&pr.pids.length&&!copyFields(pr).length?'<p class="field-help">所选版位为纯画面，无需填写文案。</p>':''}</div>${!learningForm(pr)||pr.pids.some(id=>plOf(id)?.cta_policy==='required')?`<div class="default-cta"><label for="f-cta">${learningForm(pr)?'CTA按钮文案':'按钮文字'}</label><input id="f-cta" maxlength="12" placeholder="${learningForm(pr)?LEARNING_DEFAULT_CTA:''}" value="${esc(pr.cta||'')}" oninput="setF('cta',this.value)">${learningForm(pr)?'<span class="field-help">默认点击下载，可自定义；仅应用于有CTA的版位。</span>':`<label class="inline-check"><input id="cta-enabled" type="checkbox" ${pr.cta_enabled!==false?'checked':''} onchange="setF('cta_enabled',this.checked)">添加按钮</label>`}${issue?.field==='f-cta'?`<span class="errtx">${esc(issue.message)}</span>`:''}</div>`:''}${learningForm(pr)?'<p class="field-help">只填写一句确认文案；各版位按固定规则显示内容。Logo和CTA有无不作为任务选项。</p>':''}</div>
    </fieldset></section>
    ${learningForm(pr)&&typeof viewLearningPlanPreview==='function'?viewLearningPlanPreview():''}
    <fieldset class="channel-dependent" ${unavailable?'disabled':''}>
    ${viewVisualOptions(pr)}
    <section class="card placements-card"><div class="section-heading"><h3 id="placements-title">投放版位</h3>${pr.channel?`<span class="placement-count">${multi?'多渠道':esc(pr.channel)} · ${form}（已选 ${pr.pids.length}/${placements.length}）</span>`:''}${learningForm(pr)?`<button type="button" id="learning-placements-toggle" aria-expanded="${!!S.learningPlacementsOpen}" aria-controls="learning-placement-content" onclick="toggleLearningPlacements()">${S.learningPlacementsOpen?'收起版位':'展开版位'}</button>`:''}</div>
    ${learningForm(pr)?`<div id="learning-placement-content" ${S.learningPlacementsOpen?'':'hidden'}><div class="learning-placement-actions"><button type="button" onclick="openLearningLogoConfig()">配置Logo模板</button><button onclick="selectLearningPlacements(true)">全选可用版位</button><button onclick="selectLearningPlacements(false)">清空</button></div>`:''}<div class="placement-table-head" aria-hidden="true"><span>平台与版位</span><span>尺寸</span><span>按钮文字</span></div><div id="chans" tabindex="-1" class="${multi?'channel-groups':'platform-groups'}">${Object.entries(grp).map(([channel,platforms])=>`${multi?`<section class="channel-placement-group"><h4 class="channel-placement-title">${esc(channel)}</h4><div class="platform-groups">`:''}${Object.entries(platforms).sort(([,a],[,b])=>(a.length>2)-(b.length>2)).map(([platform,list])=>`<section class="platform-group ${list.length>2?'span-two':''}"><h4>${esc(platform)}</h4><div class="platform-items ${list.length>2?'two-columns':''}">${list.map(p=>`<div class="placement-row ${pr.pids.includes(p.id)?'checked':''}" data-pid="${p.id}"><label class="placement-check"><input type="checkbox" aria-label="${esc(pname(p))} ${psz(p)}" ${pr.pids.includes(p.id)?'checked':''} onchange="togP('${p.id}')"><span>${esc(p.platform)} ${esc(p.name.replace(/\s*\d+×\d+/,''))}</span></label><span class="placement-size">${psz(p)}${p.logo_policy==='required'?`<span class="logo-lock ${pr.noLogo?'force-highlight':''}">🔒 Logo</span>`:''}</span>${placementCta(pr,p)}${p.rule_summary?`<small class="placement-rule">${esc(p.rule_summary)}</small>`:''}</div>`).join('')}</div></section>`).join('')}${multi?'</div></section>':''}`).join('')}</div>${!learningForm(pr)&&pending.length?`<details class="pending-placements"><summary>${pending.length} 个版位待确认，暂不可生成</summary>${pending.map(p=>`<p><b>${esc(p.platform)} · ${esc(p.name)} · ${psz(p)}</b><br>${esc(p.disabled_reason)}</p>`).join('')}</details>`:''}${issue?.field==='chans'?`<div class="errtx">${esc(issue.message)}</div>`:''}${issue?.field.startsWith('cta-')?`<div class="errtx">${esc(issue.message)}</div>`:''}${learningForm(pr)?'</div>':''}</section>
    </fieldset>${pr.channel&&!forms.length?'<div class="channel-empty" role="status">该渠道暂无版位</div>':''}
    </fieldset><fieldset class="card sum config-summary channel-dependent" id="sum" ${blocked||unavailable?'disabled':''}><h2 class="config-section-title">${learningForm(pr)?'本次制作':'本次生成'}</h2>${learningForm(pr)?'<p class="field-help">固定生成一整套，每个版位按规则输出，不挑选多套候选。</p>':`<label for="f-sets">每版位套数</label><div class="sets-stepper"><button aria-label="减少套数" onclick="stepSets(-1)">−</button><input id="f-sets" type="number" min="${SETS_MIN}" max="${SETS_MAX}" value="${pr.variants_by_placement&&new Set(Object.values(pr.variants_by_placement)).size>1?'':esc(pr.sets)}" placeholder="分别设置" class="${setsBad(pr)?'bad':''}" oninput="setSets(this.value)"><button aria-label="增加套数" onclick="stepSets(1)">＋</button></div>${issue?.field==='f-sets'?`<span class="errtx">${esc(issue.message)}</span>`:''}`}
    <label for="image-model">图片模型</label><select id="image-model" onchange="setF('image_model',this.value)">${imageModelOptions(pr.image_model||(typeof CFG!=='undefined'&&CFG.imageModel)||IMAGE_MODEL_OPTIONS[0][0])}</select>

    <div class="total-action"><div class="tot" id="tot" aria-live="polite">共 ${pr.channel?totalOf(pr):0} 张</div><p id="sum-formula">${summaryFormula(pr)}</p><p class="field-help" id="learning-production">${learningProduction(pr)}</p><button class="${learningForm(pr)?'plan-preview-button':'primary'}" id="go" ${setsBad(pr)||blocked||unavailable||!pr.pids.length||S.uploadingPurpose||learningUpload(pr)&&(!pr.learning_source||S.learningReadPending||!currentLearningPlan(pr))?'disabled':''} onclick="startGen()">${S.submitting?'正在保存…':learningForm(pr)?'仅预览计划':'开始生成'}</button>${learningForm(pr)&&typeof viewLearningRunStart==='function'?viewLearningRunStart():''}<span class="field-help" id="generation-hint">${esc(S.submitting?'正在提交配置，请稍候':!pr.channel?'先选渠道':formIssue(pr)?.message||'')}</span></div></fieldset></div>`;
}
function need(k){return copyFields(S.draft).some(([f])=>f===k)}

function viewOrdinaryRepeatAction(r,s){
 if(r.generation_disabled||s.state!=='done'||s.delivery_eligible===false)return '';
 const retry=imageRetry(r,s);
 return `<button class="sample-repeat" data-redo="${s.id}" title="${esc(retry.note)} 卡片沿用当前实际提示词，编辑稿可在详情中使用。" ${retry.disabled||r.generation_disabled||S.ordinaryImageActionPending||S.navigationPending||S.submitting?'disabled':''} onclick="repeatOrdinaryImage('${s.id}')">${esc(retry.label)}</button>`;
}
function cellHtml(r,s){
 const p=plOf(s.pid),invalid=s.state==='done'&&s.delivery_eligible===false;
 const failed=isFail(r,s)||s.state==='stopped',waiting=s.state==='waiting_first'||s.state==='queued'&&!!waitingSource(r,s);
 const label=invalid?'规格未通过':failed?(s.state==='stopped'?'已停止':'生成失败'):s.state==='done'?'':waiting?(s.production_mode?waitLabel(r,s):'等图 1'):waitLabel(r,s);
 let content='',actions='';
 if(s.state==='done')content=`<img onload="this.parentElement.classList.add('image-loaded');this.parentElement.classList.remove('image-load-failed')" onerror="this.parentElement.classList.add('image-load-failed')" alt="${esc(pname(p))} 第 ${s.set} 套 图 ${s.idx}" src="${imgOf(s)}">${invalid?'<span class="delivery-note">规格未通过</span>':''}`;
 else content=`<span class="vlab">${label}</span>`;
 if(s.state==='done'&&!invalid)actions=`<div class="sample-actions"><button onclick="openPv('${s.id}')">查看详情</button>${viewOrdinaryRepeatAction(r,s)}</div>`;

 if(invalid||r.generation_disabled)actions=`<div class="sample-actions"><button onclick="editRedo()">按新规则重新制作</button></div>`;
 else if(failed){const retry=imageRetry(r,s),planning=s.reason_code==='planning_failed';actions=`<div class="sample-actions"><button data-redo="${s.id}" ${retry.disabled?'disabled':''} onclick="${planning?'retryPlanning()':retry.blocked?"openPv('"+retry.head?.id+"')":retry.query?"resumeImage('"+s.id+"')":"repairSet('"+s.pid+"',"+s.set+")"}">${planning?'重试规划':retry.blocked?(s.production_mode?'查看来源图片':'查看图 1'):retry.query?'恢复查询':'补齐'}</button></div>`}
 return`<div class="sample-unit"><div class="cell ${invalid?'delivery-invalid':failed?'fail':s.state==='done'?'done':waiting?'wait':'gen'}" style="aspect-ratio:${p.target_width}/${p.target_height};--image-ratio:${p.target_width/p.target_height}" data-slot="${s.id}" data-st="${s.state}" title="${esc(failed?failMsg(r,s):s.state==='done'?'已完成':waitLabel(r,s))}" ${s.state==='done'?`role="button" tabindex="0" aria-label="套 ${s.set} · ${esc(pname(p))} 图 ${s.idx}，查看大图" onclick="openPv('${s.id}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openPv('${s.id}')}"`:`role="img" aria-label="${label}"`}>${content}</div>${actions}${s.production_mode?`<div class="sample-caption">${({first_template:'首模板',template_extension:'模板扩展',local_resize:'本机适配'})[s.production_mode]}</div>`:p.image_count>1?`<div class="sample-caption">图 ${s.idx}</div>`:''}</div>`;
}
function imageRetry(r,s){
 const head=waitingSource(r,s)||r.slots.find(x=>x.id===(s.parent_id||s.first_id)),query=!!s.query_required||['unknown','timeout'].includes(s.reason_code),blockedFirst=blocked(r,s)||s.state==='blocked_first_failed';
 const group=dependentImages(r,s);
 const busy=group.some(x=>['queued','generating'].includes(x.state)||x.local_processing);
 if(s.production_mode)return{query,blocked:blockedFirst,head,disabled:!!r.generation_disabled||busy&&!blockedFirst,
  label:query?'恢复查询':blockedFirst?'查看来源图片':s.production_mode==='local_resize'?'重新适配':group.length>1?'重出母版及依赖图片':'重出本张',
  note:query?'沿用原任务查询，不重新提交。':blockedFirst?'请先完成首模板或母版。':s.production_mode==='local_resize'?'读取当前母版，在本机重新适配；不调用图片模型。':group.length>1?`将更新本图及 ${group.length-1} 张依赖图片，并取消这些图片的当前选择；原版本和交付包保留。`:'引用本套首模板重出当前版位，保留角色、画风与场景。'};
 return {query,blocked:blockedFirst,head,disabled:!!r.generation_disabled||busy&&!blockedFirst,
 label:query?'恢复查询':blockedFirst?'查看图 1':s.idx===1&&plOf(s.pid).image_count>1?'重出图 1 及后续图':'重出本张',
 note:query?'本次查询等待已结束，供应商任务可能仍在运行。恢复查询沿用原任务号，不重新提交生图。':blockedFirst?'本张依赖图 1，请先处理图 1。':s.idx===1&&plOf(s.pid).image_count>1?'重出图 1 后，本套后续图会退出当前结果，等待新图 1 完成后重新生成；历史文件保留。':s.idx>1?'仅重出本张，继续引用本套当前图 1；其他图片保留。':'仅重出当前图片。'};
}
function refsOf(r,s){return(s.reference_images||[]).map((x,i)=>({k:i,name:(x.label||'参考图'+(i+1))+' · '+x.name+(x.retired?' · 历史参考已停用':''),src:x.thumbnail_url,bad:x.upload_status==='failed'}))}
function viewPv(){return viewProductionOrdinaryPreview()}

function viewCfg(){return`<div class="mask" id="m-settings" onclick="if(event.target===this)closeCfg()"><div class="dlg" role="dialog" aria-modal="true" aria-label="设置" id="cfgdlg"><button class="x" onclick="closeCfg()" aria-label="关闭">×</button><h2>设置</h2>
 <section data-grp="planning"><h5 style="margin-top:0">画面规划</h5>
 <div class="field"><label for="planmodel">语言模型</label><input id="planmodel" maxlength="128" value="${esc(CFG.planningModel||'')}" autocomplete="off"></div>
 <div class="field"><label for="plankey">规划 Key</label><div><div class="row"><input type="password" id="plankey" autocomplete="off" placeholder="${CFG.planningKey?'已配置，留空保留':''}" value=""><button style="flex:none" id="plantest" onclick="testPlanning()">测试连接</button></div><div id="planst" role="status"></div></div></div>
 <div class="field"><label for="planbase">接口地址</label><input id="planbase" value="${esc(CFG.planningBase||'')}" autocomplete="off"></div>
 </section>
 <section data-grp="img"><h5>图片生成</h5>
 <div class="field"><label for="cfgimagemodel">默认模型</label><select id="cfgimagemodel">${imageModelOptions(CFG.imageModel)}</select></div>
 <div class="field"><label for="kiekey">KIE Key</label><div><div class="row"><input type="password" id="kiekey" autocomplete="off" placeholder="${CFG.kie?'已配置，留空保留':''}" value="" oninput="imageKeyEntered()"><button style="flex:none" id="kietest" onclick="testConn()">测试连接</button></div><div id="kiest">${connTx("kie")}</div></div></div>
 <div class="field"><label for="cfgimagemode">图片输出</label><select id="cfgimagemode" onchange="document.getElementById('simulation-warning').hidden=this.value!=='simulation'"><option value="real" ${!CFG.simulation?'selected':''}>真实生图</option><option value="simulation" ${CFG.simulation?'selected':''}>模拟预览</option></select></div><p class="simulation-warning" id="simulation-warning" ${CFG.simulation?'':'hidden'}>模拟仅影响图片输出，画面规划仍会消耗 API 额度。</p>
 <details id="adv"><summary>高级</summary><div class="field"><label for="kbase">KIE_BASE_URL</label><input id="kbase" value="${esc(CFG.base)}"></div><div class="field"><label for="kup" style="font-size:12px">KIE_UPLOAD_BASE_URL</label><input id="kup" value="${esc(CFG.up)}"></div></details></section>
<section><h5>数据维护</h5><button onclick="openMaintenance()">备份、恢复与清理旧版本</button></section><section data-grp="gen"><h5>通用</h5><div class="field"><span class="lab">候选与暂存占用</span><div class="stor" id="stor">${storHtml()}</div></div>
 <div class="field"><label for="cfgpath">保存位置</label><div class="row"><input id="cfgpath" value="${esc(CFG.path)}"><button style="flex:none" onclick="chooseFolder()">选择…</button></div></div></section>
 <div class="foot"><button onclick="closeCfg()">取消</button><button class="primary" id="cfgsave" onclick="saveCfg()">保存设置</button></div></div></div>`}

function softRender(){if(!S.pv&&!S.cfgOpen&&!S.maintenanceOpen)return render();const a=document.querySelector("#app>.app");if(!a)return render();const m=$("main"),y=m?m.scrollTop:0,ae=document.activeElement,inApp=a.contains(ae),fref=inApp?trapRef(ae):null;
 const stage=$('.sample-stage'),stageTop=stage?.scrollTop||0,setsLeft=$('#sets')?.scrollLeft||0,directoryTop=$('.dir-list')?.scrollTop||0,directoryLeft=$('.dir-list')?.scrollLeft||0;
 const body=typeof viewPageContent==='function'?viewPageContent():S.view==='learning-run'&&typeof viewLearningRun==='function'?viewLearningRun():S.view==='learning-logo'&&typeof viewLearningLogoConfig==='function'?viewLearningLogoConfig():S.openingTask?viewPick():S.view==="form"?viewForm():S.view==="pick"?viewPick():viewDl();const d=document.createElement("div");d.innerHTML=`<div class="app ${S.view==='pick'||S.openingTask?'pick-mode':''} ${S.sidebarCollapsed?'sidebar-collapsed':''}">${viewSide()}<main id="main">${typeof viewWorkspaceTopbar==='function'?viewWorkspaceTopbar():''}${viewHead()}<div class="body" id="body">${body}</div>${(typeof showSelectionFooter==='function'?showSelectionFooter():S.view==='pick'&&!S.openingTask)?viewSelectionFooter():''}</main></div>`;const tl=$(".sidebar-scroll")||$(".tasks"),ty=tl?tl.scrollTop:0;a.replaceWith(d.firstElementChild);const tl2=$(".sidebar-scroll")||$(".tasks");if(tl2)tl2.scrollTop=ty;const m2=$("main");if(m2){m2.scrollTop=y;setHH()}if(fref){const e=document.querySelector(fref);if(e)e.focus({preventScroll:true})}updTimers();syncSelectionControls();
 const updatedStage=$('.sample-stage');if(updatedStage){updatedStage.scrollTop=stageTop;$('#sets').scrollLeft=setsLeft;$('.dir-list').scrollTop=directoryTop;$('.dir-list').scrollLeft=directoryLeft;updatePlacementScroll()}
}
function positionTaskMenu(){
 if(!S.menu)return;
 const anchor=document.querySelector('.trow.mopen .more'),menu=document.querySelector('.tmenu');
 if(!anchor?.getBoundingClientRect||!menu?.getBoundingClientRect)return;
 const a=anchor.getBoundingClientRect(),r=menu.getBoundingClientRect(),width=document.documentElement.clientWidth,height=document.documentElement.clientHeight;
 const left=Math.max(8,Math.min(a.right+8,width-r.width-8));
 const top=Math.max(8,Math.min(a.top,height-r.height-8));
 menu.style.left=left+'px';menu.style.top=top+'px';
}
document.addEventListener('scroll',positionTaskMenu,true);
function setHH(){
 updatePlacementScroll();positionTaskMenu();
 const m2=$("main"),h=$("#head"),tb=document.querySelector(".toolbar");if(!m2||!h)return;
 m2.style.setProperty("--hh",h.offsetHeight+"px");m2.style.setProperty("--sp",(h.offsetHeight+(tb&&S.view==="pick"?tb.offsetHeight+8:0)+8)+"px");
 const sets=$('#sets');if(!sets)return;
 const cards=[...sets.querySelectorAll('.set')];if(!cards.length)return;
 const style=getComputedStyle(sets),cardStyle=getComputedStyle(cards[0]);
 const width=sets.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight),gapX=parseFloat(style.columnGap),gapY=parseFloat(style.rowGap);
 const images=+style.getPropertyValue('--images'),ratio=+style.getPropertyValue('--image-ratio'),imageGap=parseFloat(style.getPropertyValue('--sample-gap'));
 const paddingX=parseFloat(cardStyle.paddingLeft)+parseFloat(cardStyle.paddingRight)+parseFloat(cardStyle.borderLeftWidth)+parseFloat(cardStyle.borderRightWidth);
 const paddingY=parseFloat(cardStyle.paddingTop)+parseFloat(cardStyle.paddingBottom)+parseFloat(cardStyle.borderTopWidth)+parseFloat(cardStyle.borderBottomWidth);
 let best={imageHeight:-1};
 // Compare every same-screen layout before considering a single scrolling row.
 for(let columns=1;columns<=cards.length+1;columns++){
  const scroll=columns>cards.length;if(scroll&&best.imageHeight>=160)break;
  const cols=scroll?cards.length:columns,rows=scroll?1:Math.ceil(cards.length/cols);
  const cardWidth=scroll?width:(width-(cols-1)*gapX)/cols;
  sets.dataset.scroll=String(scroll);sets.style.setProperty('--sample-columns',cols);sets.style.setProperty('--sample-card-width',cardWidth+'px');
  const overhead=paddingY+Math.max(...cards.map(card=>{
   const header=card.querySelector('.sethead'),headerStyle=getComputedStyle(header);
   const details=Math.max(...[...card.querySelectorAll('.sample-unit')].map(unit=>unit.getBoundingClientRect().height-unit.querySelector('.cell').getBoundingClientRect().height));
   return header.getBoundingClientRect().height+parseFloat(headerStyle.marginTop)+parseFloat(headerStyle.marginBottom)+details;
  }));
  const height=sets.clientHeight-parseFloat(style.paddingTop)-parseFloat(style.paddingBottom);
  const imageHeight=Math.max(0,Math.min((cardWidth-paddingX-(images-1)*imageGap)/images/ratio,(height-(rows-1)*gapY)/rows-overhead));
  if(scroll||imageHeight>best.imageHeight)best={columns:cols,cardWidth,cardHeight:imageHeight+overhead,imageHeight,overhead,scroll};
 }
 // A comparison gallery keeps landscape ads readable; additional rows scroll vertically.
 const vertical=images===1&&ratio>1&&cards.length>=3;
 sets.dataset.vertical=String(vertical);
 if(vertical){
  const columns=width>=800?2:1,cardWidth=(width-(columns-1)*gapX)/columns,imageHeight=(cardWidth-paddingX)/ratio;
  best={...best,columns,cardWidth,imageHeight,cardHeight:imageHeight+best.overhead,scroll:false};
 }
 // Keep tall-image cards close to the image when height, rather than width, limits the preview.
 const cardWidth=ratio<1&&!best.scroll
  ?Math.min(best.cardWidth,Math.max(260,best.imageHeight*ratio*images+(images-1)*imageGap+paddingX))
  :best.cardWidth;
 sets.dataset.scroll=String(best.scroll);sets.style.setProperty('--sample-columns',best.columns);sets.style.setProperty('--sample-card-width',cardWidth+'px');
 sets.style.setProperty('--sample-card-height',best.cardHeight+'px');sets.style.setProperty('--sample-image-width',best.imageHeight*ratio+'px');
}
function render(){const ae=document.activeElement,fk=ae&&ae.id,fref=ae&&ae!==document.body?trapRef(ae):null,ss=ae&&(ae.selectionStart||(ae.value&&ae.matches&&ae.matches('input[type=search],#styleq')?ae.value.length:ae.selectionStart)),m=$("main"),y=m?m.scrollTop:0;
 if(S.view==='form'&&typeof scheduleLearningAdaptation==='function')scheduleLearningAdaptation();
 const stage=$('.sample-stage'),stageTop=stage?.scrollTop||0,setsLeft=$('#sets')?.scrollLeft||0,directoryTop=$('.dir-list')?.scrollTop||0,directoryLeft=$('.dir-list')?.scrollLeft||0;
 const body=typeof viewPageContent==='function'?viewPageContent():S.view==='learning-run'&&typeof viewLearningRun==='function'?viewLearningRun():S.view==='learning-logo'&&typeof viewLearningLogoConfig==='function'?viewLearningLogoConfig():S.openingTask?viewPick():S.view==="form"?viewForm():S.view==="pick"?viewPick():viewDl();
 const tl=$(".sidebar-scroll")||$(".tasks"),ty=tl?tl.scrollTop:0;window._rnd=true;
 $("#app").innerHTML=`<div class="app ${S.view==='pick'||S.openingTask?'pick-mode':''} ${S.sidebarCollapsed?'sidebar-collapsed':''}">${viewSide()}<main id="main">${typeof viewWorkspaceTopbar==='function'?viewWorkspaceTopbar():''}${viewHead()}<div class="body" id="body">${body}</div>${(typeof showSelectionFooter==='function'?showSelectionFooter():S.view==='pick'&&!S.openingTask)?viewSelectionFooter():''}</main></div>${S.pv?viewPv():""}${S.cfgOpen?viewCfg():""}${S.maintenanceOpen?viewMaintenance():""}${typeof viewMasterCanvasDialog==='function'?viewMasterCanvasDialog():''}`;
 window._rnd=false;const tl2=$(".sidebar-scroll")||$(".tasks");if(tl2)tl2.scrollTop=ty;
 const m2=$("main");if(m2){m2.scrollTop=y;setHH()}
 const updatedStage=$('.sample-stage');if(updatedStage){updatedStage.scrollTop=stageTop;$('#sets').scrollLeft=setsLeft;$('.dir-list').scrollTop=directoryTop;$('.dir-list').scrollLeft=directoryLeft;updatePlacementScroll()}
 if(!fk&&fref){const e=document.querySelector(fref);if(e&&!(S.pv||S.cfgOpen))e.focus({preventScroll:true})}if(fk){const e=document.getElementById(fk);if(e&&!e.closest(".mask")||e&&(S.pv||S.cfgOpen)){e.focus({preventScroll:true});try{if(ss!=null&&e.setSelectionRange)e.setSelectionRange(ss,ss)}catch(_){}}}updTimers();syncSelectionControls();positionTaskMenu()}

/* ===== 配置动作 ===== */
function togP(id){if(S.submitting||S.navigationPending||!formPlacements(S.draft).some(p=>p.id===id))return;invalidateLearningPreview();S.learningAutoSelectAll=false;const a=S.draft.pids;S.draft.pids=a.includes(id)?a.filter(x=>x!==id):[...a,id];filterFormPlacements(S.draft);save();render()}
function setF(k,v,re){if(S.submitting||S.navigationPending)return;if(learningForm(S.draft)&&['noLogo','logo_asset_id','cta_enabled','cta_overrides','learning_mode','sets'].includes(k))return;invalidateLearningPreview();if(learningForm(S.draft)&&['ip','style','font','image_model','feature_note'].includes(k))delete S.draft.learning_visual_config;S.draft[k]=v;save();if(re)render();else updSum()}
function setSets(v){if(S.submitting||S.navigationPending)return;invalidateLearningPreview();delete S.draft.variants_by_placement;S.draft.sets=v;save();updSum()}
function stepSets(delta){setSets(Math.max(SETS_MIN,Math.min(SETS_MAX,(+S.draft.sets||SETS_MIN)+delta)));render()}
function updSum(){if(typeof scheduleLearningAdaptation==='function')scheduleLearningAdaptation();const pr=S.draft;const title=$("#title");if(title&&S.view==='form')title.textContent=tName({draft:pr});const e=$("#tot");if(e)e.textContent="共 "+(pr.channel?totalOf(pr):0)+" 张";const i=$("#f-sets");if(i){i.classList.toggle("bad",setsBad(pr));if(document.activeElement!==i)i.value=pr.sets}document.querySelectorAll('[data-cta-label]').forEach(label=>{const text=placementCtaText(pr,label.dataset.ctaLabel);label.textContent=(pr.cta_overrides?.[label.dataset.ctaLabel]?.mode==='custom'?text:text?'跟随统一':'无按钮');label.parentElement.classList.toggle('no-button',!text)});const formula=$("#sum-formula");if(formula)formula.innerHTML=summaryFormula(pr);const production=$("#learning-production");if(production)production.textContent=learningProduction(pr);const hint=$('#generation-hint');if(hint&&!S.submitting)hint.textContent=!pr.channel?'先选渠道':formIssue(pr)?.message||'';const g=$("#go");if(g)g.disabled=setsBad(pr)||!pr.channel||!pr.pids.length||!!S.submitting||!!S.navigationPending||!!S.uploadingPurpose||learningUpload(pr)&&(!pr.learning_source||!!S.learningReadPending||!currentLearningPlan(pr))}

function setTab(c){S.tab=c;S.miss=false;save();render()}
async function setRound(i){const epoch=beginNavigation();if(epoch===null)return;try{await persistPromptDraft();if(epoch!==viewEpoch)return;const t=await request('/tasks/'+S.cur+'?view=1&round='+i);if(epoch!==viewEpoch)return;installTask(t);T().ri=i;save(false);render()}finally{finishNavigation(epoch)}}

function trapRef(e){if(!e||e===document.body)return null;return e.id?"#"+e.id:e.dataset?.sel?`[data-sel="${e.dataset.sel}"]`:e.dataset?.pickPlacement?`[data-pick-placement="${e.dataset.pickPlacement}"]`:e.dataset&&e.dataset.slot?`[data-slot="${e.dataset.slot}"]`:e.closest&&e.closest("[data-slot]")?`[data-slot="${e.closest("[data-slot]").dataset.slot}"]`:null}


function curPvSlot(){return S.pvDetails?.id===S.pv?S.pvDetails:null}



function cfgRef(e){if(!e||e===document.body)return"#cfgbtn";return e.id?"#"+e.id:"#cfgbtn"}

function cfgBack(){const e=document.querySelector(window._cfgFrom||"#cfgbtn")||$("#cfgbtn");window._cfgFrom=null;if(e)e.focus({preventScroll:true})}
function closeCfg(){if(S.view==='settings'&&typeof openWorkspacePage==='function')return openWorkspacePage('tasks');S.cfgOpen=false;render();cfgBack()}

/* 键盘:Esc 关闭最上层弹窗;弹窗内锁焦点 */
document.addEventListener("keydown",e=>{
 if(S.masterCanvasDialog)return;
 if(S.menu&&['Escape','ArrowDown','ArrowUp','Home','End'].includes(e.key)){
  e.preventDefault();if(e.key==='Escape'){closeTaskMenu();return}
  const items=[...document.querySelectorAll('.tmenu button:not(:disabled)')],index=items.indexOf(document.activeElement);
  const next=e.key==='Home'?0:e.key==='End'?items.length-1:(index+(e.key==='ArrowUp'?-1:1)+items.length)%items.length;items[next]?.focus();return;
 }
 const directoryArrow=['ArrowLeft','ArrowRight'].includes(e.key)&&e.target.closest('[data-pick-placement]');
 if(S.view==='pick'&&!S.cfgOpen&&!S.pv&&!S.maintenanceOpen&&!S.navigationPending&&(['ArrowDown','ArrowUp'].includes(e.key)||directoryArrow)&&!e.target.closest('input,textarea,select,[contenteditable]')){
  e.preventDefault();const r=R(),forward=e.key==='ArrowDown'||e.key==='ArrowRight';
  const next=r.params.pids[r.params.pids.indexOf(pickPlacement(r))+(forward?1:-1)];
  if(next){setPickPlacement(next);if(directoryArrow)document.querySelector(`[data-pick-placement="${next}"]`)?.focus({preventScroll:true})}return;
 }
 const m=S.maintenanceConfirm?$(".maintenance-confirm"):S.maintenanceOpen?$(".maintenance"):S.cfgOpen?$("#cfgdlg"):S.pv?$("#pv"):null;if(!m)return;
 if(e.key==="Escape"&&S.maintenanceOpen)return;
 if(e.key==="Escape"){e.preventDefault();S.cfgOpen?closeCfg():closePv();return}
 if(S.pv&&!S.cfgOpen&&!S.maintenanceOpen&&(e.key==="ArrowLeft"||e.key==="ArrowRight")&&!e.target.closest('input,textarea,select,[contenteditable]')){e.preventDefault();$(e.key==="ArrowLeft"?'#pvprev':'#pvnext')?.click();return}
 if(e.key==="Tab"){const f=[...m.querySelectorAll("input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,button:not([disabled])")].filter(x=>x.offsetParent!==null);if(!f.length)return;const a=f[0],z=f[f.length-1];if(!m.contains(document.activeElement)){e.preventDefault();(e.shiftKey?z:a).focus()}else if(e.shiftKey&&document.activeElement===a){e.preventDefault();z.focus()}else if(!e.shiftKey&&document.activeElement===z){e.preventDefault();a.focus()}}});
document.addEventListener("click",e=>{if(S.miss&&!e.target.closest("#miss")){S.miss=false;render()}});

function selectionKey(pid,n){return pid+'::'+n}
function setsOf(r){
  const groups=new Map();
  r.slots.forEach(s=>{const id=selectionKey(s.pid,s.set);if(!groups.has(id))groups.set(id,{id,n:s.set,pid:s.pid,sl:[]});groups.get(id).sl.push(s)});
  return [...groups.values()];
}
function selectedSet(r,g){return !!r.sel[g.id]}
function attentionSet(r,g){return g.sl.some(s=>isFail(r,s)||s.state==='stopped'||s.delivery_eligible===false)}
function readySet(g){return g.sl.length===plOf(g.pid).image_count&&g.sl.every(s=>s.state==='done'&&s.delivery_eligible!==false&&s.reason_code!=='frame_failed')}
function pickPlacement(r){
 const key=S.cur+':'+r.id;
 if(S.pickRound!==key||!r.params.pids.includes(S.pickPid)){S.pickRound=key;S.pickPid=r.params.pids[0]}
 return S.pickPid;
}
function groupMatchesFilter(r,g,pf){
  if(pf==='ready')return readySet(g)&&!selectedSet(r,g);
  return pf==='yes'?selectedSet(r,g):pf==='no'?!selectedSet(r,g):pf==='bad'?attentionSet(r,g):true;
}
function setPickFilter(filter){
  S.pf=filter;
  render();
  $('#sets')?.scrollTo({left:0,top:0});
}
function setIdentity(r,pid,number){
  const meta=r.set_metadata?.[selectionKey(pid,number)]||r.set_metadata?.[number];
  return meta?[meta.style?.name,meta.ip_name||(!meta.ip_id?'原创人物':'')].filter(Boolean).join(' · '):'';
}
function selectionScope(r){
  return setsOf(r).filter(g=>g.pid===pickPlacement(r)&&groupMatchesFilter(r,g,S.pf)&&(readySet(g)||selectedSet(r,g)));
}
function bulkSelectionState(r){
  const scope=selectionScope(r),selected=scope.filter(g=>selectedSet(r,g)).length;
  return{scope,selected,all:scope.length>0&&selected===scope.length,mixed:selected>0&&selected<scope.length};
}
function syncSelectionControls(){const e=document.querySelector('#select-visible');if(e)e.indeterminate=e.getAttribute('aria-checked')==='mixed';
 const b=$('#pvsel'),s=curPvSlot();if(b&&s){const on=!!R().sel[selectionKey(s.pid,s.set)];b.classList.toggle('checked',on);b.setAttribute('aria-pressed',String(on))}
}
function pickCardClick(event,n,pid){
  if(event.target.closest('button,input,label,textarea,a,.cell')||S.selectionBusy)return;
  const r=R(),group=setsOf(r).find(g=>g.pid===pid&&g.n===n);
  if(group&&(readySet(group)||selectedSet(r,group)))toggleSel(n,false,pid);
}
function viewPick(){
  if(S.openingTask)return `<div class="pick-workbench pick-skeleton" aria-busy="true" aria-label="正在加载任务"><nav class="placement-dir"><div class="dir-list">${Array.from({length:5},()=>'<div class="skeleton skeleton-directory"></div>').join('')}</div></nav><section class="sample-stage"><div class="placement-head"><span class="skeleton skeleton-title"></span></div><div id="sets"><div class="skeleton skeleton-set"></div><div class="skeleton skeleton-set"></div></div></section></div>`;
  const r=R();if(!r)return'';
  const groups=setsOf(r),pid=pickPlacement(r),p=plOf(pid);
  const current=groups.filter(g=>g.pid===pid),filter=S.pf||'all';
  const visible=current.filter(g=>groupMatchesFilter(r,g,filter)).sort((first,second)=>first.n-second.n);
  const directory=r.params.pids.map(id=>{
    const placement=plOf(id),sets=groups.filter(g=>g.pid===id),slots=sets.flatMap(g=>g.sl),done=slots.filter(s=>s.state==='done').length;
    const completed=sets.filter(g=>g.sl.length===placement.image_count&&g.sl.every(s=>s.state==='done')).length;
    const selected=sets.filter(g=>selectedSet(r,g)).length,problems=sets.filter(g=>attentionSet(r,g)||g.sl.some(s=>s.delivery_eligible===false)).length;
    const running=slots.some(s=>['queued','generating','waiting_first'].includes(s.state));
    const progress=running?`<span class="dir-gen-progress">${done}/${slots.length}<span class="mini-progress-track" role="progressbar" aria-label="${esc(pname(placement))}生成进度" aria-valuemin="0" aria-valuemax="${slots.length}" aria-valuenow="${done}"><i style="width:${done/Math.max(1,slots.length)*100}%"></i></span></span>`:'';
    return`<button class="dir-item ${id===pid?'active':''}" data-pick-placement="${id}" aria-current="${id===pid?'true':'false'}" onclick="setPickPlacement('${id}')"><span class="dir-item-name">${esc(pname(placement))}</span><span class="dir-status-cols">${progress}${!running||completed>0?`<span class="${selected?'badge-selected':'badge-unselected-ready'}">${selected?'已选 '+selected+' 套':'未选'}</span>`:''}${problems?`<span class="dir-problem-text">· ${problems} 问题</span>`:''}</span></button>`;
  }).join('');
  const bulk=bulkSelectionState(r);
  const filters=[['all','全部',current.length],['ready','未选',current.filter(g=>groupMatchesFilter(r,g,'ready')).length],['yes','已选',current.filter(g=>selectedSet(r,g)).length],['bad','待处理',current.filter(g=>attentionSet(r,g)).length]];
  const issues=groups.filter(g=>attentionSet(r,g)).length;
  const scopeLabel=filter==='all'?'全选当前版位':'全选当前筛选';
  const selectionBar=`<div class="selection-bar pick-toolbar"><div class="sample-filters" role="group" aria-label="套图筛选">${filters.filter(([key,,count])=>key!=='bad'||count>0||filter==='bad').map(([key,label,count])=>`<button id="sample-filter-${key}" aria-pressed="${filter===key}" onclick="setPickFilter('${key}')">${label}<span>${count}</span></button>`).join('')}</div><div class="selection-actions"><label class="select-all"><input id="select-visible" type="checkbox" aria-label="${bulk.all?'取消'+scopeLabel:scopeLabel}" aria-checked="${bulk.mixed?'mixed':bulk.all?'true':'false'}" ${bulk.all?'checked':''} ${!bulk.scope.length||S.selectionBusy?'disabled':''} onchange="selectVisible(this.checked)"><span>${bulk.all?'取消全选':'全选'}</span></label>${bulk.mixed?`<button id="clear-visible" ${S.selectionBusy?'disabled':''} onclick="clearVisibleSelection()">清空当前选择</button>`:''}${r.generation_disabled||r.params.learning_mode==='upload'?'':`<button class="add-variant" ${['queued','running'].includes(r.planning_status)||current.length>=20?'disabled':''} onclick="addVariant('${pid}')">＋ 再出一套</button>`}</div></div>`;
  const legacy=r.generation_disabled?`<div class="planning-notice"><span>此制作流程已停用，已有图片和图包可查看；请提交新配置制作。</span><button onclick="editRedo()">按新规则重新制作</button></div>`:r.planning_source==='simulation'?`<div class="planning-notice"><span>历史模拟结果，尚未使用新的画面规划</span><button onclick="dupTask()">复制并重新规划</button></div>`:'';
  const planError=r.planning_status==='failed'?`<div class="planning-error" role="alert"><span>${esc(r.planning_error||'画面规划未完成')}</span><button onclick="retryPlanning()">重试规划</button></div>`:'';
  const cards=visible.map(g=>{
    const on=selectedSet(r,g),ready=readySet(g),problem=attentionSet(r,g)||g.sl.some(s=>s.delivery_eligible===false);
    const identity=setIdentity(r,g.pid,g.n);
    return`<section class="set ${on?'chosen':''} ${problem?'has-problem':''}" data-set="${g.n}" data-placement="${g.pid}" aria-label="${esc(pname(p))} · 套 ${g.n}" onclick="pickCardClick(event,${g.n},'${g.pid}')"><div class="sethead"><div class="set-identity"><b>第 ${g.n} 套</b>${identity?`<span title="${esc(identity)}">${esc(identity.split(' · ')[0])}</span>`:''}</div>${typeof masterCanvasOrdinarySource==='function'?`<button class="master-canvas-set-entry" id="master-canvas-set-${g.pid}-${g.n}" ${masterCanvasOrdinarySource(g.sl[0]?.id).error?'disabled':''} onclick="event.stopPropagation();openMasterCanvasFromOrdinary('${g.sl[0]?.id}')">制作多尺寸母版</button>`:''}<label class="set-check" title="${on?'取消选择':'选择这一套'}"><input type="checkbox" data-sel="${g.id}" aria-label="选择 ${esc(pname(p))} 套 ${g.n}" ${on?'checked':''} ${!ready&&!on||S.selectionBusy?'disabled':''} onchange="toggleSel(${g.n},false,'${g.pid}')"><span aria-hidden="true">✓</span></label></div><div class="sample-row" style="--images:${p.image_count}">${[...g.sl].sort((first,second)=>first.idx-second.idx).map(s=>cellHtml(r,s)).join('')}</div></section>`;
  }).join('');
  const empty={yes:'当前版位还没有选中的套图',bad:'当前版位没有待处理的套图',ready:'当前版位暂无可挑选的套图'}[filter]||'暂无套图';
  return`<div class="pick-workbench"><nav class="placement-dir" aria-label="本轮版位目录"><div class="directory-heading"><h2>版位</h2><span>${r.params.pids.length} 个</span></div><div class="directory-scroll"><button class="directory-arrow" id="dir-prev" aria-label="向左查看更多版位" onclick="scrollPlacementDirectory(-1)"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m12 5-5 5 5 5"/></svg></button><div class="dir-list" onscroll="updatePlacementScroll()">${directory}</div><button class="directory-arrow" id="dir-next" aria-label="向右查看更多版位" onclick="scrollPlacementDirectory(1)"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m8 5 5 5-5 5"/></svg></button></div>${issues?`<div class="directory-actions"><button id="locate-pick-issue" onclick="locatePickIssue()">定位待处理 <span>${issues} 套</span></button></div>`:''}</nav><section class="sample-stage">${legacy}${planError}<div class="placement-head"><h3>${esc(pname(p))}</h3><span class="muted">${psz(p)}</span></div>${selectionBar}<div class="suite-grid" id="sets" style="--images:${p.image_count};--image-ratio:${p.target_width/p.target_height}">${cards||`<div class="sample-empty"><strong>${empty}</strong>${filter!=='all'?'<button onclick="setPickFilter(\'all\')">查看全部</button>':''}</div>`}</div></section></div>`;
}
function ordinaryLogoExportKey(r){return (S.cur||T()?.id||'task')+':'+(r.id??T()?.ri??0)}
function ordinaryLogoExportValue(r=R()){if(!r||r.logo_export_capability?.editable!==true)return '';return canonicalLogoVariant(S.exportLogoByRound?.[ordinaryLogoExportKey(r)])}
function setOrdinaryExportLogo(value){
 const r=R(),selected=value?canonicalLogoVariant(value):'';if(!r||S.exportBusy||value&&!selected)return;
 if(selected&&r.logo_export_capability?.editable!==true){if(typeof toast==='function')toast(r.logo_export_capability?.reason||'这一轮不能直接替换Logo，可按当前图片导出');return}
 S.exportLogoByRound=S.exportLogoByRound||{};S.exportLogoByRound[ordinaryLogoExportKey(r)]=selected;render();
}
function viewOrdinaryLogoExport(r){
 const capability=r.logo_export_capability,editable=capability?.editable===true,value=ordinaryLogoExportValue(r);
 const note=editable?'只影响本次图包；无Logo图片不添加，合成不调用生图。':capability?.reason||'这一轮按现有图片导出；未提供可替换的Logo图层。';
 return `<div class="logo-export-control"><label for="ordinary-export-logo">导出Logo<select id="ordinary-export-logo" ${!editable||S.exportBusy?'disabled':''} onchange="setOrdinaryExportLogo(this.value)">${logoVariantOptions(value)}</select></label><small>${esc(note)}</small></div>`;
}
function viewSelectionFooter(){
 if(S.view==='dl')return'';
 const r=R();if(!r)return'';const d=r.delivery||{};
 const partial=d.incomplete_sets>0,saved=!ordinaryLogoExportValue(r)&&d.has_changes===false&&d.matching_version;
 const canSave=!!d.ready_sets&&(d.can_export_ready||d.can_export);
 const pid=pickPlacement(r),next=r.params.pids[r.params.pids.indexOf(pid)+1];
 const hint=d.selected_sets?(canSave||saved?'':'处理已选套图后即可保存'):'勾选要交付的成品套图';
 const label=S.exportBusy?'正在保存…':canSave?(partial?'保存已合格的 ':'保存 ')+d.ready_sets+' 套':'保存图包';
 const action=saved?'<button class="primary" onclick="openFolder()">打开文件夹</button>':`<button id="${partial?'save-ready':'save-selected'}" class="primary" ${!canSave||S.exportBusy?'disabled':''} ${hint?'aria-describedby="save-hint"':''} onclick="dlAll(${partial})">${esc(label)}</button>`;
 return `<footer class="selection-footer"><div><span class="save-facts">已选 <b>${d.selected_sets||0}</b> 套 · 覆盖 ${d.covered_placements||0}/${d.total_placements||r.params.pids.length} 个版位</span>${partial?`<button class="lnk partial-warning" onclick="locateIncomplete()" title="另 ${d.incomplete_sets} 套待处理，不纳入本次图包">${d.ready_sets||0} 套可交付 · ${d.incomplete_sets} 套待处理</button>`:''}${hint?`<span id="save-hint" class="save-hint">${hint}</span>`:''}${saved?`<span class="saved-status" role="status">已保存 ${esc(d.matching_version)}</span>`:d.last_version&&d.has_changes?'<span class="save-hint">选择已变更，尚未保存</span>':''}</div><div class="footer-actions">${viewOrdinaryLogoExport(r)}<button id="next-placement" ${next?'':'disabled'} onclick="setPickPlacement('${next||pid}')">下一版位 →</button>${action}</div></footer>`;
}

function viewDl(){
  const t=T();if(!t)return'';
  return`<div class="history-head"><div><h3>交付记录</h3><p class="muted">已保存的图包会保留，不受当前选择变化影响。</p></div><button onclick="go('pick')">返回挑选</button></div>${[...t.pkgs].reverse().map(p=>`<div class="card delivery-record"><div class="pkrow"><b>v${String(p.v).padStart(3,'0')}</b><span class="muted">${new Date(p.created_at*1000).toLocaleString('zh-CN')}</span><span class="delivery-scope">${p.images.length} 张 · ${new Set(p.images.map(image=>image.pid)).size} 个版位</span><button onclick="openFolder()">打开文件夹</button><button onclick="redl('${p.id}')">下载副本</button></div>${canonicalLogoVariant(p.logo_asset_id)?`<p class="field-help">本包导出Logo：${logoVariantLabel(p.logo_asset_id)}；缩略图展示制作图片版本。</p>`:''}<div class="ths">${(p.images||[]).map(image=>`<button class="delivery-thumb" onclick="openPv('${image.id}',${image.att})"><img src="${image.thumbnail_url}" alt="查看交付图片第${image.att}版"></button>`).join('')}</div></div>`).join('')||'<div class="empty-delivery"><strong>还没有保存的图包</strong><p>在挑选页选择完整套图，再保存到本机。</p><button onclick="go(\'pick\')">去挑选</button></div>'}`;
}

function roundLabel(r,i,count){return '第 '+(i+1)+' 次修改'+(i===count-1?' · 当前':'')+(r.created_at?' · '+new Date(r.created_at*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}):'')}
function summaryRow(t){
 const menu=S.menu===t.id,meta=[t.status,t.image_form,t.active||t.done<t.total?t.done+'/'+t.total:''].filter(Boolean).join(' · ');
 const created=Number.isFinite(t.date)&&t.date>0?new Date(t.date):null;
 const time=created&&Number.isFinite(created.getTime())?`<time datetime="${created.toISOString()}" title="创建于 ${esc(created.toLocaleString('zh-CN'))}">${esc(created.toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}))}</time>`:'';
 const details=t.image_model?meta+' · '+imageModelName(t.image_model):meta;
 return `<li class="trow ${menu?'mopen':''}">${S.ren===t.id?`<input id="renin" aria-label="任务名" value="${esc(S.renV??t.name)}" oninput="S.renV=this.value" onkeydown="if(event.key==='Enter')renOk();if(event.key==='Escape')renEnd()" onblur="renOk()">`:`<button class="task ${S.cur===t.id?'on':''}" data-task="${t.id}" onclick="openTask('${t.id}')"><div><div class="task-title-row"><div class="t1">${esc(t.name)}</div>${time}</div><div class="t2" title="${esc(details)}">${esc(meta)}</div></div></button>`}<button class="more" data-menu-task="${t.id}" aria-label="更多操作" aria-haspopup="menu" aria-expanded="${menu}" onclick="event.stopPropagation();openMenu('${t.id}')">⋯</button>${menu?`<div class="tmenu" role="menu" aria-label="任务操作"><button role="menuitem" onclick="renStart('${t.id}')">重命名</button><button role="menuitem" class="danger" ${t.active?'disabled':''} onclick="delTask('${t.id}')">删除</button></div>`:''}</li>`;
}
