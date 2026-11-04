import copy,json,time,threading
from pathlib import Path
import pytest
from local_app.config import Settings,UserError
from local_app.engine import Engine
from local_app.planning import compile_plans
from tests_local.fakes import FixturePlanner
from tests_local.test_workbench import engine,params,wait_done

class Pool:
    def __init__(self):self.calls=[]
    def submit(self,*args):self.calls.append(args)
    def shutdown(self,**kwargs):pass


def test_fair_queue_and_runtime_limit(tmp_path):
    settings=Settings(tmp_path/'state',tmp_path/'.env');settings.update({'output_dir':str(tmp_path)});settings.concurrency=1
    e=Engine(settings,start=False,planner=FixturePlanner());pool=Pool();e.pool.shutdown();e.pool=pool
    try:
        ids=[]
        for i in range(2):
            tid=e.create(params(False,3),'fair-task-'+str(i))['id'];ids.append(tid);r=e.task(tid)['rounds'][0]
            compile_plans(r,FixturePlanner().plan(r,lambda x:None));e.persist(e.task(tid))
        e.dispatch_tick();assert len(e.running)==1 and pool.calls[0][1]['id']==ids[0]
        e.dispatch_tick();assert len(pool.calls)==1
        first=pool.calls[0];first[3]['state']='done';e.running.clear()
        e.dispatch_tick();assert pool.calls[1][1]['id']==ids[1]
        e.settings.concurrency=2;e.dispatch_tick();assert len(e.running)==2
        e.settings.concurrency=1;e.dispatch_tick();assert len(e.running)==2 and len(pool.calls)==3
    finally:e.close()


def test_pause_continues_without_new_versions(engine):
    e=engine;tid=e.create(params(True,1),'pause-no-version')['id'];t=wait_done(e,tid);r=t['rounds'][0]
    with e.lock:
        s=r['slots'][1];s['state']='queued';before=s['att'];e.mutate(tid,'pause',{});e.dispatch_tick()
        assert r['paused'] and s['state']=='queued' and s['att']==before
        assert e.task_summary(t)['category']=='attention'
        e.mutate(tid,'continue',{});assert s['att']==before and not r['paused']
    wait_done(e,tid)


def test_summary_detail_and_revision(engine):
    e=engine;tid=e.create(params(True,1),'summary-details')['id'];t=wait_done(e,tid)
    result=e.list_summaries();summary=result['tasks'][0]
    assert 'rounds' not in summary and 'prompt' not in json.dumps(summary)
    assert len(json.dumps(result,ensure_ascii=False).encode())<4000
    view=e.view_task(tid);assert all('prompt' not in s for s in view['rounds'][0]['slots'])
    assert e.view_task(tid,revision=view['revision'])['unchanged']
    sid=t['rounds'][0]['slots'][0]['id'];detail=e.image_details(tid,sid)
    assert detail['prompt'] and detail['id']==sid and detail['reference_images']


def test_prompt_drafts_are_persistent_and_isolated_by_editor_and_version(engine):
    e=engine;tid=e.create(params(True,1),'prompt-history')['id'];t=wait_done(e,tid);s=t['rounds'][0]['slots'][1];sid=s['id']
    for editor,text in [('window-one','自由改词\n标题A'),('window-two','另一份修改')]:
        e.save_prompt_draft(tid,sid,{'editor_id':editor,'att':s['att'],'sequence':1,'text':text})
    assert e.image_details(tid,sid,editor='window-one')['edit_draft']['text']=='自由改词\n标题A'
    assert e.image_details(tid,sid,editor='window-two')['edit_draft']['text']=='另一份修改'
    assert s['prompt']!='自由改词\n标题A'
    e.save_prompt_draft(tid,sid,{'editor_id':'window-one','sequence':0,'text':'旧保存'})
    assert e.get_prompt_draft(tid,sid,s['att'],'window-one')['text']=='自由改词\n标题A'
    old=s['att'];e.mutate(tid,'regenerate',{'image_id':sid,'expected_att':old,'prompt':'人工自由提示词'})
    wait_done(e,tid)
    with pytest.raises(UserError,match='另一窗口'):e.mutate(tid,'regenerate',{'image_id':sid,'expected_att':old,'prompt':'旧界面修改'})
    assert e.image_details(tid,sid,att=old,editor='window-one')['edit_draft']['text']=='自由改词\n标题A'
    assert e.image_details(tid,sid)['edit_draft'] is None
    old_details=e.image_details(tid,sid,att=old);assert old_details['is_historical'] and old_details['reference_images']
    assert old_details['reference_images'][0]['thumbnail_url'].endswith('?v='+str(old))


def test_saved_history_not_deleted_and_archival_is_reversible(engine):
    e=engine;tid=e.create(params(False,1),'archive-retention')['id'];t=wait_done(e,tid);paths=[s['output'] for s in t['rounds'][0]['slots']]
    t.update(downloaded=True,downloaded_at=time.time()-365*86400);e.persist(t);e.cleanup(immediate=True)
    assert e.task(tid) and all(Path(p).exists() for p in paths)
    e.mutate(tid,'archive',{});assert e.list_summaries()['tasks'][0]['archived']
    e.mutate(tid,'unarchive',{});assert not e.list_summaries()['tasks'][0]['archived']


def test_packaging_releases_scheduler_lock_and_keeps_concurrent_selection(engine,monkeypatch):
    import local_app.delivery as delivery
    e=engine;tid=e.create(params(False,2),'package-snapshot')['id'];t=wait_done(e,tid);r=t['rounds'][0];e.mutate(tid,'adopt',{'set':1,'adopted':True})
    entered=threading.Event();release=threading.Event();original=delivery.shutil.copy2
    def copy_file(*a,**kw):entered.set();assert release.wait(5);return original(*a,**kw)
    monkeypatch.setattr(delivery.shutil,'copy2',copy_file);errors=[]
    def export():
        try:e.package(tid,0)
        except Exception as exc:errors.append(exc)
    thread=threading.Thread(target=export);thread.start();assert entered.wait(5)
    assert e.lock.acquire(timeout=.3)
    try:e.mutate(tid,'adopt',{'set':2,'adopted':True})
    finally:e.lock.release();release.set()
    thread.join(5);assert not thread.is_alive() and not errors
    assert r['sel'][r['slots'][1]['pid']+'::2'] and not t['downloaded'] and t['pkgs']


def test_two_windows_export_same_selection_once(engine):
    e=engine;tid=e.create(params(False,1),'two-exports')['id'];t=wait_done(e,tid);e.mutate(tid,'adopt',{'set':1,'adopted':True})
    results=[];errors=[]
    def export():
        try:results.append(e.package(tid,0)['id'])
        except Exception as exc:errors.append(exc)
    threads=[threading.Thread(target=export) for _ in range(2)]
    for t0 in threads:t0.start()
    for t0 in threads:t0.join(5)
    assert not errors and len(results)==2 and results[0]==results[1] and len(t['pkgs'])==1


def test_cleanup_protects_referenced_uploads(engine):
    e=engine;folder=e.settings.state_dir/'uploads';folder.mkdir(exist_ok=True)
    keep=folder/'keep.png';remove=folder/'expired.png';keep.write_bytes(b'kept');remove.write_bytes(b'temporary')
    import os
    for p in (keep,remove):os.utime(p,(time.time()-2*86400,time.time()-2*86400))
    e.save_draft('a'*32,{'draft':{'references':[{'path':str(keep)}]},'form_drafts':{},'revision':0})
    preview=e.cleanup_preview();assert preview['files']==1 and preview['bytes']==len(b'temporary')
    e.cleanup(immediate=True);assert keep.exists() and not remove.exists()


def test_legacy_database_backup_and_pause_survive_restart(tmp_path):
    settings=Settings(tmp_path/'state',tmp_path/'.env');settings.update({'output_dir':str(tmp_path)});settings.concurrency=2
    e=Engine(settings,start=False,planner=FixturePlanner());tid=e.create(params(True,1),'migration-history')['id'];e.mutate(tid,'pause',{})
    before=copy.deepcopy(e.task(tid));e.db.execute('PRAGMA user_version=0');e.db.commit();e.close()
    e=Engine(settings,start=False,planner=FixturePlanner())
    try:
        after=e.task(tid);assert after['rounds'][0]['paused']
        assert [s['id'] for s in before['rounds'][0]['slots']]==[s['id'] for s in after['rounds'][0]['slots']]
        assert list((settings.state_dir/'backups').glob('schema-1-before-upgrade-*.sqlite3'))
        assert e.db.execute('PRAGMA user_version').fetchone()[0]==2
    finally:e.close()


def test_lightweight_http_and_prompt_history(engine):
    from http.server import ThreadingHTTPServer
    from local_app.server import Handler
    import urllib.request
    e=engine;tid=e.create(params(False,1),'http-summary')['id'];t=wait_done(e,tid);sid=t['rounds'][0]['slots'][0]['id']
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.engine=e;threading.Thread(target=server.serve_forever,daemon=True).start()
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}));base='http://127.0.0.1:'+str(server.server_port)
    def get(path):return json.load(op.open(base+path))
    try:
        summary=get('/api/tasks?summary=1');assert 'rounds' not in summary['tasks'][0]
        view=get('/api/tasks/'+tid+'?view=1');assert 'prompt' not in view['rounds'][0]['slots'][0]
        detail=get('/api/tasks/'+tid+'/image-details/'+sid);assert detail['prompt']
        req=urllib.request.Request(base+'/api/tasks/'+tid+'/prompt-drafts/'+sid,data=json.dumps({'att':1,'editor_id':'http-window','sequence':1,'text':'修改\n提示词'}).encode(),headers={'Content-Type':'application/json','X-Onion-Request':'1'},method='PUT')
        op.open(req).close();assert get('/api/tasks/'+tid+'/image-details/'+sid+'?editor=http-window')['edit_draft']['text']=='修改\n提示词'
        assert get('/api/tasks/'+tid+'?view=1&revision='+str(view['revision']))['unchanged']
    finally:server.shutdown();server.server_close()


def test_proven_unsent_retry_but_ambiguous_submission_still_blocked(engine):
    import render
    e=engine;tid=e.create(params(False,1),'unsent-check')['id'];t=wait_done(e,tid);s=t['rounds'][0]['slots'][0];out=Path(s['output'])
    render.task_state_path(out).write_text(json.dumps({'status':'submitting'}));out.with_suffix('.progress.json').write_text(json.dumps({'stage':'uploading'}));out.with_suffix('.job.result.json').write_text(json.dumps({'reason':'unknown'}));s.update(state='failed',reason_code='unknown');e.persist(t)
    assert e.definitely_unsent(s) and not e.query_required(s)
    assert e.public(t)['rounds'][0]['slots'][0]['reason_code']=='not_submitted'
    out.with_suffix('.progress.json').write_text(json.dumps({'stage':'submitting'}))
    assert not e.definitely_unsent(s) and e.query_required(s)
    with pytest.raises(UserError,match='恢复查询'):e.mutate(tid,'regenerate',{'image_id':s['id']})
