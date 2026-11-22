import copy
import hashlib
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import threading
import urllib.error
import urllib.request

import pytest
from PIL import Image

from local_app.config import Settings, UserError
from local_app.engine import Engine
from local_app.learning_executor import LearningExecutor
from local_app.learning_setup import CONFIGURATION_DOCUMENT, public_config
from local_app.learning_sizing import export_exact, plan
from local_app.server import Handler
from tests_local.fakes import FixturePlanner


@pytest.fixture
def api(tmp_path, monkeypatch):
    settings=Settings(tmp_path/'state',tmp_path/'test.env')
    settings.update({'simulation':True,'output_dir':str(tmp_path)})
    engine=Engine(settings,start=False,planner=FixturePlanner())
    def forbidden(*args,**kwargs):raise AssertionError('configuration must not invoke a provider')
    monkeypatch.setattr(engine.planner,'plan',forbidden)
    from local_app.scene_planner import ApiScenePlanner
    monkeypatch.setattr(ApiScenePlanner,'_request',forbidden)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.engine=engine
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    def request(path,method='GET',body=None):
        data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None
        req=urllib.request.Request(base+path,data=data,method=method,
            headers={'Content-Type':'application/json','X-Onion-Request':'1'})
        try:response=urllib.request.urlopen(req,timeout=5)
        except urllib.error.HTTPError as error:response=error
        with response:
            content=response.read();mime=response.headers.get('Content-Type','')
            return response.status,json.loads(content) if mime.startswith('application/json') else content
    yield engine,request
    server.shutdown();server.server_close();thread.join(5);engine.close()


class FixtureLearningExecutor(LearningExecutor):
    """Use local fixture pixels at the provider boundary of a real-mode run."""
    def plan_scene(self,run,stop_event):
        return super().plan_scene({**run,'mode':'simulation'},stop_event)

    def generate_image(self,job,stop_event):
        result=super().generate_image({**job,'simulation':True},stop_event)
        return {**result,'simulated':False}

    def inspect_typography(self,path,allowed,independent,reference,stop_event,*,removed_module=None):
        return dict(verdict='pass',body=allowed.get('t1',''),cta=allowed.get('cta',''),
                    issues=[],model='test-fixture',text_matches=True)


@pytest.fixture
def production_learning_api(api):
    from local_app.learning_runtime import LearningRuntime
    engine,_=api
    engine.settings.key='test-only-image'
    engine.settings.planning_key='test-only-planning'
    engine.learning_runtime=LearningRuntime(engine,FixtureLearningExecutor(engine.settings))
    return api


def test_config_assets_and_only_one_pipeline_are_available_without_keys(api):
    engine,request=api;status,cfg=request('/api/learning-machine/config')
    assert status==200 and cfg['pipeline']=='baseline_then_suite'
    assert len(cfg['placements'])==44 and sum(p['image_count'] for p in cfg['placements'])==45
    assert sum(p['logo_required'] for p in cfg['placements'])==35
    assert sum(p['cta_required'] for p in cfg['placements'])==14
    assert cfg['execution']['enabled'] is False and not engine.tasks
    assert cfg['offline_prompt_preview_ready'] is True
    assert cfg['runtime_modes']==['real'] and cfg['default_runtime_mode']=='real'
    assert len(cfg['master_groups'])==16
    assert len(cfg['mask_presets'])==1
    assert sum(p['mask_template']['enabled'] for p in cfg['placements'])==1
    assert len(cfg['logo_assets'])==2
    for asset in cfg['logo_assets']:
        status,data=request(asset['url']);assert status==200
        with Image.open(BytesIO(data)) as image:
            assert image.format=='PNG' and image.mode=='RGBA'
            assert image.getchannel('A').getextrema()==(0,255)
    assert request('/js/learning-machine.js')[0]==200


def test_preview_saves_frozen_config_but_never_creates_or_generates_a_task(api):
    engine,request=api
    params={'channel':'学习机','t1':'不会的题拍一下','cta':'立即点击下载','ip':'full_random','style':'random','font':'none',
            'sets':9,'noLogo':True,'cta_enabled':False,'cta_overrides':{}}
    status,result=request('/api/learning-machine/preview','POST',{'params':params})
    assert status==200 and result['saved'] is True
    assert result['baseline']['is_delivery'] is False and result['baseline']['logo'] is False
    assert result['output_count']==45 and result['total_image_count']==46
    assert len(result['placements'])==44 and result['params']['sets']==1
    assert result['baseline']['needs_user_confirmation'] is True
    assert result['baseline']['has_image'] is False
    assert result['confirmation']['confirmed'] is False
    assert result['confirmation']['can_confirm'] is False
    assert result['suite']['can_expand'] is False
    assert result['master_count']==16 and result['planned_image_calls']==26
    assert result['prompt_plan']['counts']['image_model_master_calls']==15
    assert result['prompt_plan']['counts']['baseline_reused_master_count']==1
    assert all(not o['content_modules']['feature_label'] and not o['content_modules']['badge'] for o in result['outputs'])
    assert result['prompt_plan']['counts']['delivery_count']==45
    assert all(o['depends_on']==[result['baseline']['id'],result['confirmation']['id'],o['master_id']] for o in result['outputs'])
    assert result['prompt_plan']['counts']['background_image_calls']==10
    assert result['suite']['planned_image_calls_after_confirmation']==25
    assert all(o['requires_image_model_call']==(o['processing_kind']=='natural_background_then_export') for o in result['outputs'])
    assert next(o for o in result['outputs'] if o['placement_id']=='learning-youxuepai-logo-1400x340')['requires_image_model_call']
    assert not next(o for o in result['outputs'] if o['placement_id']=='learning-baidu-512x512')['requires_image_model_call']
    assert all(o['state']=='waiting_for_baseline_confirmation' for o in result['outputs'])
    assert all(o['cta_text']=='立即点击下载' if o['cta_required'] else o['cta_text']=='' for o in result['outputs'])
    assert all(o['size_plan']['target_width']==o['width'] and o['size_plan']['target_height']==o['height'] for o in result['outputs'])
    assert all(('Logo图层' in o['method'])==o['logo_required'] for o in result['outputs'])
    assert not engine.tasks and engine.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]==0
    assert not engine.audit_path.exists()
    assert engine.document(CONFIGURATION_DOCUMENT)['params']['learning_logo_snapshot']['revision']==result['logo_revision']
    status,again=request('/api/learning-machine/preview','POST',{'params':result['params']})
    assert status==200 and again['visual_config']==result['visual_config']
    assert request('/api/learning-machine/config')[1]['saved_configuration']['params']['t1']==params['t1']


def test_configuration_preview_cannot_confirm_a_baseline_from_client_flags(api):
    engine,request=api
    params={'channel':'学习机','t1':'先看基准图再决定','font':'none',
            'confirmation':{'confirmed':True,'can_expand':True},'baseline_confirmed':True,
            'baseline':{'has_image':True,'artifact_ready':True,'state':'confirmed'},
            'suite':{'can_expand':True}}
    status,result=request('/api/learning-machine/preview','POST',{'params':params})
    assert status==200
    assert result['baseline']['state']=='not_generated'
    assert result['confirmation']['status']=='waiting_for_image'
    assert result['confirmation']['confirmed'] is False
    assert result['suite']['can_expand'] is False
    assert all(o['state']=='waiting_for_baseline_confirmation' for o in result['outputs'])
    for key in ('baseline','confirmation','suite','baseline_confirmed'):
        assert key not in result['params']
        assert key not in engine.document(CONFIGURATION_DOCUMENT)['params']
    assert not engine.tasks


def test_fixed_group_ratio_and_reuse_survive_client_overrides_and_logo_variants(api):
    from kie_model import GPT_IMAGE_26_FLARE
    engine,request=api
    pids=['learning-bbg-logo-banner-1280x362','learning-bbg-no-logo-banner-1280x362','learning-bbg-logo-banner-2368x670']
    params={'channel':'学习机','t1':'不会的题拍一下','font':'none','pids':pids,
            'image_model':GPT_IMAGE_26_FLARE,'aspect_ratio':'9:16','feature_label':'AI拍题精学'}
    status,result=request('/api/learning-machine/preview','POST',{'params':params})
    assert status==200
    assert result['master_count']==1 and result['planned_image_calls']==4
    assert result['prompt_plan']['counts']['background_image_calls']==2
    assert len({o['master_id'] for o in result['outputs']})==1
    assert all(o['size_plan']['source_ratio']=='3:1' for o in result['outputs'])
    assert all(o['size_plan']['ratio_source']=='fixed_master_group' for o in result['outputs'])
    assert sum(o['logo_required'] for o in result['outputs'])==2
    assert not engine.tasks


def test_double_840_keeps_two_outputs_but_reuses_one_master(api):
    engine,request=api
    params={'channel':'学习机','t1':'不会的题拍一下','font':'none',
            'pids':['learning-youxuepai-double-840x404'],'feature_label':'AI拍题精学'}
    status,result=request('/api/learning-machine/preview','POST',{'params':params})
    assert status==200
    assert result['output_count']==2 and result['master_count']==1
    assert result['planned_image_calls']==2
    assert len({o['master_id'] for o in result['outputs']})==1
    assert all(o['size_plan']['source_ratio']=='2:1' for o in result['outputs'])


def test_pure_landscape_reuses_confirmed_baseline_without_a_second_image_call(api):
    engine,request=api
    params={'channel':'学习机','t1':'不会的题拍一下','font':'none',
            'pids':['learning-ruishi-rounded-580x320','learning-ruishi-rect-580x320']}
    status,result=request('/api/learning-machine/preview','POST',{'params':params})
    assert status==200
    assert result['master_count']==1 and result['planned_image_calls']==1
    assert result['suite']['planned_image_calls_after_confirmation']==0
    assert result['prompt_plan']['counts']['baseline_reused_master_count']==1
    assert result['prompt_plan']['masters'][0]['reuse_baseline'] is True
    assert result['suite']['can_expand'] is False
    assert all(o['state']=='waiting_for_baseline_confirmation' for o in result['outputs'])
    assert not engine.tasks


def test_unsupported_fixed_ratio_stays_fixed_and_does_not_start_a_provider(api):
    from kie_model import MODEL
    engine,request=api
    params={'channel':'学习机','t1':'不会的题拍一下','font':'none','image_model':MODEL,
            'pids':['learning-baidu-1200x400']}
    status,result=request('/api/learning-machine/preview','POST',{'params':params})
    assert status==200
    size=result['outputs'][0]['size_plan']
    assert size['source_ratio']=='3:1' and size['model_supports_ratio'] is False
    assert result['execution']['enabled'] is False and not engine.tasks


def test_logo_save_persists_and_does_not_mutate_previous_configuration(api):
    engine,request=api;_,cfg=request('/api/learning-machine/config')
    p=next(p for p in cfg['placements'] if p['logo_required'])
    _,before=request('/api/learning-machine/preview','POST',{'params':{'channel':'学习机','t1':'先做一套','pids':[p['id']],'font':'none'}})
    frozen=copy.deepcopy(before['params']['learning_logo_snapshot'])
    row={'placement_id':p['id'],'asset_id':'learning.logo.white-app','x':.08,'y':.06,'width':.2}
    status,saved=request('/api/learning-machine/logo-templates','PUT',{'revision':cfg['revision'],'templates':[row]})
    assert status==200 and saved['revision']==cfg['revision']+1
    restored=next(p for p in request('/api/learning-machine/config')[1]['placements'] if p['id']==row['placement_id'])
    assert restored['logo_template']=={k:v for k,v in row.items() if k!='placement_id'}
    assert before['params']['learning_logo_snapshot']==frozen
    assert engine.document(CONFIGURATION_DOCUMENT)['params']['learning_logo_snapshot']==frozen
    assert request('/api/learning-machine/logo-templates','PUT',{'revision':cfg['revision'],'templates':[row]})[0]==409


def test_logo_backup_document_recovers_missing_template_file_without_overwriting_live_edits(api):
    engine,request=api;_,cfg=request('/api/learning-machine/config');p=next(p for p in cfg['placements'] if p['logo_required'])
    row={'placement_id':p['id'],'asset_id':'learning.logo.black','x':.11,'y':.07,'width':.19}
    assert request('/api/learning-machine/logo-templates','PUT',{'revision':0,'templates':[row]})[0]==200
    from local_app.learning_logo import STATE_NAME
    path=engine.settings.state_dir/STATE_NAME;path.unlink()
    restored=public_config(engine);p2=next(row for row in restored['placements'] if row['id']==p['id'])
    assert p2['logo_template']['x']==.11 and path.is_file()


@pytest.mark.parametrize('path,body',[
    ('/api/learning-source/copy',{'id':'a'*64}),
    ('/api/learning-source/plan',{'params':{'learning_mode':'upload'}}),
    ('/api/uploads',{'purpose':'uploaded_master'}),
    ('/api/tasks',{'params':{'channel':'学习机','t1':'一句文案'},'idempotency_key':'no-real-image-task'}),
])
def test_retired_upload_and_old_generation_routes_do_not_call_providers(api,path,body):
    engine,request=api;engine.settings.real=True;engine.settings.key='test-only-not-used'
    status,value=request(path,'POST',body)
    assert status==409 and '基准' in value['message_zh'] and not engine.tasks


def test_preview_uses_registered_reference_not_a_client_local_path(api):
    engine,request=api;data=BytesIO();Image.new('RGB',(16,12),'#56789a').save(data,'PNG')
    raw=data.getvalue();rid=hashlib.sha256(raw).hexdigest();folder=engine.settings.state_dir/'uploads';folder.mkdir(exist_ok=True);(folder/(rid+'.png')).write_bytes(raw)
    params={'channel':'学习机','t1':'一句文案','font':'none','references':[{'id':rid,'purpose':'style','path':'/etc/passwd','note':'用此画风'}]}
    status,value=request('/api/learning-machine/preview','POST',{'params':params})
    assert status==200 and value['params']['references'][0]['path']==str(folder/(rid+'.png'))
    assert value['params']['references'][0]['thumbnail_url']=='/api/uploads/'+rid
    assert value['visual_config']['style_source']=='reference'


def test_invalid_preview_does_not_replace_saved_configuration(api):
    engine,request=api
    assert request('/api/learning-machine/preview','POST',{'params':{'channel':'学习机','t1':'保存的文案','font':'none'}})[0]==200
    before=copy.deepcopy(engine.document(CONFIGURATION_DOCUMENT))
    assert request('/api/learning-machine/preview','POST',{'params':{'channel':'学习机','t1':'','font':'none'}})[0]==400
    assert engine.document(CONFIGURATION_DOCUMENT)==before


def test_exact_export_supports_odd_dimensions_and_preserves_source(tmp_path):
    source=tmp_path/'source.png';Image.new('RGB',(1536,512),'#4590af').save(source)
    original=source.read_bytes();target=tmp_path/'target.png'
    result=export_exact(source,target,1223,471,protected_regions=[[.2,.2,.8,.8]])
    assert result['exact_size_verified'] and source.read_bytes()==original
    with Image.open(target) as image:assert image.size==(1223,471) and image.format=='PNG'
    with pytest.raises(UserError,match='重要内容'):
        export_exact(source,tmp_path/'bad.png',1400,340,protected_regions=[[.05,.02,.95,.98]])
    with pytest.raises(UserError,match='拉伸'):
        export_exact(source,tmp_path/'bad2.png',1400,340,crop_box=[0,0,1,1])


def test_model_aware_sizing_uses_supported_ratios_without_old_frame_stretch():
    value=plan(1400,340,'gpt-image-2-6/flare-image-to-image')
    assert value['source_ratio']=='3:1' and value['strategy']=='target_safe_area_recompose'
    assert abs(value['crop_percent']-27.142857142857)<1e-8
    assert value['logo_is_protected'] is False and value['content_must_fit_crop'] is True
