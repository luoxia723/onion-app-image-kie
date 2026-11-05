const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const placements = JSON.parse(fs.readFileSync(path.join(root,'config/channel-placement-rules.json'))).placements;
function context(form='单图') {
  const ctx = vm.createContext({
    document:{addEventListener(){},querySelector(){return null},querySelectorAll(){return []}},
    PLACEMENTS:placements, STYLES:[], IPS:[],
    DEF_CTA:'立即体验', SETS_MIN:1, SETS_MAX:20,
    S:{draft:{channel:'应用商店',cta_enabled:true,cta_overrides:{},image_form:form,pids:[],t1:'',t2:'',s1:'',s2:'',s3:'',cta:'立即体验',sets:3,ip:'random',style:'random'},formDrafts:{},tried:false},
    save(){}, structuredClone,
  });
  vm.runInContext(fs.readFileSync(path.join(root,'frontend/js/views.js'),'utf8'),ctx);
  vm.runInContext('render=()=>{};save=()=>{}',ctx);
  return ctx;
}
for (const [form,count,fields] of [['单图',5,['t1','t2']],['双图',2,['s1','s2']],['三图',4,['s1','s2','s3']]]) {
  test(form+'只显示自身字段与兼容版位',()=>{
    const ctx=context(form),html=vm.runInContext('viewForm()',ctx);
    for(const f of ['t1','t2','s1','s2','s3'])assert.equal(html.includes('id="f-'+f+'"'),fields.includes(f),f);
    const ids=[...html.matchAll(/class="placement-row[^"]*"[^>]*data-pid="([^"]+)"/g)].map(m=>m[1]);
    assert.equal(ids.length,count);
    assert(ids.every(id=>placements.find(p=>p.id===id).image_form===form&&placements.find(p=>p.id===id).category==='应用商店'));
    assert(html.includes('role="radiogroup"'));
  });
}
test('同一种文案允许多选兼容渠道版位',()=>{
  const ctx=context('单图');
  const ids=placements.filter(p=>p.image_form==='单图').slice(0,2).map(p=>p.id);
  vm.runInContext(`togP(${JSON.stringify(ids[0])});togP(${JSON.stringify(ids[1])})`,ctx);
  assert.deepEqual([...ctx.S.draft.pids],ids);
});
test('不允许通过旧点击事件选入其他形式的版位',()=>{
  const ctx=context('单图'),id=placements.find(p=>p.image_form==='双图').id;
  vm.runInContext(`togP(${JSON.stringify(id)})`,ctx);
  assert.equal(ctx.S.draft.pids.length,0);
});
test('双图和三图的短句是独立草稿',()=>{
  const ctx=context('双图');
  ctx.S.draft.s1='双图第一句';ctx.S.draft.s2='双图第二句';
  vm.runInContext('setImageForm("三图")',ctx);
  assert.equal(ctx.S.draft.s1,'');assert.equal(ctx.S.draft.s2,'');
  ctx.S.draft.s1='三图第一句';ctx.S.draft.s2='三图第二句';ctx.S.draft.s3='三图第三句';
  vm.runInContext('setImageForm("双图")',ctx);
  assert.equal(ctx.S.draft.s1,'双图第一句');assert.equal(ctx.S.draft.s2,'双图第二句');assert.equal(ctx.S.draft.s3,'');
  vm.runInContext('setImageForm("三图")',ctx);
  assert.equal(ctx.S.draft.s1,'三图第一句');assert.equal(ctx.S.draft.s3,'三图第三句');
});
test('切换形式时不保留不兼容的版位',()=>{
  const ctx=context('单图');ctx.S.draft.pids=[placements.find(p=>p.image_form==='单图').id];
  vm.runInContext('setImageForm("双图")',ctx);assert.equal(ctx.S.draft.pids.length,0);
});
test('画面设定默认收起，定制后显示三个固定上传位和紧凑控件',()=>{
  const ctx=context();let html=vm.runInContext('viewForm()',ctx);
  assert(html.includes('全部随机'));assert(html.includes('aria-expanded="false"'));assert(!html.includes('id="ips"'));
  ctx.S.visualOpen=true;html=vm.runInContext('viewForm()',ctx);
  assert(!/class="[^"]*\bmore\b/.test(html));
  for(const id of ['ips','styleq','nologo','f-feature','f-font','reference-options'])assert(html.includes('id="'+id+'"'),id);
  assert(!html.includes('f-direction'));assert(!html.includes('方向名'));
  for(const label of ['随机 IP','不用 IP','使用 Logo','不用 Logo','参考风格','参考排版','产品界面'])assert(html.includes(label),label);
  assert.equal((html.match(/class="reference-slot /g)||[]).length,3);
  assert.equal((html.match(/class="primary"/g)||[]).length,1);
});
test('切回已填写的图片形式时，沿用最新素材配置并保留各自文案',()=>{
  const ctx=context('单图');ctx.S.draft.t1='单图标题';
  vm.runInContext('setImageForm("双图")',ctx);
  Object.assign(ctx.S.draft,{s1:'双图第一句',ip:'none',style:'自选画风',noLogo:true,feature_note:'手不要遮挡标题',direction:'自选方向',product_facts:'已确认功能',facts_version:7,references:[{id:'ref',note:'沿用构图'}]});
  vm.runInContext('setImageForm("单图")',ctx);
  assert.equal(ctx.S.draft.t1,'单图标题');assert.equal(ctx.S.draft.s1,'');
  for(const [k,v] of Object.entries({ip:'none',style:'自选画风',noLogo:true,feature_note:'手不要遮挡标题',direction:'自选方向',product_facts:'已确认功能',facts_version:7}))assert.equal(ctx.S.draft[k],v,k);
  assert.equal(ctx.S.draft.references[0].id,'ref');
});
test('定制控件显示所选值，必带Logo逐行锁定但不改全局不用Logo',()=>{
  const ctx=context();ctx.STYLES=[{name:'指定画风'}];
  Object.assign(ctx.S.draft,{channel:'信息流',ip:'none',style:'指定画风',noLogo:true});
  const required=placements.find(p=>p.logo_policy==='required');
  vm.runInContext('togP('+JSON.stringify(required.id)+')',ctx);
  const html=vm.runInContext('viewForm()',ctx);
  assert.equal(ctx.S.draft.noLogo,true);
  assert(html.includes('value="none" selected>不用 IP'));
  assert(html.includes('value="指定画风" selected'));
  assert(html.includes('value="none" selected>不用 Logo'));
  assert(!/id="nologo"[^>]*disabled/.test(html));
  assert(html.includes('logo-lock force-highlight'));assert(html.includes('🔒 Logo'));
});
test('角色素材按标准、学段与Q版、老师展示，指定版本保持选中',()=>{
  const ctx=context();
  ctx.IPS=JSON.parse(fs.readFileSync(path.join(root,'assets/asset-manifest.json'))).assets.filter(a=>a.kind==='ip'&&a.enabled!==false).map(a=>({id:a.asset_id,label:a.asset_name_zh||a.display_name,stage:a.stage,variant:a.variant,thumb:'/api/assets/'+a.asset_id}));
  const selected=ctx.IPS.find(a=>a.id.includes('.primary.'));ctx.S.draft.ip=selected.id;
  const html=vm.runInContext('viewForm()',ctx);
  for(const name of ['标准形象','学段与 Q 版','老师角色'])assert(html.includes(name),name);
  for(const a of ctx.IPS)assert(html.includes('data-ip="'+a.id+'"'),a.id);
  assert(html.includes('value="'+selected.id+'" selected>'+selected.label));
});
test('旧草稿缺少非必填配置时补齐结构，不擅自选择渠道',()=>{
  const ctx=context();vm.runInContext('loadDraft({image_form:"单图",t1:"旧草稿标题"})',ctx);
  assert.equal(ctx.S.draft.pids.length,0);assert.equal(ctx.S.draft.font,'random');
  assert(vm.runInContext('viewForm()',ctx).includes('旧草稿标题'));
});
test('渠道过滤与形式显隐来自当前规则，学习机显示空态',()=>{
  const ctx=context();ctx.S.draft.channel='信息流';
  let html=vm.runInContext('viewForm()',ctx);
  const ids=[...html.matchAll(/class="placement-row[^"]*"[^>]*data-pid="([^"]+)"/g)].map(m=>m[1]);
  assert.deepEqual(ids.sort(),placements.filter(p=>p.category==='信息流').map(p=>p.id).sort());
  assert(!html.includes('id="image-form"'));assert(html.includes('>喜马拉雅</h4>'));
  vm.runInContext('setChannel("学习机")',ctx);html=vm.runInContext('viewForm()',ctx);
  assert(html.includes('该渠道暂无版位'));assert(!html.includes('data-pid='));
  assert(/id="sum" disabled/.test(html));assert(/id="go" disabled/.test(html));
  ctx.PLACEMENTS=[...placements,{id:'new',category:'新渠道',image_count:2}];
  assert(vm.runInContext('channelOptions()',ctx).includes('新渠道'));
  assert.deepEqual([...vm.runInContext('channelForms("新渠道")',ctx)],['双图']);
});
test('未选渠道时下方真实禁用，旧点击不能跨渠道选入版位',()=>{
  const ctx=context();ctx.S.draft.channel='';
  let html=vm.runInContext('viewForm()',ctx);
  assert(html.includes('<fieldset class="channel-dependent" disabled>'));
  assert.equal(vm.runInContext('formIssue(S.draft).field',ctx),'channel');
  ctx.S.draft.channel='信息流';
  vm.runInContext('togP('+JSON.stringify(placements.find(p=>p.category==='应用商店').id)+')',ctx);
  assert.equal(ctx.S.draft.pids.length,0);
});
test('切渠道会清除当前及其他形式草稿中的旧版位、套数和按钮覆盖',()=>{
  const ctx=context('三图'),triple=placements.find(p=>p.image_form==='三图'),single=placements.find(p=>p.category==='应用商店'&&p.image_form==='单图');
  ctx.S.draft.pids=[triple.id];ctx.S.draft.cta_overrides={[triple.id]:{mode:'custom',text:'立即学习'}};
  ctx.S.draft.variants_by_placement={[triple.id]:5};
  ctx.S.formDrafts['单图']={...structuredClone(ctx.S.draft),image_form:'单图',pids:[single.id],cta_overrides:{[single.id]:{mode:'none'}}};
  vm.runInContext('setChannel("信息流")',ctx);
  assert.equal(ctx.S.draft.image_form,'单图');
  for(const pr of [ctx.S.draft,...Object.values(ctx.S.formDrafts)]){
    assert.equal(pr.channel,'信息流');assert.equal(pr.pids.length,0);
    assert.equal(Object.keys(pr.cta_overrides).length,0);
    assert.equal(Object.keys(pr.variants_by_placement||{}).length,0);
  }
  vm.runInContext('setChannel("应用商店");setImageForm("三图")',ctx);
  assert.equal(ctx.S.draft.pids.length,0);assert.equal(Object.keys(ctx.S.draft.cta_overrides).length,0);
});
test('按钮覆盖随形式草稿恢复，取消版位清除覆盖，自定义文字验证',()=>{
  const ctx=context(),id=placements.find(p=>p.category==='应用商店'&&p.image_form==='单图').id;
  ctx.S.draft.pids=[id];ctx.S.draft.t1='标题';ctx.S.draft.t2='副标题';
  vm.runInContext('setCtaOverride('+JSON.stringify(id)+',"custom","现在学习")',ctx);
  assert(vm.runInContext('viewForm()',ctx).includes('id="cta-'+id+'"'));
  vm.runInContext('setImageForm("双图");setImageForm("单图")',ctx);
  assert.equal(ctx.S.draft.cta_overrides[id].text,'现在学习');
  ctx.S.draft.cta_overrides[id].text='';assert.equal(vm.runInContext('formIssue(S.draft).field',ctx),'cta-'+id);
  ctx.S.draft.cta_overrides[id].text='字'.repeat(13);assert.equal(vm.runInContext('formIssue(S.draft).field',ctx),'cta-'+id);
  vm.runInContext('togP('+JSON.stringify(id)+')',ctx);assert.equal(Object.keys(ctx.S.draft.cta_overrides).length,0);
});
test('参考说明选填，用途不能重复，风格参考锁定画风',()=>{
  const ctx=context(),id=placements.find(p=>p.category==='应用商店'&&p.image_form==='单图').id;
  Object.assign(ctx.S.draft,{pids:[id],t1:'标题',t2:'副标题',references:[{id:'ref',purpose:'style',note:'',preview:'data:image/jpeg;base64,AA'}]});
  assert.equal(vm.runInContext('formIssue(S.draft)',ctx),null);
  let html=vm.runInContext('viewForm()',ctx);
  assert(html.includes('🔒 按参考图'));assert(!html.includes('id="styleq"'));assert(html.includes('maxlength="200"'));
  ctx.S.draft.references.push({id:'other',purpose:'style',note:''});
  assert.equal(vm.runInContext('formIssue(S.draft).field',ctx),'reference-options');
  ctx.S.draft.references=[{id:'ref',purpose:'style',note:'字'.repeat(201)}];
  assert.equal(vm.runInContext('formIssue(S.draft).message',ctx),'参考图说明最多 200 字');
});
test('计数乘以形式张数，步进器限制在1至20且清除分别设置',()=>{
  const ctx=context('三图'),id=placements.find(p=>p.image_form==='三图').id;
  ctx.S.draft.pids=[id];ctx.S.draft.sets=2;
  assert(vm.runInContext('viewForm()',ctx).includes('共 6 张'));
  assert(vm.runInContext('viewForm()',ctx).includes('1 版位 × 2 套 × 3 张'));
  ctx.S.draft.sets=20;ctx.S.draft.variants_by_placement={[id]:4};
  vm.runInContext('stepSets(1)',ctx);assert.equal(ctx.S.draft.sets,20);assert.equal(ctx.S.draft.variants_by_placement,undefined);
  ctx.S.draft.sets=1;vm.runInContext('stepSets(-1)',ctx);assert.equal(ctx.S.draft.sets,1);
});
test('未选渠道时旧默认版位不进入计数，版位区只保留置灰结构',()=>{
  const ctx=context();Object.assign(ctx.S.draft,{channel:'',sets:2,pids:placements.filter(p=>p.image_form==='单图').slice(0,7).map(p=>p.id)});
  let html=vm.runInContext('viewForm()',ctx);
  assert(html.includes('共 0 张'));assert(!html.includes('共 14 张'));
  assert(!html.includes('placement-count'));assert(!html.includes('请先选择渠道'));assert(!html.includes('7 版位'));
  const nodes={'#tot':{},'#sum-formula':{},'#go':{}};
  ctx.document.querySelector=selector=>nodes[selector]||null;
  vm.runInContext('updSum()',ctx);
  assert.equal(nodes['#tot'].textContent,'共 0 张');assert.equal(nodes['#sum-formula'].innerHTML,'');
  assert.equal(nodes['#go'].disabled,true);
});
test('版位按钮收起时显示最终文字，菜单保留模式名并标记当前项',()=>{
  const ctx=context(),p=placements.find(p=>p.category==='应用商店'&&p.image_form==='单图');
  ctx.placement=p;ctx.S.draft.pids=[p.id];
  let html=vm.runInContext('placementCta(S.draft,placement)',ctx);
  assert(html.includes('data-cta-label="'+p.id+'">立即体验</span>'));
  assert(html.includes('value="inherit" selected>✓ 跟随统一</option>'));
  ctx.S.draft.cta_enabled=false;
  html=vm.runInContext('placementCta(S.draft,placement)',ctx);
  assert(html.includes('no-button'));assert(html.includes('>无按钮</span>'));
  ctx.S.draft.cta_enabled=true;ctx.S.draft.cta='';
  assert(vm.runInContext('placementCta(S.draft,placement)',ctx).includes('>无按钮</span>'));
  ctx.S.draft.cta_overrides[p.id]={mode:'custom',text:'马上听'};
  html=vm.runInContext('placementCta(S.draft,placement)',ctx);
  assert(html.includes('class="cta-custom-dot" aria-hidden="true">•</span>'));
  assert(html.includes('value="马上听"'));assert(html.includes('value="custom" selected>✓ 自定义</option>'));
  ctx.S.draft.cta_overrides[p.id]={mode:'none'};
  html=vm.runInContext('placementCta(S.draft,placement)',ctx);
  assert(html.includes('mode-none no-button'));assert(html.includes('value="none" selected>✓ 无按钮</option>'));
});
test('默认按钮文字和开关变化后就地更新最终文字，保留版位覆盖',()=>{
  const ctx=context(),id=placements[0].id,states=[];
  const label={dataset:{ctaLabel:id},textContent:'',parentElement:{classList:{toggle:(...args)=>states.push(args)}}};
  ctx.document.querySelectorAll=()=>[label];
  vm.runInContext('setF("cta","开始学习")',ctx);assert.equal(label.textContent,'开始学习');
  vm.runInContext('setF("cta_enabled",false)',ctx);assert.equal(label.textContent,'无按钮');
  assert.deepEqual(states.at(-1),['no-button',true]);
  ctx.S.draft.cta_overrides[id]={mode:'custom',text:'专属文字'};
  vm.runInContext('setF("cta","新的默认")',ctx);assert.equal(label.textContent,'专属文字');
});
test('配置顶栏合并为任务名和草稿状态，移除步骤条与面包屑',()=>{
  const ctx=context();Object.assign(ctx.S,{view:'form',draftStatus:'草稿已保存'});
  let html=vm.runInContext('viewHead()',ctx);
  assert(html.includes('pick-head config-head'));assert(html.includes('>新任务</h1>'));
  assert(html.includes('id="draft-status" role="status">草稿已保存</span>'));
  for(const old of ['class="crumb"','class="steps"','配置生成','挑选保存','保存草稿'])assert(!html.includes(old));
  ctx.S.cur='task';ctx.S.tasks=[{id:'task',name:'实际任务名',pkg:'APP',rounds:[]}];
  assert(vm.runInContext('viewHead()',ctx).includes('>实际任务名</h1>'));
});
test('图片模型显示短名而保留原提交值',()=>{
  const ctx=context();
  vm.runInContext('IMAGE_MODEL_OPTIONS=[["gpt-image-2-5-sunburst-image-to-image","后端长名"],["gpt-image-2-image-to-image","另一长名"]]',ctx);
  const html=vm.runInContext('imageModelOptions("gpt-image-2-5-sunburst-image-to-image")',ctx);
  assert(html.includes('value="gpt-image-2-5-sunburst-image-to-image" selected>Sunburst 2.5 · 1K</option>'));
  assert(html.includes('value="gpt-image-2-image-to-image" >GPT Image 2 · 1K</option>'));
  assert(!html.includes('后端长名'));
});

test('单图主副标题与双图三图每句输入框都有与可见标签一致的读屏名称',()=>{
 for(const form of ['单图','双图','三图']){
  const ctx=context(form),html=vm.runInContext('viewForm()',ctx);
  for(const [key,label] of vm.runInContext(`IMAGE_FORMS[${JSON.stringify(form)}].fields`,ctx)){
   const input=html.match(new RegExp('<input id="f-'+key+'"[^>]*>'))[0];
   assert(input.includes('aria-label="'+label+'"'),form+' '+key);
   assert(html.includes('<label class="copy-field" for="f-'+key+'"><span>'+label+'</span>'));
  }
 }
});
