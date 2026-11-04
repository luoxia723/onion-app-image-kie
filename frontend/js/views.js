let FORM_DEFAULTS={};
let IMAGE_MODEL_OPTIONS=[['gpt-image-2-5-sunburst-image-to-image','GPT Image 2.5 Sunburst'],['gpt-image-2-image-to-image','GPT Image 2']];
function imageModelOptions(selected){return IMAGE_MODEL_OPTIONS.map(([id,name])=>`<option value="${id}" ${id===selected?'selected':''}>${name} · 1K</option>`).join('')}

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
 const detail='画面方案 '+planned+' / '+groups.size+' 套就绪 · 图片 '+done+' / '+slots.length+' 张完成'+(generating?' · '+generating+' 张处理中':'')+(waitingFirst?' · '+waitingFirst+' 张等待首图':'');
 return{active,planning,generating,queued,done,total:slots.length,title,detail,waitingFirst};
}
function waitLabel(r,s){
 if(s.state==='generating')return({uploading:'正在上传参考图',submitting:'正在提交生成任务',generating:'正在生成',downloading:'正在下载',processing:'正在处理尺寸'})[s.stage]||'生成中';
 if(s.state==='queued'&&r.paused)return'已暂停后续';
 if(s.state==='queued'&&s.plan_ready===false)return r.planning_status==='queued'?'待规划':'规划中';
 if(s.state==='queued'&&s.idx>1&&r.slots.find(x=>x.id===s.first_id)?.state!=='done')return'等待首图';
 return s.state==='queued'?'排队中':VLAB[s.state]||'等待中';
}
function viewWorkStatus(r){
 const status=workStatus(r);
 if(S.connectionLost)return`<section class="work-status disconnected" role="status"><div><b>暂时无法连接本机服务</b><p>当前显示上次进度。请检查启动服务的窗口，连接恢复后会自动更新。</p></div></section>`;
 if(!status.active&&!r.stopped&&!r.paused)return'';
 return`<section class="work-status" id="pcard" aria-label="后台任务状态"><span class="${status.active?'wait-spinner':'work-stopped'}" aria-hidden="true">${status.active?'':'Ⅱ'}</span><div class="work-status-body"><b id="pctx" role="status">${esc(status.title)}</b><div class="work-counts">${esc(status.detail)}</div>${status.active?'<p>可以切换任务或关闭网页，后台会继续。稍后从左侧任务列表返回。</p><small>请保持本机服务运行，不要关闭启动窗口、关机或休眠。</small>':'<p>未提交的图片已停止，已完成的结果会保留。</p>'}</div>${!r.stopped?`<button onclick="pauseQueue(${!r.paused})">${r.paused?'继续队列':'暂停后续'}</button>`:''}<button class="stopb" id="stopbtn" ${r.stopped?'disabled':''} onclick="stopRest()">${r.stopped?'已停止后续':'停止后续提交'}</button></section>`;
}
function tRun(t){const r=t.rounds[t.ri];return !!t.background_running||['queued','running'].includes(r.planning_status)||r.slots.some(s=>s.state==="generating"||(s.state==="queued"&&!blocked(r,s)))}
function tProg(t){if(tRun(t))return true;if(t.downloaded)return false;const r=t.rounds[t.ri];return r.slots.some(s=>s.state==="done")}
function tGroup(t){if(t.is_summary)return t.category==='running'?'prog':t.category==='history'?'old':'attention';if(tProg(t))return"prog";const d0=new Date();d0.setHours(0,0,0,0);const s=d0.getTime(),dt=t.date||Date.now(),wd=(d0.getDay()+6)%7;if(dt>=s)return"today";if(dt>=s-864e5)return"yday";if(dt>=s-wd*864e5)return"week";return"old"}
function tHit(t,q){if(t.is_summary)return[t.name,t.pkg,t.image_model,t.image_form].some(v=>v&&String(v).toLowerCase().includes(q));const p=(t.rounds[t.ri]||{}).params||{};return[tName(t),t.pkg,p.t1,p.t2,p.s1,p.s2,p.s3].some(v=>v&&String(v).toLowerCase().includes(q))}
const GROUPS=[["prog","正在处理"],["attention","待处理"],["old","历史"]];
function taskRow(t){if(t.is_summary)return summaryRow(t);const r=t.rounds[t.ri],d=r.slots.find(s=>s.state==="done"),[dc,st]=taskStatus(t),run=tRun(t),m=S.menu===t.id;
 if(S.ren===t.id)return`<li class="trow"><div class="task on ren">${d?`<img src="${imgOf(d)}" alt="">`:'<span class="noimg"></span>'}<input id="renin" aria-label="任务名" value="${esc(S.renV!=null?S.renV:tName(t))}" oninput="S.renV=this.value" onkeydown="if(event.key==='Enter')renOk();if(event.key==='Escape'){event.stopPropagation();renEnd()}" onblur="renOk()"></div></li>`;
 return`<li class="trow ${t.downloaded?"dl":""} ${m?"mopen":""}" oncontextmenu="event.preventDefault();openMenu('${t.id}')"><button class="task ${t.id===S.cur?"on":""}" data-task="${t.id}" onclick="openTask('${t.id}')">${d?`<img src="${imgOf(d)}" alt="">`:'<span class="noimg"></span>'}<div><div class="t1">${esc(tName(t))}</div><div class="t2"><span class="dot ${dc}"></span><span class="tst">${st}</span></div>${r.delivery?.last_version&&st!=='已保存 '+r.delivery.last_version?`<div class="t3">已保存 ${r.delivery.last_version}${r.delivery.has_changes?' · 选择已变更':''}</div>`:''}</div></button><button class="more" data-more="${t.id}" aria-label="更多操作" aria-haspopup="menu" aria-expanded="${m}" onclick="event.stopPropagation();openMenu('${t.id}')">⋯</button>${m?`<div class="tmenu" role="menu"><button role="menuitem" data-act="ren" onclick="renStart('${t.id}')">重命名</button><button role="menuitem" data-act="dup" onclick="dupFrom('${t.id}')">复制为新任务</button><button role="menuitem" data-act="del" ${run?'disabled aria-disabled="true"':""} onclick="delTask('${t.id}')">删除</button>${run?'<div class="mhint">先停止后续</div>':""}</div>`:""}</li>`}
function taskList(){const q=(S.q||"").trim().toLowerCase();if(S.searchPending)return '<li class="tnone">正在搜索任务…</li>';if(q){const h=S.summaries||S.tasks.filter(t=>tHit(t,q));return h.length?h.map(taskRow).join(""):'<li class="tnone">没有匹配的任务</li>'}
 const fold=S.fold||{};return GROUPS.map(([g,lab])=>{const ts=(S.summaries||S.tasks).filter(t=>tGroup(t)===g);if(!ts.length)return"";if(g==="prog")return`<li class="gh fixed" data-g="${g}"><span>${lab}</span><span class="gn">${ts.length}</span></li>${ts.map(taskRow).join("")}`;const f=!!fold[g];return`<li><button class="gh" data-g="${g}" aria-expanded="${!f}" onclick="togFold('${g}')"><span><i>${f?"▸":"▾"}</i>${lab}</span><span class="gn">${ts.length}</span></button></li>${f?"":ts.map(taskRow).join("")}`}).join("")}
function togFold(g){S.fold=Object.assign({},S.fold);S.fold[g]=!S.fold[g];save();render()}

function viewSide(){return`<aside><div class="side-top"><div class="brandrow"><img src="${LOGO.thumb}" alt="洋葱学园">广告图${CFG.simulation?'<span class="mode-tag">模拟模式</span>':""}</div><button class="primary" id="newbtn" onclick="newTask()">＋ 新建任务</button><div class="tsearch"><input id="tq" type="search" placeholder="搜索" aria-label="搜索任务" value="${esc(S.q||"")}" oninput="searchTasks(this.value)"></div></div>
<div class="sidebar-scroll"><ul id="draft-list" class="drafts" aria-label="草稿">${typeof draftListHtml==='function'?draftListHtml():''}</ul><ul class="tasks" aria-label="任务">${taskList()||((S.drafts||[]).length?'':'<li class="empty-list">还没有任务</li>')}</ul></div>${S.undo?`<div class="undo" id="undo" role="status"><span>已删除 ·</span><button id="undobtn" onclick="undoDel()">撤销</button></div>`:""}
<div class="side-bot"><div id="queue-overview" class="queue-overview">${typeof queueText==='function'?esc(queueText()):''}</div><button class="ghost" id="cfgbtn" onclick="openCfg()">⚙ 设置</button></div></aside>`}
function stepsHtml(){const current=S.view==='form'?0:1;return`<div class="steps" role="tablist">${[['form','配置生成'],['pick','挑选保存']].map(([key,label],i)=>`<button class="step ${i===current?'on':i<current?'done':''}" ${key==='pick'&&!R()?'disabled':''} onclick="go('${key}')"><i>${i<current?'✓':i+1}</i>${label}</button>`).join('')}</div>`}
function viewHead(){const t=T(),pr=P(),nm=t?t.pkg:"新任务",tt=t?t.pkg+" · "+(pr.t1||pr.s1||""):"新任务";
 const acts=S.view==="pick"&&t?`<div class="row"><button id="redo" onclick="editRedo()">修改配置 / 补充生成</button><button id="dup" onclick="dupTask()">复制为新任务</button>${t.pkgs.length?`<button id="historybtn" onclick="go('dl')">交付记录</button>`:''}</div>`:"";
 const rr=R(),rbar=S.view!=="form"&&t&&rr?(()=>{const status=workStatus(rr);return`<div class="hbar"><div class="prog" id="prog">${status.active?'<span class="wait-spinner small" aria-hidden="true"></span>':''}<div class="pbar" role="progressbar" aria-label="图片完成进度" aria-valuemin="0" aria-valuemax="${status.total}" aria-valuenow="${status.done}"><i style="width:${Math.round(status.done/Math.max(1,status.total)*100)}%"></i></div><span id="progtx">${status.active||rr.stopped?esc(status.title)+' · ':''}${status.done} / ${status.total} 张完成</span></div><span class="muted">${esc((IMAGE_MODEL_OPTIONS.find(x=>x[0]===(rr.image_model||IMAGE_MODEL_OPTIONS[0][0]))||IMAGE_MODEL_OPTIONS[0])[1])} · 1K</span>${t.rounds.length>1?`<label class="rsel"><span class="sr">轮次</span><select id="roundSel" onchange="setRound(+this.value)">${t.rounds.map((x,i)=>`<option value="${i}" ${i===t.ri?"selected":""}>${esc(roundLabel(x,i,t.rounds.length))}</option>`).reverse().join("")}</select></label>`:''}</div>`})():'';
 return`<div class="head" id="head"><div class="crumb">任务 / <b id="crumbName">${esc(nm)}</b></div><div class="titlerow"><h1 id="title" tabindex="-1">${esc(tt)}</h1><div id="headActs">${acts}</div></div>${stepsHtml()}${S.navigationPending?'<div class="draft-state" id="navigation-status" role="status">正在打开，请稍候…</div>':''}${S.view==='form'?'<div class="draft-state"><span id="draft-status" role="status">'+esc(S.draftStatus||'草稿自动保存')+'</span><button class="lnk" onclick="persistDraft()">保存草稿</button></div>':''}${rbar}</div>`}
function setsBad(pr){const v=String(pr.sets).trim();return!/^\d+$/.test(v)||+v<SETS_MIN||+v>SETS_MAX}

const IMAGE_FORMS = {
  '单图': {count:1, fields:[['t1','主标题'],['t2','副标题']]},
  '双图': {count:2, fields:[['s1','短句 1'],['s2','短句 2']]},
  '三图': {count:3, fields:[['s1','短句 1'],['s2','短句 2'],['s3','短句 3']]},
};
function imageFormOf(pr){
  if(Object.hasOwn(pr,'image_form'))return IMAGE_FORMS[pr.image_form]?pr.image_form:'';
  const forms=[...new Set((pr.pids||[]).map(plOf).filter(Boolean).map(p=>p.image_form||Object.keys(IMAGE_FORMS).find(f=>IMAGE_FORMS[f].count===p.image_count)))];
  return forms.length===1?forms[0]:'';
}
function defParams(form='单图'){return{image_form:form,pids:[],t1:'',t2:'',s1:'',s2:'',s3:'',cta:DEF_CTA,sets:3,ip:'random',style:'random',font:'random',noLogo:false,references:[],...(FORM_DEFAULTS[form]||{})}}
function loadDraft(params){
  const form=imageFormOf(params)||'单图';
  S.draft={...defParams(form),pids:[],product_facts:S.product?.text||'',facts_version:S.product?.revision||0,...structuredClone(params)};
  S.draft.image_form=imageFormOf(params)||(params.image_form!==undefined||params.pids?.length?'':form);
  S.formDrafts={};
  S.formError=null;
}
function setImageForm(form){
  if(S.submitting||S.navigationPending||!IMAGE_FORMS[form]||form===imageFormOf(S.draft))return;
  S.formDrafts=S.formDrafts||{};
  const previous=imageFormOf(S.draft);
  if(previous)S.formDrafts[previous]=structuredClone(S.draft);
  const shared={};
  for(const k of ['cta','sets','ip','style','font','noLogo','references','feature_note','image_model','direction','product_facts','facts_version'])if(S.draft[k]!==undefined)shared[k]=structuredClone(S.draft[k]);
  S.draft={...(S.formDrafts[form]?structuredClone(S.formDrafts[form]):defParams(form)),...shared};
  if(formRequiresLogo(S.draft))S.draft.noLogo=false;
  S.tried=false;S.formError=null;save();render();
}
function formIssue(pr){
  const form=imageFormOf(pr);
  if(!form)return{field:'image-form',message:'请选择图片形式'};
  if(!pr.pids.length)return{field:'chans',message:'请选择渠道版位'};
  if(pr.pids.some(id=>!plOf(id)||plOf(id).image_count!==IMAGE_FORMS[form].count))return{field:'chans',message:'所选版位与文案形式不一致，请重新选择'};
  for(const [key,label] of IMAGE_FORMS[form].fields)if(!(pr[key]||'').trim())return{field:'f-'+key,message:'请填写'+label};
  if(setsBad(pr))return{field:'f-sets',message:'套数请填写 1–20 的整数'};
  if((pr.references||[]).some(r=>!(r.note||'').trim()))return{field:'reference-options',message:'请说明每张参考图中需要保留的内容'};
  if((pr.cta||'').length>12)return{field:'f-cta',message:'按钮文字最多 12 字'};
  return null;
}
function formErr(pr){const e=formIssue(pr);return e?e.field==='f-sets'?'sets':e.field==='chans'?'pids':'copy':''}
function formRequiresLogo(pr){return(pr.pids||[]).some(id=>{
  const p=plOf(id);return p&&(p.logo_policy==='required'||p.platform==='喜马拉雅'&&p.target_width===720&&[1280,1559].includes(p.target_height));
})}
function ipChoiceLabel(pr){return pr.ip==='none'?'不用 IP':IPS.find(a=>a.id===pr.ip)?.label||'随机 IP'}
function ipChoices(pr){
  const groups=[{name:'标准形象',items:[]},{name:'学段与 Q 版',items:[]},{name:'老师角色',items:[]}];
  for(const a of IPS){const group=a.variant==='standard'||a.id.includes('.standard.')?0:a.stage==='teacher'||a.id.includes('.teacher.')?2:1;groups[group].items.push(a)}
  const button=(id,label,thumb='')=>`<button class="ip ${pr.ip===id?'on':''}" data-ip="${id}" aria-label="${esc(label)}" title="${esc(label)}" aria-pressed="${pr.ip===id}" onclick="setF('ip','${id}',1)"><div style="${thumb?`background-image:url(${thumb})`:''}">${thumb?'':esc(label)}</div>${thumb?`<span class="ip-name">${esc(label).replace('-', '<br>')}</span>`:''}</button>`;
  return`<div class="ip-catalog" id="ips" role="group" aria-labelledby="ip-label"><div class="ips ip-modes">${button('random','随机 IP')}${button('none','不用 IP')}</div>${groups.filter(g=>g.items.length).map(g=>`<div class="ip-group"><div class="ip-group-label">${g.name}<span>${g.items.length} 份</span></div><div class="ips">${g.items.map(a=>button(a.id,a.label,a.thumb)).join('')}</div></div>`).join('')}</div>`;
}
function fontChoiceLabel(pr){return !pr.font||pr.font==='random'?'随机字体参考':pr.font==='none'?'不用字体参考':(typeof FONTS!=='undefined'?FONTS:[]).find(a=>a.id===pr.font)?.label||'已停用的字体参考'}
function viewFontOptions(pr){
  const fonts=typeof FONTS!=='undefined'?FONTS:[],selected=fonts.find(a=>a.id===pr.font);
  return`<div class="field"><label for="f-font">标题字体</label><div><select id="f-font" onchange="setF('font',this.value,1)">${[['random','随机字体参考'],['none','不用字体参考'],...fonts.map(a=>[a.id,a.label]),...(!selected&&pr.font&&!['none','random'].includes(pr.font)?[[pr.font,'已停用，请重新选择']]:[])].map(([id,label])=>`<option value="${esc(id)}" ${(pr.font||'random')===id?'selected':''}>${esc(label)}</option>`).join('')}</select>${selected?`<img class="font-preview" src="${selected.thumb}" alt="${esc(selected.label)}">`:''}<p class="field-help">${pr.font==='none'?'标题字形由模型根据画面设计。':'沿用样张字形，不使用样张里的旧文案。'}</p></div></div>`;
}
function optionsSummary(pr){return`<dt>角色 IP</dt><dd>${esc(ipChoiceLabel(pr))}</dd><dt>画风</dt><dd>${esc(pr.style&&pr.style!=='random'?pr.style:'随机画风')}</dd><dt>标题字体</dt><dd>${esc(fontChoiceLabel(pr))}</dd><dt>产品资料</dt><dd>已引用 v${esc(pr.facts_version??0)}</dd><dt>品牌 Logo</dt><dd>${pr.noLogo?'不用 Logo':'使用 Logo'}${formRequiresLogo(pr)?'（版位要求）':''}</dd><dt>自选参考图</dt><dd>${(pr.references||[]).length} 张</dd><dt>补充要求</dt><dd>${(pr.feature_note||'').trim()?'已填写':'未填写'}</dd>`}
function viewVisualOptions(pr){
  const required=formRequiresLogo(pr);
  return`<section class="card visual-options" id="visual-options" aria-labelledby="visual-options-title"><h3 id="visual-options-title">画面与素材</h3>
    <div class="field"><span class="lab" id="ip-label">角色 IP</span><div>${ipChoices(pr)}<p class="field-help">随机 IP 从标准形象中每套分配角色；其他学段、Q 版或老师请直接指定。不用 IP 时不引用品牌角色素材，画面仍可有原创人物。</p></div></div>
    <div class="field"><label for="styleq">画风</label><div class="combo" id="combo"><input id="styleq" role="combobox" aria-expanded="${!!S.styleOpen}" aria-controls="stylelist" autocomplete="off" value="${esc(S.styleOpen?(S.styleQ||''):(pr.style==='random'?'随机画风':pr.style))}" placeholder="搜索或选择画风" onfocus="styleOpen()" onclick="styleOpen()" oninput="styleFilter(this.value)" onkeydown="styleKey(event)"><span class="caret" aria-hidden="true">▾</span>${S.styleOpen?`<ul class="clist" id="stylelist" role="listbox">${styleOpts().map((s,i)=>`<li role="option" data-style="${esc(s)}" aria-selected="${pr.style===s}" class="${i===(S.styleHi||0)?'hi':''}" onmousedown="event.preventDefault();pickStyle(${esc(JSON.stringify(s))})">${s==='random'?'随机画风':esc(s)}</li>`).join('')}</ul>`:''}</div></div>
    ${viewFontOptions(pr)}
    <div class="field" style="margin:0"><span class="lab">品牌 Logo</span><div><div class="chips"><button class="chip ${!pr.noLogo?'on':''}" id="withlogo" aria-pressed="${!pr.noLogo}" onclick="setF('noLogo',false,1)">使用 Logo</button><button class="chip ${pr.noLogo?'on':''}" id="nologo" aria-pressed="${!!pr.noLogo}" ${required?'disabled':''} onclick="setF('noLogo',true,1)">不用 Logo</button></div>${required?'<p class="field-help">所选版位要求保留 Logo。</p>':''}</div></div>
  </section>`;
}
const REFERENCE_PURPOSES={style:'画风参考',composition:'构图参考',ui:'真实 UI 截图',legacy:'画风 / 构图（旧配置）'};
function referencePurposeSelect(r,i){return`<select aria-label="参考图用途" onchange="setReferencePurpose(${i},this.value)">${Object.entries(REFERENCE_PURPOSES).filter(([id])=>id!=='legacy'||!r.purpose||r.purpose==='legacy').map(([id,label])=>`<option value="${id}" ${(r.purpose||'legacy')===id?'selected':''}>${label}</option>`).join('')}</select>`}
function viewReferenceOptions(pr){return`<section class="card" id="reference-options" aria-labelledby="reference-options-title"><h3 id="reference-options-title">参考图与补充要求</h3>
  <div class="field"><span class="lab">参考图</span><div><button onclick="uploadReference()">＋ 上传参考图 / 界面截图</button><div class="upload-list">${(pr.references||[]).map((r,i)=>`<div class="upload-item"><span>${esc(r.name)}</span>${referencePurposeSelect(r,i)}<button class="lnk" onclick="removeReference(${i})" aria-label="移除参考图">×</button><textarea aria-label="参考图说明" maxlength="200" rows="2" oninput="setReferenceNote(${i},this.value)">${esc(r.note||'')}</textarea></div>`).join('')}</div><p class="field-help">画风与构图参考分别沿用对应视觉特征；真实 UI 截图用于产品屏幕，保留原有界面内容。</p>${S.tried&&formIssue(pr)?.field==='reference-options'?`<div class="errtx">${esc(formIssue(pr).message)}</div>`:''}</div></div>
  <div class="field"><label for="f-feature">补充要求</label><textarea id="f-feature" maxlength="200" placeholder="填写希望沿用的构图、场景或其他要求" oninput="setF('feature_note',this.value)">${esc(pr.feature_note||'')}</textarea></div>
  <div class="field" style="margin:0"><span class="lab">产品资料</span><div><div class="row"><span class="ro">已引用 v${esc(pr.facts_version??0)}</span><button onclick="openCfg()">维护资料</button><button onclick="useLatestProduct()">引用最新资料</button></div><details class="product-preview"><summary>查看已引用资料</summary><pre>${esc(pr.product_facts||'未提供产品资料，仅依据已确认文案。')}</pre></details></div></div>
  </section>`}
function viewForm(){
  const pr=S.draft,form=imageFormOf(pr),definition=IMAGE_FORMS[form],grp={};
  PLACEMENTS.filter(p=>definition&&p.image_count===definition.count).forEach(p=>{(grp[p.category]=grp[p.category]||[]).push(p)});
  const issue=S.tried?formIssue(pr):null;
  const fi=(key,label)=>`<div class="field"><label for="f-${key}">${label}</label><div><input id="f-${key}" data-k="${key}" required aria-required="true" aria-invalid="${!!(issue?.field==='f-'+key)}" value="${esc(pr[key]||'')}" class="${issue?.field==='f-'+key?'bad':''}" oninput="setF('${key}',this.value)">${issue?.field==='f-'+key?`<div class="errtx">${esc(issue.message)}</div>`:''}</div></div>`;
  return `<div class="form"><fieldset class="form-fields" ${S.submitting||S.navigationPending?'disabled':''}>
    <div class="card compose-card">    <div class="form-kind"><h3 id="image-form-label">图片形式</h3><div class="form-options" role="radiogroup" aria-labelledby="image-form-label" id="image-form">${Object.keys(IMAGE_FORMS).map(f=>`<label class="form-option ${f===form?'on':''}"><input type="radio" name="image_form" value="${f}" ${f===form?'checked':''} onchange="setImageForm(this.value)"><span>${f}</span></label>`).join('')}</div>${issue?.field==='image-form'?`<div class="errtx">${esc(issue.message)}</div>`:''}</div>
    ${definition?`<div class="copy-card"><div class="copy-heading"><h3>文案</h3><span>${form}</span></div>${definition.fields.map(([k,label])=>fi(k,label)).join('')}<div class="field" style="margin:0"><label for="f-cta">按钮文字</label><input id="f-cta" maxlength="12" value="${esc(pr.cta||'')}" style="max-width:240px" oninput="setF('cta',this.value)"></div></div>`:''}
    </div>
    ${viewVisualOptions(pr)}
    <div class="card"><h3>渠道版位</h3><div id="chans">${Object.entries(grp).map(([g,list])=>`<div class="grp">${g}</div><div class="chips placement-options">${list.map(p=>`<button class="chip ${pr.pids.includes(p.id)?'on':''}" data-pid="${p.id}" aria-pressed="${pr.pids.includes(p.id)}" onclick="togP('${p.id}')">${esc(pname(p))}<small>${psz(p)}${p.image_count>1?' ×'+p.image_count:''}</small></button>`).join('')}</div>`).join('')}</div>${issue?.field==='chans'?`<div class="errtx">${esc(issue.message)}</div>`:''}</div>
    <div class="card"><div class="field" style="margin:0"><label for="f-sets" class="sets-label">每版位套数</label><div><input id="f-sets" type="number" min="${SETS_MIN}" max="${SETS_MAX}" value="${pr.variants_by_placement&&new Set(Object.values(pr.variants_by_placement)).size>1?'':esc(pr.sets)}" placeholder="分别设置" style="width:120px" class="${setsBad(pr)?'bad':''}" oninput="setSets(this.value)">${issue?.field==='f-sets'?`<div class="errtx">${esc(issue.message)}</div>`:''}</div></div></div>
    ${viewReferenceOptions(pr)}
    <div class="card"><div class="field" style="margin:0"><label for="f-direction">方向名</label><div><input id="f-direction" maxlength="30" value="${esc(pr.direction||'')}" oninput="setF('direction',this.value)"><p class="field-help">用于任务和文件命名，不会作为画面文字。</p></div></div></div>
    </fieldset><div class="card sum" id="sum"><h3>本次生成</h3><div class="field" style="display:block"><label for="image-model" style="display:block;margin-bottom:8px">图片模型</label><select id="image-model" style="width:100%" ${S.submitting||S.navigationPending?'disabled':''} onchange="setF('image_model',this.value)">${imageModelOptions(pr.image_model|| (typeof CFG!=='undefined'&&CFG.imageModel)||IMAGE_MODEL_OPTIONS[0][0])}</select></div><dl><dt>版位</dt><dd id="sum-p">${pr.pids.length} 个</dd><dt>每版位</dt><dd id="sum-n">${pr.variants_by_placement&&new Set(Object.values(pr.variants_by_placement)).size>1?'分别设置':esc(pr.sets)+' 套'}</dd></dl><dl id="sum-config" class="sum-config">${optionsSummary(pr)}</dl>${S.submitting?'<p class="field-help" role="status">正在提交本次配置，请稍候。创建任务后即可离开页面。</p>':''}<div class="gorow"><button class="primary" id="go" ${setsBad(pr)||S.submitting||S.navigationPending?'disabled':''} onclick="startGen()">${S.submitting?'正在提交…':'开始生成'}</button><span class="tot" id="tot">${typeof CFG!=='undefined'&&!CFG.simulation?'真实生图 · ':''}共 ${totalOf(pr)} 张</span></div></div></div>`;
}
function need(k){return (IMAGE_FORMS[imageFormOf(S.draft)]?.fields||[]).some(([f])=>f===k)}

function cellHtml(r,s,rowh){const p=plOf(s.pid),w=Math.round(rowh*p.target_width/p.target_height),st=isFail(r,s)?"failed":s.state;
 if(st==="done")return`<div class="cell done" style="width:${w}px" data-slot="${s.id}" data-st="done" role="button" tabindex="0" aria-label="套 ${s.set} · ${esc(pname(p))}${p.image_count>1?" 图 "+s.idx:""},查看大图" onclick="openPv('${s.id}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openPv('${s.id}')}"><img alt="" src="${imgOf(s)}">${["frame_review","frame_failed"].includes(s.reason_code)?`<span class="frame-note">${s.reason_code==='frame_failed'?'待适配':'已适配'}</span>`:""}</div>`;
 if(st==="failed"){const m=failMsg(r,s),retry=imageRetry(r,s),planning=s.reason_code==='planning_failed';return`<div class="cell fail" style="width:${Math.max(w,150)}px" data-slot="${s.id}" data-st="failed"><div class="box"><span class="sr">失败</span><p tabindex="0" title="${esc(m)}" aria-label="失败:${esc(m)}" onclick="openPv('${s.id}')">${esc(m)}</p><button data-redo="${s.id}" ${retry.disabled?'disabled':''} onclick="${planning?'retryPlanning()':retry.blocked?"openPv('"+retry.head?.id+"')":(retry.query?'resumeImage':'redo')+"('"+s.id+"')"}">${planning?'重试规划':retry.label}</button></div></div>`}
 const cls={queued:"wait",waiting_first:"wait",generating:"gen",stopped:"stop"}[st],label=waitLabel(r,s);return`<div class="cell ${cls}" style="width:${w}px" data-slot="${s.id}" data-st="${st}" role="img" aria-label="${esc(label)}"><div class="box">${st==='queued'?'<span class="wait-dots" aria-hidden="true"><i></i><i></i><i></i></span>':''}<span class="vlab">${esc(label)}</span>${st==="generating"?`<span class="muted" data-t0="${s.t0}">0:00</span>`:""}</div></div>`}
function imageRetry(r,s){
 const head=r.slots.find(x=>x.id===s.first_id),query=!!s.query_required||['unknown','timeout'].includes(s.reason_code),blockedFirst=blocked(r,s)||s.state==='blocked_first_failed';
 const group=s.idx===1?r.slots.filter(x=>x.pid===s.pid&&x.set===s.set):[s];
 const busy=group.some(x=>['queued','generating'].includes(x.state));
 return {query,blocked:blockedFirst,head,disabled:busy&&!blockedFirst,
 label:query?'恢复查询':blockedFirst?'查看首图':s.idx===1&&plOf(s.pid).image_count>1?'重出首图及后续图':'重出本张',
 note:query?'本次查询等待已结束，供应商任务可能仍在运行。恢复查询沿用原任务号，不重新提交生图。':blockedFirst?'本张依赖首图，请先处理图 1。':s.idx===1&&plOf(s.pid).image_count>1?'重出图 1 后，本套后续图会退出当前结果，等待新首图完成后重新生成；历史文件保留。':s.idx>1?'仅重出本张，继续引用本套当前图 1；其他图片保留。':'仅重出当前图片。'};
}
function refsOf(r,s){return(s.reference_images||[]).map((x,i)=>({k:i,name:(x.label||'参考图'+(i+1))+' · '+x.name+(x.retired?' · 历史参考已停用':''),src:x.thumbnail_url,bad:x.upload_status==='failed'}))}
function viewPv(){const r=R();const s=curPvSlot();if(!s)return`<div class="mask"><div class="dlg" role="dialog" aria-label="正在加载预览"><button class="x" onclick="closePv()">×</button><p role="status">正在读取图片、提示词和版本…</p></div></div>`;const retry=imageRetry(r,s);const p=plOf(s.pid),f=isFail(r,s),on=!!r.sel[selectionKey(s.pid,s.set)];
 return`<div class="mask" id="m-preview" onclick="if(event.target===this)closePv()"><div class="pv" role="dialog" aria-modal="true" aria-label="大图预览" id="pv"><div class="l">${s.files_cleared?'<div class="fbig">此版本图片已清理，提示词和记录仍保留</div>':s.state==="done"&&S.pvCompare&&s.history?.filter(v=>v.image_url).length>1?`<div class="compare-images">${s.history.filter(v=>v.image_url).slice(-2).map(v=>`<figure><img src="${v.image_url}" alt="图片第${v.att}版"><figcaption>图片第${v.att}版</figcaption></figure>`).join('')}</div>`:s.state==="done"?`<img id="pvImg" alt="" src="${S.pvOriginal?s.original_image_url:imgOf(s)}">`:`<div class="fbig">${VLAB[f?"failed":s.state]}</div>`}</div><div class="r">
 <div class="pvtitle" id="pvTitle">套 ${s.set} · ${esc(pname(p))}${p.image_count>1?" · 图 "+s.idx:""}<span>${psz(p)}</span></div>
 <div class="row"><label for="imageVersion">图片版本</label><select id="imageVersion" onchange="openPv('${s.id}',+this.value)">${(s.history||[]).slice().reverse().map(v=>`<option value="${v.att}" ${v.att===s.att?'selected':''}>图片第${v.att}版${v.att===(s.history||[]).at(-1)?.att?' · 当前':v.files_cleared?' · 文件已清理':' · 历史'}</option>`).join('')}</select>${s.history?.filter(v=>v.image_url).length>1?'<button onclick="comparePrevious()">对比最近两版</button>':''}</div><div class="row"><button ${s.files_cleared?'disabled':''} onclick="pinImageVersion()">${s.pinned?'取消保留此版本':'保留此版本，清理时跳过'}</button></div><div><h4>参考图</h4><div class="refs" id="pvRefs">${refsOf(r,s).map(x=>`<div class="ref ${x.bad?"bad":""}" data-ref="${x.k}"><div style="${x.src?`background-image:url(${x.src})`:""}"></div><span>${x.bad?"未上传":esc(x.name)}</span></div>`).join("")}</div></div>
 ${s.state==='done'?`<div class="row" style="justify-content:space-between;align-items:center"><span id="pvkind" class="muted">${s.preview_kind==='raw'?'待处理原图':S.pvOriginal?'生成原图':'成品预览'}</span>${s.preview_kind!=='raw'&&s.original_image_url?`<button class="lnk" id="pvsource" onclick="togglePvOriginal()">${S.pvOriginal?'查看成品':'查看原图'}</button>`:''}</div>`:''}
 ${f||['frame_review','frame_failed'].includes(s.reason_code)?`<div class="pvwhy" id="pvwhy">${esc(s.msg||failMsg(r,s))}${s.preview_kind==='raw'&&s.has_frame&&!s.is_historical?`<div class="local-options"><button id="pvcrop" onclick="reprocessFrame('${s.id}')">重新识别蓝框</button><button id="pvfit" onclick="fitImage('${s.id}')">整图适配，保留全部内容</button></div><small>未画出蓝框时可选整图适配，仅调整尺寸；请确认画面比例。两种处理均在本机完成。</small>`:''}</div>`:""}
 <div style="display:flex;flex-direction:column;min-height:0;flex:1"><div style="display:flex;justify-content:space-between;align-items:baseline"><h4><label for="pvPrompt">提示词</label></h4><button class="lnk" id="pvReset" style="${!s.is_historical&&s.prompt!==s.orig?"":"display:none"}" onclick="pvResetP()">恢复原提示词</button></div><small class="muted">${s.is_historical?'历史版本只读，实际参考图按当时记录展示。':'可自由修改本张提示词；实际参考图及顺序不变，草稿自动保存在本机。'}</small>${!s.is_historical&&s.edit_drafts?.length>1?`<label>已保存的编辑草稿 <select onchange="choosePromptDraft(this.value)"><option value="">选择其他窗口保留的草稿</option>${s.edit_drafts.map((d,i)=>`<option value="${esc(d.editor_id)}">草稿${i+1} · ${new Date(d.updated_at*1000).toLocaleString('zh-CN')} · ${esc(d.text.slice(0,12))}</option>`).join('')}</select></label>`:''}<div class="row"><small id="prompt-draft-status" role="status">${esc(S.promptStatus||'当前图片的实际提示词')}</small>${!s.is_historical?'<button class="lnk" onclick="discardPromptDraft()">放弃草稿</button>':''}</div><textarea class="prompt" id="pvPrompt" ${s.is_historical?'readonly':''} oninput="pvChk()">${esc(S.promptDraft?.id===s.id?S.promptDraft.value:s.prompt)}</textarea></div>
 <p class="muted" id="pvRetryScope">${esc(retry.note)}</p><div class="acts"><button class="primary" id="pvsel" ${!s.is_historical&&(s.state==="done"||r.slots.some(x=>x.set===s.set&&x.state==="done"))?"":"disabled"} onclick="toggleSel(${s.set},true,'${s.pid}')">${on?"已选":"选中这一套"}</button><button id="pvredo" ${retry.disabled||s.is_historical||S.previewStale?"disabled":""} onclick="pvRedo()">${esc(retry.label)}</button></div>
 </div><button class="x" id="pvx" onclick="closePv()" aria-label="关闭">×</button></div></div>`}
function viewCfg(){return`<div class="mask" id="m-settings" onclick="if(event.target===this)closeCfg()"><div class="dlg" role="dialog" aria-modal="true" aria-label="设置" id="cfgdlg"><button class="x" onclick="closeCfg()" aria-label="关闭">×</button><h2>设置</h2>
 <section data-grp="planning"><h5 style="margin-top:0">画面规划</h5>
 <div class="field"><label for="planmodel">语言模型</label><input id="planmodel" maxlength="128" value="${esc(CFG.planningModel||'')}" autocomplete="off"></div>
 <div class="field"><label for="plankey">规划 Key</label><div><div class="row"><input type="password" id="plankey" autocomplete="off" placeholder="${CFG.planningKey?'已配置，留空保留':''}" value=""><button style="flex:none" id="plantest" onclick="testPlanning()">测试连接</button></div><div id="planst" role="status"></div></div></div>
 <div class="field"><label for="planbase">接口地址</label><input id="planbase" value="${esc(CFG.planningBase||'')}" autocomplete="off"></div>
 <div class="ro">按原 Skill 规划画面。测试连接和画面规划均会调用此模型，模拟模式也会产生规划用量。</div></section>
 <section data-grp="img"><h5>图片生成</h5>
 <div class="field"><label for="cfgimagemodel">默认模型</label><select id="cfgimagemodel">${imageModelOptions(CFG.imageModel)}</select></div><div class="ro">两个模型均使用 1K。默认值用于新任务；已有轮次重试仍使用原模型。</div>
 <div class="field"><label for="kiekey">KIE Key</label><div><div class="row"><input type="password" id="kiekey" autocomplete="off" placeholder="${CFG.kie?'已配置，留空保留':''}" value="" oninput="imageKeyEntered()"><button style="flex:none" id="kietest" onclick="testConn()">测试连接</button></div><div id="kiest">${connTx("kie")}</div></div></div>
 <div class="field"><label for="cfgimagemode">图片输出</label><select id="cfgimagemode"><option value="real" ${!CFG.simulation?'selected':''}>真实生图</option><option value="simulation" ${CFG.simulation?'selected':''}>模拟预览</option></select></div>
 <div class="ro">填入 KIE Key 后自动选择真实生图，保存即生效。点击“开始生成”后才提交图片并产生生图用量；测试连接只查询账户余额。</div>
 <details id="adv"><summary>高级</summary><div class="field"><label for="kbase">KIE_BASE_URL</label><input id="kbase" value="${esc(CFG.base)}"></div><div class="field"><label for="kup" style="font-size:12px">KIE_UPLOAD_BASE_URL</label><input id="kup" value="${esc(CFG.up)}"></div></details></section>
<section><h5>数据维护</h5><button onclick="openMaintenance()">备份、恢复与清理旧版本</button></section><section data-grp="product"><h5>产品资料</h5><textarea id="product-facts" rows="5" maxlength="20000" placeholder="填写已确认的目标人群、产品功能和可用界面文字">${esc(S.product?.text||'')}</textarea></section> <section data-grp="gen"><h5>通用</h5><div class="field"><span class="lab">候选与暂存占用</span><div class="stor" id="stor">${storHtml()}</div></div><div class="field"><label for="cfgcap">全局生图并发</label><div class="row" style="align-items:center"><input type="range" id="cfgcap" min="1" max="20" value="${CFG.cap}" style="height:auto;border:0;padding:0" oninput="cv.textContent=this.value"><output id="cv" for="cfgcap" style="width:28px;text-align:right;font-weight:600">${CFG.cap}</output></div></div>
 <div class="field"><label for="cfgpath">保存位置</label><div class="row"><input id="cfgpath" value="${esc(CFG.path)}"><button style="flex:none" onclick="chooseFolder()">选择…</button></div></div></section>
 <div class="foot"><button onclick="closeCfg()">取消</button><button class="primary" id="cfgsave" onclick="saveCfg()">保存</button></div></div></div>`}

function softRender(){if(!S.pv&&!S.cfgOpen&&!S.maintenanceOpen)return render();const a=document.querySelector("#app>.app");if(!a)return render();const m=$("main"),y=m?m.scrollTop:0,ae=document.activeElement,inApp=a.contains(ae),fref=inApp?trapRef(ae):null;
 const body=S.view==="form"?viewForm():S.view==="pick"?viewPick():viewDl();const d=document.createElement("div");d.innerHTML=`<div class="app">${viewSide()}<main id="main">${viewHead()}<div class="body" id="body">${body}</div>${S.view!=='form'?viewSelectionFooter():''}</main></div>`;const tl=$(".sidebar-scroll")||$(".tasks"),ty=tl?tl.scrollTop:0;a.replaceWith(d.firstElementChild);const tl2=$(".sidebar-scroll")||$(".tasks");if(tl2)tl2.scrollTop=ty;const m2=$("main");if(m2){m2.scrollTop=y;setHH()}if(fref){const e=document.querySelector(fref);if(e)e.focus({preventScroll:true})}updTimers();syncSelectionControls()}
function setHH(){const m2=$("main"),h=$("#head"),tb=document.querySelector(".toolbar");if(!m2||!h)return;m2.style.setProperty("--hh",h.offsetHeight+"px");m2.style.setProperty("--sp",(h.offsetHeight+(tb&&S.view==="pick"?tb.offsetHeight+8:0)+8)+"px")}
function render(){const ae=document.activeElement,fk=ae&&ae.id,fref=ae&&ae!==document.body?trapRef(ae):null,ss=ae&&(ae.selectionStart||(ae.value&&ae.matches&&ae.matches('input[type=search],#styleq')?ae.value.length:ae.selectionStart)),m=$("main"),y=m?m.scrollTop:0;
 const body=S.view==="form"?viewForm():S.view==="pick"?viewPick():viewDl();
 const tl=$(".sidebar-scroll")||$(".tasks"),ty=tl?tl.scrollTop:0;window._rnd=true;
$("#app").innerHTML=`<div class="app">${viewSide()}<main id="main">${viewHead()}<div class="body" id="body">${body}</div>${S.view!=='form'?viewSelectionFooter():''}</main></div>${S.pv?viewPv():""}${S.cfgOpen?viewCfg():""}${S.maintenanceOpen?viewMaintenance():""}`;
 window._rnd=false;const tl2=$(".sidebar-scroll")||$(".tasks");if(tl2)tl2.scrollTop=ty;
 const m2=$("main");if(m2){m2.scrollTop=y;setHH()}
 if(!fk&&fref){const e=document.querySelector(fref);if(e&&!(S.pv||S.cfgOpen))e.focus({preventScroll:true})}if(fk){const e=document.getElementById(fk);if(e&&!e.closest(".mask")||e&&(S.pv||S.cfgOpen)){e.focus({preventScroll:true});try{if(ss!=null&&e.setSelectionRange)e.setSelectionRange(ss,ss)}catch(_){}}}updTimers();syncSelectionControls()}

function styleOpts(){const q=(S.styleQ||"").trim();return["random",...STYLES.map(s=>s.name)].filter(s=>!q||(s==="random"?"随机":s).includes(q))}
function styleOpen(){if(S.styleOpen||window._skipOpen)return;S.styleOpen=true;S.styleQ="";S.styleHi=0;render();const i=$("#styleq");i.focus();i.select()}
function styleFilter(v){S.styleQ=v;S.styleHi=0;render()}
function pickStyle(s){if(S.submitting||S.navigationPending)return;S.draft.style=s;S.styleOpen=false;S.styleQ="";save();window._skipOpen=true;render();window._skipOpen=false}
function styleKey(e){if(!S.styleOpen&&e.key==="ArrowDown"){e.preventDefault();return styleOpen()}const o=styleOpts();if(e.key==="ArrowDown"){e.preventDefault();S.styleHi=Math.min(o.length-1,(S.styleHi||0)+1);render()}else if(e.key==="ArrowUp"){e.preventDefault();S.styleHi=Math.max(0,(S.styleHi||0)-1);render()}else if(e.key==="Enter"){e.preventDefault();if(o[S.styleHi||0])pickStyle(o[S.styleHi||0])}else if(e.key==="Escape"){e.stopPropagation();S.styleOpen=false;window._skipOpen=true;render();window._skipOpen=false}}
document.addEventListener("mousedown",e=>{if(S.styleOpen&&!e.target.closest("#combo")){S.styleOpen=false;window._skipOpen=true;render();window._skipOpen=false}});
/* ===== 动作 ===== */





function togP(id){if(S.submitting||S.navigationPending)return;const p=plOf(id),form=IMAGE_FORMS[imageFormOf(S.draft)];if(!p||!form||p.image_count!==form.count)return;const a=S.draft.pids;S.draft.pids=a.includes(id)?a.filter(x=>x!==id):[...a,id];if(S.draft.variants_by_placement){for(const k of Object.keys(S.draft.variants_by_placement))if(!S.draft.pids.includes(k))delete S.draft.variants_by_placement[k]}const required=formRequiresLogo(S.draft)&&S.draft.noLogo;if(required)S.draft.noLogo=false;save();render();if(required)toast('所选版位要求保留 Logo，已启用')}
function setF(k,v,re){if(S.submitting||S.navigationPending)return;S.draft[k]=v;save();if(re)render();else updSum()}
function setSets(v){if(S.submitting||S.navigationPending)return;delete S.draft.variants_by_placement;S.draft.sets=v;save();updSum()}
function updSum(){const pr=S.draft;const e=$("#tot");if(e)e.textContent=(typeof CFG!=='undefined'&&!CFG.simulation?'真实生图 · ':'')+"共 "+totalOf(pr)+" 张";const i=$("#f-sets");if(i)i.classList.toggle("bad",setsBad(pr));const sp=$("#sum-p");if(sp)sp.textContent=pr.pids.length+" 个";const sn=$("#sum-n");if(sn)sn.textContent=pr.variants_by_placement&&new Set(Object.values(pr.variants_by_placement)).size>1?'分别设置':pr.sets+" 套";const c=$("#sum-config");if(c)c.innerHTML=optionsSummary(pr);const g=$("#go");if(g)g.disabled=setsBad(pr)}

function setTab(c){S.tab=c;S.miss=false;save();render()}
async function setRound(i){const epoch=beginNavigation();if(epoch===null)return;try{await persistPromptDraft();if(epoch!==viewEpoch)return;const t=await request('/tasks/'+S.cur+'?view=1&round='+i);if(epoch!==viewEpoch)return;installTask(t);T().ri=i;save(false);render()}finally{finishNavigation(epoch)}}

function trapRef(e){if(!e||e===document.body)return null;return e.id?"#"+e.id:e.dataset&&e.dataset.slot?`[data-slot="${e.dataset.slot}"]`:e.closest&&e.closest("[data-slot]")?`[data-slot="${e.closest("[data-slot]").dataset.slot}"]`:null}


function curPvSlot(){return S.pvDetails?.id===S.pv?S.pvDetails:null}



function cfgRef(e){if(!e||e===document.body)return"#cfgbtn";return e.id?"#"+e.id:"#cfgbtn"}

function cfgBack(){const e=document.querySelector(window._cfgFrom||"#cfgbtn")||$("#cfgbtn");window._cfgFrom=null;if(e)e.focus({preventScroll:true})}
function closeCfg(){S.cfgOpen=false;render();cfgBack()}

/* 键盘:Esc 关闭最上层弹窗;弹窗内锁焦点 */
document.addEventListener("keydown",e=>{const m=S.cfgOpen?$("#cfgdlg"):S.pv?$("#pv"):null;if(!m)return;
 if(e.key==="Escape"){e.preventDefault();S.cfgOpen?closeCfg():closePv();return}
 if(e.key==="Tab"){const f=[...m.querySelectorAll("input,textarea,summary,button:not([disabled])")].filter(x=>x.offsetParent!==null);if(!f.length)return;const a=f[0],z=f[f.length-1];if(!m.contains(document.activeElement)){e.preventDefault();(e.shiftKey?z:a).focus()}else if(e.shiftKey&&document.activeElement===a){e.preventDefault();z.focus()}else if(!e.shiftKey&&document.activeElement===z){e.preventDefault();a.focus()}}});
document.addEventListener("click",e=>{if(S.miss&&!e.target.closest("#miss")){S.miss=false;render()}});

function selectionKey(pid,n){return pid+'::'+n}
function setsOf(r){
  const groups=new Map();
  r.slots.forEach(s=>{const id=selectionKey(s.pid,s.set);if(!groups.has(id))groups.set(id,{id,n:s.set,pid:s.pid,sl:[]});groups.get(id).sl.push(s)});
  return [...groups.values()];
}
function selectedSet(r,g){return !!r.sel[g.id]}
function attentionSet(r,g){return g.sl.some(s=>isFail(r,s)||s.state==='stopped'||s.reason_code==='frame_failed')}
function groupMatchesFilter(r,g,pf){
  return pf==='yes'?selectedSet(r,g):pf==='no'?!selectedSet(r,g):pf==='bad'?attentionSet(r,g):true;
}
function selectionScope(r){
  return setsOf(r).filter(g=>(S.tab==='all'||plOf(g.pid).platform===S.tab)&&groupMatchesFilter(r,g,S.pf)&&g.sl.some(s=>s.state==='done'));
}
function bulkSelectionState(r){
  const scope=selectionScope(r),selected=scope.filter(g=>selectedSet(r,g)).length;
  return{scope,selected,all:scope.length>0&&selected===scope.length,mixed:selected>0&&selected<scope.length};
}
function syncSelectionControls(){const e=document.querySelector('#select-visible');if(e)e.indeterminate=e.getAttribute('aria-checked')==='mixed'}
function pickCardClick(event,n,pid){
  if(event.target.closest('button,input,label,textarea,a,.cell')||S.selectionBusy)return;
  const r=R(),group=setsOf(r).find(g=>g.pid===pid&&g.n===n);
  if(group?.sl.some(s=>s.state==='done'))toggleSel(n,false,pid);
}
function viewPick(){
  const r=R();if(!r)return'';
  const groups=setsOf(r),channels=chans(r),rowh=S.tab==='all'?132:220;
  const inChannel=g=>S.tab==='all'||plOf(g.pid).platform===S.tab;
  const channelGroups=groups.filter(inChannel);
  const filters={all:g=>true,yes:g=>selectedSet(r,g),no:g=>!selectedSet(r,g),bad:g=>attentionSet(r,g)};
  const labels=[['all','全部'],['yes','已选'],['no','未选'],['bad','需检查']];
  const tabs=`<div class="tabs" role="tablist" aria-label="渠道"><button class="tab ${S.tab==='all'?'on':''}" onclick="setTab('all')">所有渠道</button>${channels.map(c=>{const gs=groups.filter(g=>plOf(g.pid).platform===c),done=gs.filter(g=>g.sl.every(s=>s.state==='done')).length,bad=gs.some(g=>g.sl.some(s=>isFail(r,s)));return`<button class="tab ${S.tab===c?'on':''}" onclick="setTab(${esc(JSON.stringify(c))})">${esc(c)} ${done}/${gs.length}${bad?'<span class="rd" aria-label="有失败"></span>':''}</button>`}).join('')}</div>`;
  const filter=`<div class="fseg" role="group" aria-label="筛选">${labels.map(([k,label])=>`<button class="${S.pf===k?'on':''}" aria-pressed="${S.pf===k}" onclick="S.pf='${k}';render()">${label} <span class="num">${channelGroups.filter(filters[k]).length}</span></button>`).join('')}</div>`;
  const missing=missK(r),missingHtml=missing?`<div class="miss neutral" id="miss"><button id="missbtn" aria-expanded="${!!S.miss}" onclick="S.miss=!S.miss;render()">${missing} 个版位尚未采纳 ▾</button>${S.miss?`<div class="menu">${(r.pending_placements||[]).map(p=>`<div>${esc(p.name)}<span>本次可不纳入图包</span></div>`).join('')}</div>`:''}</div>`:'';
  const progress=viewWorkStatus(r);
  const cardWidth=Math.max(320,...groups.map(g=>{const p=plOf(g.pid);return Math.ceil(rowh*p.target_width/p.target_height*p.image_count+6*(p.image_count-1)+34)}));
  const bulk=bulkSelectionState(r);
  const selectionBar=`<div class="selection-bar"><label class="select-all"><input id="select-visible" type="checkbox" aria-label="全选当前列表" aria-checked="${bulk.mixed?'mixed':bulk.all?'true':'false'}" ${bulk.all?'checked':''} ${!bulk.scope.length||S.selectionBusy?'disabled':''} onchange="selectVisible(this.checked)"><span>全选当前列表</span></label><button class="ghost" id="clear-visible" ${!bulk.selected||S.selectionBusy?'disabled':''} onclick="clearVisibleSelection()">取消选择</button><span class="selection-count">已选 ${groups.filter(g=>selectedSet(r,g)).length} 套</span></div>`;
  const visible=channelGroups.filter(filters[S.pf]||filters.all);
  const legacy=r.planning_source==='simulation'?`<div class="planning-notice"><span>历史模拟结果，尚未使用新的画面规划</span><button onclick="dupTask()">复制并重新规划</button></div>`:'';
  const planError=r.planning_status==='failed'?`<div class="planning-error" role="alert"><span>${esc(r.planning_error||'画面规划未完成')}</span><button onclick="retryPlanning()">重试规划</button></div>`:'';
  const sections=r.params.pids.filter(pid=>visible.some(g=>g.pid===pid)).map(pid=>{
    const p=plOf(pid),gs=visible.filter(g=>g.pid===pid).sort((a,b)=>a.n-b.n),all=groups.filter(g=>g.pid===pid);
    return`<section class="placement-section"><div class="placement-head"><div><b>${esc(pname(p))}</b><span>${psz(p)} · ${all.filter(g=>g.sl.every(s=>s.state==='done')).length}/${all.length}套已生成</span></div><button ${['queued','running'].includes(r.planning_status)||all.length>=20?'disabled':''} onclick="addVariant('${pid}')">＋ 再出一套</button></div><div class="suite-grid" style="--card-width:${cardWidth}px">${gs.map(g=>{
      const on=selectedSet(r,g),ip=ipOfSet(r.params,g.n),ready=g.sl.some(s=>s.state==='done'),broken=g.sl.some(s=>['failed','blocked_first_failed','stopped'].includes(s.state)||!s.delivery_eligible&&s.delivery_eligible!==undefined)&&!g.sl.some(s=>s.state==='generating');
      return`<section class="set ${on?'chosen':''}" data-set="${g.n}" data-placement="${g.pid}" aria-label="${esc(pname(p))} · 套 ${g.n}" onclick="pickCardClick(event,${g.n},'${g.pid}')"><div class="sethead"><div><b>方案 ${g.n}</b><span class="meta">${ip?esc(ip.label):''}</span></div><label class="set-check" title="${on?'取消选择':'选择这一套'}"><input type="checkbox" data-sel="${g.id}" aria-label="选择 ${esc(pname(p))} 套 ${g.n}" ${on?'checked':''} ${!ready||S.selectionBusy?'disabled':''} onchange="toggleSel(${g.n},false,'${g.pid}')"></label></div><div class="wall" style="--rowh:${rowh}px"><div class="pg"><div class="imgs">${g.sl.map(s=>cellHtml(r,s,rowh)).join('')}</div><div class="cap">${psz(p)} · ${g.sl.length}张${g.sl.some(s=>s.state==='done'&&s.delivery_eligible===false)?`<button class="lnk" onclick="openPv('${g.sl.find(s=>s.delivery_eligible===false).id}')">处理适配</button>`:broken?`<button class="lnk" onclick="repairSet('${pid}',${g.n})">补齐这套</button>`:''}</div></div></div>${g.sl.some(s=>s.reason_code==='frame_failed')?'<div class="set-notice">尚未适配到目标尺寸。查看大图后可重新去框或整图适配。</div>':g.sl.some(s=>s.reason_code==='frame_review')?'<div class="set-notice">尺寸已适配，可查看成品与原图对比。</div>':''}</section>`;
    }).join('')}</div></section>`;
  }).join('');
  return`${legacy}${planError}${progress}<div class="toolbar">${tabs}<div class="tright">${filter}${missingHtml}</div></div>${selectionBar}<div id="sets">${sections||'<div class="tnone">没有符合筛选条件的套图</div>'}</div>`;
}
function viewSelectionFooter(){
  const r=R();if(!r)return'';const d=r.delivery||{};
  const partial=d.incomplete_sets>0&&d.ready_sets>0;
  const saveButton=partial?`<button id="save-ready" class="primary" ${S.exportBusy?'disabled':''} onclick="dlAll(true)">${S.exportBusy?'正在保存…':'保存可交付的 '+d.ready_sets+' 套'}</button>`:`<button id="save-selected" class="primary" ${!d.can_export||S.exportBusy?'disabled':''} onclick="dlAll()">${S.exportBusy?'正在保存…':d.matching_version?'再次保存 '+d.matching_version:d.next_version?'保存 '+d.next_version:d.selected_sets?'暂无可保存套图':'请选择图片'}</button>`;
  return`<div class="selection-footer"><div><b>已选 ${d.selected_sets||0} 套</b><span>可交付 ${d.ready_sets||0} 套 · 覆盖 ${d.covered_placements||0}/${d.total_placements||r.params.pids.length} 个版位</span>${partial?`<small>另 ${d.incomplete_sets} 套待处理，不纳入本次图包</small>`:''}${d.last_version?`<small>已保存 ${d.last_version}${d.has_changes?' · 选择已变更':''}</small>`:''}</div><div class="row">${d.incomplete_sets?`<button onclick="locateIncomplete()">处理 ${d.incomplete_sets} 套</button>`:''}${d.last_version?'<button onclick="openFolder()">打开文件夹</button>':''}${saveButton}</div></div>`;
}

function viewDl(){
  const t=T();if(!t)return'';
  return`<div class="history-head"><h3>交付记录</h3><button onclick="go('pick')">返回挑选</button></div>${[...t.pkgs].reverse().map(p=>`<div class="card delivery-record"><div class="pkrow"><b>v${String(p.v).padStart(3,'0')}</b><span class="muted pkname">${esc(p.zip)}</span><span class="muted">${new Date(p.created_at*1000).toLocaleString('zh-CN')}</span><button onclick="redl(${p.v})">下载副本</button></div><div class="ths">${(p.images||[]).map(image=>`<button class="delivery-thumb" onclick="openPv('${image.id}',${image.att})"><img src="${image.thumbnail_url}" alt="查看交付图片第${image.att}版"></button>`).join('')}</div></div>`).join('')||'<div class="tnone">还没有保存的图包</div>'}`;
}

function roundLabel(r,i,count){const name=(IMAGE_MODEL_OPTIONS.find(x=>x[0]===(r.image_model||IMAGE_MODEL_OPTIONS[0][0]))||IMAGE_MODEL_OPTIONS[0])[1];return '第'+(i+1)+'轮'+(i===count-1?' · 本轮':'')+' · '+name+' · '+(r.params.image_form||'')+(r.created_at?' · '+new Date(r.created_at*1000).toLocaleString('zh-CN'):'')}
function summaryRow(t){const menu=S.menu===t.id;return `<li class="trow ${menu?'mopen':''}">${S.ren===t.id?`<input id="renin" aria-label="任务名" value="${esc(S.renV??t.name)}" oninput="S.renV=this.value" onkeydown="if(event.key==='Enter')renOk();if(event.key==='Escape')renEnd()" onblur="renOk()">`:`<button class="task ${S.cur===t.id?'on':''}" data-task="${t.id}" onclick="openTask('${t.id}')">${t.thumbnail_url?`<img src="${t.thumbnail_url}" alt="">`:'<span class="noimg"></span>'}<div><div class="t1">${esc(t.name)}</div><div class="t2">${esc(t.status)} · ${t.done}/${t.total}</div><div class="t3">${esc(t.image_form||'')} · ${t.round_count}轮${t.archived?' · 已归档':''}</div></div></button>`}<button class="more" aria-label="更多操作" onclick="openMenu('${t.id}')">⋯</button>${menu?`<div class="tmenu"><button onclick="renStart('${t.id}')">重命名</button><button onclick="dupFrom('${t.id}')">复制为新任务</button><button ${t.active?'disabled':''} onclick="archiveTask('${t.id}',${!t.archived})">${t.archived?'取消归档':'归档'}</button><button ${t.active?'disabled':''} onclick="delTask('${t.id}')">删除任务及候选</button></div>`:''}</li>`}
