/* Current learning-machine UI, with explicit compatibility checks for old drafts. */
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),{webcrypto}=require('node:crypto');
const root=path.resolve(__dirname,'..');
const {currentLearningConfig}=require('./helpers/workbench.cjs');
const fixture={revision:1,pipeline:'baseline_then_suite',cta:{default_text:'点击下载'},logo_assets:[{id:'learning.logo.black',label:'黑字版',url:'/api/learning-machine/logo-assets/learning.logo.black',width:200,height:40},{id:'learning.logo.white-app',label:'白字版（含APP）',url:'/api/learning-machine/logo-assets/learning.logo.white-app',width:220,height:40}],placements:[
 {id:'learning-a',platform:'甲渠道',name:'有Logo横幅',target_width:1200,target_height:400,image_count:1,logo_required:true,content_modules:{main_copy:true,cta:true},logo_template:{asset_id:'learning.logo.black',x:.025,y:.03,width:.15}},
 {id:'learning-b',platform:'乙渠道',name:'固定无Logo',target_width:400,target_height:480,image_count:1,logo_required:false,content_modules:{main_copy:true,cta:false}},
 {id:'learning-c',platform:'甲渠道',name:'同版位两张',target_width:840,target_height:404,image_count:2,logo_required:true,content_modules:{main_copy:true,cta:false},logo_template:{asset_id:'learning.logo.black',x:.025,y:.03,width:.15}},
]};
function setup(mockRequest=async()=>structuredClone(fixture)){
 const ctx=vm.createContext({crypto:webcrypto,structuredClone,TextEncoder,setTimeout,clearTimeout,btoa,mockRequest,fixture,
  document:{activeElement:null,addEventListener(){},getElementById(){return null},querySelector(){return {scrollTop:0}},querySelectorAll(){return[]}},
  window:{addEventListener(){}},history:{replaceState(){}}});
 for(const name of ['views','learning-machine','drafts','app'])vm.runInContext(fs.readFileSync(path.join(root,'frontend/js/'+name+'.js'),'utf8').replace('\nboot();','\n'),ctx);
 const run=code=>vm.runInContext(code,ctx);
 run('PLACEMENTS=[];UNAVAILABLE_PLACEMENTS=[];STYLES=[];IPS=[];ASSETS={logos:[]};FORM_DEFAULTS={};request=(...a)=>mockRequest(...a);render=()=>{};save=()=>{};toast=()=>{};report=e=>{throw e};persistDraft=async()=>{};installLearningMachineConfig(structuredClone(fixture));loadDraft(defParams());setChannel("学习机")');
 return{ctx,run};
}
test('学习机按文案、画面、版位顺序配置，默认折叠全选版位且确认基准后才扩整套',async()=>{
 const {run}=setup();assert.equal(run('S.draft.pids.length'),3);assert.equal(run('S.draft.sets'),1);assert.equal(run('totalOf(S.draft)'),4);
 const h=run('viewForm()');assert(h.includes('生成基准图'));assert(h.includes('确认基准图并扩展整套'));assert(h.includes('仅预览计划'));assert(h.includes('id="f-t1"'));
 for(const value of ['上传图片扩展','id="f-sets"','id="f-t2"','id="nologo"','id="cta-enabled"'])assert(!h.includes(value),value);
 assert(h.includes('配置Logo模板'));assert(h.includes('点击下载'));
 const order=['class="card compose-card"','id="visual-options"','class="card placements-card"'].map(token=>h.indexOf(token));
 assert(order.every(index=>index>=0));assert(order[0]<order[1]&&order[1]<order[2]);
 assert.match(h,/id="learning-placements-toggle" aria-expanded="false"/);
 assert.match(h,/id="learning-placement-content" hidden/);
 run('toggleLearningPlacements();togP("learning-b")');
 assert.equal(run('S.learningPlacementsOpen'),true);assert.equal(run('S.draft.pids.length'),2);
 assert.match(run('viewForm()'),/id="learning-placements-toggle" aria-expanded="true"/);
 run('toggleLearningPlacements()');assert.equal(run('S.draft.pids.length'),2);
 assert.match(run('viewForm()'),/id="learning-placement-content" hidden/);
 run('S.draft.t1="不会的题拍一下";selectLearningPlacements(false)');
 await run('previewLearningSuite()');assert.equal(run('S.learningPlacementsOpen'),true);
});
test('旧上传草稿转为单一路径，原历史对象保持不变',()=>{
 const {run}=setup();run('old={channel:"学习机",image_form:"单图",pids:["learning-a"],learning_mode:"upload",learning_source:{id:"old"},sets:3,noLogo:true,logo_asset_id:"old-logo",cta_enabled:false,cta_overrides:{"learning-a":{mode:"none"}},references:[],t1:"已有文案"};loadDraft(old)');
 assert.equal(run('S.draft.learning_mode'),'generate');assert.equal(run('S.draft.learning_pipeline'),'baseline_then_suite');assert.equal(run('S.draft.learning_source'),undefined);assert.equal(run('S.draft.sets'),1);assert.equal(run('S.draft.cta'),'点击下载');assert.equal(run('old.learning_source.id'),'old');
 run('setLearningMode("upload");setLogoSelection("none");setCtaOverride("learning-a","none")');assert.equal(run('S.draft.learning_mode'),'generate');assert.equal(run('S.draft.noLogo'),false);assert.equal(run('placementCtaText(S.draft,"learning-a")'),'点击下载');
});
test('学习机预览只请求离线preview，不要求API Key、不创建旧/tasks生图任务',async()=>{
 const calls=[];const {run}=setup(async(url,method,body)=>{calls.push({url,method,body});if(url==='/learning-machine/preview')return{baseline:{ratio:'16:9'},placements:fixture.placements,outputs:[{placement_id:'learning-a',size:[1200,400]}],output_count:4};return structuredClone(fixture)});
 run('S.draft.t1="不会的题拍一下";S.draft.cta="马上试试";CFG={simulation:false,planningKey:false,kie:false}');await run('startGen()');
 const call=calls.find(c=>c.url==='/learning-machine/preview');assert(call);assert.equal(call.body.params.cta,'马上试试');assert.equal(call.body.params.sets,1);assert.equal(call.body.params.learning_pipeline,'baseline_then_suite');assert(!calls.some(c=>c.url==='/tasks'||c.url.startsWith('/settings/test')));
 assert(run('viewLearningPlanPreview()').includes('3个版位、4张目标图'));
});
test('Logo无开关、黑白版本如实显示，有Logo版可编辑而无Logo版不可启用',()=>{
 const {run}=setup();run('S.view="learning-logo";S.learningLogoPid="learning-a"');let h=run('viewLearningLogoConfig()');assert(h.includes('黑字版'));assert(h.includes('白字版（含APP）'));assert(h.includes('onpointerdown="startLearningLogoDrag(event)"'));assert(!h.includes('type="file"'));
 run('chooseLearningLogoPlacement("learning-b")');h=run('viewLearningLogoConfig()');assert(h.includes('此版位固定无Logo'));assert(!h.includes('id="learning-logo-width"'));run('setLearningLogoAsset("learning.logo.white-app")');assert.equal(run('LEARNING_MACHINE.templates["learning-b"]'),undefined);
});
test('Logo拖动/尺寸参数保持素材比例且约束在精确版位画布内',()=>{
 const {run}=setup();run('S.learningLogoPid="learning-a";setLearningLogoValue("width",200);setLearningLogoValue("x",99);setLearningLogoValue("y",99)');
 const t=run('LEARNING_MACHINE.templates["learning-a"]');assert(t.width<=1);assert(t.x+t.width<=1+1e-9);const height=t.width*1200/200*40/400;assert(t.y+height<=1+1e-9);
 run('setLearningLogoAsset("learning.logo.white-app")');assert.equal(run('LEARNING_MACHINE.templates["learning-a"].asset_id'),'learning.logo.white-app');
 const h=run('viewLearningLogoConfig()');assert(h.includes('--logo-preview-ratio:3'));assert(h.includes('aspect-ratio:1200/400'));
});
test('Logo模板保存使用修订号，刷新后恢复所选素材和位置',async()=>{
 let saved=structuredClone(fixture),body;
 const service=async(url,method,data)=>{if(method==='PUT'){body=data;saved.revision++;for(const t of data.templates)saved.placements.find(p=>p.id===t.placement_id).logo_template={asset_id:t.asset_id,x:t.x,y:t.y,width:t.width}}return structuredClone(saved)};
 const {run}=setup(service);run('S.learningLogoPid="learning-a";setLearningLogoAsset("learning.logo.white-app");setLearningLogoValue("x",12);setLearningLogoValue("width",22)');await run('saveLearningLogoTemplates()');
 assert.equal(body.revision,1);assert.equal(body.templates.length,2);assert(!body.templates.some(t=>t.placement_id==='learning-b'));assert.equal(run('S.learningLogoDirty'),false);
 const fresh=setup(service);await fresh.run('loadLearningMachineConfig(true)');assert.equal(fresh.run('LEARNING_MACHINE.templates["learning-a"].asset_id'),'learning.logo.white-app');assert.equal(fresh.run('LEARNING_MACHINE.templates["learning-a"].x'),.12);
});
test('保存冲突保留工作区修改，不覆盖其他窗口配置',async()=>{
 const {run}=setup(async()=>{const e=new Error('conflict');e.status=409;throw e});run('S.learningLogoPid="learning-a";setLearningLogoValue("x",15)');await run('saveLearningLogoTemplates()');assert.equal(run('S.learningLogoDirty'),true);assert.equal(run('LEARNING_MACHINE.templates["learning-a"].x'),.15);assert(run('S.learningLogoError').includes('其他窗口'));
});

test('计划表兼容后端真实width/height与target_size字段，区分版位数和图片数',()=>{
 const {run}=setup();run('S.learningPreview={pipeline:"baseline_then_suite",baseline:{aspect_ratio:"16:9"},placements:fixture.placements,output_count:4,outputs:[{placement_id:"learning-a",platform:"甲渠道",name:"有Logo横幅",width:1200,height:400,target_size:"1200×400"},{placement_id:"learning-b",platform:"乙渠道",name:"固定无Logo",width:400,height:480}]}');
 const html=run('viewLearningPlanPreview()');assert(html.includes('1200×400'));assert(html.includes('400×480'));assert(html.includes('3个版位、4张目标图'));assert(!html.includes('<td>×</td>'));
});

test('学习机参考图只本地上传，不自动调用文案规划或要点提取API',async()=>{
 const calls=[];const {ctx,run}=setup(async(url,method,data)=>{calls.push(url);return{id:'local-ref',name:'画风.png',thumbnail_url:'/api/uploads/local-ref'}});
 ctx.file={name:'画风.png',size:3,arrayBuffer:async()=>Uint8Array.from([1,2,3]).buffer};run('referencePreview=async()=>"data:image/jpeg;base64,AA"');
 await run('addReference(file,"style")');assert.deepEqual(calls,['/uploads']);assert.equal(run('S.draft.references[0].purpose'),'style');assert.equal(run('Object.keys(S.referencePointsPending).length'),0);
});
test('预览冻结seed与视觉配置，重复预览沿用；新任务不继承其他任务seed',async()=>{
 const payloads=[];const {run}=setup(async(url,method,data)=>{if(url==='/learning-machine/preview'){payloads.push(data.params);return{baseline:{aspect_ratio:'16:9'},outputs:[],params:{...data.params,learning_seed:'frozen-one',learning_visual_config:{ip:'same-ip',style:'same-style'}}}}return structuredClone(fixture)});
 run('S.draft.t1="不会的题拍一下"');await run('startGen()');await run('startGen()');assert.equal(payloads[1].learning_seed,'frozen-one');assert.equal(payloads[1].learning_visual_config.ip,'same-ip');
 run('showDraftStatus=()=>{}');await run('newDraft(structuredClone(S.draft))');assert.equal(run('S.draft.learning_seed'),undefined);assert.equal(run('S.draft.learning_visual_config'),undefined);
});

test('保存计划后聚焦并滚到可见结果，预览位于版位长列表之前且展示冻结视觉名称',async()=>{
 const events=[];const {ctx,run}=setup(async(url,method,data)=>url==='/learning-machine/preview'?{baseline:{aspect_ratio:'16:9'},placements:fixture.placements,outputs:[],output_count:4,visual_config:{ip_name:'豆花 · 标准形象',style_name:'日系清新动漫',font_name:'标题参考 <花体>'}}:structuredClone(fixture));
 ctx.document.getElementById=id=>id==='learning-plan-preview'?{focus:options=>events.push(['focus',options]),scrollIntoView:options=>events.push(['scroll',options])}:null;
 run('S.draft.t1="不会的题拍一下"');await run('startGen()');
 assert.deepEqual(events.map(e=>e[0]),['focus','scroll']);assert.equal(events[0][1].preventScroll,true);assert.equal(events[1][1].block,'start');
 const html=run('viewForm()');assert(html.indexOf('id="learning-plan-preview"')<html.indexOf('class="card placements-card"'));
 assert(html.includes('豆花 · 标准形象'));assert(html.includes('日系清新动漫'));assert(html.includes('标题参考 &lt;花体&gt;'));assert(html.includes('这套角色、画风和字体已固定'));assert(!html.includes('标题参考 <花体>'));
});

test('配置预览不能冒充真实基准图或用户确认，制作动作进入独立运行流程',()=>{
 const {run}=setup();run('S.learningPreview={baseline:{aspect_ratio:"16:9",state:"not_generated",has_image:false,artifact_ready:false,approval:{required:true,status:"waiting_for_image",confirmed:false,can_confirm:false}},confirmation:{required:true,confirmed:false,can_confirm:false,can_expand:false},suite:{can_expand:false},outputs:[],execution:{enabled:false,prompt_generation_ready:false}}');
 const h=run('viewLearningPlanPreview()');assert(h.includes('基准图待生成'));assert(h.includes('配置预览不代表基准图已生成或已确认'));assert(h.includes('等待用户确认基准图，不会自动开始'));assert(!h.includes('<img'));
 assert(!h.includes('id="learning-confirm-baseline"'));assert(!h.includes('onclick="learningRunAction'));assert(h.includes('从右侧开始模拟或真实制作'));assert(h.includes('不满意可重新生成'));
});
test('Logo操作区先于预览画布，保存按钮不落在长画布下方',()=>{
 const {run}=setup();run('S.view="learning-logo";S.learningLogoPid="learning-a"');const h=run('viewLearningLogoConfig()');
 assert(h.indexOf('class="card learning-logo-save"')<h.indexOf('class="card learning-logo-editor"'));
 assert(h.indexOf('class="learning-logo-controls"')<h.indexOf('class="learning-logo-board-wrap"'));
});

test('Logo搜索只更新列表，保留输入节点、焦点、光标及正在编辑的画布',()=>{
 const {ctx,run}=setup();const input={value:'1223',selectionStart:4,selectionEnd:4},list={innerHTML:''};ctx.document.activeElement=input;ctx.document.getElementById=id=>id==='learning-logo-directory-list'?list:id==='learning-logo-search'?input:null;
 run('S.learningLogoPid="learning-a";LEARNING_MACHINE.config.placements.push({id:"learning-near",platform:"作业帮",name:"近尺寸横幅",target_width:1223,target_height:471,logo_required:true});render=()=>{throw new Error("search must not rebuild page")};filterLearningLogoPlacements("1223")');
 assert(list.innerHTML.includes('1223×471'));assert(!list.innerHTML.includes('1200×400'));assert.equal(ctx.document.activeElement,input);assert.equal(input.selectionStart,4);assert.equal(run('S.learningLogoPid'),'learning-a');
 input.value='作';input.selectionStart=input.selectionEnd=1;run('filterLearningLogoPlacements("作")');assert(list.innerHTML.includes('作业帮'));assert.equal(ctx.document.activeElement,input);assert.equal(input.selectionStart,1);
 input.value='';run('filterLearningLogoPlacements("")');assert(list.innerHTML.includes('learning-a'));assert(list.innerHTML.includes('learning-b'));assert(list.innerHTML.includes('learning-c'));assert(list.innerHTML.includes('learning-near'));
});

test('版位、文案及草稿变化立即清掉旧计划，非整页render也移除旧预览DOM',()=>{
 const {ctx,run}=setup();let removed=0;ctx.document.getElementById=id=>id==='learning-plan-preview'?{remove(){removed++}}:null;run('updSum=()=>{}');
 for(const change of ['setF("cta","新的按钮")','togP("learning-a")','selectLearningPlacements(true)','selectLearningPlacements(false)','loadDraft({channel:"学习机",image_form:"单图",pids:["learning-b"],t1:"另一份草稿",references:[]})']){
  run('S.learningPreview={output_count:45};S.learningPreviewError="旧提示"');run(change);assert.equal(run('S.learningPreview'),null,change);assert.equal(run('S.learningPreviewError'),'',change);
 }
 assert.equal(removed,5);
});
test('新增或移除参考图使旧计划失效，不遗留另一套参考素材的预览',async()=>{
 const {ctx,run}=setup(async()=>({id:'local-style',name:'参考图',purpose:'style',thumbnail_url:'/api/uploads/local-style'}));ctx.file={name:'参考.png',size:3,arrayBuffer:async()=>Uint8Array.from([1,2,3]).buffer};run('referencePreview=async()=>"data:image/jpeg;base64,AA";S.learningPreview={output_count:45}');
 await run('addReference(file,"style")');assert.equal(run('S.learningPreview'),null);run('S.learningPreview={output_count:45};removeReference(0)');assert.equal(run('S.learningPreview'),null);assert.equal(run('S.draft.references.length'),0);
});
test('保存Logo模板后旧版本流程预览失效，需重新预览冻结新模板',async()=>{
 let config=structuredClone(fixture);const {run}=setup(async(url,method,data)=>{if(method==='PUT'){config.revision++;for(const t of data.templates)config.placements.find(p=>p.id===t.placement_id).logo_template=t}return structuredClone(config)});
 run('S.learningPreview={logo_template_revision:1}');await run('saveLearningLogoTemplates()');assert.equal(run('S.learningPreview'),null);assert.equal(run('LEARNING_MACHINE.revision'),2);
});


test('当前44版位配置和16组固定模板联动，区分复用母版并安全显示完整提示词',()=>{
 const {ctx,run}=setup();ctx.currentConfig=currentLearningConfig();
 run('installLearningMachineConfig(currentConfig);selectLearningPlacements(true)');
 assert.equal(run('S.draft.pids.length'),44);assert.equal(run('totalOf(S.draft)'),45);
 assert.equal(run('PLACEMENTS.filter(p=>p.logo_policy==="required").length'),36);
 assert.equal(run('PLACEMENTS.filter(p=>p.cta_policy==="required").length'),14);
 assert(run('PLACEMENTS.every(p=>!p.content_modules.feature_label&&!p.content_modules.badge&&!p.content_modules.extra_heading&&!p.content_modules.extra_description)'));
 const maskConfig=JSON.parse(fs.readFileSync(path.join(root,'config/learning-machine-mask-templates.json')));
 const maskId='learning-youxuepai-masked-840x404',preset=maskConfig.mask_presets.find(p=>p.id===maskConfig.placements[maskId].preset_id);
 assert.deepEqual(ctx.currentConfig.placements.filter(p=>p.mask_template.enabled).map(p=>p.id),[maskId]);
 for(const placement of ctx.currentConfig.placements){
  ctx.maskPlacementId=placement.id;run('chooseLearningLogoPlacement(maskPlacementId)');
  const editor=run('viewLearningLogoConfig()');
  assert.equal(editor.includes('class="learning-logo-mask-overlay"'),placement.id===maskId,placement.id);
  if(placement.id===maskId){
   assert(editor.includes(`底部高度 ${(preset.height_fraction*100).toFixed(1)}%`));
   assert(editor.includes(`最大不透明度 ${(preset.max_opacity*100).toFixed(1)}%`));
   assert(editor.includes('固定无Logo'));assert(!editor.includes('id="learning-logo-image"'));
  }
 }
 const groups=JSON.parse(fs.readFileSync(path.join(root,'config/learning-machine-master-groups.json'))).groups;
 assert.equal(groups.length,16);assert.equal(groups.filter(g=>g.reuse_baseline).length,1);
 const dangerous='保留完整模板\n<script>alert("x")</script> & 一句推广文案';
 ctx.promptFixture={counts:{master_count:16,image_model_master_calls:15,baseline_reused_master_count:1,planned_image_calls:16,delivery_count:45},baseline:{prompt:dangerous},masters:groups.map((g,i)=>({
  id:'learning-master-'+g.id,group_id:g.id,aspect_ratio:g.aspect_ratio,prompt:dangerous+'\n模板 '+g.id,
  reuse_baseline:!!g.reuse_baseline,image_generation_required:!g.reuse_baseline,placement_ids:g.placement_ids,
  delivery_count:g.placement_ids.reduce((n,id)=>n+currentLearningConfig().placements.find(p=>p.id===id).image_count,0),
 }))};
 run('S.learningPreview={baseline:{aspect_ratio:"16:9"},outputs:[],prompt_plan:promptFixture}');const h=run('viewLearningPlanPreview()');
 assert(h.includes('预计 <b>16</b> 组母版'));assert(h.includes('首轮图片模型调用 <b>16</b> 次'));
 assert(h.includes('1张基准图＋15张新母版；1组直接复用基准图'));
 assert(h.includes('<details class="learning-fixed-prompts" id="learning-fixed-prompts">'));
 assert(h.includes('learning-master-B1 · 复用基准图，不调用模型'));
 assert(h.includes('learning-master-D1 · 图生图'));
 assert(h.includes('百度 · 广告图 · 512×512'));
 assert.equal((h.match(/<pre /g)||[]).length,17);assert(!h.includes('<textarea'));assert(!h.includes('<script>'));
 assert.equal((h.match(/&lt;script&gt;alert\(&quot;x&quot;\)&lt;\/script&gt; &amp;/g)||[]).length,17);
 assert(h.includes('模板 E7</pre>'));
 assert(!h.includes('id="learning-confirm-baseline"'));assert(h.includes('配置预览本身不会提交模型'));
});
test('画面规划和不支持比例显示友好状态，已移除的产品字段不再阻止离线保存',async()=>{
 const calls=[];const {ctx,run}=setup(async(url,method,data)=>{calls.push(url);return {baseline:{aspect_ratio:'16:9'},outputs:[],prompt_plan:ctx.promptFixture}});
 ctx.promptFixture={baseline:{prompt:'场景模板',missing_inputs:[{field:'scene_plan'}]},masters:[{id:'pending',aspect_ratio:'3:1',prompt:'产品文字模板',placement_ids:['learning-a'],missing_inputs:['feature_label',{name:'extra_heading'},{key:'extra_description'}],unsupported_model_ratio:true}]};
 run('S.draft.t1="拍题看思路"');assert.equal(run('formIssue(S.draft)'),null);await run('startGen()');
 assert.deepEqual(calls,['/learning-machine/preview']);const h=run('viewLearningPlanPreview()');
 for(const expected of ['画面方案将在生成基准图时确定','当前模型不支持此比例','不会新增为当前主表单必填项'])assert(h.includes(expected),expected);
 for(const stale of ['功能名产品文案待配置','精选底部标题待配置','精选底部说明待配置','feature_label','extra_heading','extra_description'])assert(!h.includes(stale),stale);
 assert(h.includes('正文和CTA按版位固定规则处理'));
 assert(h.includes(' · 待配置'));assert(!h.includes('onclick="generate'));assert.equal(run('S.submitting'),false);
});
test('只有学习机解释后续文字位的字体用途，其他渠道保留随机参考风格提示',()=>{
 const {run}=setup();run('S.visualOpen=true');const learning=run('viewVisualOptions(S.draft)');
 assert(learning.includes('字体参考用于后续带文字的版位，基准图不排广告文字'));assert(!learning.includes('抽中内置参考风格时不使用字体参考'));
 const standard=run('viewVisualOptions({...S.draft,channel:"信息流",pids:[],style:"random"})');assert(standard.includes('抽中内置参考风格时不使用字体参考'));assert(!standard.includes('基准图不排广告文字'));
});


test('固定无Logo的遮罩版位仍按配置预览渐变，终点按目标尺寸而非CSS画布计算',()=>{
 const {run}=setup();run('LEARNING_MACHINE.config.mask_presets=[{id:"bottom-gray",height_fraction:.22,max_opacity:.42,color:"#000000",curve:"linear"}];LEARNING_MACHINE.config.placements.find(p=>p.id==="learning-b").mask_template={enabled:true,preset_id:"bottom-gray"};S.learningLogoPid="learning-b"');
 const h=run('viewLearningLogoConfig()'),start=run('(1-.22)*100'),end=run('(1-1/480)*100');
 assert(h.includes('固定无Logo'));assert(h.includes('class="learning-logo-mask-overlay"'));assert(h.includes(`rgba(0,0,0,0) ${start}%,rgba(0,0,0,0.42) ${end}%`));
 assert(h.includes('底部遮罩由代码叠加，审核和导出一致'));assert(h.includes('底部高度 22.0%'));assert(h.includes('最大不透明度 42.0%'));assert(!h.includes('id="learning-logo-width"'));assert(!h.includes('id="learning-logo-image"'));
});
test('未启用遮罩版位不显示灰层，参数使用单版位覆盖且不插入未经验证的CSS',()=>{
 const {run}=setup();run('S.learningLogoPid="learning-a"');assert(!run('viewLearningLogoConfig()').includes('class="learning-logo-mask-overlay"'));
 run('LEARNING_MACHINE.config.mask_presets=[{id:"bottom-gray",height_fraction:.22,max_opacity:.42,color:"#000000",curve:"linear"}];LEARNING_MACHINE.config.placements[0].mask_template={enabled:true,preset_id:"bottom-gray",height_fraction:.3,max_opacity:.5}');
 let h=run('viewLearningLogoConfig()');assert(h.includes('底部高度 30.0%'));assert(h.includes('最大不透明度 50.0%'));assert(h.includes('id="learning-logo-image"'));
 run('LEARNING_MACHINE.config.placements[0].mask_template.enabled=false');assert.equal(run('viewLearningMaskOverlay(learningLogoPlacement())'),'');
 run('LEARNING_MACHINE.config.placements[0].mask_template={enabled:true,preset_id:"bottom-gray",color:"red;background:url(attack)"}');assert.equal(run('viewLearningMaskOverlay(learningLogoPlacement())'),'');
});


test('只选复用基准图分组时母版一组但后续零调用，模板明确不调用模型',()=>{
 const {run}=setup();run('S.learningPreview={outputs:[],prompt_plan:{baseline:{prompt:"基准图模板"},masters:[{id:"B1",aspect_ratio:"16:9",reuse_baseline:true,image_generation_required:false,source_kind:"confirmed_baseline_reuse",placement_ids:["learning-a"],delivery_count:2}],counts:{master_count:1,image_model_master_calls:0,baseline_reused_master_count:1,planned_image_calls:1}}}');const h=run('viewLearningPlanPreview()');
 assert(h.includes('预计 <b>1</b> 组母版'));assert(h.includes('首轮图片模型调用 <b>1</b> 次'));assert(h.includes('1张基准图＋0张新母版；1组直接复用基准图'));assert(h.includes('B1 · 复用基准图，不调用模型'));assert(!h.includes('B1 · 图生图'));
 assert(h.includes('直接复用已确认基准图，本组不调用图片模型。'));assert(!h.includes('id="learning-confirm-baseline"'));
});
test('计划明确拆分条件背景扩展次数，旧预览无此字段时不推断补图数量',()=>{
 const {run}=setup();run('S.learningPreview={outputs:[],prompt_plan:{masters:[],counts:{master_count:16,image_model_master_calls:15,baseline_reused_master_count:1,background_image_calls:10,planned_image_calls:26}}}');
 let html=run('viewLearningPromptCounts(S.learningPreview)');assert(html.includes('首轮图片模型调用 <b>26</b> 次'));assert(html.includes('另含10次条件背景扩展'));assert(html.includes('1张基准图＋15张新母版'));
 run('delete S.learningPreview.prompt_plan.counts.background_image_calls');html=run('viewLearningPromptCounts(S.learningPreview)');assert(!html.includes('次条件背景扩展'));
});
test('扩图工作流展示轻裁和AI自然延展条件阶段，不把构图约束当最终视觉验收',()=>{
 const {run}=setup();run('framingPlan={prompt_plan:{framing_node:{}}}');const html=run('viewLearningFramingWorkflow(framingPlan)');
 assert(html.includes('主视觉约束图生图 → 小误差轻裁／大误差AI自然延展 → 精确导出'));assert(html.includes('补边占比8%以内本机轻裁'));assert(html.includes('成图完整性由你查看确认'));
});
