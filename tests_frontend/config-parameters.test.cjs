const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),{webcrypto}=require('node:crypto');
const root=path.resolve(__dirname,'..'),placements=JSON.parse(fs.readFileSync(path.join(root,'config/channel-placement-rules.json'))).placements;
function setup(request){
  const ctx=vm.createContext({crypto:webcrypto,structuredClone,TextEncoder,setTimeout,clearTimeout,btoa,
    document:{addEventListener(){},querySelector(){return {scrollTop:0,disabled:false,classList:{toggle(){}}}},querySelectorAll(){return []}},
    window:{addEventListener(){}},history:{replaceState(){}},mockRequest:request,placements});
  for(const file of ['views','drafts','app']){
    let source=fs.readFileSync(path.join(root,'frontend/js/'+file+'.js'),'utf8');
    if(file==='app')source=source.replace('\nboot();','\n');
    vm.runInContext(source,ctx);
  }
  vm.runInContext('PLACEMENTS=placements;request=(...args)=>mockRequest(...args);render=()=>{};save=()=>{};toast=()=>{};report=e=>{throw e};referencePreview=async()=>"data:image/jpeg;base64,AA";refreshDraftList=async()=>{}',ctx);
  return {ctx,run:code=>vm.runInContext(code,ctx)};
}
test('提交沿用原接口，channel、默认按钮开关和三种覆盖写入params',async()=>{
  let submitted;
  const {ctx,run}=setup(async(url,method,body)=>{
    if(url==='/tasks'){submitted=body;return {id:'task',rounds:[{params:body.params,slots:[]}],pkgs:[]}}
    return {revision:2};
  });
  const ids=placements.filter(p=>p.category==='信息流').slice(0,3).map(p=>p.id);ctx.ids=ids;
  run('CFG={planningKey:true,simulation:true,imageModel:"model"};S.draftId="draft";loadDraft({...defParams(),channel:"信息流",t1:"标题",t2:"副标题",pids:ids,cta:"立即体验",cta_enabled:false});setCtaOverride(ids[0],"inherit");setCtaOverride(ids[1],"custom","马上听");setCtaOverride(ids[2],"none")');
  await run('startGen()');
  assert.equal(submitted.draft_id,'draft');assert.equal(submitted.params.channel,'信息流');
  assert.equal(submitted.params.cta_enabled,false);assert.equal(submitted.params.cta,'立即体验');
  assert.equal(submitted.params.cta_overrides[ids[0]].mode,'inherit');
  assert.equal(submitted.params.cta_overrides[ids[1]].text,'马上听');assert.equal(submitted.params.cta_overrides[ids[2]].mode,'none');
  assert.equal(run('S.view'),'pick');
});
test('固定上传位把purpose交给上传接口，同用途重复和并发上传不增加图片',async()=>{
  const calls=[];
  const {ctx,run}=setup(async(url,method,body)=>{calls.push({url,method,body});return {id:body.purpose,name:body.name,purpose:body.purpose,note:body.note,path:'/uploads/image.png'}});
  ctx.file={name:'图片.png',size:3,arrayBuffer:async()=>new Uint8Array([1,2,3]).buffer};
  for(const purpose of ['style','composition','ui']){
    await run('addReference(file,'+JSON.stringify(purpose)+')');
    await run('addReference(file,'+JSON.stringify(purpose)+')');
  }
  assert.equal(calls.length,3);assert(calls.every(call=>call.url==='/uploads'&&call.method==='POST'&&call.body.note===''));
  assert.deepEqual(calls.map(call=>call.body.purpose),['style','composition','ui']);
  assert.equal(run('S.draft.references.length'),3);
  assert.equal(run('S.draft.references[0].preview'),'data:image/jpeg;base64,AA');
  run('removeReference(0)');
  let release;ctx.pending=()=>new Promise(resolve=>release=resolve);run('referencePreview=pending');
  const first=run('addReference(file,"style")');
  await run('addReference(file,"style")');
  release('data:image/jpeg;base64,AA');await first;
  assert.equal(calls.length,4);assert.equal(run('S.draft.references.filter(r=>r.purpose==="style").length'),1);
});
test('草稿服务往返恢复新参数、三种参考用途、说明、缩略图及独立形式文案',async()=>{
  let stored;
  const {run}=setup(async(url,method,body)=>{
    if(method==='PUT'){stored=structuredClone(body);return {revision:2}}
    return {...stored,revision:2};
  });
  run('S.draftId="a".repeat(32);loadDraft({...defParams(),channel:"应用商店",t1:"单图标题",t2:"副标题",cta_enabled:false,cta_overrides:{},references:["style","composition","ui"].map(purpose=>({id:purpose,purpose,note:purpose+"说明",preview:"data:image/jpeg;base64,AA"}))});setImageForm("双图");S.draft.s1="双图第一句";S.draft.s2="双图第二句";setImageForm("三图");S.draft.s1="三图第一句";S.draft.s2="三图第二句";S.draft.s3="三图第三句";S.draft.pids=[placements.find(p=>p.image_form==="三图").id];setCtaOverride(S.draft.pids[0],"custom","继续学习")');
  await run('persistDraft()');
  assert.equal(stored.draft.channel,'应用商店');assert.equal(stored.draft.cta_enabled,false);
  run('S.draftId=null;S.draft=defParams();S.formDrafts={};S.view="pick"');
  await run('openDraft("a".repeat(32))');
  assert.equal(run('S.draft.references.length'),3);assert.equal(run('S.draft.references[1].note'),'composition说明');
  assert.equal(run('S.draft.references[2].preview'),'data:image/jpeg;base64,AA');
  assert.equal(run('S.draft.cta_overrides[S.draft.pids[0]].text'),'继续学习');
  assert.equal(run('S.draft.cta_enabled'),false);assert.equal(run('S.draft.channel'),'应用商店');
  run('setImageForm("双图")');assert.equal(run('S.draft.s1'),'双图第一句');
  run('setImageForm("单图")');assert.equal(run('S.draft.t1'),'单图标题');
  run('setImageForm("三图")');assert.equal(run('S.draft.s3'),'三图第三句');
});
