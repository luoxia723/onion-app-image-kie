const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {loadScripts}=require('./helpers/workbench.cjs');

function setup(service=async()=>({restored:1,documents_restored:0,skipped:0,versions:1,bytes:1024})){
 const calls=[],listeners={},counts={refresh:0};
 const ctx=vm.createContext({S:{maintenanceOpen:true,restorePreview:{path:'backup.zip',token:'restore-token'},prunePreview:{versions:[{}],bytes:1024,token:'prune-token'}},
  document:{addEventListener(name,fn){listeners[name]=fn}},render(){},esc:String,
  request:async(...args)=>{calls.push(args);return service(...args)},refresh:async()=>{counts.refresh++}});
 loadScripts(ctx,['maintenance']);
 return {calls,listeners,counts,run:source=>vm.runInContext(source,ctx)};
}

test('恢复取消或Escape不会发请求，保留预览供用户再次确认',async()=>{
 for(const cancel of ['button','escape']){
  const {run,calls,listeners}=setup();const pending=run('applyRestore()');
  assert(run('S.maintenanceConfirm'));assert.equal(calls.length,0);
  if(cancel==='button')run('settleMaintenanceConfirmation(false)');
  else listeners.keydown({key:'Escape',preventDefault(){}});
  await pending;assert.equal(calls.length,0);assert.equal(run('S.maintenanceConfirm'),null);
  assert.equal(run('S.restorePreview.token'),'restore-token');
 }
});

test('恢复和清理确认后走真实维护请求函数，只提交预览路径和令牌',async()=>{
 for(const [action,url,expected] of [
  ['applyRestore','/maintenance/restore',{path:'backup.zip',token:'restore-token'}],
  ['applyPrune','/maintenance/prune',{token:'prune-token'}],
 ]){
  let release;const {run,calls,counts}=setup(()=>new Promise(resolve=>release=resolve));
  const pending=run(action+'()');assert.equal(calls.length,0);
  run('settleMaintenanceConfirmation(true)');await new Promise(setImmediate);
  assert.equal(calls.length,1);assert.equal(calls[0][0],url);assert.equal(calls[0][1],'POST');
  assert.deepEqual({...calls[0][2]},expected);assert.equal(run('S.maintenanceBusy'),true);
  release({restored:1,documents_restored:0,skipped:0,versions:1,bytes:1024});await pending;
  assert.equal(run('S.maintenanceBusy'),false);assert.equal(counts.refresh,1);
  assert.equal(run(action==='applyRestore'?'S.restorePreview':'S.prunePreview'),null);
 }
});

test('维护失败时保留预览与错误信息，释放忙碌锁，不刷新任务',async()=>{
 const {run,calls,counts}=setup(async()=>{throw new Error('备份校验失败')});
 const pending=run('applyRestore()');run('settleMaintenanceConfirmation(true)');await pending;
 assert.equal(calls.length,1);assert.equal(run('S.maintenanceBusy'),false);
 assert.equal(run('S.maintenanceMessage'),'备份校验失败');assert.equal(run('S.restorePreview.token'),'restore-token');
 assert.equal(counts.refresh,0);
});
