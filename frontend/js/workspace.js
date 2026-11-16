/* Stable navigation and read-only aggregation; execution stays with source APIs. */
const WORKSPACE={items:[],total:0,counts:{},next:null,page:1,pageSize:10,cursors:[''],q:'',kind:'',state:'',loading:false,loaded:false,error:'',serial:0,lastRead:0,expandedPackage:null,details:{}};
const WORKSPACE_PAGES=['tasks','deliveries','settings','maintenance'];
const WORKSPACE_TYPES={ordinary:'普通出图',learning:'学习机整套',shared:'多尺寸适配'};
let workspaceSearchTimer;
function workspaceJs(value){return esc(JSON.stringify(String(value)))}
function workspaceIcon(name){
 const paths={tasks:'M7 4h10v14H3V4h4m0-2h6v4H7zM7 10h6M7 14h6',logo:'M3 3h14v14H3zM3 13l5-5 4 4 2-2 3 3',delivery:'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14m0 3v4l3 2',settings:'M7 3h6l1 3 3 1v6l-3 1-1 3H7l-1-3-3-1V7l3-1zM10 7a3 3 0 1 0 0 6 3 3 0 0 0 0-6',maintenance:'M3 5c0-4 14-4 14 0s-14 4-14 0m0 0v10c0 4 14 4 14 0V5M3 10c0 4 14 4 14 0',plus:'M10 3v14M3 10h14',file:'M5 2h7l4 4v12H4V2h1m7 0v5h4M7 11h6M7 14h6',search:'M8 3a5 5 0 1 0 0 10 5 5 0 0 0 0-10m4 9 5 5'};
 return `<svg class="ui-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name]||paths.file}"/></svg>`;
}
function workspaceActive(){return ['form','pick','dl','learning-run'].includes(S.view)?'tasks':S.view==='learning-logo'?'logo':S.view}
function viewWorkspaceSide(){
 const nav=[['tasks','制作任务'],['logo','Logo模板'],['deliveries','交付记录'],['settings','模型与设置'],['maintenance','数据维护']];
 return `<aside class="workspace-sidebar"><div class="workspace-brand"><span class="workspace-brandmark"><img src="${esc(LOGO.thumb||'/api/learning-machine/logo-assets/learning.logo.black')}" alt=""></span><strong>广告图工作台</strong><span class="local-tag">LOCAL</span></div><nav aria-label="主导航">${nav.map(([key,label])=>`<button data-workspace-nav="${key}" aria-label="${label}" title="${label}" class="${workspaceActive()===key?'active':''}" aria-current="${workspaceActive()===key?'page':'false'}" onclick="${key==='logo'?'openLearningLogoConfig()':`openWorkspacePage('${key}')`}">${workspaceIcon(key==='logo'?'logo':key==='deliveries'?'delivery':key==='tasks'?'tasks':key)}<span>${label}</span></button>`).join('')}</nav><div class="workspace-sidebar-foot"><button id="sidebar-toggle" class="workspace-collapse" aria-label="${S.sidebarCollapsed?'展开导航':'收起导航'}" aria-expanded="${!S.sidebarCollapsed}" onclick="toggleSidebar()">${S.sidebarCollapsed?'→':'←'}</button><span class="service-dot ${S.connectionLost?'lost':''}"></span><span>${S.connectionLost?'本机服务未连接':'本机服务已连接'}</span><small>${esc(globalThis.location?.host||'本机工作台')}</small>${S.undo?`<div class="undo-notice">任务已删除 <button onclick="undoDel()">撤销</button></div>`:''}</div></aside>`;
}
function viewWorkspaceTopbar(){
 const names={tasks:'制作任务',deliveries:'交付记录',settings:'模型与设置',maintenance:'数据维护','learning-logo':'Logo模板',form:'新建任务',pick:'成品挑选',dl:'任务图包','learning-run':(typeof LEARNING_RUNS!=='undefined'?LEARNING_RUNS.current?.name:null)||'制作详情'};
 const child=['form','pick','dl','learning-run'].includes(S.view);
 return `<div id="workspace-topbar"><nav aria-label="当前位置"><button onclick="openWorkspacePage('tasks')">${child?'制作任务':'工作台'}</button><span>/</span><strong>${esc(names[S.view]||'制作任务')}</strong></nav><span class="workspace-service ${S.connectionLost?'lost':''}"><i></i>${S.connectionLost?'无法连接本机服务':'本机服务已连接'}</span></div>`;
}
function viewWorkspaceHead(){
 const titles={tasks:['制作任务','管理广告图片、学习机整套与多尺寸适配。'],deliveries:['交付记录','查看已经保存的图包及其来源版本。'],settings:['模型与设置','新设置用于后续提交，已有任务沿用冻结配置。'],maintenance:['本机数据维护','备份、恢复与清理未采用的旧版本。']};
 if(!titles[S.view])return null;
 const [title,note]=titles[S.view];
 return `<header class="head workspace-page-head" id="head"><div><h1>${title}</h1><p>${note}</p></div>${S.view==='tasks'?`<button class="primary" id="newbtn" ${S.navigationPending?'disabled':''} onclick="newTask()">${workspaceIcon('plus')}新建任务</button>`:''}</header>`;
}
async function openWorkspacePage(view){
 if(!WORKSPACE_PAGES.includes(view)||S.submitting||S.navigationPending)return;
 if(S.view==='learning-logo'&&S.learningLogoDirty)return toast('请先保存Logo模板，或重新读取已保存配置');
 const previous=S.view,epoch=beginNavigation();if(epoch===null)return;
 try{
  await persistDraft();await persistPromptDraft();if(epoch!==viewEpoch)return;
  S.view=view;S.cur=null;S.draftId=null;S.editing=null;S.learningRunId=null;S.pv=null;S.pvDetails=null;S.learningImagePreview=null;S.cfgOpen=false;S.maintenanceOpen=false;S.menu=null;
  WORKSPACE.serial++;WORKSPACE.items=[];WORKSPACE.loaded=false;WORKSPACE.error='';WORKSPACE.expandedPackage=null;resetWorkspacePagination();
  if(previous!==view){WORKSPACE.q='';WORKSPACE.kind='';WORKSPACE.state=''}S.workspaceRenameKey=null;save(false);render();document.getElementById('main')?.scrollTo?.(0,0);
  if(view==='settings'){await loadWorkspaceSettings();}
  else if(view==='maintenance'){await loadMaintenance();}
  else await loadWorkspaceItems();
 }catch(e){if(epoch===viewEpoch)report(e)}finally{finishNavigation(epoch)}
}
function resetWorkspacePagination(){WORKSPACE.page=1;WORKSPACE.cursors=[''];WORKSPACE.next=null;WORKSPACE.expandedPackage=null}
function workspaceQuery(cursor=WORKSPACE.cursors[WORKSPACE.page-1]||''){
 const query=new URLSearchParams({q:WORKSPACE.q,kind:WORKSPACE.kind,state:S.view==='tasks'?WORKSPACE.state:'',limit:String(WORKSPACE.pageSize)});
 if(cursor)query.set('cursor',cursor);return query;
}
async function loadWorkspaceItems(unused=false,quiet=false,targetPage=WORKSPACE.page){
 if(!['tasks','deliveries'].includes(S.view))return;
 const page=S.view,epoch=viewEpoch,serial=++WORKSPACE.serial,query=workspaceQuery(WORKSPACE.cursors[targetPage-1]||'');
 WORKSPACE.loading=true;WORKSPACE.error='';if(!quiet)render();
 try{
  const route='/workbench/'+(page==='tasks'?'items':'packages');
  let data=await request(route+'?'+query);
  if(epoch!==viewEpoch||page!==S.view||serial!==WORKSPACE.serial)return;
  // Deleting the last item on a later page returns to the previous valid page.
  while(!data.items.length&&targetPage>1){
   targetPage--;data=await request(route+'?'+workspaceQuery(WORKSPACE.cursors[targetPage-1]||''));
   if(epoch!==viewEpoch||page!==S.view||serial!==WORKSPACE.serial)return;
  }
  WORKSPACE.page=targetPage;WORKSPACE.cursors=WORKSPACE.cursors.slice(0,targetPage);
  WORKSPACE.items=data.items;WORKSPACE.total=data.total;WORKSPACE.counts=data.counts||{};WORKSPACE.next=data.next_cursor;WORKSPACE.loaded=true;WORKSPACE.lastRead=Date.now();
  if(data.queue)S.queue=data.queue;S.connectionLost=false;
 }catch(e){if(epoch===viewEpoch&&serial===WORKSPACE.serial){WORKSPACE.error=e.message;S.connectionLost=/fetch|连接|Network/i.test(e.message)}}
 finally{if(epoch===viewEpoch&&serial===WORKSPACE.serial){WORKSPACE.loading=false;render()}}
}
async function turnWorkspacePage(direction){
 if(WORKSPACE.loading||![-1,1].includes(direction))return;
 const target=WORKSPACE.page+direction;
 if(target<1||direction===1&&!WORKSPACE.next)return;
 if(direction===1)WORKSPACE.cursors[target-1]=WORKSPACE.next;
 WORKSPACE.expandedPackage=null;await loadWorkspaceItems(false,false,target);
 document.getElementById('main')?.scrollTo?.(0,0);
}
function setWorkspaceFilter(key,value){if(!['q','kind','state'].includes(key))return;WORKSPACE[key]=value;WORKSPACE.serial++;resetWorkspacePagination();clearTimeout(workspaceSearchTimer);if(key==='q'){workspaceSearchTimer=setTimeout(()=>loadWorkspaceItems(),180)}else loadWorkspaceItems()}
function workspaceTime(value){const d=new Date(value*1000);return Number.isFinite(d.getTime())?d.toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}):'—'}
function workspaceTypeOptions(){return `<option value="">全部制作类型</option>${Object.entries(WORKSPACE_TYPES).map(([v,t])=>`<option value="${v}" ${WORKSPACE.kind===v?'selected':''}>${t}</option>`).join('')}`}
function workspaceTableTools(){return `<div class="workspace-table-tools"><label class="workspace-search">${workspaceIcon('search')}<input id="workspace-search" type="search" aria-label="搜索任务或文案" placeholder="${S.view==='tasks'?'搜索任务或文案':'搜索任务或图包'}" value="${esc(WORKSPACE.q)}" oninput="setWorkspaceFilter('q',this.value)"></label><select aria-label="筛选制作类型" onchange="setWorkspaceFilter('kind',this.value)">${workspaceTypeOptions()}</select></div>`}
function workspaceListFooter(){
 const pages=Math.max(1,Math.ceil(WORKSPACE.total/WORKSPACE.pageSize)),start=WORKSPACE.total?(WORKSPACE.page-1)*WORKSPACE.pageSize+1:0,end=WORKSPACE.total?start+WORKSPACE.items.length-1:0;
 return `<nav class="workspace-list-footer" aria-label="列表分页"><span>共 ${WORKSPACE.total} 条 · 每页 ${WORKSPACE.pageSize} 条${WORKSPACE.total?' · 当前 '+start+'–'+end+' 条':''}</span><div><button ${WORKSPACE.loading||WORKSPACE.page<=1?'disabled':''} onclick="turnWorkspacePage(-1)">上一页</button><span aria-live="polite">第 ${WORKSPACE.page} / ${pages} 页</span><button ${WORKSPACE.loading||!WORKSPACE.next?'disabled':''} onclick="turnWorkspacePage(1)">下一页</button></div></nav>`;
}
function workspaceEmpty(){return `<div class="workspace-empty">${workspaceIcon('file')}<h2>${WORKSPACE.q||WORKSPACE.kind||WORKSPACE.state?'没有匹配的记录':S.view==='deliveries'?'还没有保存的图包':'从第一份广告任务开始'}</h2><p>${WORKSPACE.q||WORKSPACE.kind||WORKSPACE.state?'调整关键词或筛选条件后再试。':S.view==='deliveries'?'完成制作后保存图包，交付版本会保留在这里。':'填写文案、确定画面，再选择需要的投放版位。'}</p>${WORKSPACE.q||WORKSPACE.kind||WORKSPACE.state?`<button onclick="clearWorkspaceFilters()">清除筛选</button>`:S.view==='tasks'?`<button class="primary" onclick="newTask()">新建任务</button>`:''}</div>`}
function clearWorkspaceFilters(){WORKSPACE.q='';WORKSPACE.kind='';WORKSPACE.state='';resetWorkspacePagination();loadWorkspaceItems()}
function workspaceThumb(row){return `<span class="workspace-thumb">${workspaceIcon('file')}${row.thumbnail_url?`<img src="${esc(row.thumbnail_url)}" alt="" loading="lazy" onerror="this.hidden=true">`:''}</span>`}
async function openWorkspaceItem(key){const r=WORKSPACE.items.find(r=>r.key===key);if(!r)return;if(r.source_type==='draft')return openDraft(r.id);if(r.source_type==='run')return openLearningRun(r.id);return openTask(r.id)}
function viewWorkspaceTaskRow(row){
 const editing=S.workspaceRenameKey===row.key,rename=`<input id="workspace-rename" aria-label="任务名" value="${esc(S.workspaceRenameValue||'')}" oninput="S.workspaceRenameValue=this.value" onkeydown="if(event.key==='Enter')saveWorkspaceRename();if(event.key==='Escape'){S.workspaceRenameKey=null;render()}"><button onclick="saveWorkspaceRename()">保存</button>`;
 const labels=row.status==='draft'?'尚未提交':`${row.done}/${row.total}张`;
 return `<tr data-workspace-key="${esc(row.key)}"><td><div class="workspace-name">${workspaceThumb(row)}<div>${editing?rename:`<button class="workspace-name-link" onclick="openWorkspaceItem(${workspaceJs(row.key)})">${esc(row.name)}</button>`}<small>${esc([Array.isArray(row.channel)?'多渠道':row.channel,row.image_form].filter(Boolean).join(' · '))}</small></div></div></td><td>${WORKSPACE_TYPES[row.type]}</td><td><span class="status-pill ${row.status}">${esc(row.status_label)}</span><small class="workspace-progress">${labels}</small></td><td class="workspace-time">${workspaceTime(row.updated_at)}</td><td><div class="workspace-row-actions"><button class="link-button" onclick="openWorkspaceItem(${workspaceJs(row.key)})">${row.source_type==='draft'?'继续编辑':row.status==='attention'?'处理':'打开'}</button>${row.source_type!=='run'?`<details class="workspace-row-menu" ontoggle="positionWorkspaceMenu(this)"><summary aria-label="${esc(row.name)}更多操作">⋯</summary><div role="menu">${row.source_type==='task'?`<button role="menuitem" onclick="beginWorkspaceRename(${workspaceJs(row.key)})">重命名</button><button role="menuitem" onclick="duplicateWorkspaceTask(${workspaceJs(row.key)})">复制为新任务</button>`:''}<button role="menuitem" class="danger" ${row.active?'disabled':''} onclick="deleteWorkspaceItem(${workspaceJs(row.key)})">删除</button></div></details>`:''}</div></td></tr>`;
}
function viewWorkspaceTasks(){
 const tabs=[['','全部任务'],['draft','草稿'],['running','制作中'],['ready','待操作'],['attention','待处理'],['completed','已完成']];
 return `<section class="card workspace-table-panel" id="workspace-task-panel"><div class="workspace-table-heading"><div class="workspace-tabs" role="tablist" aria-label="任务状态">${tabs.map(([value,label])=>`<button role="tab" aria-selected="${WORKSPACE.state===value}" onclick="setWorkspaceFilter('state','${value}')">${label}${Number(WORKSPACE.counts[value||'all'])?`<small>${WORKSPACE.counts[value||'all']}</small>`:''}</button>`).join('')}</div>${workspaceTableTools()}</div>${WORKSPACE.error?`<div role="alert" class="inline-error">${esc(WORKSPACE.error)} <button onclick="loadWorkspaceItems()">重新读取</button></div>`:''}${!WORKSPACE.loaded&&WORKSPACE.loading?'<div class="workspace-list-skeleton" role="status">正在读取本机任务…</div>':WORKSPACE.items.length?`<div class="workspace-table-scroll"><table class="workspace-table"><thead><tr><th>任务名称</th><th>制作类型</th><th>进度与状态</th><th>更新时间</th><th>操作</th></tr></thead><tbody>${WORKSPACE.items.map(viewWorkspaceTaskRow).join('')}</tbody></table></div>${workspaceListFooter()}`:workspaceEmpty()+workspaceListFooter()}</section>`;
}
function beginWorkspaceRename(key){const r=WORKSPACE.items.find(r=>r.key===key);if(!r||r.source_type!=='task')return;S.workspaceRenameKey=key;S.workspaceRenameValue=r.name;render();document.getElementById('workspace-rename')?.focus()}
async function saveWorkspaceRename(){const row=WORKSPACE.items.find(r=>r.key===S.workspaceRenameKey);if(!row)return;try{await request('/tasks/'+row.id,'PATCH',{name:S.workspaceRenameValue});S.workspaceRenameKey=null;await loadWorkspaceItems()}catch(e){report(e)}}
async function duplicateWorkspaceTask(key){const r=WORKSPACE.items.find(r=>r.key===key);if(!r)return;await openTask(r.id);if(S.cur===r.id)await dupTask()}
async function deleteWorkspaceItem(key){const row=WORKSPACE.items.find(r=>r.key===key);if(!row||row.active)return;try{if(row.source_type==='draft')await removeDraft(row.id);else await delTask(row.id);S.view='tasks';save(false);await loadWorkspaceItems()}catch(e){report(e)}}
async function toggleWorkspacePackage(key){WORKSPACE.expandedPackage=WORKSPACE.expandedPackage===key?null:key;render();if(!WORKSPACE.expandedPackage||WORKSPACE.details[key])return;const row=WORKSPACE.items.find(r=>r.key===key);if(!row)return;try{const detail=await request('/workbench/packages/'+row.source_type+'/'+row.source_id+'/'+row.id);WORKSPACE.details[key]=detail}catch(e){WORKSPACE.details[key]={error:e.message}}if(S.view==='deliveries'&&WORKSPACE.expandedPackage===key)render()}
async function openWorkspacePackageSource(key){const r=WORKSPACE.items.find(r=>r.key===key);if(!r)return;return r.source_type==='run'?openLearningRun(r.source_id):openTask(r.source_id)}
async function openWorkspacePackageFolder(key){const r=WORKSPACE.items.find(r=>r.key===key);if(!r)return;try{await request((r.source_type==='task'?'/tasks/':'/learning-machine/runs/')+r.source_id+'/open-folder','POST',{})}catch(e){report(e)}}
function viewWorkspacePackageRow(row){const open=WORKSPACE.expandedPackage===row.key,details=WORKSPACE.details[row.key];return `<tr class="${open?'expanded':''}"><td><button class="workspace-name-link" onclick="openWorkspacePackageSource(${workspaceJs(row.key)})">${esc(row.name)}</button><small class="workspace-progress">${WORKSPACE_TYPES[row.type]}</small></td><td>v${String(row.version).padStart(3,'0')}</td><td>${row.image_count}张${row.format}</td><td>${row.logo_asset_id?logoVariantLabel(row.logo_asset_id):'按各图配置'}</td><td class="workspace-time">${workspaceTime(row.updated_at)}</td><td><div class="workspace-row-actions"><a href="${esc(row.download_url)}" download>下载图包</a><button class="link-button" onclick="openWorkspacePackageFolder(${workspaceJs(row.key)})">打开文件夹</button><button class="link-button" aria-expanded="${open}" onclick="toggleWorkspacePackage(${workspaceJs(row.key)})">${open?'收起':'详情'}</button></div></td></tr>${open?`<tr><td colspan="6"><div class="workspace-package-detail"><div class="section-heading"><h3>来源与版本</h3><button class="link-button" onclick="openWorkspacePackageSource(${workspaceJs(row.key)})">查看来源任务</button></div><p class="field-help">以下图片读取图包实际文件；后续重出不会覆盖旧图包。</p>${details?.error?`<p class="inline-error">${esc(details.error)}</p>`:details?`<div class="package-thumbnails">${details.images.map(im=>`<a href="${esc(im.image_url)}" target="_blank"><img src="${esc(im.image_url)}" alt="图包第${im.index+1}张图片" loading="lazy"><span>${esc(plOf(im.placement_id)?.platform||im.placement_id)}${im.width?' · '+im.width+'×'+im.height:''}${im.version?' · 第'+im.version+'版':''}</span></a>`).join('')}</div>`:'<p role="status">正在核对图包文件…</p>'}</div></td></tr>`:''}`}
function viewWorkspaceDeliveries(){return `<section class="card workspace-table-panel"><div class="workspace-table-heading">${workspaceTableTools()}</div>${WORKSPACE.error?`<p class="inline-error" role="alert">${esc(WORKSPACE.error)}</p>`:''}${!WORKSPACE.loaded&&WORKSPACE.loading?'<div class="workspace-list-skeleton" role="status">正在读取交付记录…</div>':WORKSPACE.items.length?`<div class="workspace-table-scroll"><table class="workspace-table workspace-packages"><thead><tr><th>来源任务</th><th>图包版本</th><th>图片数与格式</th><th>Logo款式</th><th>保存时间</th><th>操作</th></tr></thead><tbody>${WORKSPACE.items.map(viewWorkspacePackageRow).join('')}</tbody></table></div>${workspaceListFooter()}`:workspaceEmpty()+workspaceListFooter()}</section>`}
async function loadWorkspaceSettings(){const epoch=viewEpoch;const [settings,st]=await Promise.all([request('/settings'),request('/storage')]);if(epoch!==viewEpoch||S.view!=='settings')return;applySettings(settings);storage=st;S.settingsTab=S.settingsTab||'image';S.cfgOpen=false;render()}
function setWorkspaceSettingsTab(tab){S.settingsTab=tab;document.querySelectorAll('[data-settings-section]').forEach(e=>e.hidden=e.dataset.settingsSection!==tab);document.querySelectorAll('[data-settings-tab]').forEach(e=>e.setAttribute('aria-selected',String(e.dataset.settingsTab===tab)))}
function viewWorkspaceSettings(){
 const tab=S.settingsTab||'image';
 return `<div class="settings-tabs workspace-tabs" role="tablist" aria-label="设置分类">${[['planning','画面规划'],['image','图片生成'],['general','保存与通用']].map(([key,label])=>`<button role="tab" data-settings-tab="${key}" aria-selected="${tab===key}" onclick="setWorkspaceSettingsTab('${key}')">${label}</button>`).join('')}</div><div class="settings-layout"><fieldset id="workspace-settings-form" ${S.settingsSaving?'disabled':''}><section class="card settings-section" data-settings-section="planning" ${tab==='planning'?'':'hidden'}><h2>画面规划</h2><label class="settings-field">语言模型<input id="planmodel" maxlength="128" value="${esc(CFG.planningModel||'')}"></label><label class="settings-field">规划 Key<div><div class="input-action"><input type="password" id="plankey" autocomplete="off" placeholder="${CFG.planningKey?'已配置，留空保留':'填写规划Key'}"><button id="plantest" onclick="testPlanning()">测试连接</button></div><span id="planst" role="status"></span></div></label><label class="settings-field">接口地址<input id="planbase" value="${esc(CFG.planningBase||'')}"></label></section><section class="card settings-section" data-settings-section="image" ${tab==='image'?'':'hidden'}><h2>图片生成</h2><label class="settings-field">默认图片模型<select id="cfgimagemodel">${imageModelOptions(CFG.imageModel)}</select></label><label class="settings-field">KIE Key<div><div class="input-action"><input type="password" id="kiekey" autocomplete="off" placeholder="${CFG.kie?'已配置，留空保留':'填写KIE Key'}" oninput="imageKeyEntered()"><button id="kietest" onclick="testConn()">测试连接</button></div><span id="kiest" role="status">${connTx('kie')||'尚未测试'}</span></div></label><label class="settings-field">普通任务默认输出<select id="cfgimagemode" onchange="document.getElementById('simulation-warning').hidden=this.value!=='simulation'"><option value="real" ${!CFG.simulation?'selected':''}>真实生图</option><option value="simulation" ${CFG.simulation?'selected':''}>模拟预览</option></select></label><p class="field-help" id="simulation-warning" ${CFG.simulation?'':'hidden'}>普通模拟仅替代图片，画面规划仍会调用模型；学习机本机演练全程离线。</p><details class="settings-advanced"><summary>高级接口配置</summary><label class="settings-field">生图接口<input id="kbase" value="${esc(CFG.base)}"></label><label class="settings-field">上传接口<input id="kup" value="${esc(CFG.up)}"></label></details></section><section class="card settings-section" data-settings-section="general" ${tab==='general'?'':'hidden'}><h2>保存与通用</h2><label class="settings-field">保存位置<div class="input-action"><input id="cfgpath" value="${esc(CFG.path)}"><button onclick="chooseFolder()">选择文件夹</button></div></label><div class="settings-field"><span>暂存占用</span><div id="stor">${storHtml()}</div></div></section><div class="settings-actions"><button class="primary" id="cfgsave" onclick="saveCfg()">保存设置</button><button onclick="loadWorkspaceSettings()">取消修改</button><span id="settings-save-state" role="status"></span></div></fieldset><aside class="card settings-help"><h3>配置作用范围</h3><p>新设置用于后续提交；正在执行的任务沿用原配置。</p><p>保存设置不会提交生图。测试规划连接会发起一次简短模型请求。</p></aside></div>`;
}
function viewWorkspaceMaintenance(){return `<div class="workspace-maintenance">${viewMaintenanceContent()}</div>${viewMaintenanceConfirmation()}`}
function viewWorkspacePage(){if(S.view==='tasks')return viewWorkspaceTasks();if(S.view==='deliveries')return viewWorkspaceDeliveries();if(S.view==='settings')return viewWorkspaceSettings();if(S.view==='maintenance')return viewWorkspaceMaintenance();return null}
function viewPageContent(){const page=typeof viewWorkspacePage==='function'?viewWorkspacePage():null;if(page!==null)return page;if(S.view==='learning-run')return viewLearningRun();if(S.view==='learning-logo')return viewLearningLogoConfig();if(S.openingTask)return viewPick();if(S.view==='form')return viewForm();if(S.view==='pick')return viewOrdinaryWorkspace();return viewDl()}
function showSelectionFooter(){return S.view==='pick'&&!S.openingTask&&(!S.ordinaryStage||S.ordinaryStage==='results')}
function setOrdinaryStage(stage){if(!['results','progress','packages'].includes(stage))return;S.ordinaryStage=stage;render()}
function viewOrdinaryWorkspace(){const stage=S.ordinaryStage||'results';return `<div class="task-stage-tabs workspace-tabs" role="tablist" aria-label="普通任务阶段">${[['results','成品挑选'],['progress','制作进度'],['packages','交付记录']].map(([key,label])=>`<button role="tab" aria-selected="${stage===key}" onclick="setOrdinaryStage('${key}')">${label}</button>`).join('')}</div>${stage==='packages'?viewDl():stage==='progress'?viewOrdinaryProgress():viewPick()}`}
function viewOrdinaryProgress(){const r=R();if(!r)return '';const status=workStatus(r);return `<section class="card production-progress"><div class="section-heading"><div><h2>${esc(status.title)}</h2><p class="field-help">${esc(status.note||'已提交图片继续收取结果，未开始的任务按队列执行。')}</p></div><button onclick="setOrdinaryStage('results')">查看已有成品</button></div>${r.planning_error?`<p class="inline-error">${esc(r.planning_error)} <button onclick="retryPlanning()">重试规划</button></p>`:''}<div class="workspace-table-scroll"><table class="workspace-table"><thead><tr><th>版位 / 套图</th><th>图片</th><th>状态</th><th>操作</th></tr></thead><tbody>${r.slots.map(s=>`<tr><td>${esc(pname(plOf(s.pid)))} · 第${s.set}套</td><td>图${s.idx}</td><td>${esc(waitLabel(r,s))}</td><td>${r.generation_disabled?`<button class="link-button" onclick="editRedo()">按新规则重新制作</button>`:s.query_required?`<button class="link-button" onclick="resumeImage('${s.id}')">恢复查询</button>`:isFail(r,s)?`<button class="link-button" onclick="repairSet('${s.pid}',${s.set})">补齐这套</button>`:s.state==='done'?`<button class="link-button" onclick="openPv('${s.id}')">查看图片</button>${viewOrdinaryRepeatAction(r,s)}`:'—'}</td></tr>`).join('')}</tbody></table></div></section>`}

async function refreshWorkspacePage(){
 lastRefreshAt=Date.now();
 if(['tasks','deliveries'].includes(S.view)){if(!WORKSPACE.loading&&!S.workspaceRenameKey&&!document.querySelector('.workspace-row-menu[open]'))return loadWorkspaceItems(false,true);return}
 const epoch=viewEpoch;try{const q=await request('/queue');if(epoch!==viewEpoch)return;S.queue=q;S.connectionLost=false}catch(e){if(epoch===viewEpoch)S.connectionLost=true}
 const status=document.querySelector('.workspace-service');if(status){status.classList.toggle('lost',!!S.connectionLost);status.innerHTML='<i></i>'+(S.connectionLost?'无法连接本机服务':'本机服务已连接')}
}


function positionWorkspaceMenu(details){
 if(!details?.open)return;
 const menu=details.querySelector('[role="menu"]'),anchor=details.querySelector('summary');if(!menu||!anchor)return;
 for(const other of document.querySelectorAll('.workspace-row-menu[open]'))if(other!==details)other.open=false;
 const a=anchor.getBoundingClientRect(),r=menu.getBoundingClientRect(),width=document.documentElement.clientWidth,height=document.documentElement.clientHeight;
 if(a.bottom<0||a.top>height){details.open=false;return}
 menu.style.left=Math.max(8,Math.min(a.right-r.width,width-r.width-8))+'px';
 menu.style.top=Math.max(8,Math.min(a.bottom+r.height+8<=height?a.bottom+8:a.top-r.height-8,height-r.height-8))+'px';
 menu.style.right='auto';menu.style.bottom='auto';
}
function closeWorkspaceMenus(target=null){for(const d of document.querySelectorAll?.('.workspace-row-menu[open]')||[])if(!target||!d.contains(target))d.open=false}
document.addEventListener('click',event=>closeWorkspaceMenus(event.target));
document.addEventListener('keydown',event=>{if(event.key==='Escape')closeWorkspaceMenus()});
document.addEventListener('scroll',()=>{for(const d of document.querySelectorAll?.('.workspace-row-menu[open]')||[])positionWorkspaceMenu(d)},true);
window.addEventListener('resize',()=>{for(const d of document.querySelectorAll?.('.workspace-row-menu[open]')||[])positionWorkspaceMenu(d)});
