"""Actual run state, file/version and export lifecycle using only local rehearsal."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import threading
import time
import zipfile
from pathlib import PurePosixPath

import pytest
from PIL import Image

from local_app.config import Settings,UserError
from local_app.engine import Engine
from local_app.learning_executor import LearningExecutor,LearningExecutionError
from local_app.learning_runtime import LearningRuntime,PREFIX
from tests_local.fakes import FixturePlanner


class CountingExecutor(LearningExecutor):
    def __init__(self,settings):
        super().__init__(settings);self.jobs=[];self.scenes=0;self.fail_one=None;self.unknown=True

    def plan_scene(self,run,stop_event):
        self.scenes+=1
        return super().plan_scene(run,stop_event)

    def generate_image(self,job,stop_event):
        assert job['simulation'] is True
        self.jobs.append(copy.deepcopy(job))
        if self.fail_one and job['kind']==self.fail_one:
            self.fail_one=None
            raise LearningExecutionError('测试中的失败',query_required=self.unknown,reason_code='unknown' if self.unknown else 'generation_failed')
        return super().generate_image(job,stop_event)


@pytest.fixture
def runtime(tmp_path):
    settings=Settings(tmp_path/'state',tmp_path/'test.env');settings.update({'simulation':True,'output_dir':str(tmp_path)})
    engine=Engine(settings,start=False,planner=FixturePlanner())
    executor=CountingExecutor(settings);service=LearningRuntime(engine,executor)
    yield service,executor,engine
    service.close();engine.close()


def params(pids=None):
    from local_app.planning import STYLES
    value={'channel':'学习机','t1':'不会的题拍一下','cta':'点击下载','ip':'none','font':'none',
           'style':STYLES[0]['name'],'image_model':'gpt-image-2-6/flare-image-to-image'}
    if pids is not None:value['pids']=pids
    return value


def settled(service,rid):
    end=time.monotonic()+20
    while time.monotonic()<end:
        run=service.get(rid)
        if not run['busy']:return run
        time.sleep(.01)
    raise AssertionError('local learning run did not settle')


def baseline(service,pids=None):
    run=service.create(params(pids),idempotency_key='create-baseline-1')
    service.generate_baseline(run['id'],'generate-baseline-1')
    run=settled(service,run['id'])
    assert run['baseline']['status']=='done',run.get('error')
    return run


def test_full_rehearsal_requires_confirmation_then_reuses_16_masters_for_45_files(runtime):
    service,executor,engine=runtime
    run=service.create(params(),idempotency_key='complete-run-create')
    rid=run['id'];assert not executor.jobs and not executor.scenes
    assert run['mode']=='simulation' and run['counts']['output_count']==45
    saved=engine.document(PREFIX+rid)
    assert len(saved['compiled']['masters'])==16 and len(saved['placement_snapshots'])==44
    assert all(key not in saved['plan'] for key in ('prompt_plan','params','normalized_params','saved_configuration'))
    assert 'placements' not in saved and 'learning_logo_snapshot' not in saved['params']
    assert service.create(params(),idempotency_key='complete-run-create')['id']==rid
    with pytest.raises(UserError,match='确认'):service.expand_suite(rid,'expand-before-approval')
    service.generate_baseline(rid,'full-first-baseline')
    run=settled(service,rid)
    assert run['status']=='waiting_for_confirmation' and run['approval'] is None
    assert len(executor.jobs)==1 and all(m['status']=='not_generated' for m in run['masters'])
    with pytest.raises(UserError):service.confirm_baseline(rid,2)
    service.confirm_baseline(rid,1)
    assert len(executor.jobs)==1  # Approval itself cannot enqueue the suite.
    service.expand_suite(rid,'full-expand-once')
    run=settled(service,rid)
    assert run['status']=='completed',run.get('error')
    assert len(executor.jobs)==26 and executor.scenes==1
    assert sum(job['kind']=='background_expansion' for job in executor.jobs)==10
    assert run['counts']['completed_outputs']==45 and len(run['masters'])==16
    base=service.image(rid,'baseline','baseline',1)
    for job in (j for j in executor.jobs if j['kind']=='master'):
        assert job['reference_bindings'][0]['kind']=='confirmed_baseline'
        assert job['reference_bindings'][0]['path']==str(base)
        expected=next(m for m in saved['compiled']['masters'] if m['id']==job['id'])
        assert job['main_visual_framing']==expected['main_visual_framing']
        assert '构图：镜头退远' in job['prompt']
    for row in run['outputs']:
        with Image.open(service.image(rid,'output',row['id'],row['version'])) as image:
            assert image.format=='PNG' and image.size==(row['width'],row['height'])
    double=[o for o in run['outputs'] if o['placement_id']=='learning-youxuepai-double-840x404']
    assert len(double)==2 and double[0]['sha256']==double[1]['sha256']
    service.expand_suite(rid,'fresh-key-still-same-suite')
    assert len(executor.jobs)==26
    package=service.package(rid);assert package['image_count']==45
    assert service.package(rid)['id']==package['id']
    with zipfile.ZipFile(service.package_file(rid,package['id'])) as archive:
        manifest=json.loads(archive.read('交付清单.json'))
        assert manifest['mode']=='simulation' and len(manifest['images'])==45
        assert manifest['archive_layout']=='channel-placement-v1'
        assert len(archive.namelist())==len(set(archive.namelist()))==46
        for row in manifest['images']:
            parts=PurePosixPath(row['path']).parts
            spec=saved['placement_snapshots'][row['placement_id']]
            assert len(parts)==3 and parts[0]==spec['platform']
            assert parts[1]==spec['name']+'_'+str(spec['target_width'])+'x'+str(spec['target_height'])
            assert hashlib.sha256(archive.read(row['path'])).hexdigest()==row['sha256']
    assert not engine.tasks


def test_single_redraw_is_one_image_and_preserves_shared_mother_and_sibling(runtime):
    service,executor,_=runtime
    pids=['learning-ruishi-rounded-580x320','learning-ruishi-rect-580x320']
    run=baseline(service,pids);rid=run['id'];service.confirm_baseline(rid,1)
    service.expand_suite(rid,'reuse-only-expand');run=settled(service,rid)
    assert len(executor.jobs)==1
    target,sibling=run['outputs'];mother=copy.deepcopy(run['masters']);old=copy.deepcopy(sibling)
    service.regenerate_output(rid,target['id'],'redraw-one-output',expected_version=1)
    run=settled(service,rid)
    assert run['status']=='completed',run.get('error')
    changed=next(o for o in run['outputs'] if o['id']==target['id'])
    assert len(executor.jobs)==2 and executor.jobs[-1]['kind']=='single'
    assert changed['version']==2 and changed['versions'][0]['version']==1
    assert next(o for o in run['outputs'] if o['id']==sibling['id'])==old
    assert run['masters']==mother and run['baseline']['version']==1
    assert service.image(rid,'output',target['id'],1).is_file()
    with pytest.raises(UserError,match='版本'):service.regenerate_output(rid,target['id'],'stale-redraw-window',expected_version=1)


def test_new_baseline_preserves_old_delivery_and_needs_new_approval(runtime):
    service,executor,_=runtime
    run=baseline(service,['learning-baidu-512x512']);rid=run['id'];service.confirm_baseline(rid,1)
    service.expand_suite(rid,'first-single-suite');before=settled(service,rid)
    target=before['outputs'][0];old_file=service.image(rid,'output',target['id'],1).read_bytes()
    service.generate_baseline(rid,'different-baseline-version');run=settled(service,rid)
    assert run['baseline']['version']==2 and run['approval'] is None
    assert run['outputs']==before['outputs']
    with pytest.raises(UserError):service.confirm_baseline(rid,1)
    with pytest.raises(UserError):service.expand_suite(rid,'cannot-expand-without-current-approval')
    service.confirm_baseline(rid,2);service.expand_suite(rid,'second-single-suite');run=settled(service,rid)
    assert run['outputs'][0]['version']==2 and run['outputs'][0]['baseline_version']==2
    assert service.image(rid,'output',target['id'],1).read_bytes()==old_file
    assert len(run['baseline_versions'])==1


def test_tampered_baseline_and_idempotency_mode_changes_are_rejected(runtime):
    service,executor,engine=runtime
    run=baseline(service,['learning-ruishi-rect-580x320']);rid=run['id']
    file=service.image(rid,'baseline','baseline');file.write_bytes(b'tampered')
    with pytest.raises(UserError,match='校验'):service.confirm_baseline(rid,1)
    with pytest.raises(UserError,match='Key'):service.create(params(),mode='real',idempotency_key='real-create-no-keys')
    engine.settings.key='test-only-kie';engine.settings.planning_key='test-only-planner'
    with pytest.raises(UserError,match='改变'):
        service.create(params(['learning-ruishi-rect-580x320']),mode='real',idempotency_key='create-baseline-1')
    with pytest.raises(UserError,match='改变'):service.create({**params(['learning-ruishi-rect-580x320']),'t1':'不同正文'},idempotency_key='create-baseline-1')
    assert len(executor.jobs)==1 and not engine.tasks


def test_unknown_baseline_recovery_keeps_version_path_and_skips_replanning(runtime):
    service,executor,_=runtime
    run=service.create(params(['learning-ruishi-rect-580x320']),idempotency_key='unknown-baseline-create');rid=run['id']
    executor.fail_one='baseline';service.generate_baseline(rid,'uncertain-baseline-request')
    failed=settled(service,rid);assert failed['baseline']['query_required']
    first_path=executor.jobs[0]['output'];service.generate_baseline(rid,'resume-baseline-query')
    run=settled(service,rid)
    assert run['baseline']['status']=='done' and run['baseline']['version']==1
    assert executor.scenes==1 and executor.jobs[1]['output']==first_path


def test_reload_keeps_completed_versions_and_reclassifies_interrupted_work(runtime):
    service,executor,engine=runtime
    run=baseline(service,['learning-ruishi-rect-580x320']);rid=run['id']
    source=service.image(rid,'baseline','baseline',1)
    stored=engine.document(PREFIX+rid);stored.update(busy=True,status='generating_suite')
    stored['masters'][0]['status']='queued'
    with engine.lock:engine.put_document(PREFIX+rid,stored)
    service.reload();restored=service.get(rid)
    assert restored['status']=='interrupted' and restored['masters'][0]['status']=='interrupted'
    assert not restored['busy'] and service.image(rid,'baseline','baseline',1)==source
    assert len(executor.jobs)==1
    assert service.list()[0]['id']==rid


def test_runtime_public_records_have_no_local_paths_and_image_scope_is_fixed(runtime):
    service,_,_=runtime
    run=baseline(service,['learning-ruishi-rect-580x320']);rid=run['id']
    encoded=json.dumps(run,ensure_ascii=False)
    assert '/.cache/' not in encoded and 'raw_path' not in encoded and 'asset_bindings' not in encoded
    with pytest.raises(UserError):service.image(rid,'output','../../etc/passwd')
    with pytest.raises(UserError):service.image(rid,'baseline','baseline',99)
    with pytest.raises(UserError):service.confirm_baseline(rid,True)


def test_uncertain_shared_master_blocks_baseline_changes_and_resumes_same_identity(runtime):
    service,executor,_=runtime
    run=baseline(service,['learning-baidu-512x512']);rid=run['id'];service.confirm_baseline(rid,1)
    executor.fail_one='master';service.expand_suite(rid,'uncertain-master-suite');failed=settled(service,rid)
    assert failed['masters'][0]['query_required']
    with pytest.raises(UserError,match='状态不明'):service.generate_baseline(rid,'must-not-replace-baseline')
    with pytest.raises(UserError,match='母版状态不明'):service.regenerate_output(rid,failed['outputs'][0]['id'],'must-not-resubmit-parent')
    service.expand_suite(rid,'recover-uncertain-master');run=settled(service,rid)
    assert run['status']=='completed' and executor.scenes==1
    assert executor.jobs[-1]['output']==executor.jobs[-2]['output']
    assert executor.jobs[-1]['reference_bindings']==executor.jobs[-2]['reference_bindings']


def test_suite_repair_after_known_single_failure_reuses_already_finished_master(runtime):
    service,executor,_=runtime
    run=baseline(service,['learning-ruishi-rect-580x320']);rid=run['id'];service.confirm_baseline(rid,1)
    service.expand_suite(rid,'repair-original-expand');run=settled(service,rid)
    original_prompt=run['outputs'][0]['prompt']
    executor.fail_one='single';executor.unknown=False
    service.regenerate_output(rid,run['outputs'][0]['id'],'known-failed-single');failed=settled(service,rid)
    assert failed['outputs'][0]['status']=='failed' and not failed['outputs'][0]['query_required']
    assert failed['outputs'][0]['prompt']==executor.jobs[-1]['prompt']!=original_prompt
    assert failed['outputs'][0]['versions'][-1]['prompt']==original_prompt
    assert failed['outputs'][0]['source_master_id'].startswith('single-')
    count=len(executor.jobs);before=copy.deepcopy(failed['masters'])
    service.expand_suite(rid,'repair-code-export-only');run=settled(service,rid)
    assert run['status']=='completed' and len(executor.jobs)==count and run['masters']==before
    assert run['outputs'][0]['prompt']==original_prompt and run['outputs'][0]['reuse_baseline'] is True


def test_concurrent_create_rechecks_the_signature_before_returning_same_key(runtime,monkeypatch):
    from local_app import learning_runtime_support
    service,_,engine=runtime;original=learning_runtime_support.freeze_run
    barrier=threading.Barrier(2)
    def freeze(*args,**kwargs):
        barrier.wait(timeout=5)
        return original(*args,**kwargs)
    monkeypatch.setattr(learning_runtime_support,'freeze_run',freeze)
    results=[]
    def create(text):
        try:results.append(service.create({**params(['learning-ruishi-rect-580x320']),'t1':text},idempotency_key='shared-create-race'))
        except UserError as error:results.append(error)
    threads=[threading.Thread(target=create,args=(text,)) for text in ('第一份文案','第二份文案')]
    for thread in threads:thread.start()
    for thread in threads:thread.join(10)
    assert all(not t.is_alive() for t in threads)
    assert len(service.list())==1 and sum(isinstance(r,UserError) for r in results)==1
    assert len(list((engine.settings.output/'.cache'/'learning-runs').iterdir()))==1


def test_restored_receipt_is_staged_to_new_execution_directory_without_new_version(runtime):
    from scripts.render import task_state_path
    service,executor,engine=runtime
    run=service.create(params(['learning-ruishi-rect-580x320']),idempotency_key='restored-query-create');rid=run['id']
    executor.fail_one='baseline';service.generate_baseline(rid,'restored-query-original');settled(service,rid)
    stored=service.runs[rid];old=Path(stored['baseline']['raw_path'])
    restored=engine.settings.output/'.restored'/'verified'/old.name;restored.parent.mkdir(parents=True)
    receipt={'task_id':'existing-only-query','status':'success','fingerprint':'frozen-provider-request'}
    task_state_path(restored).write_text(json.dumps(receipt))
    stored['baseline']['raw_path']=str(restored)
    # The fake provider does no network, but records the same version's new
    # execution path; the archived receipt remains untouched.
    service.generate_baseline(rid,'restored-query-resume');completed=settled(service,rid)
    assert completed['baseline']['status']=='done' and completed['baseline']['version']==1
    assert json.loads(task_state_path(restored).read_text())==receipt
    assert json.loads(task_state_path(Path(executor.jobs[-1]['output'])).read_text())==receipt
    assert executor.scenes==1


def test_package_reuses_same_pixels_even_when_output_version_changes(runtime,monkeypatch):
    service,executor,_=runtime
    run=baseline(service,['learning-ruishi-rect-580x320']);rid=run['id'];service.confirm_baseline(rid,1)
    service.expand_suite(rid,'same-pixel-first-suite');run=settled(service,rid)
    package=service.package(rid);row=run['outputs'][0]
    old_bytes=service.package_file(rid,package['id']).read_bytes()
    original=service.image(rid,'baseline','baseline',1)
    def same_pixels(job,stop_event):
        assert job['kind']=='single' and job['simulation']
        executor.jobs.append(copy.deepcopy(job));output=Path(job['output']);output.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(original,output)
        return {'source':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'simulated':True}
    monkeypatch.setattr(executor,'generate_image',same_pixels)
    service.regenerate_output(rid,row['id'],'same-pixels-redraw')
    changed=settled(service,rid)['outputs'][0]
    assert changed['version']==2 and changed['sha256']==row['sha256']
    again=service.package(rid)
    assert again['id']==package['id'] and len(service.get(rid)['packages'])==1
    assert service.package_file(rid,package['id']).read_bytes()==old_bytes


def test_flat_historical_package_stays_readable_but_new_save_groups_by_frozen_channel(runtime,monkeypatch):
    service,executor,engine=runtime
    run=baseline(service,['learning-baidu-512x512','learning-bbg-cover-216x260']);rid=run['id']
    service.confirm_baseline(rid,1);service.expand_suite(rid,'layout-test-expand');settled(service,rid)
    from local_app.learning_pipeline import CONTENT_BY_ID
    monkeypatch.setitem(CONTENT_BY_ID['learning-baidu-512x512'],'platform','当前目录的新名字不应覆盖旧批次')
    new=service.package(rid);saved=engine.document(PREFIX+rid)
    # Stored pre-directory ZIP fixture uses the original flat path/fingerprint contract.
    path=service.package_file(rid,new['id'])
    with zipfile.ZipFile(path) as z:
        manifest=json.loads(z.read('交付清单.json'));images=[(copy.deepcopy(row),z.read(row['path'])) for row in manifest['images']]
    manifest.pop('archive_layout',None)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for row,data in images:
            row['path']=PurePosixPath(row['path']).name;z.writestr(row['path'],data)
        manifest['images']=[row for row,_ in images];z.writestr('交付清单.json',json.dumps(manifest,ensure_ascii=False))
    legacy=copy.deepcopy(saved['packages'][0]);legacy.pop('archive_layout',None)
    legacy['fingerprint']=hashlib.sha256(json.dumps([(o['id'],o['sha256']) for o in saved['outputs']],sort_keys=True).encode()).hexdigest()
    legacy['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();service.runs[rid]['packages']=[legacy];service._save(service.runs[rid])
    before=path.read_bytes();calls=len(executor.jobs)
    package=service.package(rid)
    assert package['id']!=legacy['id'] and package['version']==2
    assert service.package_file(rid,legacy['id']).read_bytes()==before
    assert service.package(rid)['id']==package['id'] and len(executor.jobs)==calls
    with zipfile.ZipFile(service.package_file(rid,package['id'])) as z:
        rows=json.loads(z.read('交付清单.json'))['images']
        assert {PurePosixPath(row['path']).parts[0] for row in rows}=={'百度','步步高'}
        from local_app import workspace
        details=workspace.package_details(engine,service,'run',rid,package['id'])
        for i,row in enumerate(rows):
            data,mime=workspace.package_image(engine,service,'run',rid,package['id'],i)
            assert mime=='image/png' and hashlib.sha256(data).hexdigest()==details['images'][i]['sha256']==row['sha256']


def test_provider_mode_mismatch_cannot_be_approved(runtime,monkeypatch):
    service,executor,_=runtime;original=executor.generate_image
    def mismatched(job,event):
        return {**original(job,event),'simulated':False}
    monkeypatch.setattr(executor,'generate_image',mismatched)
    run=service.create(params(['learning-ruishi-rect-580x320']),idempotency_key='mismatched-mode-create')
    service.generate_baseline(run['id'],'mismatched-mode-baseline');failed=settled(service,run['id'])
    assert failed['status']=='failed' and failed['approval'] is None
    with pytest.raises(UserError):service.confirm_baseline(run['id'],1)


def test_two_runs_share_one_planner_and_keep_separate_image_owners(runtime,monkeypatch):
    service,executor,engine=runtime
    first=service.create(params(['learning-ruishi-rect-580x320']),idempotency_key='fair-first-create')
    second=service.create({**params(['learning-ruishi-rect-580x320']),'t1':'另一套文案'},idempotency_key='fair-second-create')
    first_started=threading.Event();both_submitted=threading.Event();release=threading.Event()
    counter_lock=threading.Lock();active=0;peak=0;submitted=0;owners=[]
    original_plan=executor.plan_scene;original_submit=engine.planning_pool.submit
    original_for=getattr(engine.pool,'submit_for',None);original_image_submit=engine.pool.submit
    def plan(run,event):
        nonlocal active,peak
        with counter_lock:active+=1;peak=max(peak,active)
        try:
            if run['id']==first['id']:
                first_started.set();assert release.wait(5)
            return original_plan(run,event)
        finally:
            with counter_lock:active-=1
    def planning_submit(function,*args,**kwargs):
        nonlocal submitted
        with counter_lock:
            submitted+=1
            if submitted==2:both_submitted.set()
        return original_submit(function,*args,**kwargs)
    def image_submit(owner,function,*args,**kwargs):
        owners.append(owner)
        return original_for(owner,function,*args,**kwargs) if original_for else original_image_submit(function,*args,**kwargs)
    monkeypatch.setattr(executor,'plan_scene',plan)
    monkeypatch.setattr(engine.planning_pool,'submit',planning_submit)
    monkeypatch.setattr(engine.pool,'submit_for',image_submit,raising=False)
    try:
        service.generate_baseline(first['id'],'fair-first-baseline');assert first_started.wait(3)
        service.generate_baseline(second['id'],'fair-second-baseline');assert both_submitted.wait(3)
        assert active==peak==1
    finally:release.set()
    assert settled(service,first['id'])['baseline']['status']=='done'
    assert settled(service,second['id'])['baseline']['status']=='done'
    assert peak==1
    assert sorted(owners)==sorted(['learning:'+first['id'],'learning:'+second['id']])


def test_local_exports_use_shared_processing_slots_without_holding_engine_lock(runtime,monkeypatch):
    from local_app import learning_output
    service,_,engine=runtime
    run=baseline(service,['learning-ruishi-rect-580x320']);rid=run['id'];service.confirm_baseline(rid,1)
    class Slots:
        entered=0
        def __enter__(self):self.entered+=1
        def __exit__(self,*args):self.entered-=1
    slots=Slots();observed=[];original=learning_output.export_output
    def export(*args,**kwargs):
        assert slots.entered==1
        acquired=threading.Event()
        def read_status():
            with engine.lock:acquired.set()
        reader=threading.Thread(target=read_status);reader.start()
        assert acquired.wait(2),'image processing held the global state lock'
        reader.join();observed.append(True)
        return original(*args,**kwargs)
    monkeypatch.setattr(engine,'processing_slots',slots,raising=False)
    monkeypatch.setattr(learning_output,'export_output',export)
    service.expand_suite(rid,'shared-export-slots');run=settled(service,rid)
    assert run['status']=='completed' and observed==[True] and slots.entered==0


def test_unchanged_revision_skips_full_public_record_assembly(runtime,monkeypatch):
    service,_,engine=runtime
    run=service.create(params(['learning-ruishi-rect-580x320']),idempotency_key='revision-fast-create')
    def forbidden(*args,**kwargs):raise AssertionError('full run assembly was invoked')
    monkeypatch.setattr(service,'_public',forbidden)
    loads=iter([{'running':1},{'running':2}]);monkeypatch.setattr(engine,'queue_status',lambda:next(loads))
    first=service.get(run['id'],revision=run['revision']);second=service.get(run['id'],revision=run['revision'])
    assert first['unchanged'] is True and first['id']==run['id'] and first['revision']==run['revision']
    assert first['queue']['running']==1 and second['queue']['running']==2
    assert not any(key in first for key in ('masters','outputs','baseline','params'))
    with pytest.raises(AssertionError):service.get(run['id'],revision=run['revision']-1)


def test_active_run_cap_rejects_without_consuming_key_or_starting_work(runtime,monkeypatch):
    from local_app import learning_runtime
    service,executor,_=runtime
    monkeypatch.setattr(learning_runtime,'MAX_ACTIVE_RUNS',1)
    first=service.create(params(['learning-ruishi-rect-580x320']),idempotency_key='cap-first-create')
    second=service.create(params(['learning-ruishi-rect-580x320']),idempotency_key='cap-second-create')
    started=threading.Event();release=threading.Event();original=executor.plan_scene
    def plan(run,event):
        if run['id']==first['id']:started.set();assert release.wait(5)
        return original(run,event)
    monkeypatch.setattr(executor,'plan_scene',plan)
    try:
        service.generate_baseline(first['id'],'cap-first-baseline');assert started.wait(3)
        before=copy.deepcopy(service.runs[second['id']])
        with pytest.raises(UserError) as blocked:
            service.generate_baseline(second['id'],'cap-retry-same-key')
        assert blocked.value.status==429 and service.runs[second['id']]==before
        assert len(service._threads)==1 and not executor.jobs
    finally:release.set()
    settled(service,first['id'])
    service.generate_baseline(second['id'],'cap-retry-same-key')
    assert settled(service,second['id'])['baseline']['status']=='done'


def test_image_hash_validation_does_not_hold_global_state_lock(runtime,monkeypatch):
    from local_app import learning_runtime
    service,_,engine=runtime
    run=baseline(service,['learning-ruishi-rect-580x320']);rid=run['id']
    source=service.image(rid,'baseline','baseline',1)
    checking=threading.Event();release=threading.Event();original=learning_runtime._digest;result=[]
    def digest(path):
        if Path(path)==source:
            checking.set();assert release.wait(3)
        return original(path)
    monkeypatch.setattr(learning_runtime,'_digest',digest)
    reader=threading.Thread(target=lambda:result.append(service.image(rid,'baseline','baseline',1)))
    reader.start()
    try:
        assert checking.wait(2)
        assert engine.lock.acquire(timeout=1),'image hash blocked unrelated status updates'
        engine.lock.release()
    finally:release.set();reader.join(5)
    assert result==[source] and not reader.is_alive()


def test_from_confirmed_baseline_recompiles_without_new_baseline_or_source_changes(runtime,monkeypatch):
    from local_app import learning_pipeline
    service,executor,engine=runtime
    source=baseline(service,['learning-ruishi-rect-580x320']);source_id=source['id'];service.confirm_baseline(source_id,1)
    service.expand_suite(source_id,'source-reuse-suite');settled(service,source_id)
    old_package=service.package(source_id);old_zip=service.package_file(source_id,old_package['id']).read_bytes()
    original=copy.deepcopy(engine.document(PREFIX+source_id));image_calls=len(executor.jobs)
    def no_random(*args,**kwargs):raise AssertionError('confirmed visual must not be sampled again')
    monkeypatch.setattr(learning_pipeline.random,'Random',no_random)
    from local_app.learning_pipeline import CONTENT_BY_ID
    rebuilt=service.create_from_confirmed_baseline(source_id,'rebuild-from-baseline',pids=list(CONTENT_BY_ID))
    assert len(executor.jobs)==image_calls
    assert rebuilt['status']=='baseline_confirmed' and rebuilt['baseline']['inherited']
    assert rebuilt['baseline']['sha256']==source['baseline']['sha256']
    assert rebuilt['approval']['inherited_from']['run_id']==source_id
    assert rebuilt['counts']['baseline_reused'] and rebuilt['counts']['expected_new_calls']==26
    assert rebuilt['visual_config']==source['visual_config']
    assert rebuilt['name'].endswith(' · 重新构图') and rebuilt['params']['t1']==source['params']['t1']
    assert all(not master['reuse_baseline'] for master in rebuilt['masters'])
    assert service.create_from_confirmed_baseline(source_id,'rebuild-from-baseline',pids=list(CONTENT_BY_ID))['id']==rebuilt['id']
    assert len(service.list())==2
    service.expand_suite(rebuilt['id'],'rebuild-normal-expand');done=settled(service,rebuilt['id'])
    assert done['status']=='completed',done.get('error')
    assert len(executor.jobs)==image_calls+26
    assert sum(job['kind']=='master' for job in executor.jobs[image_calls:])==16
    assert sum(job['kind']=='background_expansion' for job in executor.jobs[image_calls:])==10
    assert done['counts']['completed_outputs']==45
    assert engine.document(PREFIX+source_id)==original
    assert service.package_file(source_id,old_package['id']).read_bytes()==old_zip


def test_from_confirmed_baseline_rejects_unapproved_tampered_or_changed_request(runtime):
    service,executor,_=runtime
    source=baseline(service,['learning-ruishi-rect-580x320']);rid=source['id']
    with pytest.raises(UserError,match='确认'):service.create_from_confirmed_baseline(rid,'unapproved-base-copy')
    service.confirm_baseline(rid,1)
    child=service.create_from_confirmed_baseline(rid,'approved-base-copy')
    with pytest.raises(UserError,match='改变'):
        service.create_from_confirmed_baseline(rid,'approved-base-copy',pids=['learning-baidu-512x512'])
    assert len(service.list())==2 and len(executor.jobs)==1
    service.image(rid,'baseline','baseline',1).write_bytes(b'tampered source')
    with pytest.raises(UserError,match='校验'):service.create_from_confirmed_baseline(rid,'tampered-base-copy')
    assert len(service.list())==2 and service.image(child['id'],'baseline','baseline',1).is_file()


def test_from_confirmed_baseline_checks_source_again_after_copy_and_future_reroll_is_normal(runtime,monkeypatch):
    from local_app import learning_runtime_support
    service,executor,_=runtime
    source=baseline(service,['learning-ruishi-rect-580x320']);rid=source['id'];service.confirm_baseline(rid,1)
    original=learning_runtime_support.freeze_run
    def changed_source(*args,**kwargs):
        result=original(*args,**kwargs)
        if kwargs.get('confirmed_source'):service.confirm_baseline(rid,1)
        return result
    monkeypatch.setattr(learning_runtime_support,'freeze_run',changed_source)
    with pytest.raises(UserError,match='已变化'):service.create_from_confirmed_baseline(rid,'source-revision-race')
    assert len(service.list())==1
    monkeypatch.setattr(learning_runtime_support,'freeze_run',original)
    child=service.create_from_confirmed_baseline(rid,'after-revision-race')
    assert child['counts']['baseline_reused'] and child['counts']['expected_new_calls']==1
    calls=len(executor.jobs)
    service.generate_baseline(child['id'],'reroll-inherited-baseline');fresh=settled(service,child['id'])
    assert fresh['baseline']['version']==2 and fresh['approval'] is None
    assert not fresh['counts']['baseline_reused'] and fresh['baseline_source'] is None
    assert len(executor.jobs)==calls+1 and executor.jobs[-1]['kind']=='baseline'


def test_from_confirmed_baseline_concurrent_key_cannot_mix_identical_pixels_from_two_sources(runtime,monkeypatch):
    from local_app import learning_runtime_support
    service,executor,_=runtime
    first=baseline(service,['learning-ruishi-rect-580x320']);service.confirm_baseline(first['id'],1)
    second=service.create_from_confirmed_baseline(first['id'],'same-pixels-second-source')
    assert first['baseline']['sha256']==second['baseline']['sha256']
    original=learning_runtime_support.freeze_run;barrier=threading.Barrier(2);results=[]
    def freeze(*args,**kwargs):
        barrier.wait(timeout=5)
        return original(*args,**kwargs)
    monkeypatch.setattr(learning_runtime_support,'freeze_run',freeze)
    def copy_source(rid):
        try:results.append(service.create_from_confirmed_baseline(rid,'cross-source-concurrent-key'))
        except UserError as error:results.append(error)
    threads=[threading.Thread(target=copy_source,args=(run['id'],)) for run in (first,second)]
    for thread in threads:thread.start()
    for thread in threads:thread.join(10)
    assert all(not thread.is_alive() for thread in threads)
    assert len(results)==2 and sum(isinstance(row,UserError) and row.status==409 for row in results)==1
    assert len(service.list())==3 and len(executor.jobs)==1


def test_logo_refresh_and_export_switch_only_use_local_layers_and_keep_versions(runtime,monkeypatch):
    from local_app import learning_logo
    service,executor,engine=runtime
    yes='learning-baidu-1200x400';no='learning-bbg-no-logo-banner-1280x362'
    run=baseline(service,[yes,no]);rid=run['id'];service.confirm_baseline(rid,1)
    service.expand_suite(rid,'logo-layers-expand');run=settled(service,rid)
    before=copy.deepcopy(run);calls=len(executor.jobs)
    original_package=service.package(rid);old_zip=service.package_file(rid,original_package['id']).read_bytes()
    old_image=service.image(rid,'output',yes+'::1',1).read_bytes()
    config=learning_logo.config(engine.settings)
    learning_logo.save_templates(engine.settings,{'revision':config['revision'],'templates':[
        dict(placement_id=yes,asset_id='learning.logo.black',x=.01,y=.02,width=.125)]})
    service.refresh_logos(rid,'logo-refresh-once',[yes]);changed=settled(service,rid)
    current=next(o for o in changed['outputs'] if o['placement_id']==yes)
    assert current['version']==2 and current['versions'][0]['version']==1
    assert current['logo_template']==dict(asset_id='learning.logo.black',x=.01,y=.02,width=.125)
    assert current['prompt']==next(o for o in before['outputs'] if o['placement_id']==yes)['prompt']
    assert changed['masters']==before['masters'] and len(executor.jobs)==calls
    assert service.image(rid,'output',yes+'::1',1).read_bytes()==old_image
    assert service.package_file(rid,original_package['id']).read_bytes()==old_zip
    service.refresh_logos(rid,'logo-refresh-once',[yes]);assert settled(service,rid)['outputs']==changed['outputs']
    white=service.package(rid,logo_asset_id='learning.logo.white-app')
    black=service.package(rid,logo_asset_id='learning.logo.black')
    assert white['id']!=black['id']
    assert service.package(rid,logo_asset_id='learning.logo.white-app')['id']==white['id']
    with zipfile.ZipFile(service.package_file(rid,white['id'])) as wz,zipfile.ZipFile(service.package_file(rid,black['id'])) as bz:
        wm=json.loads(wz.read('交付清单.json'))
        bm=json.loads(bz.read('交付清单.json'))
        white_paths={o['placement_id']:o['path'] for o in wm['images']}
        black_paths={o['placement_id']:o['path'] for o in bm['images']}
        assert wm['logo_asset_id']=='learning.logo.white-app'
        assert next(o for o in wm['images'] if o['placement_id']==no)['logo_asset_id'] is None
        assert wz.read(white_paths[no])==bz.read(black_paths[no])
        assert wz.read(white_paths[yes])!=bz.read(black_paths[yes])
        from io import BytesIO
        with Image.open(BytesIO(wz.read(white_paths[yes]))) as image:assert image.size==(1200,400)
    assert len(executor.jobs)==calls and service.get(rid)['outputs']==changed['outputs']
    # A failed local layer refresh must remain recoverable without submitting
    # an image-model job or replacing the last successful pixels.
    config=learning_logo.config(engine.settings)
    learning_logo.save_templates(engine.settings,{'revision':config['revision'],'templates':[
        dict(placement_id=yes,asset_id='learning.logo.black',x=.01,y=.02,width=.13)]})
    from local_app import learning_output
    render=learning_output.export_output
    monkeypatch.setattr(learning_output,'export_output',lambda *a,**kw:(_ for _ in ()).throw(UserError('本机图层测试失败')))
    service.refresh_logos(rid,'logo-local-failure',[yes]);failed=settled(service,rid)
    failed_row=next(o for o in failed['outputs'] if o['placement_id']==yes)
    assert failed_row['status']=='failed' and failed_row['logo_refresh_pending'] is True
    monkeypatch.setattr(learning_output,'export_output',render)
    service.refresh_logos(rid,'logo-local-recovery',[yes]);recovered=settled(service,rid)
    assert recovered['status']=='completed' and len(executor.jobs)==calls
    assert next(o for o in recovered['outputs'] if o['placement_id']==yes)['logo_template']['width']==.13
