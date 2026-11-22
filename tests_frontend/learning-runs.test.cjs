const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {webcrypto}=require('node:crypto');
const {loadScripts,currentLearningConfig,currentCatalog}=require('./helpers/workbench.cjs');

function runFixture(extra={}){
 return {id:'run-one',name:'不会的题拍一下',revision:1,mode:'simulation',status:'configured',busy:false,
  params:{t1:'不会的题拍一下',cta:'点击下载',pids:['learning-baidu-512x512']},
  counts:{output_count:1,completed_outputs:0,master_count:1,completed_masters:0,planned_image_calls:2},
  baseline:{id:'baseline',version:0,status:'not_generated'},baseline_versions:[],approval:null,
  suite:{status:'not_started'},masters:[],outputs:[],packages:[],...extra};
}
function readyRun(extra={}){
 const baseline={id:'baseline',version:1,status:'done',sha256:'hash-one',image_url:'/api/learning-machine/runs/run-one/images/baseline/baseline?version=1',prompt:'基准图提示词'};
 return runFixture({status:'waiting_for_confirmation',baseline,...extra});
}
function approval(run){return {confirmed:true,baseline_version:run.baseline.version,sha256:run.baseline.sha256,mode:run.mode}}
function setup(service=async()=>runFixture()){
 const messages=[],hashes=[],downloads=[];
 const context=vm.createContext({crypto:webcrypto,structuredClone,TextEncoder,URLSearchParams,setTimeout,clearTimeout,btoa,
  document:{activeElement:null,hidden:false,addEventListener(){},getElementById(){return null},querySelector(){return null},querySelectorAll(){return[]}},
  window:{addEventListener(){}},history:{replaceState(a,b,value){hashes.push(value)}},service,messages,downloads});
 loadScripts(context,['views','learning-machine','learning-runs','drafts','prompt-drafts','maintenance','app']);
 const execute=code=>vm.runInContext(code,context);
 context.config=currentLearningConfig();context.catalog=currentCatalog();
 execute(`PLACEMENTS=catalog;installLearningMachineConfig(config);request=(...args)=>service(...args);render=()=>{};softRender=()=>{};toast=text=>messages.push(text);report=error=>messages.push(error.message);persistDraft=async()=>{};persistPromptDraft=async()=>{};downloadLink=url=>downloads.push(url);CFG={simulation:false,kie:false,planningKey:false,imageModel:'gpt-image-2-6/flare-image-to-image'};S.draft={...defParams(),channel:'学习机',t1:'不会的题拍一下',pids:['learning-baidu-512x512']}`);
 return {context,execute,messages,hashes,downloads};
}

test('学习机按钮只启动正式基准图，全局模拟设置不改变提交模式',async()=>{
 const calls=[];const {execute,hashes}=setup(async(path,method,body)=>{calls.push({path,method,body});return path.endsWith('/baseline')?runFixture({mode:'real',status:'generating_baseline',busy:true}):runFixture({mode:'real'})});
 execute('CFG.simulation=true;CFG.kie=true;CFG.planningKey=true');
 const html=execute('viewProductionStart()');
 assert.match(html,/id="learning-start-real"[^>]*>生成基准图/);
 assert.doesNotMatch(html,/learning-mode|本机演练|生成演练基准图/);
 await execute('startLearningRun()');
 assert.deepEqual(calls.map(x=>x.path),['/learning-machine/runs','/learning-machine/runs/run-one/baseline']);
 assert.equal(calls[0].body.mode,'real');assert(calls.every(x=>x.body.idempotency_key));
 assert.equal(execute('S.view'),'learning-run');assert.equal(execute('S.cur'),null);assert(hashes.at(-1).includes('view=learning-run&run=run-one'));
 assert.equal(execute('S.submitting'),false);
});
test('学习机正式制作先检查两个Key，缺配置不会创建运行',async()=>{
 const calls=[];const {execute,context}=setup(async(...args)=>{calls.push(args);return runFixture({mode:args[2]?.mode||'real'})});
 execute('opens=0;openCfg=async()=>{opens++}');await execute('startLearningRun()');
 assert.equal(calls.length,0);assert.equal(execute('opens'),1);
 context.real=runFixture({mode:'real'});execute('CFG.kie=true;CFG.planningKey=true');
 await execute('startLearningRun()');assert.equal(calls[0][2].mode,'real');
});
test('正式制作收到旧模拟模式响应时停止，不继续提交基准图',async()=>{
 const calls=[];const {execute,messages}=setup(async(path)=>{calls.push(path);return runFixture({mode:'simulation'})});
 execute('CFG.kie=true;CFG.planningKey=true');
 await execute('startLearningRun()');assert.deepEqual(calls,['/learning-machine/runs']);assert(messages.some(message=>message.includes('制作模式与请求不一致')));
});
test('确认基准图与扩展是分开的请求，模式/版本/哈希必须一致才解锁',async()=>{
 const calls=[];let current=readyRun();const {context,execute}=setup(async(path,method,body)=>{calls.push({path,body});if(path.endsWith('/confirm'))current={...current,approval:approval(current),status:'baseline_confirmed'};return structuredClone(current)});
 context.current=current;execute('installLearningRun(current);S.view="learning-run"');
 await execute('learningRunAction("expand")');assert.equal(calls.length,0);
 await execute('learningRunAction("confirm")');assert.equal(calls.length,1);assert(calls[0].path.endsWith('/confirm'));assert.equal(calls[0].body.baseline_version,1);
 await execute('learningRunAction("expand")');assert.equal(calls.length,2);assert(calls[1].path.endsWith('/expand'));
 execute('LEARNING_RUNS.current.approval.mode="real"');await execute('learningRunAction("expand")');assert.equal(calls.length,2);
});
test('查看旧基准时不能确认，基准生成中也不能确认',async()=>{
 const calls=[];const run=readyRun();const {context,execute}=setup(async(...args)=>{calls.push(args);return run});context.run=run;
 execute('installLearningRun(run);S.view="learning-run";S.learningBaselineVersion=0');await execute('learningRunAction("confirm")');assert.equal(calls.length,0);
 execute('S.learningBaselineVersion=null;LEARNING_RUNS.current.baseline.status="generating"');await execute('learningRunAction("confirm")');assert.equal(calls.length,0);
 const html=execute('viewLearningRun()');assert.match(html,/id="learning-run-confirm"[^>]*disabled/);assert.match(html,/id="learning-run-expand"[^>]*disabled/);
});
test('单张重出只提交目标输出与当前版本，不提交整组或覆盖其他结果',async()=>{
 const first={id:'learning-baidu-512x512::1',placement_id:'learning-baidu-512x512',platform:'百度',name:'广告图',image_index:1,width:512,height:512,status:'done',version:2,image_url:'/first.png',baseline_version:1};
 const second={...first,id:'second::1',image_url:'/second.png'};
 const run=readyRun({outputs:[first,second]});run.approval=approval(run);const calls=[];
 const {context,execute}=setup(async(path,method,body)=>{calls.push({path,body});return run});context.run=run;
 execute('installLearningRun(run);S.view="learning-run"');await execute('learningRunAction("regenerate","learning-baidu-512x512::1")');
 assert.equal(calls.length,1);assert(calls[0].path.includes('learning-baidu-512x512%3A%3A1/regenerate'));assert.equal(calls[0].body.expected_version,2);
 assert.equal(execute('LEARNING_RUNS.current.outputs[1].image_url'),'/second.png');
 execute('S.learningOutputVersions={"learning-baidu-512x512::1":1}');await execute('learningRunAction("regenerate","learning-baidu-512x512::1")');assert.equal(calls.length,1);
});
test('状态不明时发送恢复查询标记，成功提交后下一次显式操作换新幂等键',async()=>{
 const calls=[];const run=readyRun();run.baseline.query_required=true;
 const {context,execute}=setup(async(path,method,body)=>{calls.push({path,body});return structuredClone(run)});context.run=run;
 execute('installLearningRun(run);S.view="learning-run"');await execute('learningRunAction("baseline")');await execute('learningRunAction("baseline")');
 assert.equal(calls.length,2);assert(calls.every(call=>call.body.resume===true));assert.notEqual(calls[0].body.idempotency_key,calls[1].body.idempotency_key);
});
test('学习机轮询走独立详情和列表，离开页面后的迟到响应不能覆盖当前任务',async()=>{
 let release;const calls=[];const {context,execute}=setup(path=>{calls.push(path);return path==='/learning-machine/runs'?Promise.resolve({runs:[]}):new Promise(resolve=>release=resolve)});
 context.run=readyRun();execute('installLearningRun(run);S.view="learning-run"');const pending=execute('refresh()');
 execute('viewEpoch++;S.view="pick";S.cur="ordinary"');release(readyRun({revision:99}));await pending;
 assert(calls.every(path=>path.startsWith('/learning-machine/runs')));assert.equal(execute('S.cur'),'ordinary');assert.equal(execute('LEARNING_RUNS.current.revision'),1);
});
test('运行打开乱序时只安装最后一次选择，hash记录运行ID',async()=>{
 const waiting={};const {execute,hashes}=setup(path=>new Promise(resolve=>waiting[path]=resolve));
 const a=execute('openLearningRun("A")');await new Promise(setImmediate);const b=execute('openLearningRun("B")');await new Promise(setImmediate);
 waiting['/learning-machine/runs/B'](runFixture({id:'B'}));await b;waiting['/learning-machine/runs/A'](runFixture({id:'A'}));await a;
 assert.equal(execute('S.learningRunId'),'B');assert(hashes.at(-1).endsWith('view=learning-run&run=B'));
});
test('成品展示后端已合成图片，版本可查且不重复叠Logo或灰层',()=>{
 const output={id:'one',platform:'优学派',name:'横幅 <测试>',width:840,height:404,image_index:1,status:'done',version:2,image_url:'/composited-v2.png',baseline_version:2,versions:[{version:1,image_url:'/composited-v1.png',baseline_version:1}]};
 const run=readyRun({mode:'simulation',outputs:[output],name:'<script>alert(1)</script>'});run.approval=approval(run);
 const {context,execute}=setup();context.run=run;execute('installLearningRun(run);S.view="learning-run";S.learningOutputVersions={one:1}');
 const html=execute('viewLearningRun()');assert(html.includes('历史模拟记录'));assert(html.includes('/composited-v1.png'));assert(html.includes('横幅 &lt;测试&gt;'));assert(!html.includes('learning-logo-mask-overlay'));assert(html.includes('正在查看历史版本'));
 assert(!execute('viewLearningRunHead()').includes('<script>'));
});
test('只有全部成品完成才允许图包，下载使用服务返回地址并重读版本',async()=>{
 const run=readyRun({outputs:[{id:'one',platform:'百度',name:'广告',width:512,height:512,status:'done',version:1,image_url:'/done.png'}]});const calls=[];
 const pkg={id:'pkg',version:1,image_count:1,download_url:'/api/learning-machine/runs/run-one/images/package/pkg'};
 const {context,execute,downloads}=setup(async(path,method)=>{calls.push({path,method});return path.endsWith('/package')?pkg:{...run,packages:[pkg]}});context.run=run;
 execute('installLearningRun(run);S.view="learning-run"');assert(!execute('viewLearningRun()').match(/id="learning-run-package"[^>]*disabled/));await execute('packageLearningRun()');
 assert.deepEqual(calls.map(x=>x.path),['/learning-machine/runs/run-one/package','/learning-machine/runs/run-one']);assert.deepEqual(downloads,[pkg.download_url]);
 execute('LEARNING_RUNS.current.outputs[0].status="failed"');assert.match(execute('viewLearningRun()'),/id="learning-run-package"[^>]*disabled/);
 await execute('packageLearningRun()');assert.equal(calls.length,2);
});
test('已完成整套中的单张重出失败后仍可恢复未完成图片，不被旧suite状态永久锁住',async()=>{
 const output={id:'one',platform:'百度',name:'广告',width:512,height:512,status:'failed',version:2};
 const run=readyRun({outputs:[output],suite:{status:'completed',baseline_version:1},status:'failed'});run.approval=approval(run);
 const calls=[];const {context,execute}=setup(async(path,method,body)=>{calls.push({path,body});return run});context.run=run;
 execute('installLearningRun(run);S.view="learning-run"');let html=execute('viewLearningRun()');
 assert(!html.match(/id="learning-run-expand"[^>]*disabled/));assert(html.includes('恢复未完成图片'));
 await execute('learningRunAction("expand")');assert.equal(calls.length,1);assert(calls[0].path.endsWith('/expand'));
 execute('LEARNING_RUNS.current.outputs[0].status="done"');html=execute('viewLearningRun()');assert.match(html,/id="learning-run-expand"[^>]*disabled/);
});
test('修订号未变化时保留运行对象和页面，仅更新计时并合并并发轮询',async()=>{
 const calls=[];let release;const {context,execute}=setup(path=>{calls.push(path);return new Promise(resolve=>release=resolve)});context.run=readyRun();
 execute('installLearningRun(run);S.view="learning-run";LEARNING_RUNS.lastListAt=Date.now();renders=0;timers=0;softRender=()=>renders++;updTimers=()=>timers++');
 const original=execute('LEARNING_RUNS.current'),first=execute('refreshLearningRun()');await execute('refreshLearningRun()');
 assert.deepEqual(calls,['/learning-machine/runs/run-one?revision=1']);release({unchanged:true,id:'run-one',revision:1});await first;
 assert.equal(execute('LEARNING_RUNS.current'),original);assert.equal(execute('renders'),0);assert.equal(execute('timers'),1);assert.equal(execute('LEARNING_RUNS.loading'),false);
});
test('运行列表低频刷新，隐藏页面十秒内不重复拉列表',async()=>{
 const calls=[];const {context,execute}=setup(async path=>{calls.push(path);return path==='/learning-machine/runs'?{runs:[]}:{unchanged:true,id:'run-one',revision:1}});context.run=readyRun();
 execute('installLearningRun(run);S.view="learning-run";document.hidden=true;LEARNING_RUNS.lastListAt=Date.now()-10000');await execute('refreshLearningRun()');
 assert(!calls.includes('/learning-machine/runs'));
 execute('document.hidden=false');await execute('refreshLearningRun()');assert.equal(calls.filter(path=>path==='/learning-machine/runs').length,1);
});
test('完成整套默认打开成品，阶段切换可查看基准而不执行模型',()=>{
 const output={id:'one',platform:'百度',name:'广告',width:512,height:512,status:'done',version:1,image_url:'/done.png'};
 const run=readyRun({outputs:[output],status:'completed',suite:{status:'completed',baseline_version:1}});run.approval=approval(run);
 const {context,execute}=setup(()=>{throw new Error('切换页签不应调用API')});context.run=run;execute('installLearningRun(run);S.view="learning-run"');
 assert.equal(execute('productionStage(run)'),'results');
 let html=execute('viewLearningRun()');assert.match(html,/id="learning-stage-baseline"[^>]*hidden/);assert.match(html,/id="production-tab-results" aria-selected="true"/);
 execute('setLearningStage("baseline")');assert.equal(execute('productionStage(run)'),'baseline');assert(!execute('viewLearningRun()').match(/id="learning-stage-baseline"[^>]*hidden/));
 execute('setLearningBaselineVersion(1)');assert.equal(execute('S.learningBaselineVersion'),1);
});
test('扩套提交后打开进度页并聚焦，成品仍可由页签查看',async()=>{
 const run=readyRun();run.approval=approval(run);
 const next={...run,status:'generating_suite',busy:true,suite:{status:'generating',baseline_version:1},outputs:[{id:'one',platform:'百度',name:'广告',width:512,height:512,status:'queued',version:1}]};
 const events=[];const {context,execute}=setup(async()=>next);context.run=run;
 context.document.getElementById=id=>id==='learning-stage-progress'?{focus:options=>events.push(['focus',options]),scrollIntoView:options=>events.push(['scroll',options])}:null;
 execute('installLearningRun(run);S.view="learning-run";S.learningBaselineExpanded=true');await execute('learningRunAction("expand")');
 assert.equal(execute('S.learningBaselineExpanded'),false);assert.deepEqual(events.map(event=>event[0]),['focus','scroll']);assert.equal(events[0][1].preventScroll,true);assert.equal(events[1][1].block,'start');
 assert.equal(execute('productionStage(LEARNING_RUNS.current)'),'progress');assert(execute('viewLearningRun()').includes('id="learning-stage-progress"'));
});
test('运行响应更新全局队列摘要，缺省queue的完整或未变化响应保留已有负载',async()=>{
 let response={unchanged:true,id:'run-one',revision:1};const {context,execute}=setup(async()=>response);
 const summary={textContent:''};context.document.getElementById=id=>id==='queue-overview'?summary:null;
 context.run=readyRun({queue:{running:4,queued:8,waiting:2,limit:20,processing_limit:4}});
 execute('installLearningRun(run);S.view="learning-run";LEARNING_RUNS.lastListAt=Date.now()');assert.equal(execute('S.queue.running'),4);assert(summary.textContent.includes('出图中 4'));
 execute('installLearningRun({...run,queue:undefined})');assert.equal(execute('S.queue.queued'),8);
 await execute('refreshLearningRun()');assert.equal(execute('S.queue.running'),4);
 response={unchanged:true,id:'run-one',revision:1,queue:{running:2,queued:3,waiting:0,limit:20}};await execute('refreshLearningRun()');
 assert.equal(execute('S.queue.running'),2);assert(summary.textContent.includes('出图中 2'));assert(summary.textContent.includes('排队 3'));
});
test('成品实际提示词随历史版本切换，完整转义并复制选中版本而非当前版本',async()=>{
 const oldPrompt='旧版 <script>alert("old")</script> & 完整\n第二行',currentPrompt='当前新提示词';
 const output={id:'one',platform:'百度',name:'广告',width:512,height:512,status:'done',version:2,image_url:'/current.png',prompt:currentPrompt,source_master_id:'learning-master-D1',source_master_version:2,
  versions:[{id:'one',width:512,height:512,status:'done',version:1,image_url:'/old.png',prompt:oldPrompt,source_master_id:'learning-master-D1',source_master_version:1}]};
 const run=readyRun({mode:'real',outputs:[output],masters:[{id:'learning-master-D1',group_id:'D1',version:2,status:'done',prompt:'母版当前',versions:[{id:'learning-master-D1',group_id:'D1',version:1,status:'done',prompt:'母版旧版'}]}]});
 const writes=[];const {context,execute}=setup();context.run=run;context.navigator={clipboard:{writeText:async text=>writes.push(text)}};
 execute('installLearningRun(run);S.view="learning-run";S.learningOutputVersions={one:1}');
 const card=execute('viewLearningOutput(LEARNING_RUNS.current,LEARNING_RUNS.current.outputs[0],false,true)');assert(card.includes('/old.png'));assert(!card.includes(oldPrompt));
 execute('openLearningImage("/old.png","旧版成品","output","one",1)');let html=execute('viewLearningImageDetails(LEARNING_RUNS.current)');
 assert(html.includes('旧版 &lt;script&gt;alert(&quot;old&quot;)&lt;/script&gt; &amp; 完整'));assert(!html.includes(currentPrompt));assert(!html.includes('<script>'));assert(html.includes('复用母版 D1 · 第1版'));assert(html.includes("copyLearningActualPrompt('output',&quot;one&quot;,1,&quot;detail&quot;)"));
 await execute('copyLearningActualPrompt("output","one",1)');assert.deepEqual(writes,[oldPrompt]);
 execute('setLearningImageDetailVersion(2)');html=execute('viewLearningImageDetails(LEARNING_RUNS.current)');assert.equal(execute('S.learningOutputVersions.one'),2);assert(html.includes(currentPrompt));assert(!html.includes('旧版 &lt;script&gt;'));
});
test('基准复用和母版实际提示词标注来源，参数只显示API明确提供的字段',()=>{
 const run=readyRun({mode:'real',params:{t1:'文案',image_model:'model-record'},masters:[{id:'learning-master-B1',group_id:'B1',version:1,status:'done',reuse_baseline:true,prompt:'本分支直接复用已确认基准图，不调用图像模型。'}]});
 const output={id:'one',version:1,status:'done',prompt:run.masters[0].prompt,source_master_id:'learning-master-B1',source_master_version:1,width:580,height:320};
 const {context,execute}=setup();context.run=run;context.output=output;execute('installLearningRun(run)');
 let html=execute('viewLearningActualPrompt(run,output,"output")');assert(html.includes('本图复用基准图，未单独调用模型'));assert(!html.includes('有CTA'));assert(!html.includes('无Logo'));assert(!html.includes('learningRunAction'));assert(!html.includes('<textarea'));
 context.master={id:'learning-master-D1',group_id:'D1',version:1,status:'done',aspect_ratio:'3:1',prompt:'完整母版实际提示词'};
 html=execute('viewLearningActualPrompt(run,master,"master")');assert(html.includes('D1 · 查看实际提示词'));assert(html.includes('生图画幅：3:1'));assert(html.includes('完整母版实际提示词'));assert(html.includes('后续代码裁切、缩放和图层处理'));
});
test('复制失败保留可选择的完整提示词，不误报成功或触发其他API',async()=>{
 const output={id:'one',version:1,status:'done',prompt:'原始实际提示词\n逐字保留'};
 const {context,execute,messages}=setup(()=>{throw new Error('复制不应调用API')});context.run=readyRun({outputs:[output]});
 context.navigator={clipboard:{writeText:async()=>{throw new Error('denied')}}};
 let focused=false,selected=null;const element={focus(){focused=true}};
 context.document.getElementById=()=>element;context.document.createRange=()=>({selectNodeContents(node){selected=node}});context.window.getSelection=()=>({removeAllRanges(){},addRange(){}});
 execute('installLearningRun(run)');await execute('copyLearningActualPrompt("output","one",1)');
 assert(focused);assert.equal(selected,element);assert(messages.some(message=>message.includes('无法自动复制')));assert(!messages.includes('提示词已复制'));
 const html=execute('viewLearningActualPrompt(LEARNING_RUNS.current,LEARNING_RUNS.current.outputs[0],"output")');assert(html.includes('tabindex="0"'));assert(html.includes(output.prompt));
});
test('成品按冻结大渠道归组，跨母版的同渠道仍在一起且不读取当前目录名称',()=>{
 const make=(id,platform,master)=>({id,platform,name:'冻结版位'+id,width:512,height:512,status:'done',version:1,image_url:'/'+id+'.png',source_master_id:master});
 const run=readyRun({outputs:[make('baidu-a','百度','learning-master-D1'),make('zuoyebang','作业帮','learning-master-D1'),make('baidu-b','百度','learning-master-E7')]});
 const {context,execute}=setup();context.run=run;execute('installLearningRun(run);S.view="learning-run";PLACEMENTS.forEach(p=>p.platform="当前目录不应覆盖冻结渠道")');
 assert.deepEqual(JSON.parse(execute('JSON.stringify(learningOutputChannelGroups(run.outputs).map(g=>({channel:g.channel,ids:g.outputs.map(o=>o.id)})))')),[{channel:'百度',ids:['baidu-a','baidu-b']},{channel:'作业帮',ids:['zuoyebang']}]);
 let html=execute('viewLearningOutputGroups(run,run.outputs,false,true)');assert.equal((html.match(/class="learning-output-channel"/g)||[]).length,2);assert(html.includes('<h3>百度</h3>'));assert(html.includes('<h3>作业帮</h3>'));assert(!html.includes('当前目录不应覆盖'));
 execute('filterLearningRunChannel("作业帮")');html=execute('viewLearningOutputGroups(run,run.outputs,false,true)');assert(!html.includes('baidu-a.png'));assert(html.includes('zuoyebang.png'));
});
test('点击基准图打开详情直接显示该版本提示词，详情版本切换同步基准选择',()=>{
 const run=readyRun({mode:'real',baseline:{id:'baseline',version:2,status:'done',sha256:'new',image_url:'/base2.png',prompt:'基准第2版实际提示词'},baseline_versions:[{id:'baseline',version:1,status:'done',image_url:'/base1.png',prompt:'基准第1版实际提示词'}]});
 const {context,execute}=setup();context.run=run;execute('installLearningRun(run);S.view="learning-run";openLearningImage("/base1.png","基准旧版","baseline","baseline",1)');
 let html=execute('viewLearningImageDetails(run)');assert(html.includes('aria-label="学习机图片详情"'));assert(html.includes('基准第1版实际提示词'));assert(!html.includes('基准第2版实际提示词'));assert(html.includes('class="learning-run-prompt learning-actual-prompt" open'));
 execute('setLearningImageDetailVersion(2)');html=execute('viewLearningImageDetails(run)');assert(html.includes('/base2.png'));assert(html.includes('基准第2版实际提示词'));assert.equal(execute('S.learningBaselineVersion'),2);
});
test('图片详情和页面提示词ID隔离，复制失败只聚焦详情文本',async()=>{
 const {context,execute}=setup();context.run=readyRun();execute('installLearningRun(run);openLearningImage(run.baseline.image_url,"基准","baseline","baseline",1)');
 const page=execute('viewLearningActualPrompt(run,run.baseline,"baseline")'),detail=execute('viewLearningImageDetails(run)');
 const pageId=page.match(/<pre id="([^"]+)"/)[1],detailId=detail.match(/<pre id="([^"]+)"/)[1];assert.notEqual(pageId,detailId);
 let focusedId;context.document.getElementById=id=>({focus(){focusedId=id}});
 await execute('copyLearningActualPrompt("baseline","baseline",1,"detail")');assert.equal(focusedId,detailId);
});
test('详情只显示选中版本已有处理统计，不推断历史裁切或宣称AI补图',()=>{
 const {context,execute}=setup();context.row={processing:{sizing:{method:'contain_full_source_color_gradient',crop_percent:0,padding_percent:26.385,seam_review_required:true,content_detection:'not_performed',ai_repair_performed:false}}};
 let html=execute('viewLearningProcessing(row)');for(const text of ['等比保全原图','裁切 0%','补背景 26.39%','接缝待目视查看','未进行内容检测','未进行AI补图'])assert(html.includes(text),text);
 assert.equal(execute('viewLearningProcessing({version:1})'),'');context.row={processing:{crop_percent:NaN,padding_percent:-2}};assert.equal(execute('viewLearningProcessing(row)'),'');
});
test('已确认基准按新规则建立独立批次，只调用from-baseline不自动扩套或新生基准',async()=>{
 const source=readyRun({mode:'real',outputs:[{id:'old',status:'done',version:1,image_url:'/old.png'}]});source.approval=approval(source);
 const next=readyRun({id:'new-run',mode:'real',status:'baseline_confirmed',baseline:{...source.baseline,inherited:true},baseline_source:{run_id:source.id,baseline_version:1,sha256:source.baseline.sha256,mode:'real'},counts:{output_count:45,expected_new_calls:16}});next.approval=approval(next);
 const calls=[];const {context,execute,hashes}=setup(async(path,method,body)=>{calls.push({path,method,body});return next});context.source=source;
 execute('installLearningRun(source);S.view="learning-run"');await execute('makeLearningRunFromBaseline()');
 assert.equal(calls.length,1);assert.equal(calls[0].path,'/learning-machine/runs/run-one/from-baseline');assert(calls[0].body.idempotency_key);assert(!Object.hasOwn(calls[0].body,'mode'));
 assert.equal(execute('S.learningRunId'),'new-run');assert.equal(execute('LEARNING_RUNS.current.baseline.prompt'),source.baseline.prompt);assert.equal(source.outputs[0].image_url,'/old.png');assert(hashes.at(-1).endsWith('run=new-run'));
 const html=execute('viewLearningRun()');assert(html.includes('基准图未重新生成'));assert(html.includes('新的母版会按现行规则重新构图'));assert(html.includes('本批预计新增 16 次图片模型调用'));assert.equal(execute('productionStage(LEARNING_RUNS.current)'),'baseline');
 assert(!html.match(/id="learning-run-expand"[^>]*disabled/));
});
test('未确认、忙碌或正在查看旧基准时不能建立新规则批次',async()=>{
 const calls=[];const source=readyRun({mode:'real'});const {context,execute}=setup(async(...args)=>calls.push(args));context.source=source;
 execute('installLearningRun(source);S.view="learning-run"');await execute('makeLearningRunFromBaseline()');assert.equal(calls.length,0);assert.match(execute('viewLearningRun()'),/id="learning-run-from-baseline"[^>]*disabled/);
 context.approved=approval(source);execute('LEARNING_RUNS.current.approval=approved;LEARNING_RUNS.current.busy=true');await execute('makeLearningRunFromBaseline()');assert.equal(calls.length,0);
 execute('LEARNING_RUNS.current.busy=false;S.learningBaselineVersion=0');await execute('makeLearningRunFromBaseline()');assert.equal(calls.length,0);
});
test('来源说明只对应当前继承基准，后续新生成的基准不会显示旧来源或猜测调用次数',()=>{
 const source=readyRun({baseline_source:{run_id:'old-source',baseline_version:2},counts:{expected_new_calls:16}});
 const {context,execute}=setup();context.source=source;
 assert.equal(execute('viewLearningBaselineSource(source)'),'');
 execute('source.baseline.inherited=true');assert(execute('viewLearningBaselineSource(source)').includes('第2版'));
 execute('delete source.counts.expected_new_calls');assert(!execute('viewLearningBaselineSource(source)').includes('预计新增'));
 execute('source.baseline.inherited=false');assert.equal(execute('viewLearningBaselineSource(source)'),'');
});
test('建立新规则批次遇到未知响应失败时沿用幂等键，成功后保持同一基准哈希',async()=>{
 const source=readyRun({mode:'real'});source.approval=approval(source);const next=readyRun({id:'new-run',mode:'real',status:'baseline_confirmed',baseline:{...source.baseline,inherited:true}});next.approval=approval(next);
 const calls=[];let fail=true;const {context,execute}=setup(async(path,method,body)=>{calls.push({path,body});if(fail){fail=false;const error=new Error('connection lost');error.status=500;throw error}return next});context.source=source;
 execute('installLearningRun(source);S.view="learning-run"');await execute('makeLearningRunFromBaseline()');assert.equal(execute('S.learningRunId'),'run-one');await execute('makeLearningRunFromBaseline()');
 assert.equal(calls.length,2);assert.equal(calls[0].body.idempotency_key,calls[1].body.idempotency_key);assert.equal(execute('LEARNING_RUNS.current.baseline.sha256'),source.baseline.sha256);
});
test('学习机导出Logo选择不改模板或图片，只在保存图包时传明确版本',async()=>{
 const run=readyRun({outputs:[{id:'one',status:'done',version:1,width:512,height:512,image_url:'/original.png',logo_required:true}]});
 const calls=[];const {context,execute}=setup(async(path,method,body)=>{calls.push({path,method,body});return path.endsWith('/package')?{download_url:'/package.zip'}:run});context.run=run;
 execute('installLearningRun(run);S.view="learning-run";S.learningLogoDirty=false;setLearningExportLogo("learning.logo.white-app")');
 assert.equal(calls.length,0);assert.equal(execute('S.learningLogoDirty'),false);assert.equal(execute('LEARNING_RUNS.current.outputs[0].image_url'),'/original.png');
 const html=execute('viewLearningRun()');assert(html.includes('按各图配置'));assert(html.includes('白字APP版'));assert(html.includes('固定无Logo版位不添加'));
 await execute('packageLearningRun()');assert.equal(calls[0].body.logo_asset_id,'learning.logo.white-app');assert.equal(Object.keys(calls[0].body).length,1);assert.equal(calls[0].path,'/learning-machine/runs/run-one/package');
 calls.length=0;execute('setLearningExportLogo("")');await execute('packageLearningRun()');assert.deepEqual(Object.keys(calls[0].body),[]);
});
test('应用当前Logo模板是独立本机操作，不携带导出选择且未完成有Logo图片时拦截',async()=>{
 const run=readyRun({outputs:[{id:'one',status:'done',version:1,logo_required:true},{id:'no-logo',status:'failed',version:1,logo_required:false}]});
 const calls=[];const {context,execute}=setup(async(path,method,body)=>{calls.push({path,body});return {...run,revision:2,busy:true}});context.run=run;
 execute('installLearningRun(run);S.view="learning-run";setLearningExportLogo("learning.logo.white-app");S.learningOutputVersions={one:1}');
 await execute('refreshLearningRunLogos()');assert.equal(calls.length,1);assert(calls[0].path.endsWith('/refresh-logos'));assert(calls[0].body.idempotency_key);assert(!Object.hasOwn(calls[0].body,'logo_asset_id'));assert(!Object.hasOwn(calls[0].body,'placement_ids'));assert.equal(execute('Object.keys(S.learningOutputVersions).length'),0);
 execute('LEARNING_RUNS.current.busy=false;LEARNING_RUNS.current.outputs[0].status="failed"');await execute('refreshLearningRunLogos()');assert.equal(calls.length,1);
});
test('本机Logo更新失败显示本机重试，既不锁死恢复也不引导AI重出',async()=>{
 const output={id:'one',status:'failed',version:2,logo_required:true,logo_refresh_pending:true,width:512,height:512,platform:'百度',name:'广告'};
 const run=readyRun({outputs:[output]});run.approval=approval(run);const calls=[];
 const {context,execute}=setup(async(path,method,body)=>{calls.push({path,body});return run});context.run=run;
 execute('installLearningRun(run);S.view="learning-run"');const card=execute('viewLearningOutput(run,run.outputs[0],false,true)');assert(card.includes('重试Logo更新'));assert(card.includes('onclick="refreshLearningRunLogos()"'));assert(!card.includes("learningRunAction('regenerate'"));
 assert(!execute('viewLearningRun()').match(/id="learning-refresh-logos"[^>]*disabled/));
 await execute('learningRunAction("regenerate","one")');assert.equal(calls.length,0);
 await execute('refreshLearningRunLogos()');assert.equal(calls.length,1);assert(calls[0].path.endsWith('/refresh-logos'));
});
test('自然背景入口只按本图已有补边记录显示，8%内说明本机处理，其余明确一次AI调用',()=>{
 const {context,execute}=setup();context.output={id:'one',platform:'优学派',name:'横幅',width:1400,height:340,version:1,status:'done',image_url:'/one.png'};context.run=readyRun({mode:'real'});
 assert(!execute('viewLearningOutput(run,output,false,true)').includes('自然扩展背景'));
 context.output.processing={padding_percent:7.5,ai_repair_performed:false};let html=execute('viewLearningOutput(run,output,false,true)');assert(html.includes('自然适配背景'));assert(html.includes('不调用图片模型'));assert(!html.includes('会调用一次'));
 context.output.processing={sizing:{padding_percent:26,ai_repair_performed:false}};html=execute('viewLearningOutput(run,output,false,true)');assert(html.includes('AI自然扩展背景'));assert(html.includes('会调用一次图片模型'));
 context.output.processing.ai_repair_performed=true;assert.equal(execute('learningBackgroundCanRepair(output)'),false);
 context.output.processing={padding_percent:26,method:'ai_background_expansion'};assert.equal(execute('learningBackgroundCanRepair(output)'),false);
 context.output.processing={padding_percent:0};assert.equal(execute('learningBackgroundCanRepair(output)'),false);
});
test('背景修补只提交目标图，未知任务沿同键恢复并保留其他图片，不触发基准或整套',async()=>{
 const output={id:'one',platform:'优学派',name:'横幅',width:1400,height:340,version:1,status:'done',image_url:'/old.png',processing:{padding_percent:26,ai_repair_performed:false}};
 const run=readyRun({outputs:[output,{id:'other',status:'done',version:1,image_url:'/other.png'}]});run.approval=approval(run);
 const next={...run,status:'interrupted',outputs:[{...output,version:2,status:'interrupted',processing:undefined,background_repair_pending:true,query_required:true},run.outputs[1]]};const calls=[];
 const {context,execute}=setup(async(path,method,body)=>{calls.push({path,body});return next});context.run=run;
 execute('installLearningRun(run);S.view="learning-run"');await execute('repairLearningOutputBackground("one")');
 assert.equal(calls[0].path,'/learning-machine/runs/run-one/repair-backgrounds');assert.deepEqual(Array.from(calls[0].body.output_ids),['one']);assert.equal(execute('LEARNING_RUNS.current.outputs[1].image_url'),'/other.png');
 const card=execute('viewLearningOutput(LEARNING_RUNS.current,LEARNING_RUNS.current.outputs[0],false,true)');assert(card.includes('恢复背景适配查询'));assert(!card.includes("learningRunAction('regenerate'"));
 await execute('learningRunAction("regenerate","one")');assert.equal(calls.length,1);
 await execute('repairLearningOutputBackground("one")');assert.equal(calls.length,2);assert.equal(calls[0].body.idempotency_key,calls[1].body.idempotency_key);assert(calls.every(call=>call.path.endsWith('/repair-backgrounds')));
});
test('背景修补不允许从卡片历史版本隐式覆盖当前版本',async()=>{
 const calls=[];const output={id:'one',status:'done',version:2,processing:{padding_percent:10,ai_repair_performed:false}};
 const {context,execute}=setup(async(...args)=>calls.push(args));context.run=readyRun({outputs:[output]});execute('installLearningRun(run);S.view="learning-run";S.learningOutputVersions={one:1}');
 await execute('repairLearningOutputBackground("one")');assert.equal(calls.length,0);
});
test('AI扩背景处理记录区分最终裁切与原图像素，不沿用原图全保或零损耗声称',()=>{
 const {context,execute}=setup();context.row={processing:{sizing:{method:'contain_full_source_color_gradient',crop_percent:0,padding_percent:0,ai_repair_performed:false},ai_repair_performed:true}};
 const html=execute('viewLearningProcessing(row)');assert(html.includes('AI扩展背景'));assert(html.includes('最终精确裁切适配'));assert(!html.includes('等比保全原图'));assert(!html.includes('裁切 0%'));assert(!html.includes('未进行AI补图'));
 context.run=readyRun({mode:'real'});execute('row.id="one";row.version=2;row.status="done";row.prompt="AI实际提示词";row.reuse_baseline=true');const detail=execute('viewLearningActualPrompt(run,row,"output")');assert(detail.includes('本版本已进行AI自然扩展背景'));assert(!detail.includes('未单独调用模型'));
});
test('已完成AI扩背景仍可再次调整，使用新force请求且完成后清理旧幂等键',async()=>{
 const output={id:'one',platform:'优学派',name:'横幅',width:1400,height:340,version:2,status:'done',image_url:'/v2.png',processing:{method:'ai_background_expansion',ai_repair_performed:true,padding_percent:0},background_repair_key:'old-completed-key'};
 const run=readyRun({mode:'real',outputs:[output]});const calls=[];let version=2;
 const {context,execute}=setup(async(path,method,body)=>{calls.push({path,body});return {...run,outputs:[{...output,version:++version,background_repair_pending:false}]}});context.run=run;
 execute('installLearningRun(run);S.view="learning-run"');const card=execute('viewLearningOutput(run,run.outputs[0],false,true)');assert(card.includes('再次调整背景（AI）'));assert(card.includes('约一次图片模型'));assert(card.includes('允许少量细节变化'));
 await execute('repairLearningOutputBackground("one",true)');assert.equal(calls[0].body.force_ai,true);assert.notEqual(calls[0].body.idempotency_key,'old-completed-key');assert.equal(execute('Object.keys(LEARNING_RUNS.backgroundKeys).length'),0);
 await execute('repairLearningOutputBackground("one",true)');assert.equal(calls[1].body.force_ai,true);assert.notEqual(calls[0].body.idempotency_key,calls[1].body.idempotency_key);
 execute('S.learningOutputVersions={one:3}');await execute('repairLearningOutputBackground("one",true)');assert.equal(calls.length,2);
});
test('已有未知背景任务即使旧按钮传force，也只同键恢复而不创建新force调用',async()=>{
 const output={id:'one',version:3,status:'interrupted',background_repair_pending:true,query_required:true,background_repair_key:'existing-background-operation'};
 const run=readyRun({outputs:[output],status:'interrupted'}),calls=[];const {context,execute}=setup(async(path,method,body)=>{calls.push({path,body});return run});context.run=run;
 execute('installLearningRun(run);S.view="learning-run"');await execute('repairLearningOutputBackground("one",true)');
 assert.equal(calls.length,1);assert.equal(calls[0].body.idempotency_key,'existing-background-operation');assert(!Object.hasOwn(calls[0].body,'force_ai'));
 assert.equal(execute('LEARNING_RUNS.current.outputs[0].version'),3);
});
test('同一运行的迟到旧修订不能回退新背景版本或清除待恢复的幂等键',()=>{
 const current=readyRun({revision:7,outputs:[{id:'one',version:3,status:'interrupted',background_repair_pending:true,background_repair_key:'current-key'}]});
 const stale=readyRun({revision:6,outputs:[{id:'one',version:2,status:'done'}]});const {context,execute}=setup();context.current=current;context.stale=stale;
 execute('installLearningRun(current);LEARNING_RUNS.backgroundKeys["run-one:one"]={key:"current-key",source_version:2,accepted:true};installLearningRun(stale)');
 assert.equal(execute('LEARNING_RUNS.current.revision'),7);assert.equal(execute('LEARNING_RUNS.current.outputs[0].version'),3);assert.equal(execute('LEARNING_RUNS.backgroundKeys["run-one:one"].key'),'current-key');
});

test('有字母版复核按钮直接展示并绑定候选版本，待复核图不可当成品下载',async()=>{
 const master={id:'learning-master-E3',group_id:'E3',version:1,status:'visual_hold',visual_review:{
  status:'needs_review',can_accept:true,can_repair:true,review_sha256:'candidate-hash',
  original_url:'/api/learning-machine/runs/run-one/images/visual-master-original/learning-master-E3?version=1',
  first:{verdict:'repair',body:'第三步',issues:[{where:'末行',detail:'疑似错字'}]},
  verification:{verdict:'pass',body:'第一步',issues:[]},
  before_focus:{verdict:'pass',checks:[{text:'的第一步'}]}
 }};
 const run=readyRun({mode:'real',status:'failed',suite:{status:'failed'},masters:[master]});run.approval=approval(run);
 const calls=[];const {context,execute}=setup(async(path,method,body)=>{calls.push({path,method,body});return run});
 context.run=run;execute('installLearningRun(run);S.view="learning-run";S.learningRunId=run.id');
 assert.match(execute('viewLearningRun()'),/复核文字/);
 execute('openLearningImage("", "母版", "master", "learning-master-E3", 1)');
 const details=execute('viewLearningImageDetails(run)');
 assert.match(details,/查看审核原图/);
 assert.match(details,/确认无误，继续制作/);
 assert.match(details,/确认有问题，修复文字/);
 assert.match(details,/疑似错字/);
 assert.match(details,/疑字局部复核 · 通过/);
 assert.match(details,/读到「的第一步」/);
 assert.doesNotMatch(details,/下载这张图片/);
 await execute('resolveLearningVisual("master","learning-master-E3","accept")');
 assert.equal(calls[0].path,'/learning-machine/runs/run-one/visual/master/learning-master-E3');
 assert.equal(calls[0].body.action,'accept');
 assert.equal(calls[0].body.version,1);
 assert.equal(calls[0].body.sha256,'candidate-hash');
});

test('学习机概念图入口默认全选，查看上传图时只创建待确认批次',async()=>{
 const calls=[];
 const run=readyRun({mode:'real',concept:{id:'abc'},baseline:{id:'baseline',version:1,status:'done',uploaded:true,image_url:'/source'}});
 const {execute}=setup(async(path,method,body)=>{calls.push({path,method,body});return run});
 execute('CFG.kie=true;CFG.planningKey=true;setLearningConceptOrigin(true)');
 assert.equal(execute('S.draft.pids.length'),44);
 assert.match(execute('viewLearningSource(S.draft)'),/请上传不带 Logo 的横向 16:9 图片/);
 assert.match(execute('copyFields(S.draft)[0][1]'),/图上正文/);
 assert.equal(execute('formIssue(S.draft).field'),'concept-upload');
 execute("S.draft.concept={id:'a'.repeat(64),width:1600,height:900,button_text:'开始学习'}");
 await execute('startLearningRun()');
 assert.deepEqual(calls.map(row=>row.path),['/learning-machine/runs']);
 assert.equal(calls[0].body.params.concept.button_text,'开始学习');
 assert.equal(execute('LEARNING_RUNS.current.baseline.uploaded'),true);
});
