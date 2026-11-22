const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {webcrypto}=require('node:crypto');
const {loadScripts,currentCatalog,currentLearningConfig}=require('./helpers/workbench.cjs');

function sharedRun(extra={}){
 const baseline={id:'baseline',version:1,status:'done',sha256:'source-hash',image_url:'/source1.png',prompt:'历史来源原提示词'};
 return {id:'shared-run',kind:'shared_canvas_adaptation',target_kind:'ordinary',name:'来源套图多尺寸',revision:1,mode:'simulation',status:'baseline_confirmed',busy:false,
  params:{pids:['oppo-2'],image_model:'new-target-model'},baseline,baseline_versions:[],approval:{confirmed:true,baseline_version:1,sha256:'source-hash',mode:'simulation'},
  source_summary:{image_count:2,copy_basis:'frozen_task_copy'},source_images:[{image_index:1,width:1280,height:720,image_url:'/source1.png'},{image_index:2,width:1280,height:720,image_url:'/source2.png'}],
  counts:{master_count:2,expected_new_calls:2,output_count:2},suite:{status:'not_started',baseline_version:1},masters:[],outputs:[],packages:[],
  crop_plan:[{id:'M1',aspect_ratio:'3:1',source_index:1,target_ids:['target::1'],shared_keep_box:[.1,.1,.9,.9],allowed_text:{t1:'第一句 <script>不可执行</script>',cta:'点击下载'}},{id:'M2',aspect_ratio:'3:1',source_index:2,target_ids:['target::2'],shared_keep_box:[.1,.1,.9,.9],allowed_text:{t1:'第二句'}}],...extra};
}
function setup(service=async()=>sharedRun()){
 const messages=[];const context=vm.createContext({crypto:webcrypto,structuredClone,TextEncoder,URLSearchParams,setTimeout,clearTimeout,btoa,service,messages,
  document:{activeElement:null,hidden:false,addEventListener(){},querySelector(){return null},querySelectorAll(){return[]},getElementById(){return null}},window:{addEventListener(){}},history:{replaceState(){}}});
 loadScripts(context,['views','learning-machine','learning-runs','master-canvases','drafts','prompt-drafts','maintenance','app']);
 context.catalog=currentCatalog();context.config=currentLearningConfig();
 const execute=code=>vm.runInContext(code,context);
 execute(`PLACEMENTS=catalog;installLearningMachineConfig(config);render=()=>{};softRender=()=>{};toast=message=>messages.push(message);report=error=>messages.push(error.message);request=(...args)=>service(...args);persistDraft=async()=>{};persistPromptDraft=async()=>{};S.cur='ordinary-task';S.view='pick';S.tasks=[{id:'ordinary-task',ri:0,rounds:[{id:'old-round',simulation:true,params:{pids:['source-pair'],image_form:'双图',sets:1},placement_rules:{'source-pair':{id:'source-pair',platform:'冻结来源渠道',name:'双图',category:'应用商店',image_form:'双图',image_count:2,target_width:1280,target_height:720}},sel:{},slots:[{id:'second',pid:'source-pair',set:1,idx:2,state:'done',att:4,image_url:'/second-v4.png',original_image_url:'/second-raw.png'},{id:'first',pid:'source-pair',set:1,idx:1,state:'done',att:3,image_url:'/first-v3.png',original_image_url:'/first-raw.png'}]}]}]`);
 return {context,execute,messages};
}
test('普通来源固定同一版位整套当前N张与各版本，目标仅普通同图数且不调用模型',async()=>{
 const calls=[];const {execute}=setup(async(...args)=>{calls.push(args);return sharedRun()});
 const source=execute('masterCanvasOrdinarySource("first")');assert.deepEqual(Array.from(source.source.image_ids),['first','second']);assert.equal(source.source.atts.first,3);assert.equal(source.source.atts.second,4);assert.equal(source.count,2);
 await execute('openMasterCanvasFromOrdinary("first")');assert.equal(calls.length,0);
 assert(execute('S.masterCanvasDialog.targets.every(p=>p.category!=="学习机"&&p.image_count===2)'));assert(execute('S.masterCanvasDialog.targets.length')>0);
 const dialog=execute('viewMasterCanvasDialog()');assert(dialog.includes('完整2张'));assert(dialog.includes('先创建计划，不自动提交图片模型'));
 await execute('createMasterCanvasRun()');assert.equal(calls.length,1);assert.equal(calls[0][0],'/master-canvases');assert.equal(calls[0][2].target_kind,'ordinary');assert.deepEqual(Array.from(calls[0][2].source.image_ids),['first','second']);assert(!calls.some(call=>call[0].includes('/expand')));assert.equal(execute('S.learningRunId'),'shared-run');
});
test('历史版本和不合格套图拒绝作来源，完整套图可显式选择模型原始画布',async()=>{
 const {execute}=setup();execute('S.pv="first";S.pvDetails={...R().slots.find(s=>s.id==="first"),att:2,is_historical:true}');
 assert(execute('masterCanvasOrdinarySource("first").error').includes('当前图片版本'));
 execute('S.pv=null;S.pvDetails=null;R().slots.find(s=>s.id==="second").state="generating"');assert(execute('masterCanvasOrdinarySource("first").error'));
 execute('R().slots.find(s=>s.id==="second").state="done";R().slots.find(s=>s.id==="first").delivery_eligible=false');assert(execute('masterCanvasOrdinarySource("first").error'));
 execute('R().slots.find(s=>s.id==="first").delivery_eligible=true');await execute('openMasterCanvasFromOrdinary("first")');
 let html=execute('viewMasterCanvasDialog()');assert(html.includes('使用模型原始画布'));
 const key=execute('S.masterCanvasDialog.key');execute('setMasterCanvasUseRaw(true)');assert.notEqual(execute('S.masterCanvasDialog.key'),key);assert.equal(execute('S.masterCanvasDialog.source.use_raw'),true);assert(execute('viewMasterCanvasDialog()').includes('/first-raw.png'));
});
test('学习机基准和单图来源锁定当前版本，选择对话框不提交模型或自动扩套',()=>{
 const calls=[];const {context,execute}=setup(async(...args)=>calls.push(args));const run=sharedRun({id:'learning-run',mode:'real',kind:undefined,target_kind:undefined,params:{pids:['learning-baidu-512x512']},outputs:[{id:'one',status:'done',version:2,width:512,height:512,platform:'百度',image_url:'/one-v2.png'}]});run.approval.mode='real';context.run=run;
 execute('installLearningRun(run);S.cur=null;S.view="learning-run";openMasterCanvasFromLearningBaseline()');assert.equal(execute('S.masterCanvasDialog.source.baseline_version'),1);assert.deepEqual(Array.from(execute('S.masterCanvasDialog.pids')),['learning-baidu-512x512']);
 execute('closeMasterCanvasDialog();openMasterCanvasFromLearningOutput("one",1)');assert.equal(execute('S.masterCanvasDialog'),null);
 execute('openMasterCanvasFromLearningOutput("one",2)');assert.equal(execute('S.masterCanvasDialog.source.versions.one'),2);assert.equal(execute('S.masterCanvasDialog.targets.length'),44);assert.equal(calls.length,0);
});
test('shared运行显示完整来源/文案/裁切计划，隐藏无文案基准动作且沿用图包Logo控件',async()=>{
 const calls=[];const {context,execute}=setup(async(path,method,body)=>{calls.push({path,body});return context.run});context.run=sharedRun({outputs:[{id:'target::1',placement_id:'target',platform:'OPPO',name:'冻结目标',width:474,height:768,status:'not_generated',version:0}]});
 execute('installLearningRun(run);S.cur=null;S.view="learning-run"');let html=execute('viewLearningRun()');assert(html.includes('来源图与共用母版'));assert(html.includes('/source1.png'));assert(html.includes('/source2.png'));assert(html.includes('生成共用母版'));assert(html.includes('预计新增2次图片模型调用'));assert(html.includes('第一句 &lt;script&gt;不可执行&lt;/script&gt;'));assert(html.includes('第二句'));assert(html.includes('冻结确认文字')||html.includes('冻结的确认文字'));assert(html.includes('474×768'));assert(!html.includes('<script>'));
 for(const id of ['learning-run-baseline','learning-run-confirm','learning-run-from-baseline'])assert(!html.includes('id="'+id+'"'),id);
 assert(html.includes('id="learning-export-logo"'));assert(!html.includes('历史来源原提示词'));assert(!execute('viewLearningRunHead()').includes('学习机制作'));assert(execute('viewLearningRunList()').includes('母版适配'));
 assert(!html.includes('id="learning-refresh-logos"'));
 await execute('refreshLearningRunLogos()');assert.equal(calls.length,0);
 await execute('learningRunAction("baseline")');await execute('learningRunAction("confirm")');await execute('makeLearningRunFromBaseline()');assert.equal(calls.length,0);
 await execute('learningRunAction("expand")');assert.equal(calls.length,1);assert(calls[0].path.endsWith('/expand'));
});
test('shared母版重扩只提交一组版本，未知沿原键查询，完成后下次使用新键',async()=>{
 const master={id:'M1',group_id:'M1',version:1,status:'done',prompt:'实际母版提示词'};let phase=0;const run=sharedRun({masters:[master]}),calls=[];
 const {context,execute}=setup(async(path,method,body)=>{calls.push({path,body});phase++;return {...run,masters:[phase===1?{...master,version:2,status:'failed',query_required:true,regeneration_key:body.idempotency_key}:{...master,version:phase+1,status:'done',query_required:false}]}});context.run=run;
 execute('installLearningRun(run);S.cur=null;S.view="learning-run"');assert(execute('viewSharedMasterRetry(run,run.masters[0])').includes('一次图片模型调用')===false); // Simulation states its actual zero-call scope.
 await execute('regenerateSharedCanvasMaster("M1")');assert.equal(calls[0].body.expected_version,1);assert(calls[0].path.endsWith('/masters/M1/regenerate'));
 assert(execute('viewSharedMasterRetry(LEARNING_RUNS.current,LEARNING_RUNS.current.masters[0])').includes('恢复母版查询'));
 await execute('regenerateSharedCanvasMaster("M1")');assert.equal(calls[1].body.expected_version,2);assert.equal(calls[0].body.idempotency_key,calls[1].body.idempotency_key);
 await execute('regenerateSharedCanvasMaster("M1")');assert.notEqual(calls[2].body.idempotency_key,calls[1].body.idempotency_key);
 execute('LEARNING_RUNS.current.kind=undefined');await execute('regenerateSharedCanvasMaster("M1")');assert.equal(calls.length,3);
});
test('目标或原图选择改变更新幂等键，未知创建失败保持原键以免重复计划',async()=>{
 const keys=[];let first=true;const {execute}=setup(async(path,method,body)=>{keys.push(body.idempotency_key);if(first){first=false;const error=new Error('response lost');error.status=500;throw error}return sharedRun()});
 await execute('openMasterCanvasFromOrdinary("first")');const oldKey=execute('S.masterCanvasDialog.key');execute('setMasterCanvasTargets(false)');assert.notEqual(execute('S.masterCanvasDialog.key'),oldKey);await execute('createMasterCanvasRun()');assert.equal(keys.length,0);
 execute('setMasterCanvasTargets(true)');await execute('createMasterCanvasRun()');assert.equal(execute('S.masterCanvasDialog.busy'),false);await execute('createMasterCanvasRun()');assert.equal(keys.length,2);assert.equal(keys[0],keys[1]);
});
test('普通整套和图片详情都有显式入口，旧版本详情禁用但不改变旧生成流程',()=>{
 const {execute}=setup();let html=execute('viewPick()');assert(html.includes('id="master-canvas-set-source-pair-1"'));assert(html.includes('openMasterCanvasFromOrdinary'));
 execute('S.pv="first";S.pvDetails={...R().slots.find(s=>s.id==="first"),prompt:"原提示词",orig:"原提示词",history:[],reference_images:[]}');html=execute('viewPv()');assert(html.includes('id="master-canvas-ordinary"'));assert(!html.match(/id="master-canvas-ordinary"[^>]*disabled/));
 execute('S.pvDetails.is_historical=true');html=execute('viewPv()');assert.match(html,/id="master-canvas-ordinary"[^>]*disabled/);
});
test('选择模拟来源时错误的真实模式计划不会被安装或自动执行',async()=>{
 const calls=[];const {execute}=setup(async(path)=>{calls.push(path);return sharedRun({mode:'real'})});await execute('openMasterCanvasFromOrdinary("first")');await execute('createMasterCanvasRun()');
 assert.deepEqual(calls,['/master-canvases']);assert.equal(execute('S.cur'),'ordinary-task');assert(execute('S.masterCanvasDialog.error').includes('模式与来源不一致'));
});
test('共享成品处理统计明确裁的是新母版，不将其当原来源图损失或视觉已验证',()=>{
 const {context,execute}=setup();context.row={processing:{method:'shared_canvas_crop',source_box_scope:'generated_shared_canvas',crop_percent:12.5,padding_percent:0,cv_detection_performed:false,visual_review_required:true,ai_repair_performed:false}};
 const html=execute('viewLearningProcessing(row)');assert(html.includes('从生成的共用母版裁出'));assert(html.includes('母版裁切 12.5%'));assert(html.includes('未进行自动内容检测'));assert(html.includes('待目视检查人物与文字'));assert(!html.includes('原图损失'));assert(!html.includes('视觉通过'));
});
