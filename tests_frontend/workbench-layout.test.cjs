const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
// Unit checks for JS layout arithmetic. CSS rendering needs separate browser QA.

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
 for(const name of ['views','workspace','production','app']){
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

test('三套横图优先双列并纵向滚动，保持图片实际比例',()=>{
 const scene=layoutContext({count:3,stageWidth:1200,stageHeight:430});scene.run();
 assert.equal(scene.layout().columns,2);assert.equal(scene.sets.dataset.vertical,'true');
 assert.equal(scene.layout().scroll,false);assert(scene.layout().imageWidth>500);
});

test('窄窗口的三套横图改为单列纵向浏览，不回退为隐藏在横向滚动中的整套',()=>{
 const scene=layoutContext({count:3,stageWidth:700,stageHeight:430});scene.run();
 assert.equal(scene.layout().columns,1);assert.equal(scene.sets.dataset.vertical,'true');assert.equal(scene.layout().scroll,false);
});
