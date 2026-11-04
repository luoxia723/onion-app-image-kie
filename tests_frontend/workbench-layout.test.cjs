const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const css=fs.readFileSync(path.join(__dirname,'../frontend/css/app.css'),'utf8');

function declarations(selector){
 return [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter(match=>match[1].trim()===selector).map(match=>match[2]).join(';');
}

test('看样台用剩余空间限制图框，共享版位比例且图片完整包含',()=>{
 assert.match(declarations('.sample-stage'),/display:flex;flex-direction:column/);
 assert.match(declarations('.sample-stage #sets'),/flex:1;min-height:0;container-type:size/);
 assert.match(declarations('.sample-stage #sets'),/display:grid/);
 assert.match(declarations('.sample-stage #sets'),/overflow-y:hidden/);
 assert.match(declarations('.sample-stage .set'),/height:var\(--sample-card-height\)/);
 assert.match(declarations('.sample-stage .cell'),/width:min\(100%,var\(--sample-image-width\)\)/);
 assert.match(declarations('.sample-stage .cell img'),/object-fit:contain/);
});

test('需去框标签清除旧的右下定位，保持小标签且不截获图片点击',()=>{
 const note=declarations('.sample-stage .frame-note');
 assert.match(note,/bottom:auto/);assert.match(note,/right:auto/);
 assert.match(note,/pointer-events:none/);
});

test('更多菜单重置摘要外边距和三角，弹层在按钮下方右对齐',()=>{
 const summary=declarations('.pick-more>summary');
 assert.match(summary,/margin:0/);assert.match(summary,/height:32px/);
 assert.match(declarations('.pick-more>summary::before,.pick-more[open]>summary::before'),/content:none/);
 const panel=declarations('.pick-more>div');
 assert.match(panel,/right:0/);assert.match(panel,/top:calc\(100%\s*\+\s*6px\)/);
});

test('目录已选数用文字颜色区分，问题提示用琥珀色',()=>{
 assert.match(declarations('.badge-selected'),/color:var\(--accent-blue\)/);
 assert.match(declarations('.badge-unselected-ready'),/color:var\(--text-secondary\)/);
 assert.match(declarations('.dir-problem-text'),/color:var\(--warn-amber-text\)/);
});

function layoutContext({width=984,height=422,count=2,images=1,stageWidth=796,stageHeight=688,details=0}={}){
 const values=new Map(),listeners={};
 const style={setProperty(key,value){values.set(key,String(value))}};
 const rect=height=>({height});
 const header={getBoundingClientRect:()=>rect(28)};
 const cell={getBoundingClientRect:()=>rect(200)};
 const unit={getBoundingClientRect:()=>rect(200+details),querySelector:()=>cell};
 const cards=Array.from({length:count},()=>({querySelector:()=>header,querySelectorAll:()=>Array.from({length:images},()=>unit)}));
 const sets={style,dataset:{},clientWidth:stageWidth,clientHeight:stageHeight,scrollLeft:0,querySelectorAll:()=>cards};
 const main={style:{setProperty(){}}},head={offsetHeight:56};
 const ctx=vm.createContext({document:{addEventListener(){},querySelector(selector){return selector==='#sets'?sets:selector==='main'?main:selector==='#head'?head:null}},
  window:{addEventListener(name,fn){listeners[name]=fn}},
  getComputedStyle(element){
   if(element===sets)return{paddingLeft:'2',paddingRight:'2',paddingTop:'2',paddingBottom:'12',columnGap:'18',rowGap:'18',getPropertyValue:key=>({'--images':String(images),'--image-ratio':String(width/height),'--sample-gap':'8'})[key]};
   if(element===header)return{marginTop:'0',marginBottom:'8'};
   return{paddingLeft:'12',paddingRight:'12',paddingTop:'12',paddingBottom:'10',borderLeftWidth:'1',borderRightWidth:'1',borderTopWidth:'1',borderBottomWidth:'1'};
  },S:{},setTimeout,clearTimeout});
 for(const name of ['views','app']){
  const source=fs.readFileSync(path.join(__dirname,'../frontend/js/'+name+'.js'),'utf8');
  vm.runInContext(name==='app'?source.replace('\nboot();','\n'):source,ctx);
 }
 const run=()=>vm.runInContext('setHH()',ctx);
 const number=key=>parseFloat(values.get('--sample-'+key));
 const layout=()=>({columns:number('columns'),width:number('card-width'),height:number('card-height'),imageWidth:number('image-width'),scroll:sets.dataset.scroll==='true'});
 return{run,sets,layout,listeners};
}

test('两套横图选2行1列、两套竖图选1行2列，均完整同屏且竖图用满高度',()=>{
 for(const [width,height,columns] of [[984,422,1],[720,1559,2]]){
  const scene=layoutContext({width,height});scene.run();const result=scene.layout();
  assert.equal(result.columns,columns);assert.equal(result.scroll,false);
  const rows=Math.ceil(2/result.columns);
  assert(result.columns*result.width+(result.columns-1)*18<=792+0.01);
  assert(rows*result.height+(rows-1)*18<=674+0.01);
  if(width===720)assert(Math.abs(result.height-674)<0.01);
 }
});

test('双图三图按整套计算列宽，所有套图采用相同缩放',()=>{
 for(const images of [2,3]){
  const scene=layoutContext({images,stageWidth:1200,stageHeight:900,details:26});scene.run();const result=scene.layout();
  assert.equal(result.columns,1);assert.equal(result.scroll,false);
  assert(Math.abs(result.height-(result.imageWidth/(984/422)+86))<0.01);
  assert(result.imageWidth*images+(images-1)*8+26<=result.width+0.01);
  assert(2*result.height+18<=886+0.01);
 }
});

test('先扣除图下实际按钮高度，仅最佳同屏高度小于160时退回单行滚动',()=>{
 const fits=layoutContext({stageHeight:484});fits.run();assert.equal(fits.layout().scroll,false);
 const small=layoutContext({stageHeight:484,details:70});small.run();
 const result=small.layout();assert.equal(result.scroll,true);assert.equal(result.columns,2);
 assert.equal(result.width,792);assert(result.height<=470);
 const threshold=layoutContext({stageHeight:472});threshold.run();
 assert.equal(threshold.layout().scroll,false);assert(Math.abs(threshold.layout().imageWidth/(984/422)-160)<0.01);
});

test('窗口尺寸变化通过现有resize流程重新计算列数与图片尺寸',()=>{
 const scene=layoutContext({width:720,height:1559});scene.run();const original=scene.layout();assert.equal(original.columns,2);
 scene.sets.clientWidth=1400;scene.sets.clientHeight=360;scene.listeners.resize();
 const resized=scene.layout();assert.equal(resized.columns,2);assert(resized.imageWidth<original.imageWidth);assert.equal(resized.scroll,false);
 scene.sets.clientWidth=500;scene.sets.clientHeight=1800;scene.listeners.resize();assert.equal(scene.layout().columns,1);assert.equal(scene.layout().scroll,false);
 scene.sets.clientWidth=796;scene.sets.clientHeight=688;scene.listeners.resize();assert.deepEqual(scene.layout(),original);
});
