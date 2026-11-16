const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),{webcrypto}=require('node:crypto');
const root=path.resolve(__dirname,'..'),placements=JSON.parse(fs.readFileSync(path.join(root,'config/channel-placement-rules.json'))).placements;
function setup(request){
  const ctx=vm.createContext({crypto:webcrypto,structuredClone,TextEncoder,setTimeout,clearTimeout,btoa,
    document:{addEventListener(){},getElementById(){return {focus(){}}},querySelector(){return {scrollTop:0,disabled:false,classList:{toggle(){}}}},querySelectorAll(){return []}},
    window:{addEventListener(){}},history:{replaceState(){}},mockRequest:request,placements});
  for(const file of ['views','drafts','workspace','production','app']){
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
  const {ctx,run}=setup(async(url,method,body)=>{calls.push({url,method,body});if(url==='/references/points')return {points:['暖色','水彩','柔光']};return {id:body.purpose,name:body.name,purpose:body.purpose,note:body.note,path:'/uploads/image.png'}});
  ctx.file={name:'图片.png',size:3,arrayBuffer:async()=>new Uint8Array([1,2,3]).buffer};
  for(const purpose of ['style','composition','ui']){
    await run('addReference(file,'+JSON.stringify(purpose)+')');
    await run('addReference(file,'+JSON.stringify(purpose)+')');
  }
  const uploads=calls.filter(call=>call.url==='/uploads'),extractions=calls.filter(call=>call.url==='/references/points');
  assert.equal(uploads.length,3);assert(uploads.every(call=>call.method==='POST'&&call.body.note===''));
  assert.deepEqual(uploads.map(call=>call.body.purpose),['style','composition','ui']);
  assert.deepEqual(extractions.map(call=>({...call.body})),['style','composition','ui'].map(purpose=>({id:purpose,purpose})));
  assert.equal(run('S.draft.references.length'),3);
  assert.equal(run('S.draft.references[0].preview'),'data:image/jpeg;base64,AA');
  run('removeReference(0)');
  let release;ctx.pending=()=>new Promise(resolve=>release=resolve);run('referencePreview=pending');
  const first=run('addReference(file,"style")');
  await run('addReference(file,"style")');
  release('data:image/jpeg;base64,AA');await first;
  assert.equal(calls.length,8);assert.equal(run('S.draft.references.filter(r=>r.purpose==="style").length'),1);
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

for(const purpose of ['style','composition','ui'])test(purpose+' 上传即提炼，标签可增删改并随草稿恢复',async()=>{
  let finish,stored;
  const {ctx,run}=setup(async(url,method,body)=>{
    if(url==='/uploads')return {id:purpose,purpose,name:'图片.png'};
    if(url==='/references/points')return new Promise(resolve=>finish=resolve);
    if(method==='PUT'){stored=structuredClone(body);return {revision:2}}
    return {...stored,revision:2};
  });
  ctx.file={name:'图片.png',size:1,arrayBuffer:async()=>new Uint8Array([1]).buffer};
  run('S.draftId="a".repeat(32)');
  const upload=run(`addReference(file,"${purpose}")`);
  await new Promise(setImmediate);
  assert.equal(run('S.uploadingPurpose'),null);
  assert.equal(run('S.draft.references.length'),1);
  assert(run('viewReferenceOptions(S.draft)').includes('提炼中…'));
  assert(!Object.hasOwn(run('draftPayload().draft.references[0]'),'pending'));
  finish({points:['低饱和暖色','水彩笔触','柔和顶光']});await upload;
  let html=run('viewReferenceOptions(S.draft)');
  assert(!html.includes('提炼中…'));assert(!html.includes('确认'));
  assert(html.includes('class="points-tag-list"')&&html.includes('value="水彩笔触"'));
  assert(html.includes('setReferencePoint(0,0,this.value)')&&html.includes('removeReferencePoint(0,0)'));
  assert(html.includes('＋ 添加要点'));
  run('setReferencePoint(0,0,"明亮冷色");removeReferencePoint(0,1);addReferencePoint(0);setReferencePoint(0,2,"简洁层次")');
  assert.deepEqual(Array.from(run('draftPayload().draft.references[0].points')),['明亮冷色','柔和顶光','简洁层次']);
  await run('persistDraft()');
  assert.deepEqual(Array.from(stored.draft.references[0].points),['明亮冷色','柔和顶光','简洁层次']);
  run('S.draftId=null;S.draft=defParams();S.view="pick"');
  await run('openDraft("a".repeat(32))');
  assert.deepEqual(Array.from(run('S.draft.references[0].points')),['明亮冷色','柔和顶光','简洁层次']);
  html=run('viewReferenceOptions(S.draft)');assert(html.includes('value="明亮冷色"'));
  run('setReferencePoint(0,0,\'<img src=x onerror="bad()">\')');
  assert(!run('viewReferenceOptions(S.draft)').includes('<img src=x'));
});

test('提炼失败不报错，保留图片并允许手动添加最多六条要点',async()=>{
  const {ctx,run}=setup(async url=>{
    if(url==='/references/points')throw new Error('提炼失败');
    return {id:'style',purpose:'style',name:'图片.png'};
  });
  ctx.file={name:'图片.png',size:1,arrayBuffer:async()=>new Uint8Array([1]).buffer};
  run('toast=report=()=>{throw new Error("不应弹窗")}');
  await run('addReference(file,"style")');
  assert.equal(run('S.draft.references.length'),1);
  const html=run('viewReferenceOptions(S.draft)');
  assert(!html.includes('提炼中…'));assert(!html.includes('class="point-tag"'));
  assert(html.includes('onclick="addReferencePoint(0)"'));
  run('for(let j=0;j<7;j++){addReferencePoint(0);if(j<6)setReferencePoint(0,j,"手动要点")}');
  assert.equal(run('S.draft.references[0].points.length'),6);
  assert.deepEqual(Array.from(run('draftPayload().draft.references[0].points')),Array(6).fill('手动要点'));
});

test('移除并重传同一图片后，旧提炼响应不写回新标签',async()=>{
  const finishes=[];
  const {ctx,run}=setup(async url=>{
    if(url==='/references/points')return new Promise(resolve=>finishes.push(resolve));
    return {id:'style',purpose:'style',name:'图片.png'};
  });
  ctx.file={name:'图片.png',size:1,arrayBuffer:async()=>new Uint8Array([1]).buffer};
  const first=run('addReference(file,"style")');await new Promise(setImmediate);
  run('removeReference(0)');
  const second=run('addReference(file,"style")');await new Promise(setImmediate);
  finishes[0]({points:['过期结果']});await first;
  assert.deepEqual(Array.from(run('S.draft.references[0].points')),[]);
  assert(run('viewReferenceOptions(S.draft)').includes('提炼中…'));
  finishes[1]({points:['当前结果']});await second;
  assert.deepEqual(Array.from(run('S.draft.references[0].points')),['当前结果']);
});

test('切换形式后提炼仍写入当前参考图，切换草稿后不串入结果',async()=>{
  let finish;
  const {ctx,run}=setup(async url=>{
    if(url==='/references/points')return new Promise(resolve=>finish=resolve);
    return {id:'style',purpose:'style',name:'图片.png'};
  });
  ctx.file={name:'图片.png',size:1,arrayBuffer:async()=>new Uint8Array([1]).buffer};
  run('S.draft.channel="应用商店"');
  const first=run('addReference(file,"style")');await new Promise(setImmediate);
  run('setImageForm("双图")');finish({points:['共享要点']});await first;
  assert.deepEqual(Array.from(run('S.draft.references[0].points')),['共享要点']);
  run('setImageForm("单图")');assert.deepEqual(Array.from(run('S.draft.references[0].points')),['共享要点']);
  run('removeReference(0)');
  const second=run('addReference(file,"style")');await new Promise(setImmediate);
  run('S.draftId="新草稿";loadDraft({...defParams(),references:[{id:"style",purpose:"style",points:["用户填写"]}]})');
  finish({points:['过期要点']});await second;
  assert.deepEqual(Array.from(run('S.draft.references[0].points')),['用户填写']);
});
