"""Background changes use application jobs and immutable output versions."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest
from PIL import Image

from local_app.config import UserError
from tests_local.test_learning_runtime import runtime,params,settled


def legacy_source(service,pids):
    """Represent an already frozen color-padding recipe from the previous release."""
    run=service.create(params(pids),idempotency_key='legacy-color-source-create');rid=run['id']
    stored=service.runs[rid]
    for mapping in stored['compiled']['outputs']:
        mapping['sizing_policy']='preserve_source';mapping['requires_image_model_call']=False
    stored['compiled']['counts']['background_image_calls']=0
    service.generate_baseline(rid,'legacy-color-source-baseline');settled(service,rid);service.confirm_baseline(rid,1)
    service.expand_suite(rid,'legacy-color-source-expand');completed=settled(service,rid)
    assert completed['status']=='completed',completed.get('error')
    assert all(row['processing']['padding_percent']>0 for row in completed['outputs'])
    return completed


def test_explicit_two_background_repairs_keep_prior_versions_and_master(runtime):
    service,executor,_=runtime
    source=legacy_source(service,['learning-youxuepai-logo-1400x340','learning-youxuepai-logo-1536x1708'])
    rid=source['id'];before=copy.deepcopy(source['masters']);files={o['id']:service.image(rid,'output',o['id'],1).read_bytes() for o in source['outputs']}
    calls=len(executor.jobs)
    service.repair_backgrounds(rid,'explicit-background-two',[o['id'] for o in source['outputs']])
    done=settled(service,rid)
    assert done['status']=='completed',done.get('error')
    assert len(executor.jobs)==calls+2 and all(j['kind']=='background_expansion' for j in executor.jobs[calls:])
    for job in executor.jobs[calls:]:
        assert [r['kind'] for r in job['reference_bindings']]==['adaptation_canvas','source_picture']
    assert done['masters']==before
    for row in done['outputs']:
        assert row['version']==2 and row['background_repair_pending'] is False
        assert service.image(rid,'output',row['id'],1).read_bytes()==files[row['id']]
        with Image.open(service.image(rid,'output',row['id'],2)) as image:assert image.size==(row['width'],row['height'])
        stored=next(o for o in service.runs[rid]['outputs'] if o['id']==row['id'])
        assert stored['export_crop_box']==[0,0,1,1]
        with Image.open(stored['raw_path']) as image:assert image.size==(row['width'],row['height'])
    service.repair_backgrounds(rid,'explicit-background-two',[o['id'] for o in source['outputs']])
    assert len(executor.jobs)==calls+2


def test_background_unknown_same_key_resumes_frozen_job_without_new_version(runtime):
    service,executor,_=runtime
    source=legacy_source(service,['learning-youxuepai-logo-1400x340']);rid=source['id'];oid=source['outputs'][0]['id']
    executor.fail_one='background_expansion';service.repair_backgrounds(rid,'same-background-recovery',[oid])
    failed=settled(service,rid);assert failed['outputs'][0]['query_required'] and failed['outputs'][0]['background_repair_pending']
    frozen=copy.deepcopy(executor.jobs[-1]);guide=Path(frozen['reference_bindings'][0]['path']).read_bytes()
    with pytest.raises(UserError,match='背景'):service.regenerate_output(rid,oid,'forbidden-normal-redraw')
    service.repair_backgrounds(rid,'same-background-recovery',[oid]);done=settled(service,rid)
    assert done['status']=='completed',done.get('error')
    assert done['outputs'][0]['version']==2
    assert executor.jobs[-1]==frozen and Path(frozen['reference_bindings'][0]['path']).read_bytes()==guide
    operation=next(iter(service.runs[rid]['background_operations'].values()))
    assert operation['status']=='done' and not operation.get('query_required') and not operation.get('error')


def test_local_microcrop_recovery_same_key_has_no_image_model_call(runtime,monkeypatch):
    from local_app import learning_output
    service,executor,_=runtime
    source=legacy_source(service,['learning-xiaoyuan-1372x480']);rid=source['id'];calls=len(executor.jobs)
    original=learning_output.export_output;fail=[True]
    def once(*args,**kwargs):
        if fail.pop() if fail else False:raise UserError('本机导出暂时失败')
        return original(*args,**kwargs)
    monkeypatch.setattr(learning_output,'export_output',once)
    service.repair_backgrounds(rid,'same-local-repair');failed=settled(service,rid)
    assert failed['outputs'][0]['background_repair_pending'] and failed['outputs'][0]['version']==2
    assert failed['outputs'][0]['recovery_action']=='retry_export'
    service.repair_backgrounds(rid,'same-local-repair');done=settled(service,rid)
    assert done['status']=='completed' and done['outputs'][0]['version']==2
    assert len(executor.jobs)==calls and done['outputs'][0]['processing']['padding_percent']==0


def test_normal_expand_automatically_shares_one_natural_extension_for_logo_variants(runtime):
    service,executor,_=runtime
    run=service.create(params(['learning-bbg-logo-banner-1280x362','learning-bbg-no-logo-banner-1280x362']),idempotency_key='auto-natural-create')
    rid=run['id'];service.generate_baseline(rid,'auto-natural-baseline');settled(service,rid);service.confirm_baseline(rid,1)
    service.expand_suite(rid,'auto-natural-expand');done=settled(service,rid)
    assert done['status']=='completed',done.get('error')
    assert [job['kind'] for job in executor.jobs]==['baseline','master','background_expansion']
    assert len(service.runs[rid]['background_operations'])==1
    raw_shas={row['raw_sha256'] for row in service.runs[rid]['outputs']}
    assert len(raw_shas)==1
    for output in done['outputs']:
        assert output['processing']['padding_percent']==0
        assert output['processing']['method']=='ai_background_expansion_then_exact_export'
        assert not output.get('background_repair_key') and not output['background_repair_pending']


def test_preparation_failure_same_key_retries_the_same_output_version(runtime,monkeypatch):
    from local_app import learning_background
    service,executor,_=runtime
    run=legacy_source(service,['learning-youxuepai-logo-1400x340']);rid=run['id'];calls=len(executor.jobs)
    original=learning_background.prepare_job;failure=[True]
    def once(*args,**kwargs):
        if failure.pop() if failure else False:raise UserError('准备参考图暂时失败')
        return original(*args,**kwargs)
    monkeypatch.setattr(learning_background,'prepare_job',once)
    service.repair_backgrounds(rid,'prepare-background-retry');failed=settled(service,rid)
    assert failed['outputs'][0]['version']==2 and failed['outputs'][0]['background_repair_pending']
    assert len(executor.jobs)==calls
    service.repair_backgrounds(rid,'prepare-background-retry');done=settled(service,rid)
    assert done['status']=='completed' and done['outputs'][0]['version']==2 and len(executor.jobs)==calls+1


def test_same_key_recovers_only_pending_outputs_not_already_successful_versions(runtime):
    service,executor,_=runtime
    source=legacy_source(service,['learning-youxuepai-logo-1400x340','learning-youxuepai-logo-1536x1708']);rid=source['id']
    executor.fail_one='background_expansion';service.repair_backgrounds(rid,'mixed-background-retry')
    failed=settled(service,rid);successful=next(row for row in failed['outputs'] if row['status']=='done')
    before=copy.deepcopy(successful);calls=len(executor.jobs)
    service.repair_backgrounds(rid,'mixed-background-retry');done=settled(service,rid)
    assert done['status']=='completed' and len(executor.jobs)==calls+1
    assert next(row for row in done['outputs'] if row['id']==before['id'])==before
    assert all(row['version']==2 for row in done['outputs'])


def test_upgraded_output_redraw_keeps_natural_policy_and_runs_background_after_new_master(runtime,monkeypatch):
    service,executor,_=runtime
    source=legacy_source(service,['learning-youxuepai-logo-1400x340']);rid=source['id'];oid=source['outputs'][0]['id']
    service.repair_backgrounds(rid,'upgrade-natural-output');settled(service,rid)
    original=executor.generate_image
    def new_pixels(job,event):
        if job['kind']!='single':return original(job,event)
        executor.jobs.append(copy.deepcopy(job));output=Path(job['output']);output.parent.mkdir(parents=True,exist_ok=True)
        a,b=map(int,job['aspect_ratio'].split(':'));Image.new('RGB',(a*128,b*128),'#135724').save(output)
        return {'source':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'simulated':True}
    monkeypatch.setattr(executor,'generate_image',new_pixels)
    calls=len(executor.jobs);service.regenerate_output(rid,oid,'redraw-upgraded-output');done=settled(service,rid)
    assert done['status']=='completed',done.get('error')
    assert [job['kind'] for job in executor.jobs[calls:]]==['single','background_expansion']
    assert done['outputs'][0]['processing']['padding_percent']==0
    assert done['outputs'][0]['processing']['method']=='ai_background_expansion_then_exact_export'


def test_receipt_without_native_png_is_rehomed_during_restore(runtime,tmp_path):
    from local_app.learning_runtime_support import prepare_restored_run
    from render import task_state_path
    service,executor,_=runtime
    source=legacy_source(service,['learning-youxuepai-logo-1400x340']);rid=source['id']
    executor.fail_one='background_expansion';service.repair_backgrounds(rid,'restore-native-pending');settled(service,rid)
    saved=copy.deepcopy(service.runs[rid]);operation=next(iter(saved['background_operations'].values()))
    root=tmp_path/'restored-workspace';archive=root/'.restored'/'checked';archive.mkdir(parents=True)
    for asset_id,record in saved['logo_snapshot']['assets'].items():
        target=archive/(asset_id+'.png');shutil.copyfile(record['path'],target);record['path']=str(target)
    receipt=archive/'pending.receipt.json';receipt.write_text(json.dumps({'task_id':'already-paid-task','status':'success'}))
    operation['receipt_path']=str(receipt);operation['job']['output']='/old-machine/missing/native.png'
    restored=prepare_restored_run(SimpleNamespace(settings=SimpleNamespace(output=root)),saved)
    recovered=next(iter(restored['background_operations'].values()));native=Path(recovered['job']['output'])
    assert native.is_relative_to(root/'.cache') and not native.exists()
    assert json.loads(task_state_path(native).read_text())['task_id']=='already-paid-task'
    assert receipt.is_file() and recovered['receipt_path']==str(task_state_path(native))


def test_retired_background_request_is_rejected_before_dispatch(runtime):
    service,executor,_=runtime
    source=legacy_source(service,['learning-youxuepai-logo-1400x340']);rid=source['id'];run=service.runs[rid];row=run['outputs'][0]
    row.update(status='failed',background_repair_pending=True,background_request={'kind':'ai','operation_id':'retired-op'})
    run['background_operations']={'retired-op':{'status':'failed','job':{'background_plan':{'version':2}}}}
    before=len(executor.jobs)
    with pytest.raises(UserError,match='停用'):service.repair_backgrounds(rid,'retired-flow-rejection',[row['id']])
    assert len(executor.jobs)==before and not run['busy']
    assert service.get(rid)['outputs'][0]['recovery_action']=='retired_flow'
