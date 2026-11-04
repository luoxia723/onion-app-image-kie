import base64
import copy
import hashlib
from io import BytesIO
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from local_app.config import Settings, UserError
from local_app.engine import Engine
from local_app.planning import PLACEMENTS, REFERENCE_PURPOSES, compile_plans, copy_signature, make_round, validate
from local_app.scene_planner import ApiScenePlanner, plan_input
from local_app.server import Handler
from tests_local.fakes import FixturePlanner


@pytest.fixture
def settings(tmp_path):
    settings=Settings(tmp_path/'state',tmp_path/'.env')
    settings.update({'planning_api_key':'test-key','planning_base_url':'https://gateway.example/v1',
                     'planning_model':'gpt-6.1-terra','output_dir':str(tmp_path)})
    return settings


def api_call(settings, path, body):
    # Exercise routing and upload validation without binding a port.
    handler=Handler.__new__(Handler)
    handler.server=SimpleNamespace(server_port=12345,engine=SimpleNamespace(settings=settings))
    handler.command='POST';handler.path=path;handler.headers={'Host':'127.0.0.1:12345'}
    handler.body=lambda:body;handler.json=lambda value:value
    return handler.handle_api()


def uploaded(settings, name='参考.png'):
    image=BytesIO();Image.new('RGB',(4,3),'blue').save(image,format='PNG')
    return api_call(settings,'/api/uploads',{'name':name,'purpose':'style','data':base64.b64encode(image.getvalue()).decode()})


def completion(points):
    return {'choices':[{'message':{'content':json.dumps(points,ensure_ascii=False)},'finish_reason':'stop'}]}


def test_reference_points_route_sends_image_and_purpose_and_reuses_disk_cache(settings,monkeypatch):
    calls=[];points=['低饱和暖色','水彩笔触','柔和顶光']
    def request(self,payload,config):
        calls.append(payload)
        assert config==('test-key','https://gateway.example/v1','gpt-6.1-terra')
        return completion(points)
    monkeypatch.setattr(ApiScenePlanner,'_request',request)
    ref=uploaded(settings)
    expected={'style':'画风、配色、笔触或材质、光影','composition':'主体位置、文字区位置、留白和层次','ui':'这是什么界面、画面里必须保留的关键元素'}
    for purpose,direction in expected.items():
        body={'id':ref['id'],'purpose':purpose}
        assert api_call(settings,'/api/references/points',body)=={'points':points}
        assert direction in calls[-1]['messages'][1]['content'][0]['text']
        assert uploaded(settings,'重复上传.png')['id']==ref['id']
        assert api_call(settings,'/api/references/points',body)=={'points':points}
    assert len(calls)==3
    for payload in calls:
        assert payload['model']=='gpt-6.1-terra' and payload['max_completion_tokens']>0
        assert 'max_tokens' not in payload
        system=payload['messages'][0]['content']
        assert 'JSON 字符串数组' in system and '3–5 条' in system and '10 个字' in system
        image=payload['messages'][1]['content'][1]
        assert image['type']=='image_url'
        url=image['image_url']['url'];assert url.startswith('data:image/png;base64,')
        assert hashlib.sha256(base64.b64decode(url.split(',',1)[1])).hexdigest()==ref['id']


@pytest.mark.parametrize('body',[{'id':'../bad','purpose':'style'},{'id':'a'*64,'purpose':'style'},
                                 {'id':None,'purpose':'ui'}])
def test_points_route_rejects_missing_or_invalid_upload(settings,body):
    with pytest.raises(UserError,match='参考图不存在'):api_call(settings,'/api/references/points',body)


@pytest.mark.parametrize('purpose',['legacy','other',None,[]])
def test_points_route_rejects_invalid_purpose(settings,purpose):
    ref=uploaded(settings)
    with pytest.raises(UserError,match='请选择参考图用途'):
        api_call(settings,'/api/references/points',{'id':ref['id'],'purpose':purpose})


def test_points_route_uses_existing_missing_key_error(settings):
    ref=uploaded(settings);settings.planning_key=''
    with pytest.raises(UserError,match='请先在设置中填写画面规划 Key'):
        api_call(settings,'/api/references/points',{'id':ref['id'],'purpose':'style'})


@pytest.mark.parametrize('points',[{},['短句']*2,['短句']*6,['字'*11]*3,['']*3,[None]*3])
def test_invalid_extraction_is_not_cached(settings,monkeypatch,points):
    ref=uploaded(settings);calls=[]
    def request(*args):calls.append(1);return completion(points)
    monkeypatch.setattr(ApiScenePlanner,'_request',request)
    for _ in range(2):
        with pytest.raises(UserError,match='参考图要点'):
            api_call(settings,'/api/references/points',{'id':ref['id'],'purpose':'style'})
    assert len(calls)==2


def params():
    return dict(image_form='单图',pids=[next(p['id'] for p in PLACEMENTS if p['image_form']=='单图')],
                sets=1,t1='每天进步一点',t2='打开学习任务',ip='none',style='random',cta='立即体验')


@pytest.mark.parametrize('points',[None,'暖色',{},['短句']*7,[''],['  '],[123],['字'*17]])
def test_reference_points_validation_rejects_invalid_values(tmp_path,points):
    pr={**params(),'references':[{'id':'ref','purpose':'style','points':points}]}
    with pytest.raises(UserError,match='参考图要点最多 6 条，每条 1–16 字'):validate(pr,tmp_path)


@pytest.mark.parametrize('points',[[],['字'],['字'*16]*6])
def test_reference_points_validation_accepts_boundaries(tmp_path,points):
    validate({**params(),'references':[{'id':'ref','purpose':'style','points':points}]},tmp_path)


@pytest.mark.parametrize('purpose',['style','composition','ui'])
@pytest.mark.parametrize('points,note', [(['暖色','水彩笔触'],'保留光影'),(['暖色','水彩笔触'],''),([],''),([], '只保留补充说明'),([], ' 旧任务说明 '),([], '  ')])
def test_points_and_note_reach_planner_roles_style_and_prompt(tmp_path,purpose,points,note):
    ref={'id':'ref','purpose':purpose,'points':points,'note':note,'path':str(tmp_path/'ref.png')}
    if not points:ref.pop('points')
    pr={**params(),'references':[ref]};validate(pr,tmp_path)
    r=make_round(pr,'reference-points',tmp_path,1,True,defer_planning=True)
    expected='；'.join(part for part in ('、'.join(points),note) if part)
    job=plan_input(r)['jobs'][0]
    assert job['reference_notes']==[expected] and job['references'][0]['note']==expected
    role=next(ref['role'] for ref in r['slots'][0]['refs'] if ref.get('purpose')==purpose)
    assert role==REFERENCE_PURPOSES[purpose]+('：'+expected if expected.strip() else '')
    if purpose=='style':
        assert r['set_metadata']['1']['style']['description']=='沿用参考风格图的配色、笔触、材质和光影'+('；'+expected.strip() if expected.strip() else '')
    compile_plans(r,FixturePlanner().plan(r,lambda result:None))
    prompt=r['slots'][0]['prompt']
    if expected.strip(): assert expected.strip() in prompt
    else: assert REFERENCE_PURPOSES[purpose]+'：' not in prompt


def test_reference_points_signature_draft_restart_and_remember_form(settings):
    pr={**params(),'references':[{'id':'ref','purpose':'style','points':['暖色'],'note':''}]}
    changed=copy.deepcopy(pr);changed['references'][0]['points']=['冷色']
    assert copy_signature(changed)!=copy_signature(pr)
    old=copy.deepcopy(pr);old['references'][0].pop('points')
    empty=copy.deepcopy(old);empty['references'][0]['points']=[]
    assert copy_signature(old)==copy_signature(empty)
    e=Engine(settings,start=False,planner=FixturePlanner())
    try:
        e.save_draft('a'*32,{'draft':pr,'form_drafts':{'双图':pr}})
        e.remember_form(pr)
    finally:e.close()
    e=Engine(settings,start=False,planner=FixturePlanner())
    try:
        assert e.get_draft('a'*32)['draft']['references']==pr['references']
        assert e.get_draft('a'*32)['form_drafts']['双图']['references']==pr['references']
        assert e.document('form_defaults')['单图']['references']==pr['references']
    finally:e.close()


def test_remembered_reference_points_can_generate_a_new_task(settings):
    ref={**uploaded(settings),'points':['暖色','水彩笔触']}
    pr={**params(),'references':[ref]}
    e=Engine(settings,start=False,planner=FixturePlanner())
    try:
        original=e.create(pr,'original-reference-points')
        defaults=e.document('form_defaults')['单图']
        assert defaults['references'][0]['path']!=ref['path']
        newer=e.create({**pr,**defaults},'remembered-reference-points')
        assert newer['id']!=original['id']
        assert e.task(newer['id'])['rounds'][0]['params']['references'][0]['points']==ref['points']
    finally:e.close()
