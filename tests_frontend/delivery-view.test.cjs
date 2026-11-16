const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
function setup(){
 const app={innerHTML:''};const ctx=vm.createContext({document:{activeElement:null,querySelector:s=>s==='#app'?app:null,addEventListener(){}},window:{},
  S:{view:'dl',tasks:[],summaries:[],drafts:[],draft:{}},CFG:{},LOGO:{thumb:'logo'},PLACEMENTS:[],
  updTimers(){},task:{id:'task',name:'洋葱一拍',pkg:'APP_旧包名',ri:0,rounds:[{id:'r',params:{pids:[],image_form:'单图'},slots:[],sel:{}}],pkgs:[{id:'package',v:1,zip:'旧文件名.zip',created_at:100,images:[{id:'image',att:2,thumbnail_url:'thumb.png'}]}]}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/js/views.js'),'utf8'),ctx);
 vm.runInContext('T=()=>task;R=()=>task.rounds[task.ri];syncSelectionControls=()=>{}',ctx);
 return{ctx,app,run:s=>vm.runInContext(s,ctx)};
}
test('交付记录复用挑选页顶栏，版本白卡包含时间缩略图和文件操作，无旧步骤和底栏',()=>{
 const {run,app}=setup();run('render()');const html=app.innerHTML;
 assert(html.includes('pick-head'));assert(html.includes('洋葱一拍'));assert(html.includes('已生成'));assert(html.includes('修改配置'));assert(html.includes('复制为新任务'));
 assert(html.includes('交付记录'));assert(html.includes('返回挑选'));assert(html.includes('delivery-record'));assert(html.includes('v001'));assert(html.includes('thumb.png'));assert(html.includes('打开文件夹'));assert(html.includes('下载副本'));
 for(const old of ['class="crumb"','class="steps"','class="hbar"','selection-footer','APP_旧包名','旧文件名.zip'])assert(!html.includes(old),old);
});
test('模型短名统一且修改记录选项保持简短，菜单不再单列模型名',()=>{
 const {run}=setup();run('S.view="pick";task.rounds.push({...task.rounds[0],image_model:"gpt-image-2-5-sunburst-image-to-image",created_at:100})');
 assert(run('imageModelOptions("")').includes('Sunburst 2.5 · 1K'));
 assert.equal(run('imageModelName("gpt-image-2-5-sunburst-image-to-image")'),'Sunburst 2.5 · 1K');
 const header=run('viewHead()');assert(!header.includes('Sunburst'));assert(!run('roundLabel(task.rounds[1],1,2)').includes('GPT Image'));
});

test('任务加载时完整渲染骨架，隐藏旧内容和底部选择栏',()=>{
 const {run,app}=setup();run('S.view="form";S.openingTask="target";render()');
 assert(app.innerHTML.includes('pick-mode'));assert(app.innerHTML.includes('pick-skeleton'));assert(app.innerHTML.includes('skeleton-directory'));assert(app.innerHTML.includes('skeleton-set'));
 assert(!app.innerHTML.includes('config-form'));assert(!app.innerHTML.includes('selection-footer'));assert(!app.innerHTML.includes('正在打开，请稍候'));
});
test('撤销提示复用现有提示区域并区分草稿，空白页标题与侧栏草稿相同',()=>{
 const {run}=setup();run('S.undo={draft:{draft:{t1:"标题"}}}');const side=run('viewSide()');assert(side.includes('已删除草稿 ·'));assert(side.includes('onclick="undoDel()"'));
 run('S.view="form";S.draft={image_form:"单图",t1:"同一个标题"};S.draftId=null;S.draftStatus="草稿已保存"');
 assert(run('viewHead()').includes('同一个标题'));assert.equal(run('tName({draft:S.draft})'),'同一个标题');assert(!run('viewHead()').includes('草稿已保存'));
});

test('同版本号的历史交付仍按唯一包ID下载',()=>{
 const {run}=setup();run('task.pkgs.push({...task.pkgs[0],id:"restored-package"})');
 const html=run('viewDl()');
 assert(html.includes('redl(\'package\')'));
 assert(html.includes('redl(\'restored-package\')'));
 assert(!html.includes('redl(1)'));
});

test('图包检查并重新保存直接显示，复制任务保留在更多菜单',()=>{
 const {run}=setup();const header=run('viewHead()');
 const actions=header.split('<details class="pick-more"')[0];
 assert(!actions.includes('复制为新任务'));assert(header.includes('id="dup" onclick="dupTask()"'));
 assert(actions.includes('检查并重新保存'));assert(actions.includes('onclick="dlAll(false)"'));
});
