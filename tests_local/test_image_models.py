import json
from pathlib import Path
import pytest
from local_app.config import Settings,UserError,IMAGE_MODELS,DEFAULT_IMAGE_MODEL
from local_app.planning import BY_ID
from kie_model import MODEL,GPT_IMAGE_2,GPT_IMAGE_26_FLARE,MODELS,nearest_aspect_ratio,geometry_report
import render
from tests_local.test_workbench import engine,params,wait_done


def test_model_setting_persists_and_rejects_unknown(tmp_path):
    s=Settings(tmp_path/'state',tmp_path/'.env')
    assert s.image_model==DEFAULT_IMAGE_MODEL==GPT_IMAGE_26_FLARE
    s.update({'image_model':GPT_IMAGE_2})
    assert Settings(tmp_path/'state',tmp_path/'.env').image_model==GPT_IMAGE_2
    assert s.public()['image_resolution']=='1K' and IMAGE_MODELS==MODELS
    with pytest.raises(UserError):s.update({'image_model':'other-model'})


@pytest.mark.parametrize('model',[MODEL,GPT_IMAGE_2,GPT_IMAGE_26_FLARE])
def test_exact_request_model_resolution_and_parameters(model):
    req=render.build_create_request('https://example.invalid','test','标题','16:9','1K',['https://example.invalid/ref'],model=model)
    body=json.loads(req.data)
    assert body['model']==model and body['input']['resolution']=='1K'
    assert ('background' in body['input'])==(model!=GPT_IMAGE_2)
    if model == GPT_IMAGE_26_FLARE:
        assert body['model'] == 'gpt-image-2-6/flare-image-to-image'
        assert 'output_format' not in body['input']
        assert body['input']['background'] == 'opaque'
        assert nearest_aspect_ratio(720, 1559, model) == '9:21'
    with pytest.raises(ValueError):render.build_create_request('https://example.invalid','test','标题','16:9','2K',['https://example.invalid/ref'],model=model)


def test_model_specific_natural_geometry_contract(tmp_path):
    assert geometry_report(474,768,model=GPT_IMAGE_2)['needs_safe_area']
    assert not geometry_report(474,768,model=MODEL)['needs_safe_area']
    assert geometry_report(474,768,model=GPT_IMAGE_2)['adaptation_mode']=='natural_canvas'
    with pytest.raises(ValueError):render.build_create_request('https://example.invalid','test','标题','16:27','1K',['https://example.invalid/ref'],model=GPT_IMAGE_2)


def test_round_model_is_frozen_and_switch_creates_new_round(engine):
    e=engine;p=params(True,1);tid=e.create(p,'model-freeze-1')['id'];t=wait_done(e,tid);old=t['rounds'][0]
    e.settings.update({'image_model':GPT_IMAGE_2})
    e.mutate(tid,'regenerate',{'image_id':old['slots'][1]['id']});wait_done(e,tid)
    job=json.loads(Path(old['slots'][1]['output']).with_suffix('.job.json').read_text())
    assert job['image_model']==GPT_IMAGE_26_FLARE
    new=e.create(p,'model-freeze-2',tid);t=wait_done(e,tid)
    assert len(t['rounds'])==2 and t['rounds'][1]['image_model']==GPT_IMAGE_2
    for slot in t['rounds'][1]['slots']:
        job=json.loads(Path(slot['output']).with_suffix('.job.json').read_text())
        assert job['image_model']==GPT_IMAGE_2


def test_real_submission_adapter_uses_selected_model(tmp_path,monkeypatch):
    from types import SimpleNamespace
    ref=next((Path(__file__).parents[1]/'assets/font-references').glob('*.png'))
    sent=[]
    monkeypatch.setattr(render,'upload_references',lambda *a,**kw:['https://example.invalid/ref'])
    def request(req,*a,**kw):
        if req.method=='POST':
            sent.append(json.loads(req.data));return {'data':{'taskId':'gpt2-test-task'}}
        return {'data':{'state':'success','resultJson':json.dumps({'resultUrls':['https://example.invalid/result']})}}
    monkeypatch.setattr(render,'request_json',request)
    args=SimpleNamespace(image_model=GPT_IMAGE_2,retries=1,poll_timeout=240,max_timeout_restarts=0)
    url,state=render.obtain_result(args,'https://example.invalid','https://example.invalid','test','标题',[ref],'frozen-fingerprint',tmp_path/'state.json',{},'16:9','1K')
    assert sent[0]['model']==GPT_IMAGE_2 and state['model']==GPT_IMAGE_2
    assert sent[0]['input']['resolution']=='1K' and 'background' not in sent[0]['input']
    assert len(sent)==1


def test_injected_transport_reaches_create_and_poll(tmp_path):
    from types import SimpleNamespace
    calls=[]
    def transport(req,*args,**kwargs):
        calls.append(req.method)
        if req.method=='POST':return {'data':{'taskId':'created-test'}}
        return {'data':{'state':'success','resultJson':json.dumps({'resultUrls':['https://example.invalid/result.png']})}}
    def upload(*args,**kwargs):return ['https://example.invalid/ref.png']
    args=SimpleNamespace(image_model=MODEL,retries=1,poll_timeout=240,max_timeout_restarts=0)
    url,state=render.obtain_result(args,'https://example.invalid','https://example.invalid','fake','prompt',[],
        'test-fingerprint',tmp_path/'state.json',{},'16:9','1K',request_fn=transport,upload_fn=upload)
    assert calls==['POST','GET'] and state['task_id']=='created-test' and url.endswith('result.png')
