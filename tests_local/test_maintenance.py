import copy,json,sqlite3,threading,time
from pathlib import Path
from types import SimpleNamespace
import pytest
from local_app.config import Settings,UserError
from local_app.engine import Engine
from local_app.kie_client import generate,ImageExecutionBusy
from local_app.instance import InstanceLock
from local_app.planning import BY_ID
from tests_local.fakes import FixturePlanner
from tests_local.test_workbench import engine,params,wait_done


def test_old_versions_preview_pin_and_protected_current(engine):
    e=engine;tid=e.create(params(False,1),'prune-one')['id'];t=wait_done(e,tid);s=t['rounds'][0]['slots'][0];old=copy.deepcopy(s)
    e.mutate(tid,'regenerate',{'image_id':s['id']});wait_done(e,tid)
    plan=e.prune_plan();assert any(v['att']==1 for v in plan['versions'])
    e.pin_version(tid,s['id'],1,True)
    with pytest.raises(UserError,match='变化'):e.prune_versions(plan['token'])
    assert not e.prune_plan()['versions']
    e.pin_version(tid,s['id'],1,False);plan=e.prune_plan();e.prune_versions(plan['token'])
    assert not Path(old['output']).exists() and Path(s['output']).is_file()
    assert e.image_details(tid,s['id'],att=1)['files_cleared']
    assert e.image_details(tid,s['id'],att=1)['image_url'] is None


def test_export_and_branch_references_protect_older_files(engine):
    e=engine;tid=e.create(params(True,1),'protect-branch')['id'];t=wait_done(e,tid);r=t['rounds'][0];head=r['slots'][0]
    e.mutate(tid,'adopt',{'set':1,'adopted':True});e.package(tid,0)
    e.mutate(tid,'regenerate',{'image_id':head['id']});wait_done(e,tid)
    assert not any(v['att']==1 for v in e.prune_plan()['versions'])


def test_backup_restores_files_and_skips_existing_tasks(engine,tmp_path):
    e=engine;tid=e.create(params(True,1),'backup-real-files')['id'];t=wait_done(e,tid);e.mutate(tid,'adopt',{'set':1,'adopted':True});e.package(tid,0)
    backup=e.create_backup();preview=e.restore_preview(backup['path']);assert preview['conflicts']==1
    assert e.restore_backup(backup['path'],preview['token'])['restored']==0
    settings=Settings(tmp_path/'restored-state',tmp_path/'restored.env');settings.update({'output_dir':str(tmp_path)})
    other=Engine(settings,start=False,planner=FixturePlanner())
    try:
        p=other.restore_preview(backup['path']);result=other.restore_backup(backup['path'],p['token']);assert result['restored']==1
        restored=other.task(tid);assert restored['rounds'][0]['paused']
        for s in restored['rounds'][0]['slots']:
            assert Path(s['output']).is_file() and Path(s['jpeg']).is_file()
            import render
            render.validate_asset_reference_bindings(s['refs'])
        assert other.valid_package(restored,restored['pkgs'][0]['fingerprint'])
        assert other.restore_backup(backup['path'],p['token'])['restored']==0
    finally:other.close()


def test_corrupt_backup_does_not_restore(engine,tmp_path):
    bad=tmp_path/'bad.zip';bad.write_bytes(b'not a backup')
    with pytest.raises(UserError,match='损坏'):engine.restore_preview(bad)
    assert not engine.tasks


def test_corrupt_task_isolated_without_blocking_healthy_records(tmp_path):
    settings=Settings(tmp_path/'state',tmp_path/'.env');settings.update({'output_dir':str(tmp_path)})
    e=Engine(settings,start=False,planner=FixturePlanner());tid=e.create(params(False,1),'healthy-record')['id'];e.db.execute('INSERT INTO tasks VALUES(?,?,?)',('broken','{bad json',None));e.db.commit();e.close()
    e=Engine(settings,start=False,planner=FixturePlanner())
    try:assert tid in e.tasks and 'broken' not in e.tasks and e.maintenance_status()['quarantined'][0]['id']=='broken'
    finally:e.close()


def test_image_lock_blocks_second_executor_before_network(tmp_path):
    out=tmp_path/'image.png';lock=InstanceLock(out.with_suffix('.png.execution.lock'))
    try:
        with pytest.raises(ImageExecutionBusy):generate({'slot':{'output':str(out)}},'fake',[],lambda stage:None)
    finally:lock.close()


def test_low_disk_rejects_new_submission(engine,monkeypatch):
    import local_app.safety as safety
    monkeypatch.setattr(safety.shutil,'disk_usage',lambda p:SimpleNamespace(free=1))
    with pytest.raises(UserError,match='磁盘'):engine.create(params(False,1),'low-space')
    assert not engine.tasks


def test_historical_export_uses_frozen_rules(engine,monkeypatch):
    e=engine;tid=e.create(params(False,1),'frozen-specs')['id'];t=wait_done(e,tid);pid=t['rounds'][0]['slots'][0]['pid']
    changed=copy.deepcopy(BY_ID[pid]);changed['target_width']+=100;monkeypatch.setitem(BY_ID,pid,changed)
    e.mutate(tid,'adopt',{'set':1,'adopted':True});package=e.package(tid,0);assert Path(package['path']).is_file()


def test_pinned_current_version_survives_regeneration(engine):
    e=engine;tid=e.create(params(False,1),'pin-before-retry')['id'];t=wait_done(e,tid);s=t['rounds'][0]['slots'][0]
    e.pin_version(tid,s['id'],s['att'],True);e.mutate(tid,'regenerate',{'image_id':s['id']});wait_done(e,tid)
    assert s['versions'][0]['pinned'] and not s.get('pinned')
    assert not e.prune_plan()['versions']


def test_bad_document_is_isolated_and_backup_excludes_key_files(engine):
    e=engine;e.db.execute('INSERT INTO documents VALUES(?,?)',('draft:broken','{bad'));e.db.commit()
    assert not e.list_drafts() and e.maintenance_status()['quarantined']
    tid=e.create(params(False,1),'backup-no-key')['id'];wait_done(e,tid)
    e.settings.update({'kie_api_key':'private-backup-test-secret','simulation':True})
    backup=e.create_backup();m=e.inspect_backup(backup['path'])
    assert all(not Path(f['path']).name.startswith('.env') for f in m['files'])
    assert 'private-backup-test-secret' not in json.dumps(m)


def test_older_head_referenced_by_current_branch_is_protected(engine):
    import shutil
    e=engine;tid=e.create(params(True,1),'old-head-reference')['id'];t=wait_done(e,tid);head=t['rounds'][0]['slots'][0]
    old={k:copy.deepcopy(v) for k,v in head.items() if k!='versions'};head['versions'].append(old)
    head['att']+=1;new=Path(head['output']).with_name('local-new-head.png');shutil.copy2(head['output'],new);head['output']=str(new);e.persist(t)
    assert not any(v['image_id']==head['id'] for v in e.prune_plan()['versions'])


def test_interrupted_prune_restores_moved_file_on_restart(tmp_path):
    import shutil
    settings=Settings(tmp_path/'state',tmp_path/'.env');settings.update({'output_dir':str(tmp_path)})
    e=Engine(settings,start=True,planner=FixturePlanner());tid=e.create(params(False,1),'recycle-crash')['id'];t=wait_done(e,tid);s=t['rounds'][0]['slots'][0]
    e.mutate(tid,'regenerate',{'image_id':s['id']});wait_done(e,tid);plan=e.prune_plan();item=plan['versions'][0];source=Path(item['files'][0]);folder=settings.state_dir/'recycle'/'interrupted';folder.mkdir(parents=True);dest=folder/'0'
    (folder/'journal.json').write_text(json.dumps({'versions':plan['versions'],'moves':[{'source':str(source),'dest':str(dest)}]}));shutil.move(source,dest);e.close()
    e=Engine(settings,start=False,planner=FixturePlanner())
    try:assert source.exists() and not folder.exists()
    finally:e.close()


def test_prune_sql_failure_rolls_back_files_and_metadata(engine):
    import sqlite3
    e=engine;tid=e.create(params(False,1),'prune-sql-fail')['id'];t=wait_done(e,tid);s=t['rounds'][0]['slots'][0];e.mutate(tid,'regenerate',{'image_id':s['id']});wait_done(e,tid);plan=e.prune_plan();real=e.db
    class BrokenConnection:
        def __getattr__(self,name):return getattr(real,name)
        def execute(self,query,*args):
            if query.startswith('UPDATE tasks'):raise sqlite3.OperationalError('test write failure')
            return real.execute(query,*args)
    e.db=BrokenConnection()
    try:
        with pytest.raises(sqlite3.OperationalError):e.prune_versions(plan['token'])
    finally:e.db=real
    assert all(Path(p).exists() for v in plan['versions'] for p in v['files'])
    assert not e.task(tid)['rounds'][0]['slots'][0]['versions'][0].get('files_cleared')


def test_backup_keeps_standalone_exports_after_tasks_removed(engine,tmp_path):
    e=engine;folder=e.settings.output/'工作区'/'产物'/'2026-11-03'/'APP图片'/'旧任务'/'v001'/'06_打包';folder.mkdir(parents=True)
    export=folder/'交付.zip';export.write_bytes(b'preserved-export-contents')
    backup=e.create_backup();m=e.inspect_backup(backup['path']);assert m['standalone']==[str(export.resolve())]
    settings=Settings(tmp_path/'another-state',tmp_path/'another.env');settings.update({'output_dir':str(tmp_path)})
    other=Engine(settings,start=False,planner=FixturePlanner())
    try:
        preview=other.restore_preview(backup['path']);r=other.restore_backup(backup['path'],preview['token'])
        assert any(p.read_bytes()==export.read_bytes() for p in Path(r['path']).glob('*.zip'))
        assert other.restore_backup(backup['path'],preview['token'])['path'] is None
    finally:other.close()
