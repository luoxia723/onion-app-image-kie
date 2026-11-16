"""The normal HTTP action upgrades rules without generating another baseline."""
import time

from local_app.learning_executor import LearningExecutor
from tests_local.test_learning_setup_api import api


def test_from_confirmed_baseline_http_action_is_explicit_and_idempotent(api,monkeypatch):
    _,request=api;calls=[];original=LearningExecutor.generate_image
    def generate(self,job,event):
        calls.append(job['kind']);assert job['simulation'] is True
        return original(self,job,event)
    monkeypatch.setattr(LearningExecutor,'generate_image',generate)
    params={'channel':'学习机','t1':'不会的题拍一下','ip':'none','font':'none','pids':['learning-ruishi-rect-580x320']}
    code,source=request('/api/learning-machine/runs','POST',{'params':params,'idempotency_key':'api-source-create'})
    assert code==200;rid=source['id'];base='/api/learning-machine/runs/'+rid
    assert request(base+'/from-baseline','POST',{'idempotency_key':'api-copy-before-confirm'})[0]==409
    assert request(base+'/baseline','POST',{'idempotency_key':'api-source-baseline'})[0]==200
    def wait(path):
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            code,run=request(path)
            assert code==200
            if not run['busy']:return run
            time.sleep(.01)
        raise AssertionError('HTTP run did not settle')
    source=wait(base);assert source['baseline']['status']=='done'
    assert request(base+'/confirm','POST',{'baseline_version':1})[0]==200
    old_revision=request(base)[1]['revision'];assert calls==['baseline']
    body={'idempotency_key':'api-copy-confirmed-source'}
    code,child=request(base+'/from-baseline','POST',body)
    assert code==200 and child['id']!=rid and child['status']=='baseline_confirmed'
    assert child['counts']['baseline_reused'] and child['counts']['expected_new_calls']==1
    assert child['baseline_source']['run_id']==rid and calls==['baseline']
    assert request(base+'/from-baseline','POST',body)[1]['id']==child['id']
    assert request(base)[1]['revision']==old_revision
    newbase='/api/learning-machine/runs/'+child['id']
    assert request(newbase+'/expand','POST',{'idempotency_key':'api-copy-normal-expand'})[0]==200
    completed=wait(newbase)
    assert completed['status']=='completed' and calls==['baseline','master']
    assert completed['outputs'][0]['image_url']
