import hashlib
import json
import threading
import time
import zipfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from local_app import engine as engine_module, learning_visual, ximalaya
from local_app.config import Settings, UserError
from local_app.scene_planner import plan_input
from tests_local.fakes import FixturePlanner


def params():
    return dict(channel='信息流', pids=list(ximalaya.PLACEMENTS), ximalaya_suite=True, sets=1,
                t1='题目不会先拍一下', t2='跟着步骤，看懂解题思路', cta='立即体验',
                ip='none', font='none', noLogo=True)


def until(engine, condition):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        engine.dispatch_tick()
        with engine.lock:
            if condition():
                return
        time.sleep(.01)
    pytest.fail('本机编排未到达预期状态')


@pytest.mark.parametrize('journal,expected_state,expected_resume',[
    (None,'queued',False),
    ({'status':'submitting'},'failed',False),
    ({'status':'waiting','task_id':'original-accepted'},'queued',True),
])
def test_restart_before_create_requeues_only_with_proof(tmp_path,journal,expected_state,expected_resume):
    settings=Settings(tmp_path/'state',tmp_path/'test.env')
    settings.update({'kie_api_key':'offline-image-key','output_dir':str(tmp_path),'simulation':False})
    engine=engine_module.Engine(settings,start=False,planner=FixturePlanner())
    try:
        task=engine.task(engine.create(params(),'offline-restart-proof')['id'])
        branch=task['rounds'][0]['slots'][1]
        assert branch['ximalaya_source']
        branch.update(state='generating',stage='awaiting_submit')
        output=Path(branch['output'])
        engine_module.atomic(output.with_suffix('.progress.json'),{'stage':'awaiting_submit'})
        if journal:engine_module.atomic(engine_module.render.task_state_path(output),journal)
        engine.recover_task(task)
        assert branch['state']==expected_state
        assert bool(branch.get('resume'))==expected_resume
    finally:
        engine.close()


@pytest.mark.parametrize('progress,known_task,expected_state,expected_action',[
    ('uploading',False,'queued',None),
    (None,False,'failed','blocked'),
    ('uploading',True,'failed','blocked'),
])
def test_ordinary_restart_requires_evidence_before_resending(tmp_path,progress,known_task,expected_state,expected_action):
    settings=Settings(tmp_path/'state',tmp_path/'test.env')
    settings.update({'kie_api_key':'offline-image-key','output_dir':str(tmp_path),'simulation':False})
    engine=engine_module.Engine(settings,start=False,planner=FixturePlanner())
    try:
        task=engine.task(engine.create({**params(),'ximalaya_suite':False,'pids':[ximalaya.BASE]},'ordinary-restart-proof')['id'])
        image=task['rounds'][0]['slots'][0]
        image.update(state='generating',stage='uploading')
        if known_task:image['provider_task_ids']=['offline-accepted-task']
        if progress:
            engine_module.atomic(Path(image['output']).with_suffix('.progress.json'),{'stage':progress})
        engine.recover_task(task)
        assert image['state']==expected_state
        card=engine.public(task)['rounds'][0]['slots'][0]
        details=engine.image_details(task['id'],image['id'])
        assert card['kie_recovery_action']==details['kie_recovery_action']==expected_action
        assert card['query_required'] is False
        if expected_action=='blocked':
            with pytest.raises(UserError,match='状态未确定'):
                engine.mutate(task['id'],'regenerate',{'image_id':image['id']})
            with pytest.raises(UserError,match='没有可查询的任务号'):
                engine.mutate(task['id'],'resume',{'image_id':image['id']})
    finally:
        engine.close()


def test_first_review_gates_four_requests_and_bundle_keeps_one_source(tmp_path, monkeypatch):
    settings = Settings(tmp_path/'state', tmp_path/'test.env')
    settings.update({'kie_api_key':'offline-image-key', 'output_dir':str(tmp_path), 'simulation':False})
    engine = engine_module.Engine(settings, start=False, planner=FixturePlanner())
    entered = threading.Event()
    release = threading.Event()
    jobs = []
    audits = []

    def worker(command, **kwargs):
        job_path = Path(command[-1])
        job = json.loads(job_path.read_text())
        jobs.append(job)
        output = Path(job['slot']['output'])
        p = job['placement']
        Image.new('RGB', (p['target_width'], p['target_height']), '#ebead4').save(output)
        job_path.with_suffix('.result.json').write_text(json.dumps({'ok':True,'source':str(output)}))
        return SimpleNamespace(communicate=lambda: (b'', b''))

    def review(settings, slot, wording, stopped):
        assert not stopped()
        assert wording == {'t1':params()['t1'], 'subtitle':params()['t2'], 'cta':params()['cta']}
        audits.append((slot['att'], slot['logo_base']['sha256']))
        if len(audits) == 1:
            entered.set()
            assert release.wait(5)
            return {'verdict':'repair','issues':[{'kind':'missing','detail':'副标题缺字'}]}
        if len(audits) == 2:
            return {'verdict':'unavailable','issues':[]}
        return {'verdict':'pass','issues':[]}

    monkeypatch.setattr(engine_module.subprocess, 'Popen', worker)
    monkeypatch.setattr(ximalaya, 'review', review)
    monkeypatch.setattr(engine_module, 'REVIEW_RETRY_DELAYS', (0.25,0.5), raising=False)
    try:
        result = engine.create(params(), 'ximalaya-offline-suite')
        tid = result['id']
        task = engine.task(tid)
        round_ = task['rounds'][0]
        base, *branches = round_['slots']
        assert [item['placement_id'] for item in plan_input(round_)['jobs']] == [ximalaya.BASE]
        assert [s['brand_logo_layer']['enabled'] for s in round_['slots']] == [False,False,False,True,True]
        until(engine, entered.is_set)
        assert len(jobs) == 1
        assert base['ximalaya_review']['status'] == 'pending'
        assert not base.get('jpeg') and base['logo_base']['without_logo']
        assert all(s['state'] == 'queued' for s in branches)
        with pytest.raises(UserError, match='同套的所有已选尺寸'):
            engine.package(tid, 0, suite_number=1)
        release.set()
        until(engine, lambda: base['ximalaya_review']['status'] == 'rejected')
        assert len(jobs) == 1 and all(s['state'] == 'blocked_first_failed' for s in branches)
        assert '副标题缺字' in base['msg']
        assert engine.public(task)['rounds'][0]['slots'][0]['review_image_url']

        engine.mutate(tid, 'regenerate', {'image_id':base['id'], 'expected_att':1})
        until(engine, lambda: base.get('ximalaya_review', {}).get('auto_attempts') == 1 and base['state'] == 'queued')
        assert len(jobs) == 2 and '首图重出要求' in jobs[-1]['slot']['prompt']
        assert base['state'] == 'queued' and base['ximalaya_review']['status'] == 'pending'
        # A restart after dispatch must recover the stored audit, not the KIE job.
        with engine.lock:
            base['state'] = 'generating'
            engine.recover_task(task)
        assert base['state'] == 'queued' and not base.get('resume')
        until(engine, lambda: all(s['state']=='done' for s in round_['slots']))
        assert len(audits) == 3 and audits[1] == audits[2]
        assert len(jobs) == 6
        for s in branches:
            assert s['source_versions'][base['id']] == {'att':2,'path':base['output'],'sha256':base['raw_sha256']}
            assert len(s['refs']) == 1 and s['refs'][0]['path'] == base['output']
            assert params()['t2'] in s['prompt']
        before = [s['att'] for s in round_['slots']]
        old_review = {s['id']:s['att'] for s in round_['slots']}
        engine.mutate(tid, 'regenerate', {'image_id':branches[0]['id'], 'expected_att':branches[0]['att']})
        until(engine, lambda: all(s['state']=='done' for s in round_['slots']))
        assert [s['att'] for s in round_['slots']] == [before[0],before[1]+1,*before[2:]]
        assert len(jobs) == 7 and len(audits) == 3

        with pytest.raises(UserError, match='选中整套成品的当前版本'):
            engine.package(tid, 0, suite_number=1, reviewed_versions={})
        with pytest.raises(UserError, match='选中整套成品的当前版本'):
            engine.package(tid, 0, suite_number=1, reviewed_versions=old_review)
        reviewed = {s['id']:s['att'] for s in round_['slots']}
        assert [s['logo_review_switchable'] for s in engine.public(task)['rounds'][0]['slots']] == [False,False,False,True,True]
        package = engine.package(tid, 0, suite_number=1, reviewed_versions=reviewed)
        assert engine.package(tid, 0, suite_number=1, reviewed_versions=reviewed)['id'] == package['id']
        with zipfile.ZipFile(package['path']) as archive:
            rows = json.loads(archive.read('交付清单.json'))['images']
            assert len(rows) == 5
            for row in rows:
                p = engine_module.BY_ID[row['placement_id']]
                data = archive.read(row['path'])
                assert len(data) < 150*1024 and hashlib.sha256(data).hexdigest() == row['sha256']
                with Image.open(BytesIO(data)) as image:
                    assert image.format == 'JPEG' and image.size == (p['target_width'],p['target_height'])
                if row['placement_id'] != ximalaya.BASE:
                    assert row['ximalaya_base']['sha256'] == base['raw_sha256']
        slot=next(s for s in branches if s['delivery_logo_asset_id'])
        chosen='learning.logo.black' if slot['delivery_logo_asset_id']=='learning.logo.white-app' else 'learning.logo.white-app'
        old_zip=Path(package['path']).read_bytes()
        engine.review_image_logo(tid,{'image_id':slot['id'],'expected_att':slot['att'],
                                      'expected_sha256':slot['sha256'],'asset_id':chosen})
        assert ximalaya.complete(round_['slots'],round_['simulation'])
        assert len(jobs)==7 and slot['att']==reviewed[slot['id']]
        switched=engine.package(tid,0,suite_number=1,reviewed_versions=reviewed)
        with zipfile.ZipFile(switched['path']) as archive:
            item=next(row for row in json.loads(archive.read('交付清单.json'))['images'] if row['placement_id']==slot['pid'])
            assert item['logo_asset_id']==chosen and archive.read(item['path'])==Path(slot['logo_review']['path']).read_bytes()
        assert Path(package['path']).read_bytes()==old_zip
    finally:
        release.set()
        engine.close()


def test_mixed_feed_runs_and_exports_only_selected_sizes(tmp_path,monkeypatch):
    settings=Settings(tmp_path/'state',tmp_path/'test.env')
    settings.update({'kie_api_key':'offline-image-key','output_dir':str(tmp_path),'simulation':False})
    engine=engine_module.Engine(settings,start=False,planner=FixturePlanner())
    ordinary=[p['id'] for p in engine_module.BY_ID.values() if p['category']=='信息流' and p['platform']!='喜马拉雅']
    root,branch=ximalaya.PLACEMENTS[1],ximalaya.PLACEMENTS[3]
    jobs=[]
    audits=[]

    def worker(command,**kwargs):
        job_path=Path(command[-1])
        job=json.loads(job_path.read_text())
        placement=job['placement']
        jobs.append(placement['id'])
        output=Path(job['slot']['output'])
        Image.new('RGB',(placement['target_width'],placement['target_height']),'#ebead4').save(output)
        job_path.with_suffix('.result.json').write_text(json.dumps({'ok':True,'source':str(output)}))
        return SimpleNamespace(communicate=lambda:(b'',b''))

    def review(settings,slot,wording,stopped):
        assert branch not in jobs
        audits.append(slot['pid'])
        return {'verdict':'pass','issues':[]}

    monkeypatch.setattr(engine_module.subprocess,'Popen',worker)
    monkeypatch.setattr(ximalaya,'review',review)
    try:
        selected=[*ordinary,branch,root]
        pr={**params(),'pids':selected,'cta_overrides':{ordinary[0]:{'mode':'none','text':''}}}
        tid=engine.create(pr,'mixed-feed')['id']
        task=engine.task(tid)
        round_=task['rounds'][0]
        assert {row['placement_id'] for row in plan_input(round_)['jobs']}=={*ordinary,root}
        until(engine,lambda:all(s['state']=='done' for s in round_['slots']))
        assert sorted(jobs)==sorted(selected)
        assert audits==[root]
        slots={s['pid']:s for s in round_['slots']}
        assert slots[branch]['ximalaya_source']==slots[root]['id']
        assert all(not slots[pid].get('ximalaya_source') for pid in ordinary)
        for pid in ordinary:
            engine.mutate(tid,'adopt',{'placement_id':pid,'set':1,'adopted':True})
        reviewed={slots[pid]['id']:slots[pid]['att'] for pid in (root,branch)}
        with pytest.raises(UserError,match='当前版本'):
            engine.mutate(tid,'adopt',{'placement_id':root,'set':1,'adopted':True,'reviewed_versions':{}})
        engine.mutate(tid,'adopt',{'placement_id':root,'set':1,'adopted':True,'reviewed_versions':reviewed})
        assert engine.delivery_state(task,round_)['covered_placements']==len(selected)
        with pytest.raises(UserError,match='当前版本'):
            engine.package(tid,0,reviewed_versions={})
        xima=engine.package(tid,0,suite_number=1,reviewed_versions=reviewed)
        assert {image['pid'] for image in xima['images']}=={root,branch}
        combined=engine.package(tid,0,reviewed_versions=reviewed)
        with zipfile.ZipFile(combined['path']) as archive:
            assert {pic['placement_id'] for pic in json.loads(archive.read('交付清单.json'))['images']}==set(selected)
        engine.mutate(tid,'add-variant',{'placement_id':root})
        assert {s['pid'] for s in round_['slots'] if s['set']==2}=={root,branch}
    finally:
        engine.close()


def test_luna_parses_subtitle_as_independent_copy():
    allowed = {'t1':'题目不会先拍一下','subtitle':'跟着步骤，看懂解题思路','cta':''}
    actual = {'verdict':'pass','body':allowed['t1'],'subtitle':'','cta':'','issues':[]}
    response = lambda: {'choices':[{'message':{'content':json.dumps(actual)}}]}
    assert learning_visual._parse(response(),allowed)['verdict'] == 'review'
    actual['subtitle'] = allowed['subtitle']
    assert learning_visual._parse(response(),allowed)['verdict'] == 'pass'


@pytest.mark.parametrize('scenario',['known','attach','unaccepted'])
def test_poll_timeout_only_resumes_known_receipt_and_export_reuses_download(tmp_path,monkeypatch,scenario):
    settings=Settings(tmp_path/'state',tmp_path/'test.env')
    settings.update({'kie_api_key':'offline-image-key','simulation':False,'output_dir':str(tmp_path)})
    engine=engine_module.Engine(settings,start=False,planner=FixturePlanner())
    queries=[];exports=[];has_task_id=scenario=='known'
    monkeypatch.setattr(engine_module,'QUERY_RETRY_DELAYS',(0,))
    monkeypatch.setattr(engine_module,'LOCAL_RETRY_DELAYS',(0,))
    render=engine.materialize_image
    receipt_input={}

    def read_kie_task(req,*args,**kwargs):
        assert req.method=='GET' and '/jobs/recordInfo?taskId=' in req.full_url
        return {'data':{'taskId':'existing-receipt','state':'success','param':json.dumps(receipt_input)}}
    monkeypatch.setattr(engine_module.render,'request_json',read_kie_task)

    def worker(command,**kwargs):
        job_path=Path(command[-1]);job=json.loads(job_path.read_text());out=Path(job['slot']['output'])
        queries.append(job['query_only'])
        if len(queries)==1:
            state={'status':'poll_timeout','task_id':'existing-receipt'} if has_task_id else {'status':'submit_uncertain'}
            receipt_input.update(model=job['image_model'],input={'prompt':job['slot']['prompt'],'aspect_ratio':'1:1','resolution':'1K'})
            state['submission_signature']=engine_module.render.submission_signature(receipt_input['model'],receipt_input['input'])
            engine_module.atomic(engine_module.render.task_state_path(out),state)
            result={'ok':False,'reason':'timeout','state':state}
        else:
            if scenario in ('known','attach'):
                assert job['query_only'] and json.loads(engine_module.render.task_state_path(out).read_text())['task_id']=='existing-receipt'
            else:
                assert not job['query_only'] and job['slot']['att']==2
            p=job['placement'];Image.new('RGB',(p['target_width'],p['target_height']),'white').save(out)
            result={'ok':True,'source':str(out),'state':{'status':'downloaded','task_id':'existing-receipt'}}
        engine_module.atomic(job_path.with_suffix('.result.json'),result)
        return SimpleNamespace(communicate=lambda:(b'',b''))

    def local(slot,result,path,placement):
        exports.append(Path(result['source']))
        if len(exports)==1:raise OSError('temporarily busy')
        return render(slot,result,path,placement)

    monkeypatch.setattr(engine_module.subprocess,'Popen',worker)
    monkeypatch.setattr(engine,'materialize_image',local)
    try:
        data=params();data.update(ximalaya_suite=False,pids=[ximalaya.BASE])
        task=engine.create(data,'offline-query-retry')
        s=engine.task(task['id'])['rounds'][0]['slots'][0]
        until(engine,lambda:s['state'] in ('done','failed'))
        if has_task_id:
            assert queries==[False,True] and len(exports)==2 and exports[0]==exports[1]
            assert s['state']=='done' and s['att']==1
        else:
            assert queries==[False] and not exports and s['state']=='failed'
            if scenario=='attach':
                engine.attach_kie_receipt(task['id'],{'image_id':s['id'],'expected_att':1,'task_id':'existing-receipt'})
                with pytest.raises(UserError):
                    engine.attach_kie_receipt(task['id'],{'image_id':s['id'],'expected_att':1,'task_id':'existing-receipt'})
            else:
                with pytest.raises(UserError):engine.mutate(task['id'],'retry-confirmed-submission',{'image_id':s['id']})
                engine.mutate(task['id'],'retry-confirmed-submission',{'image_id':s['id'],'expected_att':1,'confirmed_unaccepted':True})
            until(engine,lambda:s['state']=='done')
            if scenario=='attach':
                assert queries==[False,True] and s['att']==1
            else:
                assert queries==[False,False] and s['submission_reconciliation']['previous_version']==1
    finally:
        engine.close()
