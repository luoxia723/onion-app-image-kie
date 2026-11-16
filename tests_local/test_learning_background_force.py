"""An explicit retry creates a fresh AI operation while keeping its visual source."""
from tests_local.test_learning_runtime import runtime,settled
from tests_local.test_learning_background_runtime import legacy_source


def test_force_background_retry_uses_original_picture_new_operation_and_same_key_noop(runtime):
    service,executor,_=runtime
    before=legacy_source(service,['learning-youxuepai-logo-1400x340']);rid=before['id'];oid=before['outputs'][0]['id']
    original_sha=next(o for o in service.runs[rid]['outputs'] if o['id']==oid)['raw_sha256']
    service.repair_backgrounds(rid,'first-natural-operation',[oid]);first=settled(service,rid)
    assert first['status']=='completed'
    calls=len(executor.jobs);previous_path=executor.jobs[-1]['output']
    for index in (1,2):
        key='force-natural-retry-'+str(index)
        service.repair_backgrounds(rid,key,[oid],force_ai=True);done=settled(service,rid)
        assert done['status']=='completed',done.get('error')
        job=executor.jobs[-1]
        assert len(executor.jobs)==calls+index
        assert job['reference_bindings'][1]['sha256']==original_sha
        assert job['output']!=previous_path
        previous_path=job['output'];version=done['outputs'][0]['version']
        service.repair_backgrounds(rid,key,[oid],force_ai=True)
        assert service.get(rid)['outputs'][0]['version']==version
        assert len(executor.jobs)==calls+index
