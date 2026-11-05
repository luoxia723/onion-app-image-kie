const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
const root=path.resolve(__dirname,'..');
function setup(){
 const placements=[{id:'oppo',platform:'OPPO',name:'双图',image_count:2,target_width:320,target_height:210},{id:'xiaomi',platform:'小米',name:'双图',image_count:2,target_width:320,target_height:210}];
 const slots=placements.flatMap(p=>[1,2].flatMap(n=>[1,2].map(idx=>({id:p.id+n+idx,pid:p.id,set:n,idx,state:p.id==='xiaomi'&&n===2?'queued':'done'}))));
 const r={params:{pids:['oppo','xiaomi'],sets:2,ip:'none'},slots,sel:{'oppo::1':true},pending_placements:[]};
 const ctx=vm.createContext({document:{addEventListener(){},querySelector(){return null}},PLACEMENTS:placements,IPS:[],S:{tab:'OPPO',pf:'all'},blocked:()=>false});
 vm.runInContext(fs.readFileSync(path.join(root,'frontend/js/views.js'),'utf8'),ctx);
 ctx.round=r;vm.runInContext('R=()=>round;imgOf=()=>""',ctx);
 return ctx;
}
test('全选范围只包括当前版位和筛选下已合格或已选的套图',()=>{
 const ctx=setup();assert.deepEqual([...vm.runInContext('selectionScope(R()).map(g=>g.id)',ctx)],['oppo::1','oppo::2']);
 ctx.S.pf='no';assert.deepEqual([...vm.runInContext('selectionScope(R()).map(g=>g.id)',ctx)],['oppo::2']);
 ctx.S.pf='all';vm.runInContext('pickPlacement(R());S.pickPid="xiaomi"',ctx);assert.deepEqual([...vm.runInContext('selectionScope(R()).map(g=>g.id)',ctx)],['xiaomi::1']);
});
test('全选支持未选、部分选中、全部选中三态',()=>{
 const ctx=setup();let state=vm.runInContext('bulkSelectionState(R())',ctx);assert.equal(state.mixed,true);assert.equal(state.all,false);
 ctx.round.sel['oppo::2']=true;state=vm.runInContext('bulkSelectionState(R())',ctx);assert.equal(state.all,true);assert.equal(state.mixed,false);
 ctx.round.sel={};state=vm.runInContext('bulkSelectionState(R())',ctx);assert.equal(state.selected,0);assert.equal(state.all,false);
});
test('卡片用复选框表示选择，不再重复放选择按钮',()=>{
 const ctx=setup();const html=vm.runInContext('viewPick()',ctx);
 assert(!html.includes('选中这一套'));
 assert(html.includes('type="checkbox"'));
 assert(html.includes('全选当前版位'));
 assert(html.includes('取消选择'));
 assert(html.includes('aria-checked="mixed"'));
});

test('选中待处理套图时仍可明确保存合格套图',()=>{
 const ctx=setup();ctx.round.delivery={selected_sets:21,ready_sets:19,incomplete_sets:2,covered_placements:7,total_placements:7,can_export:false,can_export_ready:true};
 const html=vm.runInContext('viewSelectionFooter()',ctx);
 assert(html.includes('保存已合格的 19 套'));
 assert(html.includes('onclick="dlAll(true)"'));
 assert(html.includes('另 2 套待处理，不纳入本次图包'));
 assert(!/id="save-ready"[^>]*disabled/.test(html));
});
test('裁切错误不把长文本压在窄缩略图上',()=>{
 const ctx=setup();ctx.round.slots[0].reason_code='frame_failed';ctx.round.slots[0].msg='自动去框失败，当前显示完整原图，暂不可交付';
 const html=vm.runInContext('cellHtml(R(),R().slots[0],132)',ctx);
 assert(html.includes('需去框'));
 assert(html.includes('reprocessFrame('));assert(html.includes('fitImage('));
 assert(!html.includes('自动去框失败'));
 assert(html.includes('class="sample-actions"'));assert(!html.includes('320×210</div>'));
});

test('目录列出本轮全部版位，看样台只渲染当前版位并使用真实比例',()=>{
 const ctx=setup();let html=vm.runInContext('viewPick()',ctx);
 assert(html.includes('data-pick-placement="oppo"'));assert(html.includes('data-pick-placement="xiaomi"'));
 assert(html.includes('data-slot="oppo11"'));assert(!html.includes('data-slot="xiaomi11"'));
 assert(html.includes('aspect-ratio:320/210'));assert(html.includes('class="sample-caption">图 2</div>'));assert(!html.includes('图 2 · 320×210'));
 assert(html.includes('--image-ratio:'+320/210));
 assert(!html.includes('勾完自动跳到下一版位'));assert(html.includes('下一版位 →'));
 ctx.S.pickPid='xiaomi';html=vm.runInContext('viewPick()',ctx);
 assert(html.includes('data-slot="xiaomi11"'));assert(!html.includes('data-slot="oppo11"'));
 assert(html.includes('2/4'));assert(html.includes('mini-progress-track'));assert(html.includes('已选 0/1'));
 assert(/data-sel="xiaomi::2"[^>]*disabled/.test(html));
});

test('目录区分已选、出齐待选及问题套数',()=>{
 const ctx=setup();let html=vm.runInContext('viewPick()',ctx);assert(html.includes('badge-selected">已选 1/2'));
 ctx.round.sel={};ctx.round.slots.forEach(slot=>slot.state='done');html=vm.runInContext('viewPick()',ctx);
 assert.equal((html.match(/已选 0\/2/g)||[]).length,2);
 ctx.round.slots[0].delivery_eligible=false;ctx.round.slots[1].state='failed';html=vm.runInContext('viewPick()',ctx);
 assert(html.includes('· 1 问题'));assert(html.includes('已选 0/1'));assert(!html.includes('2 问题'));
 assert(html.includes("repairSet('oppo',1)"));assert(html.includes('需去框'));
 assert(/data-sel="oppo::1"[^>]*disabled/.test(html));
});

test('部分完成的套图不能新勾选，已选但变为不合格的套图仍可取消',()=>{
 const ctx=setup();ctx.round.slots[1].state='generating';
 let html=vm.runInContext('viewPick()',ctx);assert(!/data-sel="oppo::1"[^>]*disabled/.test(html));
 assert.deepEqual([...vm.runInContext('selectionScope(R()).map(group=>group.id)',ctx)],['oppo::1','oppo::2']);
 ctx.round.sel={};html=vm.runInContext('viewPick()',ctx);assert(/data-sel="oppo::1"[^>]*disabled/.test(html));
 assert.deepEqual([...vm.runInContext('selectionScope(R()).map(group=>group.id)',ctx)],['oppo::2']);
});

test('三图按图号排序并排，换轮后回到新一轮第一个版位',()=>{
 const ctx=setup();ctx.PLACEMENTS[0].image_count=3;
 ctx.round.slots.unshift({id:'third',pid:'oppo',set:1,idx:3,state:'done'});
 let html=vm.runInContext('viewPick()',ctx);
 assert(html.includes('--images:3'));assert(html.indexOf('data-slot="oppo12"')<html.indexOf('data-slot="third"'));
 vm.runInContext('S.pickPid="xiaomi";round.id="new-round"',ctx);vm.runInContext('viewPick()',ctx);assert.equal(ctx.S.pickPid,'oppo');
});

test('保存栏只呈现一个实心主按钮，零合格时禁用且不导出',()=>{
 const ctx=setup();ctx.round.delivery={selected_sets:2,ready_sets:0,incomplete_sets:2,can_export:false,can_export_ready:false};
 let html=vm.runInContext('viewSelectionFooter()',ctx);assert(html.includes('保存已合格的 0 套'));assert(/id="save-ready"[^>]*disabled/.test(html));
 assert.equal((html.match(/class="primary"/g)||[]).length,1);
 ctx.round.delivery={selected_sets:2,ready_sets:2,covered_placements:1,total_placements:2,can_export:true,can_export_ready:true};
 html=vm.runInContext('viewSelectionFooter()',ctx);assert(html.includes('onclick="dlAll(false)"'));assert(html.includes('1/2 个版位'));
 assert(!/id="save-selected"[^>]*disabled/.test(html));
});

test('任务摘要压成两行，保留状态、图片形式、进度和归档信息',()=>{
 const ctx=setup();ctx.summary={id:'task',name:'标题',status:'待挑选',done:4,total:6,image_form:'三图',archived:true};
 const html=vm.runInContext('summaryRow(summary)',ctx);
 assert(html.includes('class="t1">标题'));assert(html.includes('待挑选 · 三图 · 4/6 · 已归档'));
 assert(!html.includes('class="t3"'));assert(!html.includes('<img'));
});

test('保存后选择未变化时主按钮禁用并显示匹配版本，变化后恢复保存',()=>{
 const ctx=setup();ctx.round.delivery={selected_sets:1,ready_sets:1,incomplete_sets:0,can_export:true,has_changes:false,matching_version:'v001',last_version:'v001'};
 let html=vm.runInContext('viewSelectionFooter()',ctx),button=html.match(/<button id="save-selected"[^>]*>[^<]*<\/button>/)[0];
 assert.match(button,/disabled/);assert(button.endsWith('>已保存 v001</button>'));
 ctx.round.delivery.has_changes=true;ctx.round.delivery.ready_sets=2;
 html=vm.runInContext('viewSelectionFooter()',ctx);button=html.match(/<button id="save-selected"[^>]*>[^<]*<\/button>/)[0];
 assert(!button.includes('disabled'));assert(button.endsWith('>保存已合格的 2 套</button>'));
 ctx.round.delivery.has_changes=false;ctx.round.delivery.matching_version=null;
 html=vm.runInContext('viewSelectionFooter()',ctx);button=html.match(/<button id="save-selected"[^>]*>[^<]*<\/button>/)[0];
 assert(!button.includes('disabled'));assert(button.includes('保存已合格的 2 套'));
});

test('出图中尚无完整套图时目录只显示进度，出好一套后再显示已选数',()=>{
 const ctx=setup();ctx.round.sel={};ctx.round.slots.forEach(slot=>slot.state='generating');
 let directory=vm.runInContext('viewPick()',ctx).match(/<nav class="placement-dir"[\s\S]*?<\/nav>/)[0];
 assert(directory.includes('0/4'));assert(directory.includes('mini-progress-track'));assert(!directory.includes('已选'));
 ctx.round.slots.find(slot=>slot.id==='oppo11').state='done';
 directory=vm.runInContext('viewPick()',ctx).match(/<nav class="placement-dir"[\s\S]*?<\/nav>/)[0];
 assert(directory.includes('1/4'));assert(!directory.includes('已选'));
 ctx.round.slots.find(slot=>slot.id==='oppo12').state='done';
 directory=vm.runInContext('viewPick()',ctx).match(/<nav class="placement-dir"[\s\S]*?<\/nav>/)[0];
 assert(directory.includes('2/4'));assert(directory.includes('已选 0/1'));assert(!directory.includes('已选 0/0'));
 ctx.round.slots.forEach(slot=>slot.state='done');
 directory=vm.runInContext('viewPick()',ctx).match(/<nav class="placement-dir"[\s\S]*?<\/nav>/)[0];
 assert(!directory.includes('mini-progress-track'));assert.equal((directory.match(/已选 0\/2/g)||[]).length,2);
});

test('切版位后的图片在load事件前显示灰色占位，加载后显示图片',()=>{
 const ctx=setup();const html=vm.runInContext('cellHtml(R(),R().slots[0])',ctx),handler=html.match(/<img onload="([^"]+)"/)[1];
 const classes=[];ctx.loadedImage={parentElement:{classList:{add:name=>classes.push(name)}}};
 vm.runInContext(`(function(){${handler}}).call(loadedImage)`,ctx);assert.deepEqual(classes,['image-loaded']);
 const css=fs.readFileSync(path.join(root,'frontend/css/app.css'),'utf8');assert(css.includes('.cell:has(img):not(.image-loaded){background:#E1E4E8}'));assert(css.includes('.cell.image-loaded img{opacity:1}'));
});
