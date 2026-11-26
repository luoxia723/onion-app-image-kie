const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {webcrypto}=require('node:crypto');
const {loadScripts,currentCatalog,currentLearningConfig}=require('./helpers/workbench.cjs');
function setup(service=async()=>({items:[],total:0,counts:{},next_cursor:null})){
 const calls=[],context=vm.createContext({crypto:webcrypto,TextEncoder,URLSearchParams,structuredClone,setTimeout,clearTimeout,btoa,location:{host:'127.0.0.1:9876'},
 document:{activeElement:null,hidden:false,addEventListener(){},getElementById(){return null},querySelector(){return null},querySelectorAll(){return[]}},window:{addEventListener(){}},history:{replaceState(){}},service,calls});
 loadScripts(context,['views','learning-machine','learning-runs','master-canvases','drafts','prompt-drafts','maintenance','workspace','production','app']);
 const run=code=>vm.runInContext(code,context);context.catalog=currentCatalog();context.config=currentLearningConfig();
 run(`PLACEMENTS=catalog;installLearningMachineConfig(config);render=()=>{};softRender=()=>{};toast=()=>{};report=()=>{};persistDraft=async()=>{};persistPromptDraft=async()=>{};request=(...args)=>{calls.push(args);return service(...args)};S.view='tasks'`);
 return {run,context,calls};
}
test('侧栏显示实际端口，顶栏显示连接状态',()=>{
 const {run}=setup();const html=run('viewWorkspaceSide()');
 assert.equal((html.match(/data-workspace-nav=/g)||[]).length,5);assert(html.includes('127.0.0.1:9876'));assert(!html.includes('draft-list'));
 assert(run('viewWorkspaceTopbar()').includes('本机服务已连接'));
 run('S.connectionLost=true');assert(run('viewWorkspaceTopbar()').includes('无法连接本机服务'));
});
test('Logo模板入口列出应用商店、信息流和学习机，不只显示学习机模板',()=>{
 const {run}=setup();run('S.view="learning-logo"');const html=run('viewLearningLogoConfig()');
 for(const label of ['应用商店','信息流','学习机'])assert(html.includes(label),label+'应有独立模板入口');
});
test('普通渠道Logo模板可筛选并保存位置，沿用独立修订且不改学习机规则',async()=>{
 const config={revision:3,logo_assets:currentLearningConfig().logo_assets,placements:currentCatalog().filter(p=>p.category!=='学习机').map(p=>({...p,logo_required:true,logo_template:{asset_id:'learning.logo.black',x:.03,y:.02,width:.2}}))};
 const calls=[];const {run,context}=setup(async(path,method,body)=>{calls.push([path,method,body]);if(method==='PUT'){config.revision++;for(const t of body.templates)config.placements.find(p=>p.id===t.placement_id).logo_template=t}return structuredClone(config)});
 const original=run('JSON.stringify(LEARNING_MACHINE.templates)');await run('setLogoTemplateCategory("信息流")');
 assert.equal(run('learningLogoPlacements().length'),8);assert(run('viewLearningLogoConfig()').includes('微博粉丝通'));
 run('setLogoTemplatePlatform("喜马拉雅")');assert.equal(run('matchingLearningLogoPlacements("").length'),5);
 run('chooseLearningLogoPlacement("weibo-current-single-1280x720");setLearningLogoValue("x",7)');await run('saveLearningLogoTemplates()');
 const put=calls.find(c=>c[1]==='PUT');assert.equal(put[0],'/logo-templates');assert.equal(put[2].revision,3);assert.equal(put[2].templates.length,19);
 assert.equal(put[2].templates.find(p=>p.placement_id==='weibo-current-single-1280x720').x,.07);
 assert.equal(run('JSON.stringify(LEARNING_MACHINE.templates)'),original);assert.equal(run('ORDINARY_LOGOS.revision'),4);assert.equal(run('PLACEMENTS.filter(p=>p.category==="信息流").length'),8);
 run('S.draft.channel="信息流";S.draft.pids=["weibo-current-single-1280x720"];S.draft.logo_asset_id="learning.logo.black";setLogoSelection("auto");S.visualOpen=true');
 assert.equal(run('S.draft.noLogo'),false);assert.equal(run('S.draft.logo_asset_id'),undefined);assert.match(run('viewVisualOptions(S.draft)'),/value="auto" selected>添加 Logo/);
});
test('Logo版位列表按八条翻页，渠道和搜索重置页码且保留编辑参数',()=>{
 const {run,context}=setup();const list={innerHTML:''};context.document.getElementById=id=>id==='learning-logo-directory-list'?list:null;
 run('S.logoTemplateCategory="学习机";viewLearningLogoConfig();turnLogoDirectoryPage(1)');assert.equal(run('S.logoDirectoryPage'),2);assert(!list.innerHTML.includes('data-logo-placement="learning-baidu-512x512"'));
 const original=run('JSON.stringify(LEARNING_MACHINE.templates)');run('filterLearningLogoPlacements("百度")');assert.equal(run('S.logoDirectoryPage'),1);assert(list.innerHTML.includes('learning-baidu-512x512'));assert.equal(run('JSON.stringify(LEARNING_MACHINE.templates)'),original);
});
test('任务和交付记录始终显示页码与上一页下一页，少于一页时禁用翻页',()=>{
 const {run}=setup();run('WORKSPACE.total=0;WORKSPACE.loaded=true');const html=run('workspaceListFooter()');
 assert(html.includes('上一页'));assert(html.includes('下一页'));assert(html.includes('第 1 / 1 页'));
 assert.equal((html.match(/disabled/g)||[]).length,2);
});
test('列表使用全范围聚合接口，类型与状态筛选不提交生成动作',async()=>{
 const {run,calls}=setup();run('WORKSPACE.q="不会的题";WORKSPACE.kind="learning";WORKSPACE.state="ready"');await run('loadWorkspaceItems()');
 assert.equal(calls.length,1);const q=new URLSearchParams(calls[0][0].split('?')[1]);assert.equal(q.get('q'),'不会的题');assert.equal(q.get('kind'),'learning');assert.equal(q.get('state'),'ready');assert.equal(calls[0][1],undefined);
});
test('搜索结果乱序和离页后旧响应均不覆盖最后一次选择',async()=>{
 const pending=[];const {run}=setup(()=>new Promise(resolve=>pending.push(resolve)));
 const first=run('loadWorkspaceItems()');run('WORKSPACE.q="new"');const last=run('loadWorkspaceItems()');pending[1]({items:[{key:'run:new'}],total:1});await last;pending[0]({items:[{key:'task:old'}],total:1});await first;
 assert.equal(run('WORKSPACE.items[0].key'),'run:new');
 const leaving=run('loadWorkspaceItems()');run('viewEpoch++;S.view="learning-logo"');pending[2]({items:[{key:'stale'}],total:1});await leaving;assert.equal(run('WORKSPACE.items[0].key'),'run:new');
});
test('明确翻页替换当前十条，轮询保留当前页，上一页返回后筛选从第一页开始',async()=>{
 const {run,calls}=setup(async path=>{const cursor=new URLSearchParams(path.split('?')[1]).get('cursor'),start=cursor==='ten'?10:0;return{items:Array.from({length:start?9:10},(_,i)=>({key:'task:'+(start+i)})),total:19,next_cursor:start?null:'ten'}});
 await run('loadWorkspaceItems()');assert.equal(run('WORKSPACE.items.length'),10);assert.equal(new URLSearchParams(calls[0][0].split('?')[1]).get('limit'),'10');
 await run('turnWorkspacePage(1)');assert.equal(run('WORKSPACE.page'),2);assert.equal(run('WORKSPACE.items[0].key'),'task:10');assert.equal(run('WORKSPACE.items.length'),9);
 await run('loadWorkspaceItems(false,true)');assert.equal(new URLSearchParams(calls.at(-1)[0].split('?')[1]).get('cursor'),'ten');assert.equal(run('WORKSPACE.page'),2);
 await run('turnWorkspacePage(-1)');assert.equal(run('WORKSPACE.items[0].key'),'task:0');assert.equal(run('WORKSPACE.page'),1);
 await run('turnWorkspacePage(1)');run('setWorkspaceFilter("kind","learning")');await new Promise(resolve=>setImmediate(resolve));assert.equal(run('WORKSPACE.page'),1);assert.equal(new URLSearchParams(calls.at(-1)[0].split('?')[1]).get('cursor'),null);
});
test('翻页失败不清空当前记录或跳页，删除末页唯一记录后退回前页',async()=>{
 let fail=false,deleted=false;const {run}=setup(async path=>{if(fail)throw Error('Network error');const cursor=new URLSearchParams(path.split('?')[1]).get('cursor');return{items:cursor?(deleted?[]:[{key:'last'}]):[{key:'first'}],total:deleted?10:11,next_cursor:cursor?null:'last-page'}});
 await run('loadWorkspaceItems()');fail=true;await run('turnWorkspacePage(1)');assert.equal(run('WORKSPACE.page'),1);assert.equal(run('WORKSPACE.items[0].key'),'first');
 fail=false;await run('turnWorkspacePage(1)');assert.equal(run('WORKSPACE.page'),2);deleted=true;await run('loadWorkspaceItems()');assert.equal(run('WORKSPACE.page'),1);assert.equal(run('WORKSPACE.items[0].key'),'first');
});
test('统一记录打开时按来源路由分发，不按名称或同形ID混用任务',async()=>{
 const {run,context}=setup();context.rows=[{key:'draft:same',id:'same',source_type:'draft'},{key:'task:same',id:'same',source_type:'task'},{key:'run:same',id:'same',source_type:'run'}];
 run('WORKSPACE.items=rows;opened=[];openDraft=async id=>opened.push("draft:"+id);openTask=async id=>opened.push("task:"+id);openLearningRun=async id=>opened.push("run:"+id)');
 for(const kind of ['draft','task','run'])await run(`openWorkspaceItem('${kind}:same')`);assert.deepEqual(Array.from(run('opened')),['draft:same','task:same','run:same']);
});
test('任务中心读取失败保留上次记录，并明确显示错误而非成功空态',async()=>{
 const {run}=setup(async()=>{throw Error('Network error')});run('WORKSPACE.items=[{key:"task:keep",name:"旧记录",source_type:"task",status:"ready",type:"ordinary",done:1,total:1,updated_at:1}];WORKSPACE.loaded=true');await run('loadWorkspaceItems()');
 assert.equal(run('WORKSPACE.items.length'),1);assert.equal(run('S.connectionLost'),true);assert(run('viewWorkspaceTasks()').includes('Network error'));assert(run('viewWorkspaceTasks()').includes('旧记录'));
});
test('学习机组合确认只在明确点击后先确认再扩套，查看页签不触发生成',async()=>{
 const fixture={id:'r',name:'基准',mode:'simulation',status:'waiting_for_confirmation',busy:false,revision:1,params:{pids:[],t1:'主题',cta:'点击下载'},baseline:{id:'baseline',status:'done',version:1,sha256:'sha',image_url:'/base.png'},approval:null,outputs:[],masters:[],suite:{status:'not_started'},packages:[],counts:{}};
 let current=fixture;const {run,context,calls}=setup(async path=>{if(path.endsWith('/confirm'))current={...current,approval:{confirmed:true,mode:'simulation',baseline_version:1,sha256:'sha'}};return current});context.fixture=fixture;
 run('installLearningRun(fixture);S.view="learning-run";setLearningStage("baseline");setLearningStage("progress")');assert.equal(calls.length,0);await run('confirmAndExpandLearningRun()');
 assert.deepEqual(calls.map(c=>c[0]),['/learning-machine/runs/r/confirm','/learning-machine/runs/r/expand']);assert.equal(calls[0][2].baseline_version,1);
});
test('实际提示词与编辑草稿分开，历史版本不开放编辑或重出',()=>{
 const {run,context}=setup();context.slot={id:'s',pid:'weibo-current-single-1280x720',set:1,idx:1,state:'done',att:2,prompt:'真实已发送 <文案>',orig:'原始',image_url:'/v2.jpg',is_historical:true,history:[{att:1,image_url:'/v1.jpg'},{att:2,image_url:'/v2.jpg'}]};
 run('S.cur="t";S.view="pick";S.tasks=[{id:"t",ri:0,rounds:[{params:{pids:[slot.pid]},slots:[slot],sel:{}}]}];S.pv="s";S.pvDetails=slot;S.promptDraft={id:"s",value:"草稿不得覆盖实际提示词"}');
 const html=run('viewPv()');assert.match(html,/id="pvActualPrompt"[^>]*>真实已发送 &lt;文案&gt;/);assert(!html.includes('id="pv-edit-prompt"'));assert.match(html,/id="pvredo"[^>]*disabled/);assert(html.includes('草稿不得覆盖实际提示词'));
});
test('学习机本机导出失败在卡片直接显示重试按钮，避免只藏在更多菜单和空白占位',()=>{
 const {run,context}=setup();context.output={id:'learning-dsl-rounded-card-484x580::1',placement_id:'learning-dsl-rounded-card-484x580',width:484,height:580,version:1,status:'failed',error:'PNG大小超限',background_repair_pending:true,background_repair_key:'same-key',recovery_action:'retry_export',image_url:null};
 context.fixture={id:'r',mode:'real',outputs:[context.output]};
 const html=run('viewProductionOutput(fixture,output,false,true)');
 assert(html.includes('重新压缩并导出'));assert(html.includes('class="learning-output-actions"><button class="primary"'));
 assert(html.includes('不调用AI'));assert(!html.includes('style="aspect-ratio:484/580"'));
});
test('已完成学习机图片的重出直接显示在详情旁，历史版与制作中禁用且不显示空菜单',()=>{
 const {run,context}=setup();context.output={id:'one',placement_id:'learning-baidu-512x512',width:512,height:512,version:2,status:'done',image_url:'/two.png',versions:[{version:1,status:'done',image_url:'/one.png'}]};context.fixture={id:'r',mode:'real',outputs:[context.output]};
 let html=run('viewProductionOutput(fixture,output,false,true)');
 const button=html.match(/<button[^>]*id="learning-output-regenerate-one"[^>]*>重出本图<\/button>/)?.[0];
 assert(button,'直接显示重出本图按钮');assert(!button.includes('disabled'));assert(button.includes('learningRunAction'));assert(!html.includes('class="output-more"'));
 assert(html.indexOf('learning-output-detail-one')<html.indexOf('learning-output-regenerate-one'));
 html=run('viewProductionOutput(fixture,output,true,true)');assert.match(html,/<button[^>]*id="learning-output-regenerate-one"[^>]*disabled/);
 run('S.learningOutputVersions={one:1}');html=run('viewProductionOutput(fixture,output,false,true)');assert.match(html,/<button[^>]*id="learning-output-regenerate-one"[^>]*disabled/);
});
function ordinaryActionFixture(){
 const pid='weibo-current-single-1280x720',slot={id:'ordinary-one',pid,set:1,idx:1,att:3,state:'done',image_url:'/image.png'};
 const round={id:'round',simulation:true,planning_status:'done',params:{channel:'信息流',image_form:'单图',pids:[pid],sets:1},slots:[slot],sel:{}};
 return {id:'ordinary-task',name:'已有广告',ri:0,rounds:[round],pkgs:[]};
}
test('普通成品卡片可直接重出，首图说明后续范围，依赖生成中时禁用',()=>{
 const {run,context,calls}=setup();context.task=ordinaryActionFixture();run('S.cur=task.id;S.view="pick";S.tasks=[task]');
 let html=run('cellHtml(R(),R().slots[0])');assert(html.includes('repeatOrdinaryImage'));assert(html.includes('重出本张'));assert(!html.includes('<details'));
 run('PLACEMENTS.find(p=>p.id===R().slots[0].pid).image_count=2;R().slots.push({...R().slots[0],id:"child",idx:2,first_id:"ordinary-one"})');
 html=run('cellHtml(R(),R().slots[0])');assert(html.includes('重出图 1 及后续图'));
 run('R().slots[1].state="generating"');assert.match(run('viewOrdinaryRepeatAction(R(),R().slots[0])'),/disabled/);assert.equal(calls.length,0);
});
test('普通卡片重出保留图片版本门禁且连续点击只提交一次原接口',async()=>{
 let release;const task=ordinaryActionFixture();const {run,context,calls}=setup(()=>new Promise(resolve=>release=resolve));context.task=task;run('S.cur=task.id;S.view="pick";S.tasks=[task]');
 const first=run('repeatOrdinaryImage("ordinary-one")');await run('repeatOrdinaryImage("ordinary-one")');assert.equal(calls.length,1);
 assert.equal(calls[0][0],'/tasks/ordinary-task/regenerate');assert.deepEqual(JSON.parse(JSON.stringify(calls[0][2])),{round:0,image_id:'ordinary-one',expected_att:3});
 release(task);await first;assert.equal(run('S.ordinaryImageActionPending'),false);
});
test('普通队列暂停继续和停止直接在顶栏，混合选择可直接清空',()=>{
 const {run,context}=setup();context.task=ordinaryActionFixture();run('S.cur=task.id;S.view="pick";S.tasks=[task];R().slots[0].state="generating"');
 let header=run('viewHead()').split('<details class="pick-more"')[0];assert(header.includes('暂停后续'));assert(header.includes('停止后续提交'));
 run('R().paused=true');header=run('viewHead()').split('<details class="pick-more"')[0];assert(header.includes('继续队列'));
 run('R().paused=false;R().slots[0].state="done";R().slots.push({...R().slots[0],id:"second-set",set:2});R().sel={"weibo-current-single-1280x720::1":true}');
 const html=run('viewPick()');assert(html.includes('id="clear-visible"'));assert(!html.includes('class="selection-options"'));
});
function readyActionRun(){
 return {id:'learning-actions',name:'现有批次',mode:'real',busy:false,status:'completed',baseline:{id:'baseline',status:'done',version:1,sha256:'sha',image_url:'/base.png'},approval:{confirmed:true,baseline_version:1,sha256:'sha',mode:'real'},params:{t1:'正文',cta:'点击下载'},suite:{status:'completed',baseline_version:1},masters:[],outputs:[{id:'one',placement_id:'learning-baidu-512x512',status:'done',version:2,width:512,height:512,logo_required:true,image_url:'/two.png',versions:[{version:1,status:'done',image_url:'/one.png'}]}],packages:[]};
}
test('背景调整与Logo应用直接显示，未知背景仍只有恢复入口',()=>{
 const {run,context,calls}=setup();context.fixture=readyActionRun();run('installLearningRun(fixture);fixture.outputs[0].processing={method:"ai_background_expansion"}');
 let html=run('viewProductionOutput(fixture,fixture.outputs[0],false,true)');assert(html.includes('再次调整背景（AI）'));assert(!html.includes('<details'));
 html=run('viewProductionDelivery(fixture,false)');assert(html.includes('id="learning-refresh-logos"'));assert(!html.includes('<details'));
 run('fixture.outputs[0].background_repair_pending=true;fixture.outputs[0].query_required=true;fixture.outputs[0].status="failed"');
 html=run('viewProductionOutput(fixture,fixture.outputs[0],false,true)');assert(html.includes('恢复背景适配查询'));assert(!html.includes('learningRunAction(\'regenerate\''));assert.equal(calls.length,0);
});
test('学习机详情可直接重出且保持历史只读，详情与卡片按钮ID不冲突',()=>{
 const {run,context,calls}=setup();context.fixture=readyActionRun();run('installLearningRun(fixture);S.learningImagePreview={kind:"output",id:"one",version:2};S.learningRunId=fixture.id');
 let html=run('viewLearningImageDetails(fixture)');assert(html.includes('id="learning-detail-regenerate-one"'));assert(!/id="learning-detail-regenerate-one"[^>]*disabled/.test(html));
 run('S.learningImagePreview.version=1');html=run('viewLearningImageDetails(fixture)');assert.match(html,/id="learning-detail-regenerate-one"[^>]*disabled/);assert(html.includes('历史版本只读'));
 run('S.learningImagePreview={kind:"baseline",id:"baseline",version:1}');assert(run('viewLearningImageDetails(fixture)').includes('重新生成基准图'));assert.equal(calls.length,0);
});
test('共用母版行无须展开记录即可重试，母版详情历史版不能重扩',()=>{
 const {run,context,calls}=setup();context.fixture=readyActionRun();run('fixture.kind="shared_canvas_adaptation";fixture.target_kind="learning";fixture.masters=[{id:"M1",group_id:"M1",version:2,status:"done",versions:[{version:1,status:"done"}]}];installLearningRun(fixture);S.learningExpandedMaster=null');
 let html=run('viewProductionProgress(fixture,false)');assert(html.includes('重新扩展此母版（AI）'));assert(!html.includes('class="production-master-detail"'));
 run('S.learningImagePreview={kind:"master",id:"M1",version:1}');html=run('viewLearningImageDetails(fixture)');assert.match(html,/<button disabled[^>]*onclick="regenerateSharedCanvasMaster/);assert.equal(calls.length,0);
});

test('设置保存期间保持输入快照，离页后的响应不重画新页面',async()=>{
 let release;const {run,context,calls}=setup(()=>new Promise(resolve=>release=resolve));let renders=0;
 const values={cfgimagemodel:'model',kiekey:'new-fake-key',cfgimagemode:'simulation',plankey:'',planbase:'https://planner.invalid',planmodel:'planner',cfgpath:'/temporary/output',kbase:'https://image.invalid',kup:'https://upload.invalid'};
 const controls=Object.fromEntries(Object.entries(values).map(([id,value])=>['#'+id,{value,isConnected:true}]));controls['#workspace-settings-form']={disabled:false,isConnected:true};controls['#cfgsave']={disabled:false,isConnected:true};
 context.document.querySelector=selector=>controls[selector]||null;context.renderCount=()=>renders++;
 run('S.view="settings";render=renderCount');const saving=run('saveCfg()');assert.equal(controls['#workspace-settings-form'].disabled,true);
 assert.equal(calls[0][0],'/settings');assert.equal(calls[0][2].simulation,true);assert.equal(calls[0][2].kie_api_key,'new-fake-key');
 run('viewEpoch++;S.view="tasks"');release({simulation:true,key_configured:true});await saving;
 assert.equal(renders,0);assert.equal(controls['#workspace-settings-form'].disabled,false);assert.equal(run('S.settingsSaving'),false);
});

test('进入全局页面清除当前来源路由，但不删除草稿或运行记录',async()=>{
 const {run}=setup();run('S.cur="ordinary";S.draftId="draft";S.learningRunId="run";S.editing="ordinary"');await run('openWorkspacePage("deliveries")');
 assert.equal(run('S.view'),'deliveries');for(const field of ['cur','draftId','learningRunId','editing'])assert.equal(run('S.'+field),null);
});
test('带旧task或draft参数的设置URL刷新后仍打开设置，避免跳回旧任务',async()=>{
 const {run,context,calls}=setup(async path=>path==='/bootstrap'?{placements:[],assets:{ips:[],logos:[],fonts:[],styles:[]},form_defaults:{},product:{}}:path==='/drafts'?{drafts:[]}:path==='/storage'?{used_bytes:0}:{simulation:true});
 context.location.hash='#view=settings&task=old-task&draft=old-draft';context.setInterval=()=>0;
 await run('boot()');assert.equal(run('S.view'),'settings');assert(!calls.some(c=>c[0].includes('/tasks/old-task')||c[0].includes('/drafts/old-draft')));
});

test('表格末行菜单在视口内向上展开，离开视口后关闭而非被表格裁掉',()=>{
 const {run,context}=setup();const style={};let top=740;
 const anchor={getBoundingClientRect:()=>({left:900,right:930,top,bottom:top+30})},menu={style,getBoundingClientRect:()=>({width:165,height:126})};
 const details={open:true,querySelector:q=>q==='summary'?anchor:menu};context.details=details;context.document.documentElement={clientWidth:1024,clientHeight:768};context.document.querySelectorAll=()=>[details];
 run('positionWorkspaceMenu(details)');assert(parseFloat(style.top)+126<=768);assert(parseFloat(style.left)+165<=1024);assert(parseFloat(style.top)<740);
 top=900;run('positionWorkspaceMenu(details)');assert.equal(details.open,false);
});

test('固定自然画布规则在编辑器可见，退役流程只提供重新配置入口',()=>{
 const {run,context}=setup();context.slot={id:'s',pid:'weibo-current-single-1280x720',set:1,idx:1,state:'done',att:1,prompt:'真实提示词',orig:'真实提示词',image_url:'/one.jpg',canvas_fixed_rule:'完整自然画布与安全区',history:[{att:1,image_url:'/one.jpg'}]};
 run('S.cur="t";S.tasks=[{id:"t",ri:0,rounds:[{params:{pids:[slot.pid]},slots:[slot],sel:{}}]}];S.pv="s";S.pvDetails=slot');
 assert(run('viewPv()').includes('画幅固定规则'));assert(run('viewPv()').includes('完整自然画布与安全区'));
 run('R().generation_disabled=true');assert(run('viewPv()').includes('id="pv-new-generation"'));assert(!run('viewPv()').includes('id="pvredo"'));const retired=run('viewPick()');assert(retired.includes('按新规则重新制作'));assert(!retired.includes('class="add-variant"'));assert(!retired.includes('class="sample-repeat"'));
 context.fixture=readyActionRun();run('fixture.outputs[0].status="failed";fixture.outputs[0].background_repair_pending=true;fixture.outputs[0].recovery_action="retired_flow"');
 const html=run('viewProductionOutput(fixture,fixture.outputs[0],false,true)');assert(html.includes('按新规则重新配置'));assert(!html.includes('onclick="repairLearningOutputBackground'));
});
