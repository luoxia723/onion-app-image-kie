import copy
import json
import time
from pathlib import Path
import pytest
from local_app.config import Settings, UserError
from local_app.engine import Engine
from local_app.planning import PLACEMENTS
from tests_local.fakes import FixturePlanner

@pytest.fixture
def engine(tmp_path,monkeypatch):
    monkeypatch.setenv('ONION_SIM_SECONDS','.05')
    st=Settings(tmp_path/'state',tmp_path/'.env');st.update({'output_dir':str(tmp_path)})
    e=Engine(st,planner=FixturePlanner())
    yield e
    e.close()

def params(form='单图',sets=1):
    return dict(image_form=form,pids=[p['id'] for p in PLACEMENTS if p['image_form']==form][:1],sets=sets,t1='每天学1/2小时?',t2='从今天开始学习',s1='想把数学补起来',s2='安排每天的学习任务',s3='看看学习进度',ip='random',style='random',cta='立即体验',noLogo=False)

def done(e,tid):
    end=time.time()+20
    while time.time()<end:
        t=e.task(tid)
        if not e.is_running(t): return t
        time.sleep(.03)
    raise AssertionError('unfinished')

def test_draft_survives_restart_and_rejects_stale_editor(tmp_path):
    st=Settings(tmp_path/'state',tmp_path/'.env');e=Engine(st,start=False,planner=FixturePlanner());did='a'*32
    value=e.save_draft(did,{'draft':params(),'form_drafts':{'双图':params('双图')},'editor_id':'one','sequence':1,'revision':0})
    e.close();e=Engine(st,start=False,planner=FixturePlanner())
    assert e.get_draft(did)['draft']['t1']=='每天学1/2小时?'
    assert e.get_draft(did)['form_drafts']['双图']['image_form']=='双图'
    with pytest.raises(UserError): e.save_draft(did,{'draft':params(),'editor_id':'two','sequence':2,'revision':0})
    current=e.save_draft(did,{'draft':{**params(),'t1':'较新的草稿'},'editor_id':'one','sequence':3,'revision':value['revision']})
    ignored=e.save_draft(did,{'draft':params(),'editor_id':'one','sequence':2,'revision':value['revision']})
    assert ignored['draft']['t1']==current['draft']['t1']=='较新的草稿'
    e.close()

def test_incremental_additions_preserve_slots_adoption_and_one_round(engine):
    e=engine;p=params(sets=2);tid=e.create(p,'increment-original')['id'];t=done(e,tid);r=t['rounds'][0]
    before={s['id']:(s['att'],s['sha256'],s['prompt']) for s in r['slots']}
    e.mutate(tid,'adopt',{'set':1,'adopted':True})
    updated=copy.deepcopy(r['params']);updated['sets']=3
    response=e.create(updated,'increment-more-sets',tid)
    assert response['added_image_count']==1
    done(e,tid)
    assert len(t['rounds'])==1 and len(r['slots'])==3
    assert all(before[sid]==(s['att'],s['sha256'],s['prompt']) for sid in before for s in r['slots'] if s['id']==sid)
    assert r['sel'][p['pids'][0]+'::1']
    updated=copy.deepcopy(r['params']);new=next(p['id'] for p in PLACEMENTS if p['image_form']=='单图' and p['id'] not in updated['pids'])
    updated['pids'].append(new)
    result=e.create(updated,'increment-new-placement',tid)
    assert result['added_image_count']==3
    done(e,tid);assert len(r['slots'])==6 and len(t['rounds'])==1
    assert e.create(copy.deepcopy(r['params']),'increment-no-change',tid)['added_image_count']==0

def test_new_copy_creates_round_and_keeps_export_history(engine):
    e=engine;p=params();tid=e.create(p,'copy-old-input')['id'];t=done(e,tid)
    e.mutate(tid,'adopt',{'set':1,'adopted':True});pkg=e.package(tid,0)
    assert e.public(t)['delivery']['last_version']=='v001'
    changed=copy.deepcopy(t['rounds'][0]['params']);changed['t1']='另一份确认文案'
    e.create(changed,'copy-new-input',tid);done(e,tid)
    assert len(t['rounds'])==2 and Path(pkg['path']).exists()
    state=e.public(t)['delivery'];assert state['last_version']=='v001' and state['has_changes']

def test_preselection_cannot_export_incomplete_or_failed_spec(engine):
    e=engine;p=params('三图');tid=e.create(p,'full-suite-export')['id'];t=done(e,tid);r=t['rounds'][0]
    e.mutate(tid,'adopt',{'set':1,'adopted':True})
    s=r['slots'][1];old=s['state'];s['state']='failed'
    assert not e.public(t)['delivery']['can_export']
    with pytest.raises(UserError,match='完整|补齐'):e.package(tid,0)
    s['state']=old;s['delivery_eligible']=False
    with pytest.raises(UserError):e.package(tid,0)
    s['delivery_eligible']=True
    assert e.public(t)['delivery']['can_export']
    e.package(tid,0)

def test_planning_failure_never_submits_images(engine):
    class BrokenPlanner:
        def plan(self,*args): raise UserError('规划连接失败')
    engine.planner=BrokenPlanner();tid=engine.create(params(),'failed-real-planning')['id'];t=done(engine,tid)
    assert t['rounds'][0]['planning_status']=='failed'
    assert all(s['reason_code']=='planning_failed' and not Path(s['output']).exists() for s in t['rounds'][0]['slots'])
    engine.planner=FixturePlanner();engine.mutate(tid,'retry-planning',{});t=done(engine,tid)
    assert all(s['state']=='done' for s in t['rounds'][0]['slots'])


def test_same_workspace_cannot_run_two_engines(engine):
    with pytest.raises(UserError,match='已在运行'):
        Engine(engine.settings,start=False,planner=FixturePlanner())


def test_deleted_draft_cannot_be_resurrected_by_late_autosave(engine):
    did='b'*32
    body={'draft':params(),'editor_id':'browser-one','sequence':1,'revision':0}
    engine.save_draft(did,body);engine.delete_draft(did)
    with pytest.raises(UserError,match='已提交或删除'):engine.save_draft(did,{**body,'sequence':2})
    assert not engine.list_drafts()


def test_planning_chunks_and_existing_prompts_are_preserved(engine):
    class Counting(FixturePlanner):
        def __init__(self):self.sizes=[]
        def plan(self,r,*args):
            self.sizes.append(len(r['planning_targets']))
            return super().plan(r,*args)
    planner=Counting();engine.planner=planner
    tid=engine.create(params(sets=5),'chunked-planning')['id'];t=done(engine,tid)
    assert planner.sizes==[3,2]
    assert all(s['plan_ready'] for s in t['rounds'][0]['slots'])


def test_retrying_submitted_draft_never_creates_another_task(engine):
    did='c'*32
    engine.save_draft(did,{'draft':params(),'editor_id':'test','sequence':1,'revision':0})
    first=engine.create(params(),'draft-first-submit',draft_id=did)
    retry=engine.create(params(),'draft-different-new-key',draft_id=did)
    assert retry['id']==first['id'] and retry['recovered_submission']
    assert engine.get_draft(did)['submitted_task_id']==first['id']
    assert len(engine.tasks)==1
    done(engine,first['id'])


def test_mode_change_never_extends_mock_round_as_real_work(tmp_path):
    st=Settings(tmp_path/'state',tmp_path/'.env');e=Engine(st,start=False,planner=FixturePlanner())
    tid=e.create(params(),'mode-mock-original')['id']
    st.real=True;st.key='test-only-never-submitted'
    e.create(params(),'mode-real-new-round',tid)
    t=e.task(tid)
    assert len(t['rounds'])==2 and t['rounds'][0]['simulation'] and not t['rounds'][1]['simulation']
    assert not e.running
    e.close()


def test_kie_key_alone_enables_real_generation_and_preserves_mock_history(tmp_path):
    st=Settings(tmp_path/'state',tmp_path/'.env');e=Engine(st,start=False,planner=FixturePlanner())
    try:
        tid=e.create(params(),'key-mode-original')['id']
        state=st.update({'kie_api_key':'test-only-image-key'})
        assert not state['simulation'] and st.real
        assert Settings(st.state_dir,st.env_file).real
        e.create(params(),'key-mode-real-round',tid)
        rounds=e.task(tid)['rounds']
        assert len(rounds)==2 and rounds[0]['simulation'] and not rounds[1]['simulation']
        assert not e.running # This test never submits an image or invokes a provider.
        st.update({'simulation':True})
        assert not st.real and st.key=='test-only-image-key'
        st.update({'kie_api_key':'test-only-replacement','simulation':True})
        assert not st.real # Explicit preview choice wins over auto-enabling from key input.
    finally:e.close()


def test_real_generation_mode_requires_key_and_valid_boolean(tmp_path):
    st=Settings(tmp_path/'state',tmp_path/'.env')
    for value in (False,'false',0,None):
        with pytest.raises(UserError):st.update({'simulation':value})
    assert not st.real and not st.key
    st.update({'simulation':True})
    assert not st.real


def test_export_ready_selected_suites_is_explicit_and_never_exports_partial_suites(engine):
    import zipfile
    e=engine;tid=e.create(params('三图',sets=2),'partial-ready-export')['id'];t=done(e,tid);r=t['rounds'][0]
    e.mutate(tid,'adopt-bulk',{'sets':[{'placement_id':r['params']['pids'][0],'set':n} for n in (1,2)],'adopted':True})
    r['slots'][1]['delivery_eligible']=False
    selection=copy.deepcopy(r['sel'])
    with pytest.raises(UserError):e.package(tid,0)
    pkg=e.package(tid,0,ready_only=True)
    with zipfile.ZipFile(pkg['path']) as archive:
        manifest=json.loads(archive.read('交付清单.json'))
        assert len(manifest['images'])==3 and {x['set'] for x in manifest['images']}=={2}
        assert manifest['export_scope']=='ready_selected' and len(manifest['excluded_suites'])==1
    assert r['sel']==selection and not t['downloaded']
    assert e.public(t)['delivery']['incomplete_sets']==1
    assert e.package(tid,0,ready_only=True)['id']==pkg['id']


def test_missing_image_record_still_blocks_complete_suite_export(engine):
    e=engine;tid=e.create(params('三图'),'missing-slot-completeness')['id'];t=done(e,tid);r=t['rounds'][0]
    e.mutate(tid,'adopt',{'set':1,'adopted':True})
    r['slots'].pop()
    assert not e.delivery_state(t,r)['can_export']
    with pytest.raises(UserError):e.package(tid,0)
    with pytest.raises(UserError):e.package(tid,0,ready_only=True)
