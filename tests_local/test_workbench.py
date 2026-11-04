import hashlib
import json
from pathlib import Path
import threading
import time
from http.server import ThreadingHTTPServer
import urllib.request
import urllib.error
import zipfile
import pytest
from PIL import Image
from local_app.config import Settings, UserError, safe_direction
from local_app.engine import Engine
from tests_local.fakes import FixturePlanner
from local_app.planning import PLACEMENTS, BY_ID, make_round
from local_app.server import Handler
import positive_prompt

@pytest.fixture
def engine(tmp_path,monkeypatch):
    monkeypatch.setenv('ONION_SIM_SECONDS','.05')
    settings=Settings(tmp_path/'state',tmp_path/'.env')
    settings.update({'output_dir':str(tmp_path),'concurrency':2})
    e=Engine(settings,planner=FixturePlanner())
    yield e
    e.close()

def params(multi=False,sets=2):
    p=next(p for p in PLACEMENTS if p['image_count']==(3 if multi else 1))
    return dict(pids=[p['id']],t1='每天进步一点',t2='打开今天的学习任务',s1='开始学习',s2='继续探索',s3='整理知识',cta='立即体验',sets=sets,ip='random',style='random',noLogo=False)

def wait_done(e,tid):
    end=time.monotonic()+30
    while time.monotonic()<end:
        with e.lock:
            t=e.task(tid)
            if not e.is_running(t):return t
        time.sleep(.05)
    raise AssertionError('generation did not finish')

def test_end_to_end_dependency_prompt_versions_and_zip(engine):
    e=engine;p=params(True)
    t=e.create(p,'idempotency-1');tid=t['id']
    assert e.create(p,'idempotency-1')['id']==tid
    t=wait_done(e,tid);r=t['rounds'][0]
    assert all(s['state']=='done' for s in r['slots'])
    for s in r['slots']:
        cfg=r['configs'][s['config_idx']]
        label=s['refs'][-1]['label'] if s.get('frame') and s['idx']==1 else '参考图1' if s.get('frame') else None
        assert s['orig']==positive_prompt.compose(cfg['config'],cfg['direction'],s['idx'],s['refs'],label)
        if s['idx']>1:
            assert len(s['refs'])==1
            h=next(x for x in r['slots'] if x['id']==s['first_id'])
            assert s['refs'][0]['path']==h['output']
            assert h['raw_sha256']==hashlib.sha256(Path(h['output']).read_bytes()).hexdigest()
        with Image.open(s['jpeg']) as im:
            spec=BY_ID[s['pid']]
            assert im.size==(spec['target_width'],spec['target_height'])
            assert Path(s['jpeg']).stat().st_size<spec['max_file_size_kb']*1024
    e.mutate(tid,'adopt',{'set':1,'adopted':True})
    assert e.package_preview(tid,0)['next_version']=='v001'
    first=e.package(tid,0)
    assert e.package(tid,0)['id']==first['id']
    assert e.package_preview(tid,0)=={'next_version':None,'package_id':first['id']}
    with zipfile.ZipFile(first['path']) as z:
        names=z.namelist()
        assert len([n for n in names if n.endswith('.jpg')])==3
        assert not any('.env' in n or '.cache' in n for n in names)
        manifest=json.loads(z.read('交付清单.json'))
        for image in manifest['images']:
            assert hashlib.sha256(z.read(image['path'])).hexdigest()==image['sha256']
    s=r['slots'][0]
    old=s['att']
    e.mutate(tid,'regenerate',{'image_id':s['id']})
    assert all(x['att']==old+1 for x in r['slots'] if x['set']==1)
    assert not r['sel'].get('1')
    wait_done(e,tid)
    e.mutate(tid,'adopt',{'set':1,'adopted':True})
    # Simulator is deterministic: unchanged pixels reuse the package even after regeneration.
    assert e.package(tid,0)['id']==first['id']
    assert len(t['pkgs'])==1
    e.mutate(tid,'adopt',{'set':2,'adopted':True})
    second=e.package(tid,0)
    assert second['v']==2 and Path(first['path']).exists()

def test_stop_cleanup_delete_restore(engine):
    e=engine;p=params(True,20)
    tid=e.create(p,'stop-batch')['id']
    end=time.time()+5
    while not e.running and time.time()<end:time.sleep(.02)
    e.mutate(tid,'stop',{})
    t=wait_done(e,tid);r=t['rounds'][0]
    assert r['stopped']
    assert sum(s['state']=='stopped' for s in r['slots'])>=58
    assert e.public(t)['rounds'][0]['status']=='stopped'
    assert len(e.tasks)==1
    assert e.cleanup(immediate=True)['freed_bytes']==0
    e.mutate(tid,'delete',{})
    assert not e.list_tasks()['tasks']
    e.mutate(tid,'restore',{})
    assert e.list_tasks()['tasks']
    r['slots'][0]['state']='done'
    t['downloaded']=True;t['downloaded_at']=time.time()-6*86400;e.persist(t)
    e.cleanup();assert tid in e.tasks
    t['downloaded_at']=time.time()-8*86400;e.persist(t)
    delivery=Path(t['output_dir'])/'delivery.zip';delivery.write_bytes(b'keep')
    e.cleanup();assert tid in e.tasks and delivery.exists()
    e.mutate(tid,'archive',{});assert e.task(tid)['archived']
    assert e.task_summary(e.task(tid))['category']=='history'

def test_settings_redaction_and_validation(engine,tmp_path):
    s=engine.settings
    s.env_file.write_text('# retained\nOTHER=value\n')
    s.update({'kie_api_key':'test-secret-123','concurrency':20,'kie_base_url':''})
    assert 'test-secret' not in json.dumps(s.public())
    assert 'OTHER=value' in s.env_file.read_text()
    s.update({'kie_api_key':''});assert s.key=='test-secret-123'
    assert s.env_file.stat().st_mode&0o777==0o600
    for invalid in (0,21,1.5,True):
        with pytest.raises(UserError):s.update({'concurrency':invalid})
    for name in ['CON','NUL.jpg','bad/thing','name.',' name','..']:
        with pytest.raises(UserError):safe_direction(name)
    with pytest.raises(UserError):s.update({'kie_base_url':'http://example.com'})
    for invalid in (0,21):
        with pytest.raises(UserError):engine.create({**params(),'sets':invalid},'invalid-'+str(invalid))
    p=next(p for p in PLACEMENTS if p['platform']=='喜马拉雅' and p['logo_policy']=='required')
    with pytest.raises(UserError):engine.create({**params(),'pids':[p['id']],'noLogo':True},'invalid-logo')

def test_restart_does_not_resubmit_unknown(engine):
    e=engine;p=params();t=e.create(p,'recovery-batch');e.mutate(t['id'],'stop',{})
    t=e.task(t['id']);s=t['rounds'][0]['slots'][0]
    s['state']='generating';t['rounds'][0]['simulation']=False
    e.persist(t);e.recover()
    assert s['state']=='failed' and s['reason_code']=='unknown'
    with pytest.raises(UserError):e.mutate(t['id'],'regenerate',{'image_id':s['id']})
    with pytest.raises(UserError):e.mutate(t['id'],'resume',{'image_id':s['id']})

def test_http_filesystem_boundary_and_csrf(engine):
    srv=ThreadingHTTPServer(('127.0.0.1',0),Handler);srv.engine=engine
    thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(srv.server_port)
    try:
        for path in ['/.env','/../.env','/%2e%2e/.env','/.onion-local/index.sqlite3','/工作区/产物','/css/../js/app.js']:
            req=urllib.request.Request(base+urllib.parse.quote(path,safe='/%'))
            with pytest.raises(urllib.error.HTTPError) as err:urllib.request.urlopen(req)
            assert err.value.code==404
        for headers in ({'Content-Type':'application/json'},{'Content-Type':'application/json','X-Onion-Request':'1','Origin':'https://evil.example'}):
            req=urllib.request.Request(base+'/api/storage',data=b'{}',headers=headers)
            with pytest.raises(urllib.error.HTTPError) as err:urllib.request.urlopen(req)
            assert err.value.code==403
        assert json.load(urllib.request.urlopen(base+'/api/health'))['simulation']
    finally:srv.shutdown();srv.server_close()


def test_concurrency_is_shared_between_tasks(engine):
    e=engine
    tids=[e.create(params(True,3),'shared-'+str(i))['id'] for i in range(2)]
    peak=0;end=time.monotonic()+20
    while time.monotonic()<end:
        with e.lock:
            peak=max(peak,len(e.running))
            if all(not e.is_running(e.task(tid)) for tid in tids):break
        time.sleep(.01)
    assert peak<=2
    assert all(all(s['state']=='done' for s in e.task(tid)['rounds'][0]['slots']) for tid in tids)


def test_one_copy_fans_out_to_compatible_placement_jobs(engine):
    p=params(False,2)
    p['image_form']='单图'
    p['pids']=[slot['id'] for slot in PLACEMENTS if slot['image_form']=='单图'][:2]
    tid=engine.create(p,'compatible-copy-batch')['id']
    t=wait_done(engine,tid);r=t['rounds'][0]
    assert len(r['slots'])==4
    assert r['params']['s1']==r['params']['s2']==r['params']['s3']==''
    assert all(len(c['config']['placements'])==1 for c in r['configs'])
    assert all(p['t1'] in s['prompt'] and p['t2'] in s['prompt'] for s in r['slots'])
    assert all(s['state']=='done' for s in r['slots'])


def test_duplicate_keeps_uploaded_reference_usable(engine):
    e=engine
    upload=e.settings.state_dir/'uploads'/'test-reference.png'
    upload.parent.mkdir(exist_ok=True)
    Image.new('RGB',(32,32),'white').save(upload)
    p=params(False,1)
    p['references']=[{'id':'test-reference','path':str(upload),'note':'参考留白与画面配色','name':upload.name}]
    tid=e.create(p,'with-reference')['id']
    wait_done(e,tid)
    copied=e.mutate(tid,'duplicate',{})['params']
    clone=e.create(copied,'duplicated-reference')
    assert clone['id']!=tid
    wait_done(e,clone['id'])


def test_each_placement_can_adopt_its_own_variant(engine):
    e=engine;p=params(False,2)
    p['pids']=[slot['id'] for slot in PLACEMENTS if slot['image_form']=='单图'][:2]
    tid=e.create(p,'independent-picks')['id'];t=wait_done(e,tid)
    first,second=p['pids']
    e.mutate(tid,'adopt',{'placement_id':first,'set':1,'adopted':True})
    chosen,_=e.adopted(t,0)
    assert {(s['pid'],s['set']) for s in chosen}=={(first,1)}
    e.mutate(tid,'adopt',{'placement_id':second,'set':2,'adopted':True})
    chosen,_=e.adopted(t,0)
    assert {(s['pid'],s['set']) for s in chosen}=={(first,1),(second,2)}
    other=next(s for s in t['rounds'][0]['slots'] if s['pid']==second and s['set']==1)
    e.mutate(tid,'regenerate',{'image_id':other['id']})
    chosen,_=e.adopted(t,0)
    assert {(s['pid'],s['set']) for s in chosen}=={(first,1),(second,2)}
    wait_done(e,tid)


def test_bulk_adopt_changes_only_explicit_scope(engine):
    e=engine;p=params(False,2)
    p['pids']=[slot['id'] for slot in PLACEMENTS if slot['image_form']=='单图'][:2]
    tid=e.create(p,'bulk-selection-scope')['id'];t=wait_done(e,tid)
    first,second=p['pids']
    e.mutate(tid,'adopt',{'placement_id':second,'set':2,'adopted':True})
    scope=[{'placement_id':first,'set':n} for n in (1,2)]
    e.mutate(tid,'adopt-bulk',{'sets':scope,'adopted':True})
    selected,_=e.adopted(t,0)
    assert {(s['pid'],s['set']) for s in selected}=={(first,1),(first,2),(second,2)}
    e.mutate(tid,'adopt-bulk',{'sets':scope,'adopted':False})
    selected,_=e.adopted(t,0)
    assert {(s['pid'],s['set']) for s in selected}=={(second,2)}
    with pytest.raises(UserError):
        e.mutate(tid,'adopt-bulk',{'sets':[scope[0],{'placement_id':'missing','set':1}],'adopted':True})
    selected,_=e.adopted(t,0)
    assert {(s['pid'],s['set']) for s in selected}=={(second,2)}


@pytest.mark.parametrize('code,expected',[(200,'connected'),(401,'failed')])
def test_kie_connection_is_readonly_and_respects_edited_endpoint(engine,monkeypatch,code,expected):
    import local_app.server as server_module
    calls=[]
    def query(req,*args,**kwargs):
        calls.append((req.full_url,req.get_method(),req.data))
        return {'code':code,'data':100}
    monkeypatch.setattr(server_module.render,'request_json',query)
    srv=ThreadingHTTPServer(('127.0.0.1',0),Handler);srv.engine=engine
    thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
    try:
        body={'kie_api_key':'test-only-key','kie_base_url':'https://edited-kie.example'}
        req=urllib.request.Request('http://127.0.0.1:'+str(srv.server_port)+'/api/settings/test',data=json.dumps(body).encode(),
            headers={'Content-Type':'application/json','X-Onion-Request':'1'})
        result=json.load(urllib.request.urlopen(req))
        assert result['key_status']==expected
        assert calls==[('https://edited-kie.example/api/v1/chat/credit','GET',None)]
        assert not engine.settings.key and not engine.settings.real
        assert 'test-only-key' not in json.dumps(result)
    finally:srv.shutdown();srv.server_close()


def test_branch_retry_keeps_first_and_other_branch(engine):
    e=engine;tid=e.create(params(True,1),'retry-one-branch')['id']
    r=wait_done(e,tid)['rounds'][0]
    with e.lock:
        head,second,third=r['slots']; before=[(s['att'],s['output']) for s in r['slots']]
        e.mutate(tid,'regenerate',{'image_id':second['id']})
        assert (head['att'],head['output'])==before[0]
        assert (third['att'],third['output'])==before[2]
        assert second['refs'][0]['path']==head['output']
        assert second['att']==before[1][0]+1
    wait_done(e,tid)


def test_blocked_branch_never_silently_regenerates_head(engine):
    e=engine;tid=e.create(params(True,1),'retry-blocked-branch')['id']
    r=wait_done(e,tid)['rounds'][0]
    with e.lock:
        head,second,third=r['slots'];head.update(state='failed',reason_code='no_image')
        second.update(state='blocked_first_failed',reason_code='first_failed')
        before=[s['att'] for s in r['slots']]
        with pytest.raises(UserError,match='首图'): e.mutate(tid,'regenerate',{'image_id':second['id']})
        assert [s['att'] for s in r['slots']]==before


def test_head_retry_does_not_discard_uncertain_branch(engine):
    e=engine;tid=e.create(params(True,1),'retry-uncertain-branch')['id']
    r=wait_done(e,tid)['rounds'][0]
    with e.lock:
        head,second,third=r['slots'];second.update(state='failed',reason_code='timeout')
        before=[s['att'] for s in r['slots']]
        with pytest.raises(UserError,match='恢复查询'): e.mutate(tid,'regenerate',{'image_id':head['id']})
        assert [s['att'] for s in r['slots']]==before


def test_repair_timeout_resumes_same_task_and_version(engine):
    import render
    e=engine;tid=e.create(params(True,1),'repair-resume-branch')['id']
    r=wait_done(e,tid)['rounds'][0]
    with e.lock:
        head,second,third=r['slots'];before=[s['att'] for s in r['slots']]
        second.update(state='failed',reason_code='timeout')
        render.task_state_path(Path(second['output'])).write_text(json.dumps({'task_id':'existing-task','status':'waiting'}))
        e.mutate(tid,'repair-set',{'placement_id':second['pid'],'set':second['set']})
        assert second['resume'] and second['state']=='queued'
        assert [s['att'] for s in r['slots']]==before
        assert head['state']==third['state']=='done'
    wait_done(e,tid)


def test_manual_prompt_is_verbatim_and_survives_later_retry(engine):
    e=engine;tid=e.create(params(True,1),'manual-free-edit')['id'];r=wait_done(e,tid)['rounds'][0]
    prompt='自由改写\n主标题："我的新标题"\n参考图按原顺序使用。'
    with e.lock:
        head,second,third=r['slots'];before=json.loads(json.dumps(second['refs']));head_version=head['att']
        e.mutate(tid,'regenerate',{'image_id':second['id'],'prompt':prompt})
        assert second['prompt']==prompt and second['prompt_origin']=='manual'
        assert second['refs']==before and head['att']==head_version
    wait_done(e,tid)
    with e.lock:
        e.mutate(tid,'regenerate',{'image_id':second['id']})
        assert second['prompt']==prompt and second['prompt_origin']=='manual'
    wait_done(e,tid)


def test_rebrief_creates_one_new_round_with_same_assets_and_new_heads(engine):
    e=engine;tid=e.create(params(True,1),'rebrief-series')['id'];t=wait_done(e,tid);old=t['rounds'][0]
    with e.lock:
        result=e.mutate(tid,'rebrief-round',{'round':0});new=t['rounds'][1]
        assert t['ri']==1 and new['reformatted_from']==old['id']
        assert new['slots'][0]['refs']==old['slots'][0]['refs']
        assert new['set_metadata']==old['set_metadata']
        for s in new['slots']:
            assert '画面文字：\n' in s['prompt'] and '参考图用途：\n' in s['prompt']
            if s['idx']>1:
                assert len(s['refs'])==1 and s['refs'][0]['path']==new['slots'][0]['output']
                assert s['refs'][0]['path']!=old['slots'][0]['output']
        assert all(s['state']=='done' for s in old['slots'])
        e.mutate(tid,'rebrief-round',{'round':0})
        assert len(t['rounds'])==2
    wait_done(e,tid)


def test_rebrief_http_route(engine):
    e=engine;tid=e.create(params(True,1),'rebrief-http')['id'];wait_done(e,tid)
    srv=ThreadingHTTPServer(('127.0.0.1',0),Handler);srv.engine=e
    threading.Thread(target=srv.serve_forever,daemon=True).start()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        req=urllib.request.Request('http://127.0.0.1:'+str(srv.server_port)+'/api/tasks/'+tid+'/rebrief-round',
            data=json.dumps({'round':0}).encode(),headers={'Content-Type':'application/json','X-Onion-Request':'1'})
        result=json.load(opener.open(req))
        assert result['ri']==1 and result['rounds'][1]['reformatted_from']==result['rounds'][0]['id']
        wait_done(e,tid)
    finally: srv.shutdown();srv.server_close()
