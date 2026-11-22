"""The normal HTTP action upgrades rules without generating another baseline."""
from collections import Counter
from hashlib import sha256
from io import BytesIO
import time

from PIL import Image

from local_app.learning_executor import LearningExecutor
from tests_local.test_learning_setup_api import api


def test_from_confirmed_baseline_http_action_is_explicit_and_idempotent(api,monkeypatch):
    _,request=api;calls=[];original=LearningExecutor.generate_image
    def generate(self,job,event):
        calls.append(job['kind']);assert job['simulation'] is True
        if job['kind']=='background_expansion':
            assert '减少远景重复纹样' in job['prompt']
            assert '材质与细节密度' not in job['prompt']
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
    sizes={'learning-dsl-rounded-card-484x580':(484,580),
           'learning-dsl-resource-1280x348':(1280,348)}
    body={'idempotency_key':'api-copy-confirmed-source','pids':list(sizes)}
    code,child=request(base+'/from-baseline','POST',body)
    assert code==200 and child['id']!=rid and child['status']=='baseline_confirmed'
    assert child['counts']['baseline_reused'] and child['counts']['expected_new_calls']==3
    assert child['baseline']['sha256']==source['baseline']['sha256']
    assert child['baseline_source']['run_id']==rid and calls==['baseline']
    assert {row['placement_id'] for row in child['outputs']}==set(sizes)
    assert all('减少远景重复纹样' in master['prompt'] for master in child['masters'])
    assert request(base+'/from-baseline','POST',body)[1]['id']==child['id']
    assert request(base)[1]['revision']==old_revision
    newbase='/api/learning-machine/runs/'+child['id']
    assert request(newbase+'/expand','POST',{'idempotency_key':'api-copy-normal-expand'})[0]==200
    completed=wait(newbase)
    assert completed['status']=='completed'
    expected_calls={'baseline':1,'master':2,'background_expansion':1}
    assert Counter(calls)==expected_calls
    for row in completed['outputs']:
        assert row['main_copy_required'] and row['logo_required'] and not row['cta_required']
        status, data = request(row['image_url'])
        assert status==200 and len(data)<100*1024 and sha256(data).hexdigest()==row['sha256']
        with Image.open(BytesIO(data)) as image:
            assert image.size==sizes[row['placement_id']] and image.format=='PNG'
            if image.size==(484,580):
                alpha=image.convert('RGBA').getchannel('A')
                assert alpha.getpixel((0,0))==0 and alpha.getpixel((242,290))==255
    assert request(newbase+'/expand','POST',{'idempotency_key':'api-copy-normal-expand'})[1]['status']=='completed'
    assert Counter(calls)==expected_calls
