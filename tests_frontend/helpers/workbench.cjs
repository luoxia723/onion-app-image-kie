const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const root=path.resolve(__dirname,'../..');
const readJSON=name=>JSON.parse(fs.readFileSync(path.join(root,name),'utf8'));

function loadScripts(context,names){
 names=[...names];if(names.includes('app')){const i=names.indexOf('app');if(!names.includes('workspace'))names.splice(i,0,'workspace');if(!names.includes('production'))names.splice(names.indexOf('app'),0,'production')}
 for(const name of names){
  const filename=path.join(root,'frontend/js',name+'.js');
  let source=fs.readFileSync(filename,'utf8');
  if(name==='app'){
   // Exercise the full module; only the browser-only initial network bootstrap is deferred.
   assert.equal((source.match(/^boot\(\);$/gm)||[]).length,1,'app has one bootstrap entry');
   source=source.replace(/^boot\(\);$/m,'');
  }
  vm.runInContext(source,context,{filename});
 }
}

function currentLearningConfig(){
 const content=readJSON('config/learning-machine-content-rules.json');
 const logos=readJSON('config/learning-machine-logo-templates.json');
 const masks=readJSON('config/learning-machine-mask-templates.json');
 return {
  revision:logos.revision,pipeline:'baseline_then_suite',cta:{default_text:content.default_cta},
  mask_presets:masks.mask_presets,
  logo_assets:logos.assets.map(({id,label,width,height})=>({id,label,width,height,url:'/api/learning-machine/logo-assets/'+id})),
  placements:content.placements.map(row=>({...row,category:'学习机',image_form:'单图',enabled:true,
   content_modules:row.modules,logo_required:row.modules.logo,cta_required:row.modules.cta,
   logo_policy:row.modules.logo?'required':'forbidden',cta_policy:row.modules.cta?'required':'forbidden',
   logo_template:row.modules.logo?logos.templates[row.id]:null,
   mask_template:masks.placements[row.id]||{enabled:false}})),
 };
}

function currentCatalog(){
 const current=new Map(currentLearningConfig().placements.map(row=>[row.id,row]));
 return readJSON('config/channel-placement-rules.json').placements.map(row=>current.has(row.id)?{...row,...current.get(row.id)}:row);
}

module.exports={root,loadScripts,currentLearningConfig,currentCatalog};
