"""Actual local HTTP with a fixture at the image provider boundary."""
import copy
import json
import time
from io import BytesIO
import zipfile

import pytest
from PIL import Image

from tests_local.test_learning_setup_api import api, production_learning_api, FixtureLearningExecutor


def settled(request,rid,timeout=45):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        status,run=request('/api/learning-machine/runs/'+rid)
        assert status==200
        if not run['busy']:return run
        time.sleep(.03)
    pytest.fail('Local learning rehearsal did not settle')


def test_full_http_production_confirm_reuse_45_exports_single_versions_and_zip(production_learning_api):
    engine,request=production_learning_api
    params={'channel':'学习机','t1':'不会的题拍一下','font':'none','ip':'none','style':'random'}
    payload={'params':params,'idempotency_key':'api-production-create'}
    status,run=request('/api/learning-machine/runs','POST',payload)
    assert status==200 and run['mode']=='real' and run['baseline']['status']=='not_generated'
    rid=run['id'];base='/api/learning-machine/runs/'+rid
    assert request('/api/learning-machine/runs','POST',payload)[1]['id']==rid
    assert request(base+'/expand','POST',{'idempotency_key':'api-expand-before-image'})[0]==409
    assert request(base+'/confirm','POST',{'baseline_version':1})[0]==409
    assert request(base+'/baseline','POST',{'idempotency_key':'api-first-baseline'})[0]==200
    run=settled(request,rid)
    assert run['status']=='waiting_for_confirmation' and run['baseline']['status']=='done',run.get('error')
    assert run['approval'] is None and all(o['version']==0 for o in run['outputs'])
    assert request(base+'/baseline','POST',{'idempotency_key':'api-first-baseline'})[1]['baseline']['version']==1
    assert request(base+'/confirm','POST',{'baseline_version':2})[0]==409
    assert request(base+'/confirm','POST',{'baseline_version':1})[1]['approval']['mode']=='real'
    assert request(base+'/expand','POST',{'idempotency_key':'api-expand-suite'})[0]==200
    run=settled(request,rid)
    assert run['status']=='completed',[(o['id'],o.get('error')) for o in run['outputs'] if o['status']!='done']
    assert len(run['outputs'])==45 and len(run['masters'])==16
    assert len(list((engine.settings.output/'.cache'/'learning-runs'/rid).rglob('*.simulation.json')))==26
    for output in run['outputs']:
        status,raw=request(output['image_url']);assert status==200
        with Image.open(BytesIO(raw)) as image:
            assert image.format=='PNG' and image.size==(output['width'],output['height'])
    double=[o for o in run['outputs'] if o['placement_id']=='learning-youxuepai-double-840x404']
    assert len(double)==2 and double[0]['sha256']==double[1]['sha256']
    status,package=request(base+'/package','POST',{})
    assert status==200 and package['image_count']==45
    status,zip_bytes=request(package['download_url']);assert status==200
    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        manifest=json.loads(archive.read('交付清单.json'))
        assert manifest['mode']=='real' and len(manifest['images'])==45
        assert manifest['archive_layout']=='channel-placement-v1'
        assert next(row for row in manifest['images'] if row['placement_id']=='learning-baidu-512x512')['path'].startswith('百度/广告图_512x512/')
        assert len([n for n in archive.namelist() if n.endswith('.png')])==45
    versions={o['id']:(o['version'],o['sha256']) for o in run['outputs']}
    target=next(o for o in run['outputs'] if o['placement_id']=='learning-ruishi-rect-580x320')
    baseline_sha=run['baseline']['sha256'];old_image=target['image_url']
    route=base+'/outputs/'+target['id']+'/regenerate'
    assert request(route,'POST',{'idempotency_key':'api-redraw-stale','expected_version':target['version']+1})[0]==409
    assert request(route,'POST',{'idempotency_key':'api-redraw-one','expected_version':target['version']})[0]==200
    run=settled(request,rid)
    assert run['status']=='completed' and run['baseline']['sha256']==baseline_sha
    for output in run['outputs']:
        if output['id']==target['id']:assert output['version']==versions[output['id']][0]+1
        else:assert (output['version'],output['sha256'])==versions[output['id']]
    assert request(old_image)[0]==200 and request(package['download_url'])[0]==200
    assert len(list((engine.settings.output/'.cache'/'learning-runs'/rid).rglob('*.simulation.json')))==27
    before=copy.deepcopy(run['outputs'])
    assert request(base+'/baseline','POST',{'idempotency_key':'api-next-baseline'})[0]==200
    run=settled(request,rid)
    assert run['baseline']['version']==2 and run['approval'] is None
    assert run['outputs']==before
    assert request(base+'/confirm','POST',{'baseline_version':1})[0]==409
    assert not engine.tasks


def test_current_runtime_static_and_missing_runs_are_safe(api):
    engine,request=api
    assert request('/js/learning-runs.js')[0]==200
    assert request('/api/learning-machine/runs')[1]=={'runs':[]}
    assert request('/api/learning-machine/runs/'+'f'*32)[0]==404
    params={'params':{'t1':'一句正文'},'idempotency_key':'api-no-real-keys'}
    status,value=request('/api/learning-machine/runs','POST',params)
    assert status==400 and 'Key' in value['message_zh']
    status,value=request('/api/learning-machine/runs','POST',{**params,'mode':'simulation'})
    assert status==400 and '正式制作' in value['message_zh']
    assert request('/api/learning-machine/runs')[1]=={'runs':[]}
    historical=engine.learning_runtime.create({'t1':'旧演练文案','pids':['learning-baidu-512x512']},
                                               mode='simulation',idempotency_key='historical-rehearsal')
    rid=historical['id']
    base='/api/learning-machine/runs/'+rid
    assert request(base)[1]['mode']=='simulation'
    assert request(base+'/from-baseline','POST',{'idempotency_key':'historical-to-new'})[0]==409
    engine.learning_runtime.generate_baseline(rid,'historical-baseline-fixture')
    settled(request,rid)
    engine.learning_runtime.confirm_baseline(rid,1)
    code,message=request('/api/master-canvases','POST',{'source':{'kind':'learning','run_id':rid,'baseline':True},
        'target_kind':'learning','pids':['learning-baidu-512x512'],'idempotency_key':'historical-shared-target'})
    assert code==409 and '正式制作' in message['message_zh']
    assert len(request('/api/learning-machine/runs')[1]['runs'])==1


def test_shared_rate_limit_burst_reduces_once_and_holds_fair_admission(api,monkeypatch):
    import local_app.engine as module
    engine,_=api;clock=[0.0]
    monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
    engine.note_rate_limit();assert engine.throttle==10
    clock[0]=2;engine.note_rate_limit();assert engine.throttle==10
    assert engine.pool.stats()['limit']==0
    assert '限流' in engine.queue_status()['blocked_reason']
    clock[0]=8;engine.note_rate_limit();assert engine.throttle==5


def test_reload_after_completion_before_final_journal_commit_reuses_finished_masters(production_learning_api):
    from local_app.learning_runtime import PREFIX
    engine,request=production_learning_api
    _,run=request('/api/learning-machine/runs','POST',{'params':{'t1':'不会的题拍一下','font':'none','pids':['learning-baidu-512x512']},'idempotency_key':'crash-journal-create'})
    rid=run['id'];base='/api/learning-machine/runs/'+rid
    request(base+'/baseline','POST',{'idempotency_key':'crash-journal-baseline'});settled(request,rid)
    request(base+'/confirm','POST',{'baseline_version':1});request(base+'/expand','POST',{'idempotency_key':'crash-journal-expand'})
    run=settled(request,rid);assert run['status']=='completed'
    folder=engine.settings.output/'.cache'/'learning-runs'/rid
    count=len(list(folder.rglob('*.simulation.json')))
    # Valid crash window: all files landed but final suite completion did not.
    journal=engine.document(PREFIX+rid);journal.update(busy=True,status='generating_suite');journal['suite']['status']='generating'
    engine.put_document(PREFIX+rid,journal);engine.learning_runtime.reload()
    recovered=engine.learning_runtime.get(rid)
    assert recovered['status']=='interrupted' and recovered['suite']['status']=='interrupted'
    request(base+'/expand','POST',{'idempotency_key':'crash-journal-resume'})
    recovered=settled(request,rid);assert recovered['status']=='completed'
    assert recovered['outputs'][0]['version']==run['outputs'][0]['version']
    assert len(list(folder.rglob('*.simulation.json')))==count


def test_learning_only_backup_restores_pixels_and_frozen_specs_into_an_open_runtime(production_learning_api,tmp_path,monkeypatch):
    from local_app.config import Settings
    from local_app.engine import Engine
    from local_app.learning_runtime import LearningRuntime
    from local_app.learning_pipeline import CONTENT_BY_ID
    from tests_local.fakes import FixturePlanner
    engine,request=production_learning_api;pid='learning-ruishi-rect-580x320'
    params={'channel':'学习机','t1':'不会的题拍一下','font':'none','ip':'none','pids':[pid]}
    _,run=request('/api/learning-machine/runs','POST',{'params':params,'idempotency_key':'backup-learning-create'})
    rid=run['id'];base='/api/learning-machine/runs/'+rid
    request(base+'/baseline','POST',{'idempotency_key':'backup-learning-baseline'});run=settled(request,rid)
    assert run['baseline']['status']=='done'
    request(base+'/confirm','POST',{'baseline_version':1});request(base+'/expand','POST',{'idempotency_key':'backup-learning-expand'})
    run=settled(request,rid);assert run['status']=='completed'
    original=request(run['outputs'][0]['image_url'])[1]
    # Changing the default output location must not omit this older run's
    # frozen directory from the backup.
    next_workspace=tmp_path/'new-default-workspace';next_workspace.mkdir()
    engine.settings.update({'output_dir':str(next_workspace)})
    backup=engine.create_backup();assert not engine.tasks and backup['tasks']==0
    folder=tmp_path/'restored-learning';folder.mkdir()
    settings=Settings(folder/'state',folder/'test.env');settings.update({'simulation':True,'output_dir':str(folder)})
    other=Engine(settings,start=False,planner=FixturePlanner());other.learning_runtime=LearningRuntime(other,FixtureLearningExecutor(settings))
    try:
        preview=other.restore_preview(backup['path']);other.restore_backup(backup['path'],preview['token'])
        manager=other.learning_runtime
        restored=manager.get(rid)
        assert restored['outputs'][0]['sha256']==run['outputs'][0]['sha256']
        assert manager.image(rid,'output',restored['outputs'][0]['id']).read_bytes()==original
        # A later live catalog edit must not change the restored run's recipe.
        changed=copy.deepcopy(CONTENT_BY_ID[pid]);changed.update(target_width=12,target_height=12,corner_radius=0,max_file_size_kb=.1)
        monkeypatch.setitem(CONTENT_BY_ID,pid,changed)
        manager.generate_baseline(rid,'restore-next-baseline')
        deadline=time.monotonic()+20
        while manager.get(rid)['busy'] and time.monotonic()<deadline:time.sleep(.02)
        manager.confirm_baseline(rid,2);manager.expand_suite(rid,'restore-next-suite')
        deadline=time.monotonic()+20
        while manager.get(rid)['busy'] and time.monotonic()<deadline:time.sleep(.02)
        restored=manager.get(rid);assert restored['status']=='completed',restored.get('error')
        with Image.open(manager.image(rid,'output',restored['outputs'][0]['id'])) as image:assert image.size==(580,320)
    finally:other.close()


def test_uploaded_concept_exact_ratio_full_default_and_confirmed_group_routing(production_learning_api):
    import base64
    import hashlib
    engine,request=production_learning_api
    def upload(width,height):
        stream=BytesIO()
        Image.new('RGB',(width,height),'white').save(stream,'PNG')
        data=stream.getvalue()
        status,result=request('/api/uploads','POST',{'purpose':'learning_concept','name':'概念.png',
            'data':base64.b64encode(data).decode('ascii')})
        return status,result,data
    assert upload(900,900)[0]==400
    status,item,source=upload(960,540)
    assert status==200 and item['width']==960 and item['height']==540
    params={'channel':'学习机','t1':'按图填写的整句文案。','concept':{'id':item['id'],'button_text':'开始学习'}}
    status,plan=request('/api/learning-machine/preview','POST',{'params':params})
    assert status==200 and len(plan['params']['pids'])==44 and plan['output_count']==45
    modes={m['group_id']:m['concept_route'] for m in plan['prompt_plan']['masters']}
    assert {k:modes[k] for k in ('A1','D1','D2','D3','E3')}=={
        'A1':'pure','D1':'reflow','D2':'direct','D3':'background','E3':'remove_cta'}
    pure=[m for m in plan['prompt_plan']['masters'] if m['concept_route']=='pure']
    assert [(m['group_id'],m['main_visual_framing']['orientation']) for m in pure]==[('A1','tall'),('B1','wide')]
    for m in pure:
        assert m['main_visual_framing']['source_framing']=='recompose_after_content_removal'
        assert m['main_visual_framing']['removed_ad_module']=='body'
        assert m['concept_audit_box'] and m['allowed_text']=={}
        assert '重新分配整张画面的空间' in m['prompt'] and '镜头退远' not in m['prompt']
        assert '道具' in m['single_regeneration_prompt'] and '分镜' in m['single_regeneration_prompt']
    cta=next(m for m in plan['prompt_plan']['masters'] if m['group_id']=='E3')
    assert cta['main_visual_framing']['removed_ad_module']=='cta'
    assert cta['concept_audit_box'] and cta['allowed_text']=={'t1':params['t1']}
    assert '重新安排正文与主视觉的间距和位置' in cta['prompt']
    assert '镜头退远' not in cta['single_regeneration_prompt']
    assert {r['placement_id'] for r in plan['outputs'] if r['concept_route']=='direct'}=={
        'learning-iflytek-1005x564','learning-zuoyebang-632x354'}
    assert plan['prompt_plan']['counts']['baseline_image_calls']==0
    without_button=copy.deepcopy(params)
    without_button['concept']['button_text']=''
    _,other=request('/api/learning-machine/preview','POST',{'params':without_button})
    assert next(m for m in other['prompt_plan']['masters'] if m['group_id']=='D2')['concept_route']=='add_cta'
    assert 'removed_ad_module' not in next(m for m in other['prompt_plan']['masters'] if m['group_id']=='E3')['main_visual_framing']
    assert other['params']['cta']=='点击下载'

    params['pids']=['learning-iflytek-1005x564','learning-bbg-logo-banner-988x460','learning-bbg-cover-216x260',
                    'learning-dsl-resource-500x312','learning-baidu-512x512']
    status,run=request('/api/learning-machine/runs','POST',{'params':params,'idempotency_key':'concept-http-create'})
    assert status==200 and run['baseline']['uploaded'] and run['approval'] is None
    rid=run['id'];url='/api/learning-machine/runs/'+rid
    assert request(run['baseline']['image_url'])==(200,source)
    assert request(url+'/baseline','POST',{'idempotency_key':'concept-http-baseline'})[0]==409
    assert request(url+'/expand','POST',{'idempotency_key':'concept-http-before'})[0]==409
    assert request(url+'/confirm','POST',{'baseline_version':1})[1]['approval']['sha256']==hashlib.sha256(source).hexdigest()
    assert request(url+'/expand','POST',{'idempotency_key':'concept-http-after'})[0]==200
    complete=settled(request,rid)
    assert complete['counts']['completed_outputs']==len(params['pids'])
    saved=engine.document('learning-run:'+rid)
    direct=next(o for o in saved['outputs'] if o['concept_route']=='direct')
    assert direct['raw_sha256']==item['id'] and direct['provider_task_id'] is None
    assert not list((engine.settings.output/'.cache'/'learning-runs'/rid/'baselines').glob('*.simulation.json'))
