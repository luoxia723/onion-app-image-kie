import base64
from io import BytesIO
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from scripts.kie_model import NANO_BANANA_REPAIR, NANO_REPAIR_SIZES
from local_app.config import Settings, UserError
from local_app.engine import Engine
from local_app.learning_executor import LearningExecutor
from local_app.learning_runtime import LearningRuntime, PREFIX, _digest
from local_app.learning_visual import MODEL, _parse, confirmed_issues, inspect_suspect_text
from local_app.scene_planner import ApiScenePlanner
from scripts.render import build_create_request
from tests_local.fakes import FixturePlanner
from tests_local.test_learning_runtime import params, settled


def response(allowed, verdict='pass', target='', kind='glyph', body=None):
    issues = [dict(kind=kind, target=target, where='该字笔画', detail='字内不连续')] if target else []
    data = dict(verdict=verdict, issues=issues, body=allowed.get('t1', '') if body is None else body,
                cta=allowed.get('cta', ''))
    return _parse({'choices': [{'message': {'content': json.dumps(data)}}]}, allowed)


class VisualProvider(LearningExecutor):
    def __init__(self, settings):
        super().__init__(settings)
        self.events = []
        self.post_repair_available = True
        self.post_repair_wrong_read = False
        self.focused_read = '的第一步'
        self.mismatch = True
        self.composition_fault = True

    def plan_scene(self, run, stop_event):
        return super().plan_scene({**run, 'mode': 'simulation'}, stop_event)

    def generate_image(self, job, stop_event):
        self.events.append(('generate', job['kind'], job.get('id')))
        if job['kind'] == 'typography_repair':
            path = Path(job['output'])
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new('RGB', NANO_REPAIR_SIZES[job['aspect_ratio']], '#adb9df').save(path)
            return dict(source=str(path), sha256=_digest(path), simulated=False, provider_task_id='nano-result',
                        actual_prompt=job['prompt'], reference_bindings=job['reference_bindings'])
        return {**super().generate_image({**job, 'simulation': True}, stop_event), 'simulated': False}

    def inspect_typography(self, path, allowed, independent, reference, stop_event, *, removed_module=None):
        group = path.parent.name
        self.events.append(('review', group, independent, bool(reference)))
        if removed_module:
            self.events.append(('removal_composition',path,independent,removed_module))
            if not self.composition_fault:return response(allowed)
            result=response(allowed,'repair','主视觉',kind='composition')
            if removed_module=='cta':
                result['issues'].append(dict(kind='glyph',target='拍',where='字面',detail='笔画不连续'))
            return result
        if path.name == 'fitted.png' and self.post_repair_wrong_read:
            return response(allowed, 'repair', '第二步', 'wrong_text', '题目不会，找到解题的第二步。')
        if reference:
            if not self.post_repair_available:
                return dict(verdict='unavailable', issues=[], model=MODEL)
            return response(allowed)
        if group == 'learning-master-E3' and self.mismatch and not independent:
            return response(allowed, 'repair', '第一步', kind='wrong_text', body='题目拍一下找第三步。')
        if group == 'learning-master-D3':
            return response(allowed, 'repair', '拍')
        return response(allowed)

    def inspect_suspect_text(self, path, targets, stop_event):
        self.events.append(('focus', path.name, targets))
        verdict='pass' if self.focused_read=='的第一步' else 'repair'
        return dict(verdict=verdict, model=MODEL, checks=[{'text':self.focused_read,'verdict':verdict}])


@pytest.fixture
def live_boundary(tmp_path):
    settings = Settings(tmp_path/'state', tmp_path/'test.env')
    settings.update({'simulation': True, 'output_dir': str(tmp_path), 'kie_api_key': 'test-only-image',
                     'planning_api_key': 'test-only-planning'})
    engine = Engine(settings, start=False, planner=FixturePlanner())
    executor = VisualProvider(settings)
    runtime = LearningRuntime(engine, executor)
    try:
        yield runtime, executor, engine
    finally:
        runtime.close()
        engine.close()


def run_started(service, pids, **copy):
    run = service.create({**params(pids),**copy}, mode='real', idempotency_key='visual-test-config')
    rid = run['id']
    service.generate_baseline(rid, 'visual-test-baseline')
    assert settled(service, rid)['baseline']['status'] == 'done'
    service.confirm_baseline(rid, 1)
    service.expand_suite(rid, 'visual-test-expand')
    return rid, settled(service, rid)


def test_workflow_gates_every_text_master_rechecks_before_nano_and_uses_correct_source(live_boundary):
    service, executor, engine = live_boundary
    rid, run = run_started(service, ['learning-bbg-cover-216x260', 'learning-xueersi-1125x885',
                                    'learning-bbg-logo-banner-988x460', 'learning-dsl-resource-500x312'])
    masters = {r['group_id']:r for r in run['masters']}
    assert masters['A1'].get('visual_review') is None
    assert masters['C2']['visual_review']['status'] == 'approved'
    repaired = masters['D3']['visual_review']
    assert [repaired[k]['verdict'] for k in ('first', 'verification', 'after')] == ['repair', 'repair', 'pass']
    assert repaired['repaired'] and masters['D3']['status'] == 'done'
    gate = masters['E3']['visual_review']
    assert gate['can_accept'] and gate['status'] == 'needs_review'
    assert masters['E3']['status'] == 'visual_hold'
    assert run['counts']['completed_outputs'] == 3
    e3 = next(r for r in run['outputs'] if r['master_id'] == masters['E3']['id'])
    assert e3['status']=='blocked' and e3['image_url'] is None
    launch = executor.events.index(('generate', 'typography_repair', None))
    assert executor.events.index(('review', 'learning-master-D3', True, False)) < launch
    assert executor.events.index(('review', 'v1', False, True)) > launch
    assert sum(e[:2]==('generate','typography_repair') for e in executor.events) == 1
    saved = engine.document(PREFIX+rid)
    source = next(m for m in saved['masters'] if m['group_id']=='D3')
    output = next(o for o in saved['outputs'] if o['master_id']==source['id'])
    assert output['raw_sha256'] == source['visual_review']['repair']['result']['sha256']
    assert _digest(service.visual_image(rid,'master',source['id'],1,'original')) != output['raw_sha256']
    assert _digest(service.visual_image(rid,'master',source['id'],1,'repair')) == output['raw_sha256']
    with pytest.raises(UserError,match='图片已更新'):
        service.resolve_visual_review(rid,'master',masters['E3']['id'],'accept',1,'old-sha','visual-test-stale')
    service.resolve_visual_review(rid,'master',masters['E3']['id'],'accept',1,gate['review_sha256'],'visual-test-accept')
    assert settled(service,rid)['counts']['completed_outputs'] == 4
    assert sum(e[:2]==('generate','typography_repair') for e in executor.events) == 1


def test_unavailable_post_repair_stays_blocked_and_review_retry_does_not_edit_again(live_boundary):
    service, executor, engine = live_boundary
    executor.post_repair_available = False
    rid, run = run_started(service, ['learning-bbg-logo-banner-988x460'])
    row = run['masters'][0]
    review = row['visual_review']
    assert row['status']=='visual_hold' and run['counts']['completed_outputs']==0
    assert review['repaired'] and review['status']=='unavailable'
    with pytest.raises(UserError):
        service.package(rid)
    executor.post_repair_available = True
    service.resolve_visual_review(rid,'master',row['id'],'retry',1,review['review_sha256'],'visual-test-resume')
    end = settled(service,rid)
    assert end['counts']['completed_outputs']==1
    assert end['masters'][0]['visual_review']['status']=='approved'
    assert sum(e[:2]==('generate','typography_repair') for e in executor.events)==1
    saved = engine.document(PREFIX+rid)
    assert saved['masters'][0]['visual_review']['history'][0]['verdict']=='unavailable'


def test_luna_disagreement_does_not_authorize_a_paid_edit():
    allowed = {'t1': '找到解题的第一步。'}
    first = response(allowed, 'repair','一','wrong_text','找到解题的第三步。')
    second = response(allowed, body='找到解题的第一步.')
    assert first['verdict']=='repair' and second['verdict']=='pass'
    assert not confirmed_issues(first,second,allowed)
    assert response(allowed, body='找到解题的第三步。')['verdict']=='review'
    assert not confirmed_issues(response(allowed,'repair','一'),response(allowed,'repair','步'),allowed)


@pytest.mark.parametrize('fragment,approved',[('的第一步',True),('的第二步',False)])
def test_suspected_wrong_character_in_repair_is_checked_on_same_image_before_export(live_boundary,fragment,approved):
    service, executor, _ = live_boundary
    executor.post_repair_wrong_read = True
    executor.focused_read = fragment
    _, run = run_started(service, ['learning-bbg-logo-banner-988x460'], t1='题目不会，找到解题的第一步。')
    master = run['masters'][0]
    event = next((e for e in executor.events if e[0]=='focus'), None)
    assert event is not None, 'the full image reading never reached a localized recheck'
    assert event[1]=='fitted.png' and event[2][0]['left']=='的第' and event[2][0]['right']=='步'
    assert master['visual_review']['after']['body'].endswith('第二步。')
    assert master['visual_review']['after_focus']['checks'][0]['text']==fragment
    assert master['status']==('done' if approved else 'visual_hold')
    assert run['counts']['completed_outputs']==int(approved)
    assert sum(e[:2]==('generate','typography_repair') for e in executor.events)==1


def test_luna_receives_context_and_an_independent_glyph_crop_without_expected_character(tmp_path,monkeypatch):
    # One filled stroke surrounded by dark outline and bright exterior lines.
    source=Image.new('RGB',(800,400),'#10161e')
    draw=ImageDraw.Draw(source)
    for rectangle,color in [((0,181,799,184),'#7ceefa'),((0,221,799,224),'#7ceefa'),((374,197,414,205),'#bef4f5')]:
        draw.rectangle(rectangle,fill=color)
    path=tmp_path/'repaired.png';source.save(path)
    responses=iter([{'box':[350,390,640,618]}, {'box':[380,340,565,610]},
                    {'context':'的第二步。','glyph':'一','certain':True}])
    calls=[]
    def fake(self,payload,config,stopped):
        content=payload['messages'][-1]['content']
        assert payload['model']==config[2]==MODEL
        prompt=content[0]['text']
        assert '的第' in prompt and '步' in prompt and '第一步' not in prompt and '第二步' not in prompt
        calls.append([Image.open(BytesIO(base64.b64decode(part['image_url']['url'].split(',')[1]))).copy()
                      for part in content[1:]])
        return {'choices':[{'message':{'content':json.dumps(next(responses))}}]}
    monkeypatch.setattr(ApiScenePlanner,'_request',fake)
    settings=Settings(tmp_path/'state',tmp_path/'env')
    monkeypatch.setattr(settings,'planning_key','test-vision')
    target=dict(field='body',left='的第',right='步',expected='一',alternatives=['二'])
    check=inspect_suspect_text(settings,path,[target],lambda:False)['checks'][0]
    assert [len(images) for images in calls]==[1,1,3]
    assert check['verdict']=='pass' and check['text']=='的第一步'
    assert calls[0][0].size==(800,400) and calls[-1][0].width>800
    mask=calls[-1][-1].convert('L')
    center=[row for row in range(mask.height) if mask.getpixel((mask.width//2,row))>200]
    assert center and center==list(range(center[0],center[-1]+1))


def test_nano_transport_uses_internal_single_reference_png_payload():
    request = build_create_request('https://api.kie.ai','test-only','修复字形','21:9','1K',['https://example.com/src.png'],model=NANO_BANANA_REPAIR)
    assert json.loads(request.data)=={'model':NANO_BANANA_REPAIR,'input': {
        'prompt':'修复字形','aspect_ratio':'21:9','resolution':'1K',
        'image_input':['https://example.com/src.png'],'output_format':'png'}}


def test_readable_copy_with_dirty_outline_requires_separate_lettering_review(tmp_path,monkeypatch):
    from local_app.learning_visual import inspect
    path=tmp_path/'mother.png'
    Image.new('RGB',(1200,800),'#dddddd').save(path)
    allowed={'t1':'开始精学','cta':'点击下载'}
    readings=iter([
        dict(verdict='pass',body='开始精学',cta='点击下载',issues=[],
             text_boxes={'body':[100,100,610,500],'cta':[85,560,450,750]}),
        dict(verdict='repair',issues=[dict(kind='glyph',target='精',
             where='字间的黑色描边',detail='青色碎屑侵入描边')]),
        dict(verdict='pass',issues=[]),
    ])
    calls=[]
    def fake(self,payload,config,stopped):
        content=payload['messages'][-1]['content']
        pics=[Image.open(BytesIO(base64.b64decode(part['image_url']['url'].split(',')[1]))).size
              for part in content[1:]]
        calls.append((content[0]['text'],pics))
        return {'choices':[{'message':{'content':json.dumps(next(readings))}}]}
    monkeypatch.setattr(ApiScenePlanner,'_request',fake)
    settings=Settings(tmp_path/'state',tmp_path/'env')
    monkeypatch.setattr(settings,'planning_key','test-vision')
    review=inspect(settings,path,allowed,False,None,lambda:False)
    assert review['text_matches'] and review['lettering_checked']
    assert review['verdict']=='repair'
    assert review['issues'][0]['target']=='精'
    assert len(calls)==3 and len(calls[1][1])==len(calls[2][1])==1
    assert calls[1][1][0][0]>calls[0][1][0][0]
    assert '描边' in calls[1][0] and allowed['t1'] not in calls[1][0]


def test_explicit_clean_lettering_reuses_approved_master_and_preserves_previous_version(live_boundary):
    service,executor,_=live_boundary
    rid,run=run_started(service,['learning-xueersi-1125x885'])
    m=run['masters'][0]
    assert m['status']=='done' and m['visual_review']['can_clean_lettering']
    original=service.image(rid,'master',m['id'],1).read_bytes()
    output=run['outputs'][0]
    previous=service.image(rid,'output',output['id'],1).read_bytes()
    with pytest.raises(UserError,match='图片已更新'):
        service.resolve_visual_review(rid,'master',m['id'],'clean_lettering',1,'counterfeit','new-review-stale')
    key='test-approved-lettering-clean'
    service.resolve_visual_review(rid,'master',m['id'],'clean_lettering',1,m['sha256'],key)
    service.resolve_visual_review(rid,'master',m['id'],'clean_lettering',1,m['sha256'],key)
    completed=settled(service,rid)
    assert completed['status']=='completed'
    assert completed['masters'][0]['version']==2 and completed['outputs'][0]['version']==2
    assert completed['masters'][0]['visual_review']['repaired']
    assert sum(e[:2]==('generate','typography_repair') for e in executor.events)==1
    assert sum(e[:2]==('generate','master') for e in executor.events)==1
    assert service.image(rid,'master',m['id'],1).read_bytes()==original
    assert service.image(rid,'output',output['id'],1).read_bytes()==previous


def test_original_brush_comparison_localizes_repeated_character_and_does_not_waive_color_bleed():
    from local_app.learning_visual import brush_mark_target, review_passed
    allowed={'t1':'这步看不懂？拍题看分步解析'}
    first=response(allowed,'repair','看')
    first['issues'][0].update(where='下方与“不”之间',detail='游离的黑色短划')
    second={**first,'body':'这步看不懂？','cta':'拍题看分步解析'}
    target=brush_mark_target(allowed,first,second)
    assert target==dict(target='看',context='这步看不懂',check_button=True)
    assert not review_passed(first,second,None,allowed,{'verdict':'review'})
    assert review_passed(first,second,None,allowed,{'verdict':'pass'})
    second['issues']=[dict(kind='glyph',target='看',where='笔画下沿',detail='青色碎斑侵入黑色描边')]
    assert brush_mark_target(allowed,first,second) is None
    assert not review_passed(first,second,None,allowed,{'verdict':'pass'})


@pytest.mark.parametrize('placement,button,module,native',[
    ('learning-ruishi-rect-580x320','','body',(16,9)),
    ('learning-dsl-resource-500x312','点击下载','cta',(3,2)),
])
def test_content_removal_composition_uses_common_crop_and_holds_before_export(live_boundary,placement,button,module,native):
    service,executor,engine=live_boundary
    stream=BytesIO()
    Image.new('RGB',(1600,900),'#dce7ed').save(stream,'PNG')
    from hashlib import sha256
    data=stream.getvalue()
    digest=sha256(data).hexdigest()
    upload=engine.settings.state_dir/'uploads'/(digest+'.png')
    upload.parent.mkdir(exist_ok=True)
    upload.write_bytes(data)
    request={**params([placement]),'concept':{'id':digest,'button_text':button}}
    rid=service.create(request,mode='real',idempotency_key='pure-create-review')['id']
    service.confirm_baseline(rid,1)
    service.expand_suite(rid,'pure-expand-review')
    run=settled(service,rid)
    master=run['masters'][0]
    assert master['status']=='visual_hold' and '构图需调整' in master['error']
    assert master['visual_review']['first']['body']==('不会的题拍一下' if module=='cta' else '')
    assert master['visual_review']['first']['cta']==''
    assert master['visual_review']['can_recompose'] and not master['visual_review']['can_repair']
    assert run['counts']['completed_outputs']==0 and run['outputs'][0]['status']=='blocked'
    checks=[e for e in executor.events if e[0]=='removal_composition']
    assert [event[2] for event in checks]==[False,True]
    assert all(event[3]==module for event in checks)
    with Image.open(checks[0][1]) as audited:
        assert audited.width*native[1]>audited.height*native[0]
    assert [e[1] for e in executor.events if e[0]=='generate']==['master']
    version=master['version'];signature=master['visual_review']['review_sha256']
    with pytest.raises(UserError):
        service.resolve_visual_review(rid,'master',master['id'],'repair',version,signature,'incorrect-lettering-repair')
    executor.composition_fault=False
    token='manual-recompose-confirmed'
    service.resolve_visual_review(rid,'master',master['id'],'recompose',version,signature,token)
    service.resolve_visual_review(rid,'master',master['id'],'recompose',version,signature,token)
    done=settled(service,rid)
    assert done['status']=='completed' and done['outputs'][0]['version']==2
    assert [e[1] for e in executor.events if e[0]=='generate']==['master','master']
