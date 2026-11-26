const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function setup(){
 const listeners={},calls=[],nodes=new Map();
 let ctx;
 const document={activeElement:null,body:{},addEventListener(type,callback){(listeners[type]??=[]).push(callback)},
  querySelector(selector){return nodes.get(selector)||null}};
 ctx=vm.createContext({document,window:{addEventListener(){}},setTimeout,clearTimeout,TextEncoder,DRAFT_EDITOR:'editor',calls});
 for(const name of ['views','prompt-drafts','workspace','production','app']){
  let source=fs.readFileSync(path.join(__dirname,'../frontend/js/'+name+'.js'),'utf8');
  if(name==='app')source=source.replace('\nboot();','\n');
  vm.runInContext(source,ctx);
 }
 const run=code=>vm.runInContext(code,ctx);
 function renderPreview(){
  for(const selector of nodes.keys())if(selector.startsWith("#pv"))nodes.delete(selector);
  ctx.html=run('S.pv?viewPv():""');
  if(!ctx.html)return;
  nodes.set('#pv',{});
  for(const match of ctx.html.matchAll(/<button\b([^>]*)id="([^"]+)"([^>]*)>/g)){
   const attrs=match[1]+match[3],id=match[2],handler=attrs.match(/onclick="([^"]+)"/);
   nodes.set('#'+id,{disabled:/\bdisabled\b/.test(attrs),focus(){document.activeElement=this},
    click(){return !this.disabled&&handler?run(handler[1]):undefined}});
  }
 }
 ctx.renderPreview=renderPreview;
 run(`
  PLACEMENTS=[{id:'xm',platform:'小米',name:'三图',image_count:3,target_width:960,target_height:540},{id:'other',platform:'其他',name:'单图',image_count:1,target_width:720,target_height:1559}];
  S.cur='task';S.view='pick';
  const slots=[['last','xm',2,1],['other','other',1,1],['third','xm',1,3],['first','xm',1,1],['second','xm',1,2]].map(([id,pid,set,idx])=>({id,pid,set,idx,state:'done',att:2,round_index:0,prompt:'实际提示词',orig:'原提示词',image_url:id+'.png',original_image_url:id+'-raw.png',history:[{att:1,image_url:id+'-v1.png'},{att:2,image_url:id+'.png'}]}));
  S.tasks=[{id:'task',ri:0,rounds:[{id:'round',params:{pids:['xm','other']},sel:{},slots}]}];
  S.pv='first';S.pvDetails={...slots.find(s=>s.id==='first')};window._pvFrom='[data-slot="first"]';
  render=renderPreview;softRender=()=>{};report=e=>{throw e};toast=()=>{};
  request=async(url,method,body)=>{calls.push({url,method,body});return method==='PUT'?{}:{...R().slots.find(s=>url.includes('/image-details/'+s.id+'?'))}};
 `);
 renderPreview();
 async function key(key,editing=false){
  const event={key,target:{closest:()=>editing?{}:null},prevented:false,preventDefault(){this.prevented=true}};
  for(const listener of listeners.keydown||[])await listener(event);
  // Keyboard handlers trigger the same asynchronous open/close actions as the buttons.
  await new Promise(resolve=>setImmediate(resolve));
  return event;
 }
 return{ctx,run,calls,nodes,key,html:()=>run('viewPv()')};
}
test('喜马拉雅待复审首图通过缩略图打开当前版本，处理入口留在工作台',async()=>{
 const {run,html,calls}=setup();
 run(`S.pv=null;S.pvDetails=null;R().params.ximalaya_suite=true;plOf('xm').platform='喜马拉雅';
      Object.assign(R().slots.find(s=>s.id==='first'),{image_url:null,original_image_url:null,
       state:'failed',delivery_eligible:false,review_image_url:'/review.png?v=2',
       ximalaya_review:{status:'unavailable',message:'视觉审核暂未返回'}});
      const read=request;request=async(...args)=>{const details=await read(...args);delete details.review_image_url;return details};`);
 const trigger=run('viewXimalayaImage(R(), R().slots.find(s=>s.id==="first"), R().slots.find(s=>s.id==="first"))')
  .match(/<button[^>]*class="ximalaya-image-preview"[^>]*onclick="([^"]+)"/);
 assert(trigger,'缩略图应在本页打开图片详情');
 await run(trigger[1]);
 assert.equal(calls.length,1);assert.match(calls[0].url,/\/image-details\/first\?/);assert.equal(calls[0].method,undefined);
 assert.match(html(),/id="pvImg"[^>]*src="\/review\.png\?v=2"/);
 assert.match(html(),/视觉审核暂未返回/);
 assert.match(html(),/重试审核/);
 assert.doesNotMatch(html(),/id="pvredo"|下载这张图片|选这一套/);
 run('S.pvDetails.att=1;S.pvDetails.is_historical=true');
 assert.doesNotMatch(html(),/id="pvImg"[^>]*\/review\.png|重试审核/);
});

test('新图层图片旁显示固定无Logo规则但不改写提示词，旧图片编辑保持原状',()=>{
 const {run}=setup();run('S.pvDetails.logo_fixed_rule="固定：不绘Logo <品牌>";S.pvDetails.prompt="用户逐字编辑的原文\\n第二行"');
 let html=run('viewPv()');assert(html.includes('Logo固定规则'));assert(html.includes('固定：不绘Logo &lt;品牌&gt;'));assert(html.includes('验收时可切换'));
 const text=html.match(/<textarea[^>]*id="pvPrompt"[^>]*>([\s\S]*?)<\/textarea>/)[1];assert.equal(text,'用户逐字编辑的原文\n第二行');assert(!text.includes('固定：'));
 run('delete S.pvDetails.logo_fixed_rule');html=run('viewPv()');assert(!html.includes('class="fixed-logo-rule"'));assert(html.includes('用户逐字编辑的原文'));
});

test('预览在同一版位内按套号和图号前后切换，首尾禁用且计数同步',async()=>{
 const {run,nodes,html}=setup();
 assert(nodes.get('#pvprev').disabled);assert.match(html(),/id="pvCounter">1 \/ 4/);
 for(const [id,count] of [['second',2],['third',3],['last',4]]){
  await nodes.get('#pvnext').click();assert.equal(run('S.pv'),id);assert.match(html(),new RegExp('id="pvCounter">'+count+' / 4'));
 }
 assert(nodes.get('#pvnext').disabled);await nodes.get('#pvnext').click();assert.equal(run('S.pv'),'last');
 for(const id of ['third','second','first']){await nodes.get('#pvprev').click();assert.equal(run('S.pv'),id)}
 assert(nodes.get('#pvprev').disabled);
});

test('单图版位的左右按钮直接切换上一套和下一套',async()=>{
 const {run,nodes}=setup();
 run('PLACEMENTS[0].image_count=1;R().slots=R().slots.filter(s=>s.idx===1);render()');
 await nodes.get('#pvnext').click();assert.equal(run('S.pv'),'last');
 await nodes.get('#pvprev').click();assert.equal(run('S.pv'),'first');
});

test('左右键复用按钮导航，编辑控件保留方向键，Esc关闭并恢复焦点',async()=>{
 const {run,key,nodes}=setup();
 assert((await key('ArrowRight')).prevented);assert.equal(run('S.pv'),'second');
 assert(!(await key('ArrowLeft',true)).prevented);assert.equal(run('S.pv'),'second');
 await key('ArrowLeft');assert.equal(run('S.pv'),'first');
 let restored=false;nodes.set('[data-slot="first"]',{focus(){restored=true}});
 assert((await key('Escape')).prevented);assert.equal(run('S.pv'),null);assert(restored);
});

test('设置面板打开时不触发预览导航，预览加载中也能Esc取消',async()=>{
 const {run,key,calls,nodes}=setup();nodes.set('#cfgdlg',{});
 run('S.cfgOpen=true');
 assert(!(await key('ArrowRight')).prevented);assert.equal(calls.length,0);
 run('S.cfgOpen=false;S.pvDetails=null;render()');
 await key('Escape');assert.equal(run('S.pv'),null);
});

test('切图先保存提示词草稿，保存失败则保留当前图片与编辑内容',async()=>{
 const {run,nodes,calls}=setup();
 run('S.promptDraft={id:"first",att:2,value:"草稿内容",dirty:true,sequence:0}');
 await nodes.get('#pvnext').click();
 assert.equal(calls[0].method,'PUT');assert.equal(calls[0].body.text,'草稿内容');
 assert.match(calls[1].url,/image-details\/second\?/);assert.equal(run('S.pv'),'second');
 run('S.promptDraft={id:"second",att:2,value:"未保存内容",dirty:true,sequence:0};request=async()=>{throw Error("offline")}');
 await assert.rejects(nodes.get('#pvnext').click(),/offline/);
 assert.equal(run('S.pv'),'second');assert.equal(run('S.promptDraft.value'),'未保存内容');
});

test('实际提示词默认可读，编辑稿和自然画布处理记录分开',()=>{
 const {run,html}=setup();
 run('S.pvDetails.delivery_eligible=false;S.pvDetails.preview_kind="raw"');
 let markup=html();
 for(const id of ['pvwhy','pvsel','pvredo','pvRetryScope','pvActualPrompt','pvPrompt','pvReset','pvRefs','imageVersion','prompt-draft-status'])assert(markup.includes('id="'+id+'"'),id);
 assert(markup.includes('实际提示词'));assert(markup.includes('处理记录'));assert(markup.includes('参考素材'));
 assert.match(markup,/<div class="prompt-editor" hidden/);
 assert.match(markup,/未通过交付规格/);
 run('document.getElementById=()=>null;editOrdinaryPreviewPrompt()');markup=html();assert(!markup.match(/<div class="prompt-editor" hidden/));
 run('S.promptDraft={id:"first",value:"编辑后的草稿"}');markup=html();assert.match(markup,/id="pvActualPrompt"[^>]*>实际提示词/);assert.match(markup,/>编辑后的草稿<\/textarea>/);
});

test('历史版本保持只读与禁用重出，已清理版本显示状态并禁用保留',()=>{
 const {run,html}=setup();run('S.pvDetails.is_historical=true;S.pvDetails.files_cleared=true');
 const markup=html();
 assert.match(markup,/历史版本只读/);assert.match(markup,/id="pvPrompt"[^>]*readonly/);
 assert.match(markup,/id="pvsel"[^>]*disabled/);assert.match(markup,/id="pvredo"[^>]*disabled/);
 assert.match(markup,/文件已清理/);assert.match(markup,/<button disabled onclick="pinImageVersion\(\)"/);
});

test('选套成功、取消与失败后同步真实选择状态并保留复选框外形',async()=>{
 const {run,nodes,html}=setup();
 const classes=new Set(),attrs={};
 const button={classList:{toggle(name,on){on?classes.add(name):classes.delete(name)}},setAttribute(key,value){attrs[key]=value}};
 nodes.set('#pvsel',button);
 run('softRender=syncSelectionControls;action=async(name,data)=>{R().sel[selectionKey(data.placement_id,data.set)]=data.adopted}');
 await run('toggleSel(1,true,"xm")');assert(classes.has('checked'));assert.equal(attrs['aria-pressed'],'true');assert.match(html(),/class="pv-check"/);
 await run('toggleSel(1,true,"xm")');assert(!classes.has('checked'));assert.equal(attrs['aria-pressed'],'false');
 run('report=()=>{};action=async()=>{throw Error("offline")}');
 await run('toggleSel(1,true,"xm")');assert(!classes.has('checked'));assert.equal(attrs['aria-pressed'],'false');
});

test('成品与原图切换在对比后仍可用，版本和编辑草稿保持分离',()=>{
 const {run,html}=setup();
 run('S.pvEditing=true;S.promptDraft={id:"first",value:"编辑中"};comparePrevious()');
 assert.match(html(),/class="compare-images"/);
 run('togglePvOriginal()');
 assert.match(html(),/id="pvImg"[^>]*src="first-raw.png"/);assert.match(html(),/id="pvsource"[^>]*aria-pressed="true"/);
 assert(!html().match(/<div class="prompt-editor" hidden/));assert.match(html(),/>编辑中<\/textarea>/);
 run('togglePvOriginal()');assert.match(html(),/id="pvImg"[^>]*src="first.png"/);
 assert.match(html(),/id="imageVersion" onchange="openPv\('first',\+this.value\)"/);
});

test('设置保留字段、Key占位、连接和保存动作，删除分组说明段落',()=>{
 const {run}=setup();run('CFG.kie=true;CFG.planningKey=true');const html=run('viewWorkspaceSettings()');
 for(const id of ['planmodel','plankey','plantest','planst','planbase','cfgimagemodel','kiekey','kietest','kiest','cfgimagemode','kbase','kup','stor','cfgpath','cfgsave'])assert(html.includes('id="'+id+'"'),id);
 assert(!html.includes('id="product-facts"'));
 assert.equal((html.match(/已配置，留空保留/g)||[]).length,2);assert(!html.includes('class="ro"'));
 for(const action of ['testPlanning()','testConn()','imageKeyEntered()','chooseFolder()','saveCfg()'])assert(html.includes('onclick="'+action+'"')||html.includes('oninput="'+action+'"'));
});

test('固定功能导航不混放任务列表或全局模拟标签，模式属于当前任务',()=>{
 const {run}=setup();run('S.tasks=[];S.pv=null');
 const markup=run('viewSide()');
 for(const label of ['制作任务','Logo模板','交付记录','模型与设置','数据维护'])assert(markup.includes(label));
 assert(!markup.includes('draft-list'));assert(!markup.includes('模拟预览'));
 run('CFG.simulation=false');assert.equal(run('viewSide()'),markup);
});

test('队列合并等待依赖，暂停显示短词，空闲或未读取时无文字',()=>{
 const {run}=setup();
 for(const [queue,expected] of [
  [null,''],[{running:0,queued:0,waiting:0,paused:0},''],[{running:0,queued:0,waiting:0,paused:2},''],
  [{running:2,queued:3,waiting:4,paused:0},'出图中 2 · 排队 7'],
  [{running:1,queued:2,waiting:3,paused:2},'出图中 1 · 排队 5 · 已暂停'],
  [{running:0,queued:0,waiting:3,paused:1},'出图中 0 · 排队 3 · 已暂停'],
 ]){run('S.queue='+JSON.stringify(queue));assert.equal(run('queueText()'),expected)}
});

test('队列阻塞与维护仍显示原提示，并优先于任务计数',()=>{
 const {run}=setup();run('S.queue={running:2,queued:3,waiting:4,maintenance:true}');
 assert.equal(run('queueText()'),'正在进行本机数据维护，队列暂缓提交');
 run('S.queue.blocked_reason="请先配置 Key"');assert.equal(run('queueText()'),'请先配置 Key');
});

test('自然画布处理记录与未合格原图明确区分',()=>{
 const {run,html}=setup();run('S.pvDetails.natural_processing={method:"natural_canvas_exact_crop"};S.pvDetails.preview_kind="processed"');
 let content=html();assert(content.includes('已按固定安全区从完整自然画布裁成目标尺寸'));
 run('S.pvDetails.delivery_eligible=false;S.pvDetails.preview_kind="raw"');content=html();assert(content.includes('当前图片未通过交付规格'));
});
