const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const placements = JSON.parse(fs.readFileSync(path.join(root,'config/channel-placement-rules.json'))).placements;
function context(form='单图') {
  const ctx = vm.createContext({
    document:{addEventListener(){},querySelector(){return null}},
    PLACEMENTS:placements, STYLES:[], IPS:[],
    DEF_CTA:'立即体验', SETS_MIN:1, SETS_MAX:20,
    S:{draft:{image_form:form,pids:[],t1:'',t2:'',s1:'',s2:'',s3:'',cta:'立即体验',sets:3,ip:'random',style:'random'},formDrafts:{},tried:false},
    save(){}, structuredClone,
  });
  vm.runInContext(fs.readFileSync(path.join(root,'frontend/js/views.js'),'utf8'),ctx);
  vm.runInContext('render=()=>{};save=()=>{}',ctx);
  return ctx;
}
for (const [form,count,fields] of [['单图',13,['t1','t2']],['双图',2,['s1','s2']],['三图',4,['s1','s2','s3']]]) {
  test(form+'只显示自身字段与兼容版位',()=>{
    const ctx=context(form),html=vm.runInContext('viewForm()',ctx);
    for(const f of ['t1','t2','s1','s2','s3'])assert.equal(html.includes('id="f-'+f+'"'),fields.includes(f),f);
    const ids=[...html.matchAll(/class="chip[^\"]*"[^>]*data-pid="([^\"]+)"/g)].map(m=>m[1]);
    assert.equal(ids.length,count);
    assert(ids.every(id=>placements.find(p=>p.id===id).image_form===form));
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
test('自主配置直接可见，不放进折叠区或复用菜单按钮样式',()=>{
  const ctx=context(),html=vm.runInContext('viewForm()',ctx);
  assert(!html.split('id="visual-options"')[1].split('</section>')[0].includes('<details'));
  assert(!/class="[^"]*\bmore\b/.test(html));
  for(const id of ['ips','styleq','nologo','f-feature','f-direction','sum-config'])assert(html.includes('id="'+id+'"'),id);
  for(const label of ['随机 IP','不用 IP','使用 Logo','不用 Logo','参考图与补充要求'])assert(html.includes(label),label);
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
test('生成摘要明确显示用户选择，必带Logo的版位给出限制',()=>{
  const ctx=context();Object.assign(ctx.S.draft,{ip:'none',style:'指定画风',noLogo:true});
  let html=vm.runInContext('viewForm()',ctx);
  const summary=html.split('id="sum-config"')[1];
  assert(summary.includes('不用 IP'));assert(summary.includes('指定画风'));assert(summary.includes('不用 Logo'));
  const required=placements.find(p=>p.logo_policy==='required');ctx.S.draft.pids=[required.id];ctx.S.draft.noLogo=false;
  html=vm.runInContext('viewForm()',ctx);
  assert(/id="nologo"[^>]*disabled/.test(html));assert(html.includes('要求保留 Logo'));
});
test('角色素材按标准、学段与Q版、老师展示，指定版本进入摘要',()=>{
  const ctx=context();
  ctx.IPS=JSON.parse(fs.readFileSync(path.join(root,'assets/asset-manifest.json'))).assets.filter(a=>a.kind==='ip'&&a.enabled!==false).map(a=>({id:a.asset_id,label:a.asset_name_zh||a.display_name,stage:a.stage,variant:a.variant,thumb:'/api/assets/'+a.asset_id}));
  const selected=ctx.IPS.find(a=>a.id.includes('.primary.'));ctx.S.draft.ip=selected.id;
  const html=vm.runInContext('viewForm()',ctx);
  for(const name of ['标准形象','学段与 Q 版','老师角色'])assert(html.includes(name),name);
  for(const a of ctx.IPS)assert(html.includes('data-ip="'+a.id+'"'),a.id);
  assert(html.split('id="sum-config"')[1].includes(selected.label));
});
test('旧草稿缺少非必填配置时补齐结构，不擅自选择渠道',()=>{
  const ctx=context();vm.runInContext('loadDraft({image_form:"单图",t1:"旧草稿标题"})',ctx);
  assert.equal(ctx.S.draft.pids.length,0);assert.equal(ctx.S.draft.font,'random');
  assert(vm.runInContext('viewForm()',ctx).includes('旧草稿标题'));
});
