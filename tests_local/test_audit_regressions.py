"""Read-only review repros: isolated temporary stores; simulation and fixture planner only."""
from pathlib import Path
import copy
import pytest
from tests_local.test_workbench import engine, params, wait_done
from tests_local.fakes import FixturePlanner
from local_app.config import Settings
from local_app.engine import Engine
from local_app.planning import PLACEMENTS

@pytest.fixture(autouse=True)
def offline_only(monkeypatch,tmp_path):
    import socket
    monkeypatch.setenv('ONION_REAL_MODE','false')
    monkeypatch.setenv('ONION_IMAGE_WORKSPACE',str(tmp_path))
    monkeypatch.setenv('ONION_SIM_SECONDS','.01')
    def deny_network(*args,**kwargs):
        raise AssertionError('Audit repros must not use network')
    monkeypatch.setattr(socket,'create_connection',deny_network)


def test_removing_placement_does_not_regenerate_remaining(engine):
    p=params(False,1)
    first=next(x for x in PLACEMENTS if x['id']==p['pids'][0])
    second=next(x for x in PLACEMENTS if x['id']!=first['id'] and x['image_form']==first['image_form'] and x['category']==first['category'])
    p['pids'].append(second['id'])
    p['cta_overrides']={second['id']:{'mode':'none','text':''}}
    tid=engine.create(p,'audit-placement-initial')['id']
    t=wait_done(engine,tid)
    retained_before={s['id']:(s['att'],s['state'],s['output'],s['sha256'])
                     for s in t['rounds'][0]['slots'] if s['pid']==first['id']}
    assert retained_before and all(state=='done' for _,state,_,_ in retained_before.values())
    changed=copy.deepcopy(t['rounds'][0]['params'])
    changed['pids']=[first['id']]
    changed['cta_overrides']={}
    result=engine.create(changed,'audit-placement-remove',tid)
    assert len(result['rounds'])==1, 'Removing only a placement created a new round and queued remaining images'
    retained_after={s['id']:(s['att'],s['state'],s['output'],s['sha256'])
                    for s in engine.task(tid)['rounds'][0]['slots'] if s['pid']==first['id']}
    assert retained_after==retained_before, 'Removing a different placement changed retained image versions or queued regeneration'
    assert not engine.is_running(engine.task(tid))


def test_corrupt_package_does_not_disable_resave(engine):
    tid=engine.create(params(False,1),'audit-corrupt-initial')['id']
    t=wait_done(engine,tid)
    engine.mutate(tid,'adopt',{'set':1,'adopted':True})
    pkg=engine.package(tid,0)
    Path(pkg['path']).write_bytes(b'broken zip')
    assert engine.valid_package(t,pkg['fingerprint']) is None
    assert engine.package_preview(tid,0)['package_id'] is None
    d=engine.delivery_state(t,t['rounds'][0])
    saved=(d['has_changes'] is False and d['matching_version']) # frontend viewSelectionFooter
    assert not saved, 'Frontend still considers broken package saved and disables its save button'


def test_restored_export_versions_are_unique(engine,tmp_path):
    tid=engine.create(params(False,2),'audit-restore-initial')['id']
    wait_done(engine,tid)
    engine.mutate(tid,'adopt',{'set':1,'adopted':True})
    first=engine.package(tid,0)
    backup=engine.create_backup()
    target=tmp_path/'new-machine';target.mkdir()
    settings=Settings(target/'state',target/'test.env');settings.update({'output_dir':str(target),'simulation':True})
    other=Engine(settings,start=False,planner=FixturePlanner())
    try:
        preview=other.restore_preview(backup['path'])
        other.restore_backup(backup['path'],preview['token'])
        other.mutate(tid,'adopt',{'set':2,'adopted':True})
        second=other.package(tid,0)
        assert second['v']>first['v'], 'New export after restore reused v001; frontend download lookup selects old package'
    finally: other.close()


def test_rate_limited_receipt_can_retry(tmp_path,monkeypatch):
    import json
    import render
    from PIL import Image
    from local_app.kie_client import generate
    from kie_model import MODEL
    ref=tmp_path/'ref.png';Image.new('RGB',(80,45),'white').save(ref)
    out=tmp_path/'out.png'
    render.atomic_write_json(render.task_state_path(out),{'status':'rate_limited','fingerprint':'old','attempt_history':[],'timeout_restarts':0})
    def fake_obtain(*args,**kwargs):return 'local-fixture',{'task_id':'fixture','status':'success'}
    monkeypatch.setattr(render,'obtain_result',fake_obtain)
    monkeypatch.setattr(render,'download_image',lambda url,path:Image.new('RGB',(80,45),'white').save(path))
    job={'slot':{'idx':1,'refs':[{'label':'参考图1','path':str(ref),'role':'参考素材'}],'prompt':'测试','prompt_origin':'manual','output':str(out)},'placement':{'target_width':960,'target_height':540},'base':'https://unused.invalid','upload':'https://unused.invalid','image_model':MODEL,'upload_cache':str(tmp_path/'uploads.json'),'stop_marker':str(tmp_path/'STOP'),'query_only':False}
    result=generate(job,'fake-test-key',[],lambda stage:None)
    assert result['ok']


@pytest.mark.parametrize("multi",[False,True])
def test_restore_queued_outputs_do_not_write_original_workspace(tmp_path,multi):
    source=tmp_path/'source';source.mkdir()
    target=tmp_path/'target';target.mkdir()
    def isolated(root):
        settings=Settings(root/'state',root/'test.env');settings.update({'output_dir':str(root),'simulation':True})
        return Engine(settings,start=False,planner=FixturePlanner())
    first=isolated(source);other=isolated(target)
    try:
        from local_app.planning import STYLES
        pr=params(multi,1);pr['style']=STYLES[0]['name']
        tid=first.create(pr,'audit-pending-backup')['id']
        original=Path(first.task(tid)['rounds'][0]['slots'][0]['output'])
        assert not original.exists()
        backup=first.create_backup()
        preview=other.restore_preview(backup['path']);other.restore_backup(backup['path'],preview['token'])
        t=other.task(tid);r=t['rounds'][0];s=r['slots'][0]
        import time
        other.mutate(tid,'continue',{})
        deadline=time.monotonic()+10
        while other.is_running(t) and time.monotonic()<deadline:
            other.dispatch_tick();time.sleep(.02)
        assert all(slot['state']=='done' for slot in r['slots']), [(slot['state'],slot.get('msg')) for slot in r['slots']]
        assert all(str(target) in slot['output'] for slot in r['slots'])
        assert not original.exists(), 'Restored pending image wrote into the original workspace instead of the restore directory'
    finally:other.close();first.close()


def test_retained_placement_cta_change_still_starts_new_round(engine):
    tid=engine.create(params(False,1),'audit-real-cta-change')['id']
    t=wait_done(engine,tid)
    changed=copy.deepcopy(t['rounds'][0]['params'])
    changed['cta_overrides']={changed['pids'][0]:{'mode':'custom','text':'马上试试'}}
    assert len(engine.create(changed,'audit-real-cta-changed',tid)['rounds'])==2


def test_uncertain_receipt_still_refuses_resubmission(tmp_path):
    import render
    out=tmp_path/'out.png'
    render.atomic_write_json(render.task_state_path(out),{'status':'submit_uncertain'})
    with pytest.raises(render.KieError,match='uncertain'):
        render.load_output_state(out)


@pytest.mark.parametrize('planning_status',['queued','running'])
def test_recovered_retired_learning_plan_never_calls_planner(tmp_path,monkeypatch,planning_status):
    from tests_local.learning_history import install_history
    from tests_local.test_learning_workflow import params as learning_params,ROOT
    import time
    settings=Settings(tmp_path/'state',tmp_path/'test.env')
    settings.update({'output_dir':str(tmp_path),'simulation':True})
    engine=Engine(settings,start=False,planner=FixturePlanner());calls=[]
    def forbidden(*args,**kwargs):
        calls.append(True)
        raise AssertionError('Retired learning plans must not reach a model')
    monkeypatch.setattr(engine.planner,'plan',forbidden)
    try:
        task=install_history(engine,learning_params(ROOT));round=task['rounds'][0]
        round.update(planning_status=planning_status,planning_targets=[ROOT+'::1'],paused=False,stopped=False)
        for slot in round['slots']:slot.update(state='queued',plan_ready=False)
        engine.recover_task(task)
        engine.dispatch_tick()
        deadline=time.monotonic()+3
        while engine.planning_running and time.monotonic()<deadline:time.sleep(.01)
        assert not engine.planning_running and not calls
        assert round['planning_status']=='failed'
        assert '基准图' in round['planning_error']
        assert all(slot['state']=='failed' and slot['reason_code']=='planning_failed' for slot in round['slots'])
    finally:engine.close()
