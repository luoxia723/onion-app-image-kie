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
test('全选范围只包括当前渠道和筛选下有结果的套图',()=>{
 const ctx=setup();assert.deepEqual([...vm.runInContext('selectionScope(R()).map(g=>g.id)',ctx)],['oppo::1','oppo::2']);
 ctx.S.pf='no';assert.deepEqual([...vm.runInContext('selectionScope(R()).map(g=>g.id)',ctx)],['oppo::2']);
 ctx.S.tab='all';ctx.S.pf='all';assert.deepEqual([...vm.runInContext('selectionScope(R()).map(g=>g.id)',ctx)],['oppo::1','oppo::2','xiaomi::1']);
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
 assert(html.includes('全选当前列表'));
 assert(html.includes('取消选择'));
 assert(html.includes('aria-checked="mixed"'));
});

test('选中待处理套图时仍可明确保存合格套图',()=>{
 const ctx=setup();ctx.round.delivery={selected_sets:21,ready_sets:19,incomplete_sets:2,covered_placements:7,total_placements:7,can_export:false,can_export_ready:true};
 const html=vm.runInContext('viewSelectionFooter()',ctx);
 assert(html.includes('保存可交付的 19 套'));
 assert(html.includes('另 2 套待处理，不纳入本次图包'));
 assert(!/id="save-ready"[^>]*disabled/.test(html));
});
test('裁切错误不把长文本压在窄缩略图上',()=>{
 const ctx=setup();ctx.round.slots[0].reason_code='frame_failed';ctx.round.slots[0].msg='自动去框失败，当前显示完整原图，暂不可交付';
 const html=vm.runInContext('cellHtml(R(),R().slots[0],132)',ctx);
 assert(html.includes('待适配'));
 assert(!html.includes('自动去框失败'));
});
