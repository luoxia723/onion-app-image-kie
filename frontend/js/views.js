let FORM_DEFAULTS={};
let IMAGE_MODEL_OPTIONS=[['gpt-image-2-5-sunburst-image-to-image','GPT Image 2.5 Sunburst'],['gpt-image-2-image-to-image','GPT Image 2']];
function imageModelOptions(selected){return IMAGE_MODEL_OPTIONS.map(([id,name])=>`<option value="${id}" ${id===selected?'selected':''}>${id==='gpt-image-2-5-sunburst-image-to-image'?'Sunburst 2.5 · 1K':id==='gpt-image-2-image-to-image'?'GPT Image 2 · 1K':esc(name)}</option>`).join('')}

const $=s=>document.querySelector(s);
function esc(s){return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}
function plOf(id){if(S.view!=='form'){const r=R();if(r?.placement_rules?.[id])return r.placement_rules[id]}return PLACEMENTS.find(p=>p.id===id)}
function pname(p){return p.platform+" "+p.name.replace(/\s*\d+×\d+/,"")}
function psz(p){return p.target_width+"×"+p.target_height}
function fnv(s){let h=0x811c9dc5;for(const c of s){h^=c.charCodeAt(0);h=Math.imul(h,16777619)>>>0}return h.toString(16).padStart(8,"0")}
function toast(t){const e=$("#toast");e.textContent=t;e.classList.add("on");clearTimeout(toast._t);toast._t=setTimeout(()=>e.classList.remove("on"),1800)}

function ipOfSet(pr,n){const r=R();const selected=r?.set_metadata?.[String(n)]?.ip_id;if(selected!==undefined)return IPS.find(a=>a.id===selected)||null;if(pr.ip==='none')return null;return IPS.find(a=>a.id===pr.ip)||null}
function styleOfSet(pr,n){return pr.style==="random"?STYLES[(n*7)%STYLES.length].name:pr.style}
function fontOfSet(n){return FONTS[(n*5)%FONTS.length]}
function perSet(pr){return pr.pids.map(plOf).filter(Boolean).reduce((a,p)=>a+p.image_count,0)}
function totalOf(pr){return pr.pids.map(plOf).filter(Boolean).reduce((n,p)=>n+p.image_count*(pr.variants_by_placement?.[p.id]??(+pr.sets||0)),0)}
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

function tName(t){if(t.name)return t.name;const p=(t.rounds[0]||{}).params||{},multi=(p.pids||[]).some(id=>{const q=plOf(id);return q&&q.image_count>1});return Array.from(((multi?p.s1:p.t1)||t.pkg||"").trim()).slice(0,16).join("")||t.pkg}
function workStatus(r){
 const slots=r.slots||[],done=slots.filter(s=>s.state==='done').length,generating=slots.filter(s=>s.state==='generating').length,queued=slots.filter(s=>s.state==='queued').length;
 const planning=r.planning_status==='running'||!r.stopped&&!r.paused&&r.planning_status==='queued',active=generating>0||r.planning_status==='running'||!r.stopped&&!r.paused&&(planning||queued>0);
 const groups=new Map();for(const slot of slots){const key=slot.pid+'::'+slot.set;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(slot)}
 const planned=[...groups.values()].filter(group=>group.every(slot=>slot.plan_ready!==false)).length;
 const waitingFirst=slots.filter(slot=>slot.state==='queued'&&slot.plan_ready!==false&&slot.idx>1&&slots.find(head=>head.id===slot.first_id)?.state!=='done').length;
 let title=r.paused?(generating?'已暂停后续，已开始的图片仍在处理':r.planning_status==='running'?'已暂停后续，已开始的规划仍在完成':'已暂停后续提交'):r.stopped?(generating?'已停止后续，已提交图片仍在生成':'已停止后续'):planning?(r.planning_status==='queued'?'正在排队，等待画面规划':generating?'正在规划画面，并陆续生成图片':'正在规划画面'):generating?'正在生成图片':queued?'排队等待生图':'生成已结束';
 const detail='画面 '+planned+' / '+groups.size+' 套就绪 · 图片 '+done+' / '+slots.length+' 张完成'+(generating?' · '+generating+' 张处理中':'')+(waitingFirst?' · '+waitingFirst+' 张等待图 1':'');
 return{active,planning,generating,queued,done,total:slots.length,title,detail,waitingFirst};
}
function waitLabel(r,s){
 if(s.state==='generating')return({uploading:'正在上传参考图',submitting:'正在提交生成任务',generating:'正在生成',downloading:'正在下载',processing:'正在处理尺寸'})[s.stage]||'生成中';
 if(s.state==='queued'&&r.paused)return'已暂停后续';
 if(s.state==='queued'&&s.plan_ready===false)return r.planning_status==='queued'?'待规划':'规划中';
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
const GROUPS=[["prog","正在处理"],["attention","待处理"],["old","历史"]];
function taskRow(t){if(t.is_summary)return summaryRow(t);const r=t.rounds[t.ri],[dc,st]=taskStatus(t),run=tRun(t),m=S.menu===t.id;
 if(S.ren===t.id)return`<li class="trow"><div class="task on ren"><input id="renin" aria-label="任务名" value="${esc(S.renV!=null?S.renV:tName(t))}" oninput="S.renV=this.value" onkeydown="if(event.key==='Enter')renOk();if(event.key==='Escape'){event.stopPropagation();renEnd()}" onblur="renOk()"></div></li>`;
 const meta=st+(r.delivery?.last_version&&st!=='已保存 '+r.delivery.last_version?' · 已保存 '+r.delivery.last_version+(r.delivery.has_changes?' · 勾选有变化，需重新保存':''):'');
 return`<li class="trow ${t.downloaded?"dl":""} ${m?"mopen":""}" oncontextmenu="event.preventDefault();openMenu('${t.id}')"><button class="task ${t.id===S.cur?"on":""}" data-task="${t.id}" onclick="openTask('${t.id}')"><div><div class="t1">${esc(tName(t))}</div><div class="t2" title="${esc(meta)}"><span class="dot ${dc}"></span><span class="tst">${esc(meta)}</span></div></div></button><button class="more" data-more="${t.id}" aria-label="更多操作" aria-haspopup="menu" aria-expanded="${m}" onclick="event.stopPropagation();openMenu('${t.id}')">⋯</button>${m?`<div class="tmenu" role="menu"><button role="menuitem" data-act="ren" onclick="renStart('${t.id}')">重命名</button><button role="menuitem" data-act="dup" onclick="dupFrom('${t.id}')">复制为新任务</button><button role="menuitem" data-act="del" ${run?'disabled aria-disabled="true"':""} onclick="delTask('${t.id}')">删除</button>${run?'<div class="mhint">先停止后续</div>':""}</div>`:""}</li>`}
function taskList(){const q=(S.q||"").trim().toLowerCase();if(S.searchPending)return '<li class="tnone">正在搜索任务…</li>';if(q){const h=S.summaries||S.tasks.filter(t=>tHit(t,q));return h.length?h.map(taskRow).join(""):'<li class="tnone">没有匹配的任务</li>'}
 const fold=S.fold||{};return GROUPS.map(([g,lab])=>{const ts=(S.summaries||S.tasks).filter(t=>tGroup(t)===g);if(!ts.length)return"";if(g==="prog")return`<li class="gh fixed" data-g="${g}"><span>${lab}</span><span class="gn">${ts.length}</span></li>${ts.map(taskRow).join("")}`;const f=!!fold[g];return`<li><button class="gh" data-g="${g}" aria-expanded="${!f}" onclick="togFold('${g}')"><span><i>${f?"▸":"▾"}</i>${lab}</span><span class="gn">${ts.length}</span></button></li>${f?"":ts.map(taskRow).join("")}`}).join("")}
function togFold(g){S.fold=Object.assign({},S.fold);S.fold[g]=!S.fold[g];save();render()}

function viewSide(){return`<aside><div class="side-top"><div class="brandrow"><img src="${LOGO.thumb}" alt="洋葱学园"><span>广告图工作台</span></div><button id="newbtn" onclick="newTask()">＋ 新建任务</button><div class="tsearch"><input id="tq" type="search" placeholder="搜索" aria-label="搜索任务" value="${esc(S.q||"")}" oninput="searchTasks(this.value)"></div></div>
<div class="sidebar-scroll"><ul id="draft-list" class="drafts" aria-label="草稿">${typeof draftListHtml==='function'?draftListHtml():''}</ul><ul class="tasks" aria-label="任务">${taskList()||((S.drafts||[]).length?'':'<li class="empty-list">还没有任务</li>')}</ul></div>${S.undo?`<div class="undo" id="undo" role="status"><span>已删除 ·</span><button id="undobtn" onclick="undoDel()">撤销</button></div>`:""}
<div class="side-bot"><div id="queue-overview" class="queue-overview">${typeof queueText==='function'?esc(queueText()):''}</div><div class="side-settings"><button class="ghost" id="cfgbtn" onclick="openCfg()">⚙ 设置</button>${CFG.simulation?'<span class="simulation-note">模拟预览</span>':""}</div></div></aside>`}
function stepsHtml(){const current=S.view==='form'?0:1;return`<div class="steps" role="tablist">${[['form','配置生成'],['pick','挑选保存']].map(([key,label],i)=>`<button class="step ${i===current?'on':i<current?'done':''}" ${key==='pick'&&!R()?'disabled':''} onclick="go('${key}')"><i>${i<current?'✓':i+1}</i>${label}</button>`).join('')}</div>`}
function viewHead(){const t=T(),pr=P(),nm=t?t.pkg:"新任务",tt=t?t.pkg+" · "+(pr.t1||pr.s1||""):"新任务";
 if(S.view==='form')return `<header class="head pick-head config-head" id="head"><div class="pick-heading"><h1 id="title" tabindex="-1">${esc(t?tName(t):'新任务')}</h1></div><span class="config-draft-state" id="draft-status" role="status">${esc(S.navigationPending?'正在打开，请稍候…':S.draftStatus||'草稿自动保存')}</span></header>`;

 if(S.view==='pick'&&t){
  const round=R(),status=workStatus(round);
  const queueActions=status.active||round.paused?`${!round.stopped?`<button onclick="pauseQueue(${!round.paused})">${round.paused?'继续队列':'暂停后续'}</button>`:''}<button id="stopbtn" ${round.stopped?'disabled':''} onclick="stopRest()">${round.stopped?'已停止后续':'停止后续提交'}</button>`:'';
  const rounds=t.rounds.length>1?`<label>修改记录<select id="roundSel" onchange="setRound(+this.value)">${t.rounds.map((entry,index)=>`<option value="${index}" ${index===t.ri?'selected':''}>${esc(roundLabel(entry,index,t.rounds.length))}</option>`).reverse().join('')}</select></label>`:'';
  return`<header class="head pick-head" id="head"><div class="pick-heading"><h1 id="title" tabindex="-1">${esc(tName(t))}</h1><span class="pick-progress" id="progtx">已出 <strong>${status.done} / ${status.total}</strong> 张</span>${viewWorkStatus(round)}</div><div class="pick-head-actions"><button id="redo" onclick="editRedo()">修改配置</button><button id="dup" onclick="dupTask()">复制为新任务</button><details class="pick-more" ${S.pickMore?'open':''} ontoggle="S.pickMore=this.open"><summary aria-label="任务更多操作">⋯</summary><div>${queueActions}${t.pkgs.length?'<button onclick="go(\'dl\')">交付记录</button>':''}${rounds}<span>${esc((IMAGE_MODEL_OPTIONS.find(model=>model[0]===(round.image_model||IMAGE_MODEL_OPTIONS[0][0]))||IMAGE_MODEL_OPTIONS[0])[1])} · 1K</span></div></details></div>${S.navigationPending?'<span class="pick-opening" role="status">正在打开，请稍候…</span>':''}</header>`;
 }
 const acts=S.view==="pick"&&t?`<div class="row"><button id="redo" onclick="editRedo()">修改配置 / 补充生成</button><button id="dup" onclick="dupTask()">复制为新任务</button>${t.pkgs.length?`<button id="historybtn" onclick="go('dl')">交付记录</button>`:''}</div>`:"";
 const rr=R(),rbar=S.view!=="form"&&t&&rr?(()=>{const status=workStatus(rr);return`<div class="hbar"><div class="prog" id="prog">${status.active?'<span class="wait-spinner small" aria-hidden="true"></span>':''}<div class="pbar" role="progressbar" aria-label="图片完成进度" aria-valuemin="0" aria-valuemax="${status.total}" aria-valuenow="${status.done}"><i style="width:${Math.round(status.done/Math.max(1,status.total)*100)}%"></i></div><span id="progtx">${status.active||rr.stopped?esc(status.title)+' · ':''}${status.done} / ${status.total} 张完成</span></div><span class="muted">${esc((IMAGE_MODEL_OPTIONS.find(x=>x[0]===(rr.image_model||IMAGE_MODEL_OPTIONS[0][0]))||IMAGE_MODEL_OPTIONS[0])[1])} · 1K</span>${t.rounds.length>1?`<label class="rsel"><span class="sr">修改记录</span><select id="roundSel" onchange="setRound(+this.value)">${t.rounds.map((x,i)=>`<option value="${i}" ${i===t.ri?"selected":""}>${esc(roundLabel(x,i,t.rounds.length))}</option>`).reverse().join("")}</select></label>`:''}</div>`})():'';
 return`<div class="head" id="head"><div class="crumb">任务 / <b id="crumbName">${esc(nm)}</b></div><div class="titlerow"><h1 id="title" tabindex="-1">${esc(tt)}</h1><div id="headActs">${acts}</div></div>${stepsHtml()}${S.navigationPending?'<div class="draft-state" id="navigation-status" role="status">正在打开，请稍候…</div>':''}${S.view==='form'?'<div class="draft-state"><span id="draft-status" role="status">'+esc(S.draftStatus||'草稿自动保存')+'</span><button class="lnk" onclick="persistDraft()">保存草稿</button></div>':''}${rbar}</div>`}
function setsBad(pr){const v=String(pr.sets).trim();return!/^\d+$/.test(v)||+v<SETS_MIN||+v>SETS_MAX}

const IMAGE_FORMS = {
  '单图': {count:1, fields:[['t1','主标题'],['t2','副标题']]},
  '双图': {count:2, fields:[['s1','句 1'],['s2','句 2']]},
  '三图': {count:3, fields:[['s1','句 1'],['s2','句 2'],['s3','句 3']]},
};
function imageFormOf(pr){
  if(Object.hasOwn(pr,'image_form'))return IMAGE_FORMS[pr.image_form]?pr.image_form:'';
  const forms=[...new Set((pr.pids||[]).map(plOf).filter(Boolean).map(p=>p.image_form||Object.keys(IMAGE_FORMS).find(f=>IMAGE_FORMS[f].count===p.image_count)))];
  return forms.length===1?forms[0]:'';
}
function channelOptions(){return [...new Set([...PLACEMENTS.map(p=>p.category),'学习机'])]}
function channelForms(channel){return Object.keys(IMAGE_FORMS).filter(form=>PLACEMENTS.some(p=>p.category===channel&&p.image_count===IMAGE_FORMS[form].count))}
function formPlacements(pr){return PLACEMENTS.filter(p=>p.category===pr.channel&&p.image_count===IMAGE_FORMS[imageFormOf(pr)]?.count)}
function defParams(form='单图'){return{channel:'',image_form:form,pids:[],t1:'',t2:'',s1:'',s2:'',s3:'',cta:DEF_CTA,cta_enabled:true,cta_overrides:{},sets:3,ip:'random',style:'random',font:'random',noLogo:false,references:[],...(FORM_DEFAULTS[form]||{})}}
function loadDraft(params){
  const form=imageFormOf(params)||'单图';
  S.draft={...defParams(form),pids:[],product_facts:S.product?.text||'',facts_version:S.product?.revision||0,...structuredClone(params)};
  S.draft.image_form=imageFormOf(params)||(params.image_form!==undefined||params.pids?.length?'':form);
  if(!Object.hasOwn(params,'channel')){const channels=[...new Set(S.draft.pids.map(plOf).filter(Boolean).map(p=>p.category))];S.draft.channel=channels.length===1?channels[0]:''}
  S.visualOpen=visualCustomized(S.draft);S.referenceMode=!!S.draft.references.length;
  S.referencePointsPending={};
  S.formDrafts={};
  S.formError=null;
}
function setImageForm(form){
  if(S.submitting||S.navigationPending||!channelForms(S.draft.channel).includes(form)||form===imageFormOf(S.draft))return;
  S.formDrafts=S.formDrafts||{};
  const previous=imageFormOf(S.draft);
  if(previous)S.formDrafts[previous]=structuredClone(S.draft);
  const shared={};
  for(const k of ['channel','cta','cta_enabled','sets','ip','style','font','noLogo','references','feature_note','image_model','direction','product_facts','facts_version'])if(S.draft[k]!==undefined)shared[k]=structuredClone(S.draft[k]);
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
  if(S.submitting||S.navigationPending)return;
  const forms=channelForms(channel),form=imageFormOf(S.draft);
  S.draft.channel=channel;
  if(forms.length&&!forms.includes(form))setImageForm(forms[0]);
  for(const pr of [S.draft,...Object.values(S.formDrafts||{})]){pr.channel=channel;filterFormPlacements(pr)}
  S.tried=false;save();render();
}
function setCtaOverride(id,mode,text){
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
  if(pr.pids.some(id=>!formPlacements(pr).some(p=>p.id===id)))return{field:'chans',message:'所选版位与当前渠道、形式不一致，请重新选择'};
  for(const [key,label] of IMAGE_FORMS[form].fields)if(!(pr[key]||'').trim())return{field:'f-'+key,message:'请填写'+label};
  if(setsBad(pr))return{field:'f-sets',message:'套数请填写 1–20 的整数'};
  if((pr.cta||'').length>12)return{field:'f-cta',message:'按钮文字最多 12 字'};
  for(const [id,value] of Object.entries(pr.cta_overrides||{}))if(value.mode==='custom'&&(!value.text.trim()||value.text.length>12))return{field:'cta-'+id,message:'版位按钮文字请填写 1–12 字'};
  const refs=pr.references||[];
  if(refs.some(r=>(r.note||'').length>200))return{field:'reference-options',message:'参考图说明最多 200 字'};
  if(refs.some(r=>r.points!==undefined&&(!Array.isArray(r.points)||r.points.length>6||r.points.some(p=>typeof p!=='string'||!p.trim()||[...p].length>16))))return{field:'reference-options',message:'参考图要点最多 6 条，每条 1–16 字'};
  if(new Set(refs.map(r=>r.purpose)).size!==refs.length)return{field:'reference-options',message:'每种用途最多上传 1 张参考图'};
  return null;
}
function formErr(pr){const e=formIssue(pr);return e?e.field==='f-sets'?'sets':e.field==='chans'?'pids':'copy':''}
function visualCustomized(pr){return !!((pr.references||[]).length||pr.ip!=='random'||pr.style!=='random'||pr.noLogo||pr.font&&pr.font!=='random'||pr.feature_note)}
const REFERENCE_PURPOSES={style:'参考风格',composition:'参考排版',ui:'产品界面'};
function viewReferenceOptions(pr){return `<div class="reference-slots" id="reference-options" tabindex="-1">${Object.entries(REFERENCE_PURPOSES).map(([purpose,label])=>{
  const i=(pr.references||[]).findIndex(r=>r.purpose===purpose),r=pr.references?.[i];
  const pending=S.referencePointsPending?.[purpose],extracting=pending?.draft===S.draftId&&pending?.id===r?.id;
  const points=r?`<div class="points-tag-list">${extracting?'<span class="points-pending" role="status">提炼中…</span>':(r.points||[]).map((point,j)=>`<span class="point-tag"><input class="point-tag-text" id="ref-point-${purpose}-${j}" aria-label="${label}要点 ${j+1}" value="${esc(point)}" maxlength="16" size="${Math.max(2,[...point].length*2)}" oninput="setReferencePoint(${i},${j},this.value);this.size=Math.max(2,[...this.value].length*2)"><button type="button" class="point-tag-del" aria-label="删除${label}要点 ${j+1}" onclick="removeReferencePoint(${i},${j})">×</button></span>`).join('')}<button type="button" class="point-add-btn" ${extracting||(r.points||[]).length>=6?'disabled':''} onclick="addReferencePoint(${i})">＋ 添加要点</button></div>`:'';
  return `<section class="reference-slot ${r?'uploaded':''}" data-purpose="${purpose}"><div class="slot-heading"><h4>${label}</h4>${r?`<button ${S.uploadingPurpose?'disabled':''} onclick="removeReference(${i})" aria-label="移除${label}">移除</button>`:''}</div>${r?`<img class="reference-thumb" src="${esc(r.thumbnail_url||r.preview||'')}" alt="${esc(r.name)}">${points}<label class="slot-note">补充说明（选填）<textarea id="ref-note-${purpose}" maxlength="200" rows="2" oninput="setReferenceNote(${i},this.value)">${esc(r.note||'')}</textarea></label>`:`<button class="reference-upload" ${S.uploadingPurpose?'disabled':''} onclick="uploadReference('${purpose}')">${S.uploadingPurpose===purpose?'正在上传…':'＋ 上传图片'}</button>`}</section>`;
}).join('')}</div>`}
function viewVisualOptions(pr){
  const open=S.visualOpen??visualCustomized(pr),reference=!!(pr.references||[]).some(r=>r.purpose==='style'),fonts=typeof FONTS!=='undefined'?FONTS:[];
  const groups=[['标准形象',IPS.filter(a=>a.variant==='standard'||a.id.includes('.standard.'))],['学段与 Q 版',IPS.filter(a=>a.variant!=='standard'&&!a.id.includes('.standard.')&&a.stage!=='teacher'&&!a.id.includes('.teacher.'))],['老师角色',IPS.filter(a=>a.stage==='teacher'||a.id.includes('.teacher.'))]];
  return `<section class="card visual-options" id="visual-options" aria-labelledby="visual-options-title"><div class="section-heading"><h3 id="visual-options-title">画面设定</h3><span class="scene-summary">${visualCustomized(pr)?'已定制':'全部随机'}</span><button aria-expanded="${open}" onclick="S.visualOpen=${!open};render()">${open?'收起':'定制'}</button></div>${open?`
    <div class="scene-mode"><div class="config-segments" role="group" aria-label="画面参考"><button class="${!S.referenceMode?'active':''}" aria-pressed="${!S.referenceMode}" ${S.uploadingPurpose?'disabled':''} onclick="setReferenceMode(false)">随机</button><button class="${S.referenceMode?'active':''}" aria-pressed="${!!S.referenceMode}" ${S.uploadingPurpose?'disabled':''} onclick="setReferenceMode(true)">按参考图</button></div></div>
    ${viewReferenceOptions(pr)}
    <div class="custom-controls"><label>IP<select id="ips" onchange="setF('ip',this.value,1)"><option value="random" ${pr.ip==='random'?'selected':''}>随机 IP</option><option value="none" ${pr.ip==='none'?'selected':''}>不用 IP</option>${groups.map(([label,items])=>`<optgroup label="${label}">${items.map(a=>`<option data-ip="${a.id}" value="${a.id}" ${pr.ip===a.id?'selected':''}>${esc(a.label)}</option>`).join('')}</optgroup>`).join('')}</select></label>
    <label>画风${reference?'<span class="style-locked" role="status">🔒 按参考图</span>':`<select id="styleq" onchange="setF('style',this.value,1)">${['random',...STYLES.map(s=>s.name)].map(name=>`<option value="${esc(name)}" ${pr.style===name?'selected':''}>${name==='random'?'随机画风':esc(name)}</option>`).join('')}</select>`}</label>
    <label>Logo<select id="nologo" onchange="setF('noLogo',this.value==='none',1)"><option value="use" ${!pr.noLogo?'selected':''}>使用 Logo</option><option value="none" ${pr.noLogo?'selected':''}>不用 Logo</option></select></label>
    <label>标题字体<select id="f-font" onchange="setF('font',this.value,1)">${[['random','随机字体参考'],['none','不用字体参考'],...fonts.map(a=>[a.id,a.label])].map(([id,label])=>`<option value="${id}" ${(pr.font||'random')===id?'selected':''}>${esc(label)}</option>`).join('')}</select></label></div>
    <label class="scene-note" for="f-feature">补充要求（选填）<textarea id="f-feature" maxlength="200" rows="2" oninput="setF('feature_note',this.value)">${esc(pr.feature_note||'')}</textarea></label>
    <details class="product-preview"><summary>产品资料 · 已引用 v${esc(pr.facts_version??0)}</summary><div class="row"><button onclick="openCfg()">维护资料</button><button onclick="useLatestProduct()">引用最新资料</button></div><pre>${esc(pr.product_facts||'未提供产品资料，仅依据已确认文案。')}</pre></details>
    ${S.tried&&formIssue(pr)?.field==='reference-options'?`<div class="errtx">${esc(formIssue(pr).message)}</div>`:''}`:''}</section>`;
}
function placementCtaText(pr,id){
  const value=pr.cta_overrides?.[id]||{mode:'inherit'};
  return value.mode==='custom'?value.text:value.mode==='none'||pr.cta_enabled===false?'':pr.cta||'';
}
function placementCta(pr,p){
  const value=pr.cta_overrides?.[p.id]||{mode:'inherit'},selected=pr.pids.includes(p.id),label=pname(p)+'按钮文字',text=placementCtaText(pr,p.id);
  return `<div class="placement-cta mode-${value.mode} ${text?'':'no-button'}">${value.mode==='custom'?`<span class="cta-custom-dot" aria-hidden="true">•</span><input id="cta-${p.id}" aria-label="${esc(label)}" maxlength="12" value="${esc(value.text||'')}" ${!selected?'disabled':''} oninput="setCtaOverride('${p.id}','custom',this.value)">`:`<span class="placement-cta-label" data-cta-label="${p.id}">${esc(text||'无按钮')}</span>`}<select aria-label="${esc(label)}模式" ${!selected?'disabled':''} onchange="setCtaOverride('${p.id}',this.value)">${[['inherit','跟随统一'],['custom','自定义'],['none','无按钮']].map(([mode,label])=>`<option value="${mode}" ${mode===value.mode?'selected':''}>${mode===value.mode?'✓ ':''}${label}</option>`).join('')}</select></div>`;
}
function summaryFormula(pr){
  if(!pr.channel)return '';
  const mixed=pr.variants_by_placement&&new Set(pr.pids.map(id=>pr.variants_by_placement[id]??+pr.sets)).size>1;
  return mixed?`${pr.pids.length} 版位 × 分别设置套数`:`${pr.pids.length} 版位 × ${esc(pr.sets)} 套${IMAGE_FORMS[imageFormOf(pr)]?.count>1?' × '+IMAGE_FORMS[imageFormOf(pr)].count+' 张':''}`;
}
function viewForm(){
  const pr=S.draft,form=imageFormOf(pr),definition=IMAGE_FORMS[form],placements=formPlacements(pr),grp={},forms=channelForms(pr.channel),blocked=S.submitting||S.navigationPending,unavailable=!forms.length;
  placements.forEach(p=>{(grp[p.platform]=grp[p.platform]||[]).push(p)});
  const issue=S.tried?formIssue(pr):null;
  const fi=(key,label)=>`<label class="copy-field" for="f-${key}"><span>${label}</span><input id="f-${key}" data-k="${key}" aria-label="${esc(label)}" required aria-required="true" aria-invalid="${issue?.field==='f-'+key}" value="${esc(pr[key]||'')}" class="${issue?.field==='f-'+key?'bad':''}" oninput="setF('${key}',this.value)">${issue?.field==='f-'+key?`<span class="errtx">${esc(issue.message)}</span>`:''}</label>`;
  return `<div class="form config-form"><fieldset class="form-fields config-main" ${blocked?'disabled':''}>
    <section class="card compose-card"><div class="channel-row"><h3 id="channel-label">渠道</h3><div id="channel" class="config-segments" role="radiogroup" aria-labelledby="channel-label" tabindex="-1">${channelOptions().map(channel=>`<button role="radio" aria-checked="${pr.channel===channel}" class="${pr.channel===channel?'active':''}" onclick="setChannel('${channel}')">${esc(channel)}</button>`).join('')}</div>${issue?.field==='channel'?`<span class="errtx">${esc(issue.message)}</span>`:''}</div>
    <fieldset class="channel-dependent" ${unavailable?'disabled':''}>
    ${forms.length>1?`<div class="format-row"><h3 id="image-form-label">形式</h3><div class="config-segments" role="radiogroup" aria-labelledby="image-form-label" id="image-form">${forms.map(f=>`<button role="radio" aria-checked="${f===form}" class="${f===form?'active':''}" onclick="setImageForm('${f}')">${f}</button>`).join('')}</div></div>`:''}
    <div class="config-copy"><div class="copy-lines">${(definition?.fields||[]).map(([k,label])=>fi(k,label)).join('')}</div><div class="default-cta"><label for="f-cta">默认按钮文字</label><input id="f-cta" maxlength="12" value="${esc(pr.cta||'')}" oninput="setF('cta',this.value)"><label class="inline-check"><input id="cta-enabled" type="checkbox" ${pr.cta_enabled!==false?'checked':''} onchange="setF('cta_enabled',this.checked)">默认加按钮</label>${issue?.field==='f-cta'?`<span class="errtx">${esc(issue.message)}</span>`:''}</div></div>
    </fieldset></section>
    <fieldset class="channel-dependent" ${unavailable?'disabled':''}>
    <section class="card placements-card"><div class="section-heading"><h3>版位</h3>${pr.channel?`<span class="placement-count">${esc(pr.channel)} · ${form}（已选 ${pr.pids.length}/${placements.length}）</span>`:''}</div><div id="chans" tabindex="-1" class="platform-groups">${Object.entries(grp).sort(([,a],[,b])=>(a.length>2)-(b.length>2)).map(([platform,list])=>`<section class="platform-group ${list.length>2?'span-two':''}"><h4>${esc(platform)}</h4><div class="platform-items ${list.length>2?'two-columns':''}">${list.map(p=>`<div class="placement-row ${pr.pids.includes(p.id)?'checked':''}" data-pid="${p.id}"><label class="placement-check"><input type="checkbox" aria-label="${esc(pname(p))} ${psz(p)}" ${pr.pids.includes(p.id)?'checked':''} onchange="togP('${p.id}')"><span>${esc(p.name.replace(/\s*\d+×\d+/,''))}</span></label><span class="placement-size">${psz(p)}${p.logo_policy==='required'?`<span class="logo-lock ${pr.noLogo?'force-highlight':''}">🔒 Logo</span>`:''}</span>${placementCta(pr,p)}</div>`).join('')}</div></section>`).join('')}</div>${issue?.field==='chans'?`<div class="errtx">${esc(issue.message)}</div>`:''}${issue?.field.startsWith('cta-')?`<div class="errtx">${esc(issue.message)}</div>`:''}</section>
    ${viewVisualOptions(pr)}</fieldset>${pr.channel&&!forms.length?'<div class="channel-empty" role="status">该渠道暂无版位</div>':''}
    </fieldset><fieldset class="card sum config-summary channel-dependent" id="sum" ${blocked||unavailable?'disabled':''}><label for="f-sets">每版位套数</label><div class="sets-stepper"><button aria-label="减少套数" onclick="stepSets(-1)">−</button><input id="f-sets" type="number" min="${SETS_MIN}" max="${SETS_MAX}" value="${pr.variants_by_placement&&new Set(Object.values(pr.variants_by_placement)).size>1?'':esc(pr.sets)}" placeholder="分别设置" class="${setsBad(pr)?'bad':''}" oninput="setSets(this.value)"><button aria-label="增加套数" onclick="stepSets(1)">＋</button></div>${issue?.field==='f-sets'?`<span class="errtx">${esc(issue.message)}</span>`:''}
    <label for="image-model">图片模型</label><select id="image-model" onchange="setF('image_model',this.value)">${imageModelOptions(pr.image_model||(typeof CFG!=='undefined'&&CFG.imageModel)||IMAGE_MODEL_OPTIONS[0][0])}</select>
    <div class="total-action"><div class="tot" id="tot" aria-live="polite">共 ${pr.channel?totalOf(pr):0} 张</div><p id="sum-formula">${summaryFormula(pr)}</p><button class="primary" id="go" ${setsBad(pr)||blocked||unavailable||!pr.pids.length||S.uploadingPurpose?'disabled':''} onclick="startGen()">${S.submitting?'正在提交…':'开始生成'}</button>${S.submitting?'<span class="field-help" role="status">正在提交配置，请稍候</span>':''}</div></fieldset></div>`;
}
function need(k){return (IMAGE_FORMS[imageFormOf(S.draft)]?.fields||[]).some(([f])=>f===k)}

function cellHtml(r,s){
 const p=plOf(s.pid),frame=s.reason_code==='frame_failed'||s.state==='done'&&s.delivery_eligible===false;
 const failed=isFail(r,s)||s.state==='stopped',waiting=s.state==='waiting_first'||s.state==='queued'&&s.idx>1&&r.slots.find(slot=>slot.id===s.first_id)?.state!=='done';
 const label=frame?'需去框':failed?'生成失败':s.state==='done'?'':waiting?'等图 1':r.paused?'已暂停后续':'生成中';
 let content='',actions='';
 if(s.state==='done')content=`<img alt="${esc(pname(p))} 第 ${s.set} 套 图 ${s.idx}" src="${imgOf(s)}">${frame?'<span class="frame-note">需去框</span>':''}`;
 else content=`<span class="vlab">${label}</span>`;
 if(frame)actions=`<div class="sample-actions"><button ${S.localProcessing?'disabled':''} onclick="reprocessFrame('${s.id}')">重新去框</button><button ${S.localProcessing?'disabled':''} onclick="fitImage('${s.id}')">整图适配</button></div>`;
 else if(failed){const retry=imageRetry(r,s),planning=s.reason_code==='planning_failed';actions=`<div class="sample-actions"><button data-redo="${s.id}" ${retry.disabled?'disabled':''} onclick="${planning?'retryPlanning()':retry.blocked?"openPv('"+retry.head?.id+"')":retry.query?"resumeImage('"+s.id+"')":"repairSet('"+s.pid+"',"+s.set+")"}">${planning?'重试规划':retry.blocked?'查看图 1':retry.query?'恢复查询':'补齐'}</button></div>`}
 return`<div class="sample-unit"><div class="cell ${frame?'frame-pending':failed?'fail':s.state==='done'?'done':waiting?'wait':'gen'}" style="aspect-ratio:${p.target_width}/${p.target_height};--image-ratio:${p.target_width/p.target_height}" data-slot="${s.id}" data-st="${s.state}" title="${esc(failed?failMsg(r,s):s.state==='done'?'已完成':waitLabel(r,s))}" ${s.state==='done'?`role="button" tabindex="0" aria-label="套 ${s.set} · ${esc(pname(p))} 图 ${s.idx}，查看大图" onclick="openPv('${s.id}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openPv('${s.id}')}"`:`role="img" aria-label="${label}"`}>${content}</div>${actions}${p.image_count>1?`<div class="sample-caption">图 ${s.idx}</div>`:''}</div>`;
}
function imageRetry(r,s){
 const head=r.slots.find(x=>x.id===s.first_id),query=!!s.query_required||['unknown','timeout'].includes(s.reason_code),blockedFirst=blocked(r,s)||s.state==='blocked_first_failed';
 const group=s.idx===1?r.slots.filter(x=>x.pid===s.pid&&x.set===s.set):[s];
 const busy=group.some(x=>['queued','generating'].includes(x.state));
 return {query,blocked:blockedFirst,head,disabled:busy&&!blockedFirst,
 label:query?'恢复查询':blockedFirst?'查看图 1':s.idx===1&&plOf(s.pid).image_count>1?'重出图 1 及后续图':'重出本张',
 note:query?'本次查询等待已结束，供应商任务可能仍在运行。恢复查询沿用原任务号，不重新提交生图。':blockedFirst?'本张依赖图 1，请先处理图 1。':s.idx===1&&plOf(s.pid).image_count>1?'重出图 1 后，本套后续图会退出当前结果，等待新图 1 完成后重新生成；历史文件保留。':s.idx>1?'仅重出本张，继续引用本套当前图 1；其他图片保留。':'仅重出当前图片。'};
}
function refsOf(r,s){return(s.reference_images||[]).map((x,i)=>({k:i,name:(x.label||'参考图'+(i+1))+' · '+x.name+(x.retired?' · 历史参考已停用':''),src:x.thumbnail_url,bad:x.upload_status==='failed'}))}
function viewPv(){const r=R();const s=curPvSlot();if(!s)return`<div class="mask" id="m-preview"><div class="pv" role="dialog" aria-modal="true" aria-label="正在加载预览" id="pv"><div class="l"><p class="fbig" role="status">正在读取图片…</p></div><div class="r"><div class="pv-panel-top"><div class="pvtitle">大图预览</div><button class="x" id="pvx" onclick="closePv()" aria-label="关闭">×</button></div></div></div></div>`;const retry=imageRetry(r,s);const p=plOf(s.pid),f=isFail(r,s),on=!!r.sel[selectionKey(s.pid,s.set)];
 const slots=r.slots.filter(x=>x.pid===s.pid).sort((a,b)=>a.set-b.set||a.idx-b.idx),index=slots.findIndex(x=>x.id===s.id),frame=['frame_review','frame_failed'].includes(s.reason_code);
 return`<div class="mask" id="m-preview" onclick="if(event.target===this)closePv()"><div class="pv" role="dialog" aria-modal="true" aria-label="大图预览" id="pv"><div class="l">
 <button class="pv-nav" id="pvprev" aria-label="上一张" ${index>0?`onclick="openPv('${slots[index-1].id}')"`:'disabled'}>←</button><div class="pv-center"><div class="pv-image-frame">${s.files_cleared?'<div class="fbig">文件已清理</div>':s.state==="done"&&S.pvCompare&&s.history?.filter(v=>v.image_url).length>1?`<div class="compare-images">${s.history.filter(v=>v.image_url).slice(-2).map(v=>`<figure><img src="${v.image_url}" alt="图片第${v.att}版"><figcaption>图片第${v.att}版</figcaption></figure>`).join('')}</div>`:s.state==="done"?`<img id="pvImg" alt="第 ${s.set} 套 · ${esc(pname(p))} · 图 ${s.idx}" src="${S.pvOriginal?s.original_image_url:imgOf(s)}">`:`<div class="fbig">${VLAB[f?"failed":s.state]}</div>`}</div><div class="pv-counter" id="pvCounter">${index+1} / ${slots.length}</div></div><button class="pv-nav" id="pvnext" aria-label="下一张" ${index<slots.length-1?`onclick="openPv('${slots[index+1].id}')"`:'disabled'}>→</button></div><div class="r">
 <div class="pv-panel-top"><div class="pvtitle" id="pvTitle">第 ${s.set} 套 · ${esc(pname(p))} <span>${psz(p)}</span>${p.image_count>1?`<small>图 ${s.idx}</small>`:''}</div><button class="x" id="pvx" onclick="closePv()" aria-label="关闭">×</button></div>
 ${f||frame?`<div class="pvwhy ${frame?'frame-review':''}" id="pvwhy">${frame?'需去框':esc(s.msg||failMsg(r,s))}${s.preview_kind==='raw'&&s.has_frame&&!s.is_historical?`<div class="local-options"><button id="pvcrop" onclick="reprocessFrame('${s.id}')">重新去框</button><button id="pvfit" onclick="fitImage('${s.id}')">整图适配</button></div>`:''}</div>`:''}
 <div class="acts" id="pvRetryScope"><button class="pv-select ${on?'checked':''}" id="pvsel" aria-pressed="${on}" ${!s.is_historical&&(s.state==="done"||r.slots.some(x=>x.set===s.set&&x.state==="done"))?"":"disabled"} onclick="toggleSel(${s.set},true,'${s.pid}')"><span class="pv-check" aria-hidden="true">✓</span>选这一套</button><button id="pvredo" ${retry.disabled||s.is_historical||S.previewStale?"disabled":""} onclick="pvRedo()">${esc(retry.label)}</button></div>
 <details class="pv-advanced" ${S.pvAdvanced?'open':''} ontoggle="S.pvAdvanced=this.open"><summary>高级</summary><div class="pv-advanced-stack">
 <div><div class="pv-prompt-heading"><h4><label for="pvPrompt">提示词</label></h4><button class="lnk" id="pvReset" style="${!s.is_historical&&s.prompt!==s.orig?"":"display:none"}" onclick="pvResetP()">恢复原提示词</button></div>${s.is_historical?'<small class="muted">历史版本只读</small>':''}${!s.is_historical&&s.edit_drafts?.length>1?`<label>已保存的编辑草稿 <select onchange="choosePromptDraft(this.value)"><option value="">选择草稿</option>${s.edit_drafts.map((d,i)=>`<option value="${esc(d.editor_id)}">草稿${i+1} · ${new Date(d.updated_at*1000).toLocaleString('zh-CN')} · ${esc(d.text.slice(0,12))}</option>`).join('')}</select></label>`:''}<div class="row"><small id="prompt-draft-status" role="status">${esc(S.promptStatus||'当前图片的实际提示词')}</small>${!s.is_historical?'<button class="lnk" onclick="discardPromptDraft()">放弃草稿</button>':''}</div><textarea class="prompt" id="pvPrompt" ${s.is_historical?'readonly':''} oninput="pvChk()">${esc(S.promptDraft?.id===s.id?S.promptDraft.value:s.prompt)}</textarea></div>
 <div><h4>参考图</h4><div class="refs" id="pvRefs">${refsOf(r,s).map(x=>`<div class="ref ${x.bad?"bad":""}" data-ref="${x.k}"><div style="${x.src?`background-image:url(${x.src})`:""}"></div><span>${x.bad?"未上传":esc(x.name)}</span></div>`).join("")}</div></div>
 <div><h4><label for="imageVersion">图片版本</label></h4><select id="imageVersion" onchange="openPv('${s.id}',+this.value)">${(s.history||[]).slice().reverse().map(v=>`<option value="${v.att}" ${v.att===s.att?'selected':''}>图片第${v.att}版${v.att===(s.history||[]).at(-1)?.att?' · 当前':v.files_cleared?' · 文件已清理':' · 历史'}</option>`).join('')}</select></div>${s.history?.filter(v=>v.image_url).length>1?`<button aria-pressed="${!!S.pvCompare}" onclick="comparePrevious()">对比最近两版</button>`:''}
 ${s.state==='done'?`<div class="row pv-source"><span id="pvkind" class="muted">${s.preview_kind==='raw'?'待处理原图':S.pvOriginal?'生成原图':'成品预览'}</span>${s.preview_kind!=='raw'&&s.original_image_url?`<button class="lnk" id="pvsource" onclick="togglePvOriginal()">${S.pvOriginal?'查看成品':'查看原图'}</button>`:''}</div>`:''}
 <button ${s.files_cleared?'disabled':''} onclick="pinImageVersion()">${s.pinned?'取消保留此版本':'保留此版本'}</button>
 </div></details></div></div></div>`}
function viewCfg(){return`<div class="mask" id="m-settings" onclick="if(event.target===this)closeCfg()"><div class="dlg" role="dialog" aria-modal="true" aria-label="设置" id="cfgdlg"><button class="x" onclick="closeCfg()" aria-label="关闭">×</button><h2>设置</h2>
 <section data-grp="planning"><h5 style="margin-top:0">画面规划</h5>
 <div class="field"><label for="planmodel">语言模型</label><input id="planmodel" maxlength="128" value="${esc(CFG.planningModel||'')}" autocomplete="off"></div>
 <div class="field"><label for="plankey">规划 Key</label><div><div class="row"><input type="password" id="plankey" autocomplete="off" placeholder="${CFG.planningKey?'已配置，留空保留':''}" value=""><button style="flex:none" id="plantest" onclick="testPlanning()">测试连接</button></div><div id="planst" role="status"></div></div></div>
 <div class="field"><label for="planbase">接口地址</label><input id="planbase" value="${esc(CFG.planningBase||'')}" autocomplete="off"></div>
 </section>
 <section data-grp="img"><h5>图片生成</h5>
 <div class="field"><label for="cfgimagemodel">默认模型</label><select id="cfgimagemodel">${imageModelOptions(CFG.imageModel)}</select></div>
 <div class="field"><label for="kiekey">KIE Key</label><div><div class="row"><input type="password" id="kiekey" autocomplete="off" placeholder="${CFG.kie?'已配置，留空保留':''}" value="" oninput="imageKeyEntered()"><button style="flex:none" id="kietest" onclick="testConn()">测试连接</button></div><div id="kiest">${connTx("kie")}</div></div></div>
 <div class="field"><label for="cfgimagemode">图片输出</label><select id="cfgimagemode"><option value="real" ${!CFG.simulation?'selected':''}>真实生图</option><option value="simulation" ${CFG.simulation?'selected':''}>模拟预览</option></select></div>
 <details id="adv"><summary>高级</summary><div class="field"><label for="kbase">KIE_BASE_URL</label><input id="kbase" value="${esc(CFG.base)}"></div><div class="field"><label for="kup" style="font-size:12px">KIE_UPLOAD_BASE_URL</label><input id="kup" value="${esc(CFG.up)}"></div></details></section>
<section><h5>数据维护</h5><button onclick="openMaintenance()">备份、恢复与清理旧版本</button></section><section data-grp="product"><h5>产品资料</h5><textarea id="product-facts" rows="5" maxlength="20000" placeholder="填写已确认的目标人群、产品功能和可用界面文字">${esc(S.product?.text||'')}</textarea></section> <section data-grp="gen"><h5>通用</h5><div class="field"><span class="lab">候选与暂存占用</span><div class="stor" id="stor">${storHtml()}</div></div>
 <div class="field"><label for="cfgpath">保存位置</label><div class="row"><input id="cfgpath" value="${esc(CFG.path)}"><button style="flex:none" onclick="chooseFolder()">选择…</button></div></div></section>
 <div class="foot"><button onclick="closeCfg()">取消</button><button class="primary" id="cfgsave" onclick="saveCfg()">保存</button></div></div></div>`}

function softRender(){if(!S.pv&&!S.cfgOpen&&!S.maintenanceOpen)return render();const a=document.querySelector("#app>.app");if(!a)return render();const m=$("main"),y=m?m.scrollTop:0,ae=document.activeElement,inApp=a.contains(ae),fref=inApp?trapRef(ae):null;
 const stage=$('.sample-stage'),stageTop=stage?.scrollTop||0,setsLeft=$('#sets')?.scrollLeft||0,directoryTop=$('.dir-list')?.scrollTop||0;
 const body=S.view==="form"?viewForm():S.view==="pick"?viewPick():viewDl();const d=document.createElement("div");d.innerHTML=`<div class="app ${S.view==='pick'?'pick-mode':''}">${viewSide()}<main id="main">${viewHead()}<div class="body" id="body">${body}</div>${S.view!=='form'?viewSelectionFooter():''}</main></div>`;const tl=$(".sidebar-scroll")||$(".tasks"),ty=tl?tl.scrollTop:0;a.replaceWith(d.firstElementChild);const tl2=$(".sidebar-scroll")||$(".tasks");if(tl2)tl2.scrollTop=ty;const m2=$("main");if(m2){m2.scrollTop=y;setHH()}if(fref){const e=document.querySelector(fref);if(e)e.focus({preventScroll:true})}updTimers();syncSelectionControls();
 const updatedStage=$('.sample-stage');if(updatedStage){updatedStage.scrollTop=stageTop;$('#sets').scrollLeft=setsLeft;$('.dir-list').scrollTop=directoryTop}
}
function setHH(){
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
  if(scroll||imageHeight>best.imageHeight)best={columns:cols,cardWidth,cardHeight:imageHeight+overhead,imageHeight,scroll};
 }
 sets.dataset.scroll=String(best.scroll);sets.style.setProperty('--sample-columns',best.columns);sets.style.setProperty('--sample-card-width',best.cardWidth+'px');
 sets.style.setProperty('--sample-card-height',best.cardHeight+'px');sets.style.setProperty('--sample-image-width',best.imageHeight*ratio+'px');
}
function render(){const ae=document.activeElement,fk=ae&&ae.id,fref=ae&&ae!==document.body?trapRef(ae):null,ss=ae&&(ae.selectionStart||(ae.value&&ae.matches&&ae.matches('input[type=search],#styleq')?ae.value.length:ae.selectionStart)),m=$("main"),y=m?m.scrollTop:0;
 const stage=$('.sample-stage'),stageTop=stage?.scrollTop||0,setsLeft=$('#sets')?.scrollLeft||0,directoryTop=$('.dir-list')?.scrollTop||0;
 const body=S.view==="form"?viewForm():S.view==="pick"?viewPick():viewDl();
 const tl=$(".sidebar-scroll")||$(".tasks"),ty=tl?tl.scrollTop:0;window._rnd=true;
$("#app").innerHTML=`<div class="app ${S.view==='pick'?'pick-mode':''}">${viewSide()}<main id="main">${viewHead()}<div class="body" id="body">${body}</div>${S.view!=='form'?viewSelectionFooter():''}</main></div>${S.pv?viewPv():""}${S.cfgOpen?viewCfg():""}${S.maintenanceOpen?viewMaintenance():""}`;
 window._rnd=false;const tl2=$(".sidebar-scroll")||$(".tasks");if(tl2)tl2.scrollTop=ty;
 const m2=$("main");if(m2){m2.scrollTop=y;setHH()}
 const updatedStage=$('.sample-stage');if(updatedStage){updatedStage.scrollTop=stageTop;$('#sets').scrollLeft=setsLeft;$('.dir-list').scrollTop=directoryTop}
 if(!fk&&fref){const e=document.querySelector(fref);if(e&&!(S.pv||S.cfgOpen))e.focus({preventScroll:true})}if(fk){const e=document.getElementById(fk);if(e&&!e.closest(".mask")||e&&(S.pv||S.cfgOpen)){e.focus({preventScroll:true});try{if(ss!=null&&e.setSelectionRange)e.setSelectionRange(ss,ss)}catch(_){}}}updTimers();syncSelectionControls()}

/* ===== 配置动作 ===== */
function togP(id){if(S.submitting||S.navigationPending||!formPlacements(S.draft).some(p=>p.id===id))return;const a=S.draft.pids;S.draft.pids=a.includes(id)?a.filter(x=>x!==id):[...a,id];filterFormPlacements(S.draft);save();render()}
function setF(k,v,re){if(S.submitting||S.navigationPending)return;S.draft[k]=v;save();if(re)render();else updSum()}
function setSets(v){if(S.submitting||S.navigationPending)return;delete S.draft.variants_by_placement;S.draft.sets=v;save();updSum()}
function stepSets(delta){setSets(Math.max(SETS_MIN,Math.min(SETS_MAX,(+S.draft.sets||SETS_MIN)+delta)));render()}
function updSum(){const pr=S.draft;const e=$("#tot");if(e)e.textContent="共 "+(pr.channel?totalOf(pr):0)+" 张";const i=$("#f-sets");if(i){i.classList.toggle("bad",setsBad(pr));if(document.activeElement!==i)i.value=pr.sets}document.querySelectorAll('[data-cta-label]').forEach(label=>{const text=placementCtaText(pr,label.dataset.ctaLabel);label.textContent=text||'无按钮';label.parentElement.classList.toggle('no-button',!text)});const formula=$("#sum-formula");if(formula)formula.innerHTML=summaryFormula(pr);const g=$("#go");if(g)g.disabled=setsBad(pr)||!pr.channel||!pr.pids.length||!!S.submitting||!!S.navigationPending||!!S.uploadingPurpose}

function setTab(c){S.tab=c;S.miss=false;save();render()}
async function setRound(i){const epoch=beginNavigation();if(epoch===null)return;try{await persistPromptDraft();if(epoch!==viewEpoch)return;const t=await request('/tasks/'+S.cur+'?view=1&round='+i);if(epoch!==viewEpoch)return;installTask(t);T().ri=i;save(false);render()}finally{finishNavigation(epoch)}}

function trapRef(e){if(!e||e===document.body)return null;return e.id?"#"+e.id:e.dataset?.sel?`[data-sel="${e.dataset.sel}"]`:e.dataset?.pickPlacement?`[data-pick-placement="${e.dataset.pickPlacement}"]`:e.dataset&&e.dataset.slot?`[data-slot="${e.dataset.slot}"]`:e.closest&&e.closest("[data-slot]")?`[data-slot="${e.closest("[data-slot]").dataset.slot}"]`:null}


function curPvSlot(){return S.pvDetails?.id===S.pv?S.pvDetails:null}



function cfgRef(e){if(!e||e===document.body)return"#cfgbtn";return e.id?"#"+e.id:"#cfgbtn"}

function cfgBack(){const e=document.querySelector(window._cfgFrom||"#cfgbtn")||$("#cfgbtn");window._cfgFrom=null;if(e)e.focus({preventScroll:true})}
function closeCfg(){S.cfgOpen=false;render();cfgBack()}

/* 键盘:Esc 关闭最上层弹窗;弹窗内锁焦点 */
document.addEventListener("keydown",e=>{
 if(S.view==='pick'&&!S.cfgOpen&&!S.pv&&!S.navigationPending&&['ArrowDown','ArrowUp'].includes(e.key)&&!e.target.closest('input,textarea,select,[contenteditable]')){
  e.preventDefault();const r=R(),next=r.params.pids[r.params.pids.indexOf(pickPlacement(r))+(e.key==='ArrowDown'?1:-1)];if(next)setPickPlacement(next);return;
 }
 const m=S.cfgOpen?$("#cfgdlg"):S.pv?$("#pv"):null;if(!m)return;
 if(e.key==="Escape"){e.preventDefault();S.cfgOpen?closeCfg():closePv();return}
 if(!S.cfgOpen&&(e.key==="ArrowLeft"||e.key==="ArrowRight")&&!e.target.closest('input,textarea,select,[contenteditable]')){e.preventDefault();$(e.key==="ArrowLeft"?'#pvprev':'#pvnext')?.click();return}
 if(e.key==="Tab"){const f=[...m.querySelectorAll("input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,button:not([disabled])")].filter(x=>x.offsetParent!==null);if(!f.length)return;const a=f[0],z=f[f.length-1];if(!m.contains(document.activeElement)){e.preventDefault();(e.shiftKey?z:a).focus()}else if(e.shiftKey&&document.activeElement===a){e.preventDefault();z.focus()}else if(!e.shiftKey&&document.activeElement===z){e.preventDefault();a.focus()}}});
document.addEventListener("click",e=>{if(S.miss&&!e.target.closest("#miss")){S.miss=false;render()}});

function selectionKey(pid,n){return pid+'::'+n}
function setsOf(r){
  const groups=new Map();
  r.slots.forEach(s=>{const id=selectionKey(s.pid,s.set);if(!groups.has(id))groups.set(id,{id,n:s.set,pid:s.pid,sl:[]});groups.get(id).sl.push(s)});
  return [...groups.values()];
}
function selectedSet(r,g){return !!r.sel[g.id]}
function attentionSet(r,g){return g.sl.some(s=>isFail(r,s)||s.state==='stopped'||s.reason_code==='frame_failed')}
function readySet(g){return g.sl.length===plOf(g.pid).image_count&&g.sl.every(s=>s.state==='done'&&s.delivery_eligible!==false&&s.reason_code!=='frame_failed')}
function pickPlacement(r){
 const key=S.cur+':'+r.id;
 if(S.pickRound!==key||!r.params.pids.includes(S.pickPid)){S.pickRound=key;S.pickPid=r.params.pids[0]}
 return S.pickPid;
}
function groupMatchesFilter(r,g,pf){
  return pf==='yes'?selectedSet(r,g):pf==='no'?!selectedSet(r,g):pf==='bad'?attentionSet(r,g):true;
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
  const r=R();if(!r)return'';
  const groups=setsOf(r),pid=pickPlacement(r),p=plOf(pid),visible=groups.filter(g=>g.pid===pid).sort((first,second)=>first.n-second.n);
  const directory=r.params.pids.map(id=>{
    const placement=plOf(id),sets=groups.filter(g=>g.pid===id),slots=sets.flatMap(g=>g.sl),done=slots.filter(s=>s.state==='done').length;
    const completed=sets.filter(g=>g.sl.length===placement.image_count&&g.sl.every(s=>s.state==='done')).length;
    const selected=sets.filter(g=>selectedSet(r,g)).length,problems=sets.filter(g=>attentionSet(r,g)||g.sl.some(s=>s.delivery_eligible===false)).length;
    const running=slots.some(s=>['queued','generating','waiting_first'].includes(s.state));
    const progress=running?`<span class="dir-gen-progress">${done}/${slots.length}<span class="mini-progress-track" role="progressbar" aria-label="${esc(pname(placement))}生成进度" aria-valuemin="0" aria-valuemax="${slots.length}" aria-valuenow="${done}"><i style="width:${done/Math.max(1,slots.length)*100}%"></i></span></span>`:'';
    return`<button class="dir-item ${id===pid?'active':''}" data-pick-placement="${id}" aria-current="${id===pid?'true':'false'}" onclick="setPickPlacement('${id}')"><span class="dir-item-name">${esc(pname(placement))}</span><span class="dir-item-size">${psz(placement)}</span><span class="dir-status-cols">${progress}${!running||completed>0?`<span class="${selected?'badge-selected':'badge-unselected-ready'}">已选 ${selected}/${completed}</span>`:''}${problems?`<span class="dir-problem-text">· ${problems} 问题</span>`:''}</span></button>`;
  }).join('');
  const bulk=bulkSelectionState(r);
  const selectionBar=`<div class="selection-bar"><label class="select-all"><input id="select-visible" type="checkbox" aria-label="全选当前版位" aria-checked="${bulk.mixed?'mixed':bulk.all?'true':'false'}" ${bulk.all?'checked':''} ${!bulk.scope.length||S.selectionBusy?'disabled':''} onchange="selectVisible(this.checked)"><span>全选当前版位</span></label><button class="ghost" id="clear-visible" ${!bulk.selected||S.selectionBusy?'disabled':''} onclick="clearVisibleSelection()">取消选择</button></div>`;
  const legacy=r.planning_source==='simulation'?`<div class="planning-notice"><span>历史模拟结果，尚未使用新的画面规划</span><button onclick="dupTask()">复制并重新规划</button></div>`:'';
  const planError=r.planning_status==='failed'?`<div class="planning-error" role="alert"><span>${esc(r.planning_error||'画面规划未完成')}</span><button onclick="retryPlanning()">重试规划</button></div>`:'';
  const cards=visible.map(g=>{
    const on=selectedSet(r,g),ready=readySet(g),problem=attentionSet(r,g)||g.sl.some(s=>s.delivery_eligible===false);
    return`<section class="set ${on?'chosen':''} ${problem?'has-problem':''}" data-set="${g.n}" data-placement="${g.pid}" aria-label="${esc(pname(p))} · 套 ${g.n}" onclick="pickCardClick(event,${g.n},'${g.pid}')"><div class="sethead"><b>第 ${g.n} 套</b><label class="set-check" title="${on?'取消选择':'选择这一套'}"><input type="checkbox" data-sel="${g.id}" aria-label="选择 ${esc(pname(p))} 套 ${g.n}" ${on?'checked':''} ${!ready&&!on||S.selectionBusy?'disabled':''} onchange="toggleSel(${g.n},false,'${g.pid}')"><span aria-hidden="true">✓</span></label></div><div class="sample-row" style="--images:${p.image_count}">${[...g.sl].sort((first,second)=>first.idx-second.idx).map(s=>cellHtml(r,s)).join('')}</div></section>`;
  }).join('');
  const next=r.params.pids[r.params.pids.indexOf(pid)+1];
  return`<div class="pick-workbench"><nav class="placement-dir" aria-label="本轮版位目录"><div class="dir-list">${directory}</div></nav><section class="sample-stage"><div class="placement-head"><h2>${esc(pname(p))} <span>${psz(p)}</span></h2><div><button ${['queued','running'].includes(r.planning_status)||visible.length>=20?'disabled':''} onclick="addVariant('${pid}')">＋ 再出一套</button><button id="next-placement" ${next?'':'disabled'} onclick="setPickPlacement('${next||pid}')">下一版位 →</button></div></div>${legacy}${planError}${selectionBar}<div class="suite-grid" id="sets" style="--images:${p.image_count};--image-ratio:${p.target_width/p.target_height}">${cards||'<div class="tnone">暂无套图</div>'}</div></section></div>`;
}
function viewSelectionFooter(){
  const r=R();if(!r)return'';const d=r.delivery||{};
  const partial=d.incomplete_sets>0,saved=d.has_changes===false&&d.matching_version;
  const saveButton=`<button id="${partial?'save-ready':'save-selected'}" class="primary" ${saved||!d.ready_sets||!(d.can_export_ready||d.can_export)||S.exportBusy?'disabled':''} onclick="dlAll(${partial})">${S.exportBusy?'正在保存…':saved?'已保存 '+esc(d.matching_version):'保存已合格的 '+(d.ready_sets||0)+' 套'}</button>`;
  return`<footer class="selection-footer"><div><span class="save-facts">已选 <b>${d.selected_sets||0}</b> 套 · ${d.covered_placements||0}/${d.total_placements||r.params.pids.length} 个版位</span>${partial?`<button class="lnk" onclick="locateIncomplete()" title="另 ${d.incomplete_sets} 套待处理，不纳入本次图包">${d.incomplete_sets} 套待处理</button>`:''}${d.last_version?`<button class="lnk" onclick="openFolder()">已保存 ${esc(d.last_version)}${d.has_changes?' · 勾选有变化，需重新保存':''} · 打开文件夹</button>`:''}</div>${saveButton}</footer>`;
}

function viewDl(){
  const t=T();if(!t)return'';
  return`<div class="history-head"><h3>交付记录</h3><button onclick="go('pick')">返回挑选</button></div>${[...t.pkgs].reverse().map(p=>`<div class="card delivery-record"><div class="pkrow"><b>v${String(p.v).padStart(3,'0')}</b><span class="muted pkname">${esc(p.zip)}</span><span class="muted">${new Date(p.created_at*1000).toLocaleString('zh-CN')}</span><button onclick="redl(${p.v})">下载副本</button></div><div class="ths">${(p.images||[]).map(image=>`<button class="delivery-thumb" onclick="openPv('${image.id}',${image.att})"><img src="${image.thumbnail_url}" alt="查看交付图片第${image.att}版"></button>`).join('')}</div></div>`).join('')||'<div class="tnone">还没有保存的图包</div>'}`;
}

function roundLabel(r,i,count){const name=(IMAGE_MODEL_OPTIONS.find(x=>x[0]===(r.image_model||IMAGE_MODEL_OPTIONS[0][0]))||IMAGE_MODEL_OPTIONS[0])[1];return '第 '+(i+1)+' 次修改'+(i===count-1?' · 当前':'')+' · '+name+' · '+(r.params.image_form||'')+(r.created_at?' · '+new Date(r.created_at*1000).toLocaleString('zh-CN'):'')}
function summaryRow(t){const menu=S.menu===t.id,meta=[t.status,t.image_form,t.done+'/'+t.total,t.archived?'已归档':''].filter(Boolean).join(' · ');return `<li class="trow ${menu?'mopen':''}">${S.ren===t.id?`<input id="renin" aria-label="任务名" value="${esc(S.renV??t.name)}" oninput="S.renV=this.value" onkeydown="if(event.key==='Enter')renOk();if(event.key==='Escape')renEnd()" onblur="renOk()">`:`<button class="task ${S.cur===t.id?'on':''}" data-task="${t.id}" onclick="openTask('${t.id}')"><div><div class="t1">${esc(t.name)}</div><div class="t2" title="${esc(meta)}">${esc(meta)}</div></div></button>`}<button class="more" aria-label="更多操作" onclick="openMenu('${t.id}')">⋯</button>${menu?`<div class="tmenu"><button onclick="renStart('${t.id}')">重命名</button><button onclick="dupFrom('${t.id}')">复制为新任务</button><button ${t.active?'disabled':''} onclick="archiveTask('${t.id}',${!t.archived})">${t.archived?'取消归档':'归档'}</button><button ${t.active?'disabled':''} onclick="delTask('${t.id}')">删除任务及候选</button></div>`:''}</li>`}
