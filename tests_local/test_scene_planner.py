import copy
import json
import threading
import time
from pathlib import Path
import pytest
from local_app.config import Settings,UserError
from local_app.planning import make_round,compile_plans,PLACEMENTS
from local_app.scene_planner import ApiScenePlanner,PlanningStopped,plan_input,rules_text
from tests_local.fakes import FixturePlanner


def round_for_test(tmp_path):
    p=next(p for p in PLACEMENTS if p['image_form']=='三图')
    pr=dict(image_form='三图',pids=[p['id']],sets=1,t1='',t2='',s1='先看今天学什么',s2='完成今天的学习任务',s3='查看学习进度',cta='立即体验',ip='none',style='random',feature_note='画面采用柔和的侧光',product_facts='只表达已确认的学习任务与进度功能')
    return make_round(pr,'original-skill-test',tmp_path,2,True,defer_planning=True)


def test_actual_compose_inputs_are_frozen_and_feature_applies_every_image(tmp_path):
    import positive_prompt
    r=round_for_test(tmp_path);result=FixturePlanner().plan(r,lambda x:compile_plans(r,x,apply=False));compile_plans(r,result)
    entry=r['configs'][0]
    for s in r['slots']:
        label=(s['refs'][-1]['label'] if s['idx']==1 else '参考图1') if s['frame'] else None
        assert s['orig']==positive_prompt.compose(entry['config'],entry['direction'],s['idx'],s['refs'],label)
        assert '画面采用柔和的侧光' in s['orig']
    assert r['planning_source']=='codex_skill' and entry['config']['learner_story_required']


@pytest.mark.parametrize('corruption',['style','actions','story','missing_target'])
def test_model_output_cannot_bypass_original_contract(tmp_path,corruption):
    r=round_for_test(tmp_path);result=FixturePlanner().plan(r,lambda x:None)
    if corruption=='style':result['plans'][0]['concept']['style_id']='invented'
    if corruption=='actions':result['plans'][0]['concept']['slot_actions']=['仅一张']
    if corruption=='story':result['plans'][0]['concept'].pop('learner_story')
    if corruption=='missing_target':result['plans']=[]
    with pytest.raises(UserError):compile_plans(r,result)
    assert not any(s['plan_ready'] for s in r['slots'])


@pytest.fixture
def api(tmp_path):
    settings=Settings(tmp_path/'state',tmp_path/'.env')
    settings.update({'planning_api_key':'test-planning-secret','planning_model':'gpt-6.1-terra',
                     'planning_base_url':'https://gateway.example/v1'})
    return ApiScenePlanner(settings)


def completion(content, reason='stop'):
    return {'choices':[{'message':{'content':content},'finish_reason':reason}],
            'usage':{'prompt_tokens':12,'completion_tokens':34,'total_tokens':46,'private':'omit'}}


def test_api_freezes_original_skill_and_reuses_validated_cache(api,tmp_path,monkeypatch):
    r=round_for_test(tmp_path)
    result=FixturePlanner().plan(r,lambda x:None);result.pop('_provenance')
    calls=[]
    def request(payload,config,stopped):
        calls.append((payload,config))
        return completion(json.dumps(result,ensure_ascii=False))
    monkeypatch.setattr(api,'_request',request)
    validate=lambda x:compile_plans(r,x,apply=False)
    one=api.plan(r,validate);two=api.plan(r,validate)
    assert one==two and len(calls)==1
    payload,config=calls[0]
    assert payload['model']=='gpt-6.1-terra' and payload['response_format']=={'type':'json_object'}
    assert config==('test-planning-secret','https://gateway.example/v1','gpt-6.1-terra')
    assert 'test-planning-secret' not in json.dumps(payload)
    assert '不要运行命令' in payload['messages'][0]['content']
    assert '## 用原数学案例' not in rules_text()
    assert '只表达已确认的学习任务与进度功能' in payload['messages'][1]['content']
    assert one['_provenance']['provider']=='openai_compatible'
    assert one['_provenance']['usage']=={'prompt_tokens':12,'completion_tokens':34,'total_tokens':46}
    api.settings.update({'planning_model':'explicitly-changed-model'})
    api.plan(r,validate)
    assert len(calls)==2 # A different model must not reuse old model's cache.


def test_api_repairs_schema_and_contract_failures_only(api,tmp_path,monkeypatch):
    r=round_for_test(tmp_path)
    good=FixturePlanner().plan(r,lambda x:None);good.pop('_provenance')
    wrong=copy.deepcopy(good);wrong['plans'][0]['concept']['slot_actions']=['one']
    outputs=[{'plans':[]},wrong,good];calls=[]
    def request(payload,*args):
        calls.append(copy.deepcopy(payload))
        return completion(json.dumps(outputs.pop(0)))
    monkeypatch.setattr(api,'_request',request)
    api.plan(r,lambda x:compile_plans(r,x,apply=False))
    assert len(calls)==3 and len(calls[-1]['messages'])==4
    assert not any(s['plan_ready'] for s in r['slots'])
    monkeypatch.setattr(api,'_request',lambda *a:(_ for _ in ()).throw(UserError('network failure')))
    api.settings.update({'planning_model':'different-cache'})
    with pytest.raises(UserError,match='network failure'):api.plan(r,lambda x:None)


@pytest.mark.parametrize('reason',['length','content_filter','tool_calls'])
def test_incomplete_api_response_is_not_retried_or_cached(api,tmp_path,monkeypatch,reason):
    calls=[]
    def request(*a):calls.append(1);return completion('{}',reason)
    monkeypatch.setattr(api,'_request',request)
    with pytest.raises(UserError):api.plan(round_for_test(tmp_path),lambda x:None)
    assert len(calls)==1 and not list(tmp_path.rglob('*.validated.json'))


def test_planning_settings_never_return_either_key(api):
    s=api.settings
    s.update({'kie_api_key':'test-image-secret','planning_api_key':''})
    assert s.planning_key=='test-planning-secret'
    public=json.dumps(s.public())
    assert 'test-planning-secret' not in public and 'test-image-secret' not in public
    assert s.public()['planning_key_configured']
    assert s.env_file.stat().st_mode&0o777==0o600
    for url in ['http://gateway.example/v1','https://user:pass@gateway.example/v1','https://gateway.example/v1?key=secret','https://gateway.example:bad/v1']:
        with pytest.raises(UserError):s.update({'planning_base_url':url})
    with pytest.raises(UserError):s.update({'planning_model':''})


def test_stopped_api_call_is_not_submitted(api,tmp_path,monkeypatch):
    r=round_for_test(tmp_path);Path(r['stop_marker']).touch()
    monkeypatch.setattr(api,'_request',lambda *a:pytest.fail('stopped request submitted'))
    with pytest.raises(PlanningStopped):api.plan(r,lambda x:None)


class FakeSocket:
    def settimeout(self,n):pass
    def shutdown(self,how):pass


@pytest.mark.parametrize('status',[200,302,401,429,500])
def test_https_transport_does_not_redirect_or_expose_provider_error(api,monkeypatch,status):
    calls=[]
    class Connection:
        sock=FakeSocket()
        def __init__(self,*a,**kw):calls.append(('connect',a))
        def connect(self):pass
        def request(self,method,path,body,headers):calls.append((method,path,json.loads(body),headers))
        def getresponse(self):return self
        def read(self,n):return json.dumps(completion('OK')).encode()
        def close(self):pass
    Connection.status=status
    monkeypatch.setattr('local_app.scene_planner.http.client.HTTPSConnection',Connection)
    if status==200:
        assert api.test_connection()['key_status']=='connected'
        assert calls[1][1]=='/v1/chat/completions'
        assert calls[1][3]['Authorization']=='Bearer test-planning-secret'
    else:
        with pytest.raises(UserError) as exc:api.test_connection()
        assert 'test-planning-secret' not in exc.value.message
    assert len(calls)==2


def test_transport_cancellation_returns_without_waiting_for_gateway(api,monkeypatch):
    started=threading.Event();release=threading.Event();stop=threading.Event()
    class Connection:
        sock=FakeSocket()
        def __init__(self,*a,**kw):pass
        def connect(self):pass
        def request(self,*a,**kw):started.set()
        def getresponse(self):release.wait(2);raise OSError('private-error-body')
        def close(self):release.set()
    monkeypatch.setattr('local_app.scene_planner.http.client.HTTPSConnection',Connection)
    def cancel():started.wait(1);stop.set()
    t=threading.Thread(target=cancel);t.start()
    before=time.monotonic()
    with pytest.raises(PlanningStopped):api._request({},api.configuration(),stop.is_set)
    t.join();assert time.monotonic()-before<1


def test_settings_http_test_uses_planning_adapter_and_redacts_keys(api,monkeypatch):
    import urllib.request
    from http.server import ThreadingHTTPServer
    from types import SimpleNamespace
    from local_app.server import Handler
    captured=[]
    def connection(self,overrides=None):
        captured.append(self.configuration(overrides))
        return {'key_status':'connected','message_zh':'已连接 · gpt-6.1-terra'}
    monkeypatch.setattr(ApiScenePlanner,'test_connection',connection)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.engine=SimpleNamespace(settings=api.settings)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(server.server_port)
    try:
        req=urllib.request.Request(base+'/api/settings/test-planning',data=b'{}',
            headers={'Content-Type':'application/json','X-Onion-Request':'1'})
        result=json.load(urllib.request.urlopen(req))
        assert result['key_status']=='connected' and captured[0][2]=='gpt-6.1-terra'
        public=json.load(urllib.request.urlopen(base+'/api/settings'))
        assert public['planning_key_configured'] and public['planning_key_status']=='connected'
        assert 'test-planning-secret' not in json.dumps(public)+json.dumps(result)
    finally:server.shutdown();server.server_close()

@pytest.mark.parametrize('form', ['双图', '三图'])
def test_scoped_multi_image_context_and_reference_roles(tmp_path, form):
    p=next(p for p in PLACEMENTS if p['image_form']==form)
    pr=dict(image_form=form,pids=[p['id']],sets=1,t1='',t2='',s1='第二张试卷',s2='当前第二句',s3='当前第三句',cta='',ip='none',style='random',feature_note='',product_facts='')
    r=make_round(pr,'scope-test',tmp_path,2,True,defer_planning=True)
    result=FixturePlanner().plan(r,lambda x:None)
    concept=result['plans'][0]['concept']
    concept['prompt']='整套说明：第二张引用第一张，未来流程标记。'
    concept['learner_story']['product_action']='未来产品动作标记'
    concept['slot_actions']=['当前动作标记'+str(i) for i in range(1,p['image_count']+1)]
    compile_plans(r,result)
    first=r['slots'][0]['prompt']
    assert '第二张试卷' in first and '当前动作标记1' in first
    assert '未来流程标记' not in first and '未来产品动作标记' not in first
    assert '当前第二句' not in first and '当前动作标记2' not in first
    assert '附带贴纸' in first
    for slot in r['slots'][1:]:
        assert len(slot['refs'])==1 and slot['refs'][0]['path']==r['slots'][0]['output']
        assert '当前动作标记'+str(slot['idx']) in slot['prompt']
        assert '未来产品动作标记' not in slot['prompt']
        assert '当前动作标记1' not in slot['prompt']


def test_scoped_context_requires_separate_common_scene(tmp_path):
    r=round_for_test(tmp_path);result=FixturePlanner().plan(r,lambda x:None)
    result['plans'][0]['concept'].pop('common_visual')
    with pytest.raises(UserError): compile_plans(r,result)
    assert not any(s['plan_ready'] for s in r['slots'])


def test_multi_image_ip_uses_style_material_adaptation(tmp_path):
    p=next(p for p in PLACEMENTS if p['image_form']=='双图')
    pr=dict(image_form='双图',pids=[p['id']],sets=1,t1='',t2='',s1='拍题精学',s2='一拍就会',s3='',cta='',ip='ip.xiaochui.junior.standard.001',style='折纸',feature_note='',product_facts='')
    r=make_round(pr,'style-test',tmp_path,2,True,defer_planning=True)
    result=FixturePlanner().plan(r,lambda x:None);compile_plans(r,result)
    from art_direction import concise_ip_note
    from visual_directions import load_catalog
    style=next(s for s in load_catalog()['styles'] if s['id']=='origami')
    note=concise_ip_note(style['ip_adaptation'])
    assert note and note in r['slots'][0]['prompt']
    assert note not in r['slots'][1]['prompt']
