import copy
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import threading
import time

import pytest
from PIL import Image

from local_app.config import Settings,UserError
from local_app.learning_executor import LearningExecutor,LearningExecutionError
from local_app.learning_pipeline import preview
from local_app.learning_prompts import build
from local_app.scene_planner import ApiScenePlanner,PlanningStopped
from kie_model import GPT_IMAGE_26_FLARE,MODEL
from tests_local.test_learning_setup_api import api
import render


def make_settings(tmp_path):
    settings=Settings(tmp_path/'state',tmp_path/'test.env')
    settings.update({'output_dir':str(tmp_path),'simulation':True})
    return settings


def compiled():
    return build(preview({'t1':'不会的题拍一下','ip':'none','font':'none'},seed='provider-test'),GPT_IMAGE_26_FLARE)


def test_local_rehearsal_has_no_planning_or_image_requests(tmp_path,monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('simulation must never call a provider')
    monkeypatch.setattr(ApiScenePlanner,'_request',forbidden)
    monkeypatch.setattr(render,'request_json',forbidden)
    executor=LearningExecutor(make_settings(tmp_path));plan=compiled()
    scene=executor.plan_scene({'mode':'simulation','params':{'t1':'不会的题拍一下'},'compiled':plan})
    assert set(scene)==set(plan['scene_planning']['output_schema']['properties'])
    assert '本地演练' in scene['communication_goal']
    output=tmp_path/'demo.png'
    result=executor.generate_image({'simulation':True,'kind':'baseline','prompt':'本机演练',
        'aspect_ratio':'16:9','model':GPT_IMAGE_26_FLARE,'output':str(output),
        'allowed_text':{},'content_safe_area':[.1,.1,.9,.9]},threading.Event())
    with Image.open(output) as image:assert image.width*9==image.height*16
    assert result['simulated'] and result['provider_task_id'] is None
    assert not render.task_state_path(output).exists()


def test_rehearsal_versions_are_immutable_and_do_not_become_real_receipts(tmp_path):
    executor=LearningExecutor(make_settings(tmp_path))
    job={'simulation':True,'kind':'baseline','prompt':'演练场景','aspect_ratio':'16:9',
         'model':GPT_IMAGE_26_FLARE,'output':str(tmp_path/'demo.png'),'allowed_text':{}}
    first=executor.generate_image(job);before=Path(job['output']).read_bytes()
    assert executor.generate_image(job)==first
    with pytest.raises(LearningExecutionError,match='不能被不同配置覆盖'):
        executor.generate_image({**job,'prompt':'改变的场景'})
    assert Path(job['output']).read_bytes()==before
    assert not render.task_state_path(Path(job['output'])).exists()


def test_rehearsal_supports_fixed_ratios_even_when_selected_real_model_does_not(tmp_path,monkeypatch):
    monkeypatch.setattr(render,'request_json',lambda *a,**kw:pytest.fail('local rehearsal reached provider'))
    executor=LearningExecutor(make_settings(tmp_path))
    job={'simulation':True,'kind':'baseline','prompt':'演练场景','aspect_ratio':'3:1',
         'model':MODEL,'output':str(tmp_path/'wide-demo.png'),'allowed_text':{}}
    result=executor.generate_image(job)
    with Image.open(result['source']) as image:assert image.width==image.height*3
    assert result['simulated']
    with pytest.raises(UserError,match='不支持冻结母版比例'):
        executor.generate_image({**job,'simulation':False,'output':str(tmp_path/'real.png')})


def test_real_scene_planner_uses_numbered_frozen_images_and_validates_schema(tmp_path,monkeypatch):
    settings=make_settings(tmp_path);settings.planning_key='test-planning-only'
    image=tmp_path/'composition.png';Image.new('RGB',(32,18),'blue').save(image)
    calls=[];plan=compiled();schema=plan['scene_planning']['output_schema']
    answer={name:'已确认场景描述' for name in schema['properties']}
    def request(self,payload,config,stopped):
        calls.append(payload);assert not stopped()
        return {'choices':[{'message':{'content':json.dumps(answer)},'finish_reason':'stop'}]}
    monkeypatch.setattr(ApiScenePlanner,'_request',request)
    run={'mode':'real','params':{'t1':'不会的题拍一下'},'compiled':plan,
         'baseline_reference_bindings':[{'slot':1,'kind':'registered_reference','purpose':'仅参考构图',
            'path':str(image),'sha256':hashlib.sha256(image.read_bytes()).hexdigest()}]}
    result=LearningExecutor(settings).plan_scene(run,threading.Event())
    assert result==answer and len(calls)==1
    content=calls[0]['messages'][1]['content']
    assert '参考图1' in content[1]['text'] and '仅参考构图' in content[1]['text']
    assert content[2]['image_url']['url'].startswith('data:image/png;base64,')
    assert 'test-planning-only' not in json.dumps(calls)
    answer['invented_field']='must not be accepted'
    with pytest.raises(UserError,match='字段'):
        LearningExecutor(settings).plan_scene(run,threading.Event())


@pytest.fixture
def image_server(tmp_path):
    buffer=BytesIO();Image.new('RGB',(300,100),'#c4d6e8').save(buffer,'PNG')
    records=[];payloads=[];control={'waiting':False,'event':None,'expire':False,'create_errors':[],'successful_creates':0,
                                 'on_poll':None,'distinct_upload_urls':False}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def send_image(self):
            if control.get('native_size'):
                image=BytesIO()
                Image.new('RGB',control['native_size'],'white').save(image,'PNG')
                return self.send(image.getvalue(),'image/png')
            return self.send(buffer.getvalue(),'image/png')
        def send(self,value,mime='application/json',status=200):
            raw=json.dumps(value).encode() if mime=='application/json' else value
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_POST(self):
            records.append(self.path);body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/api/file-base64-upload':
                payloads.append(('upload',body))
                url=base+'/reference-'+Path(body['fileName']).stem+'.png' if control['distinct_upload_urls'] else base+'/ref.png'
                self.send({'code':200,'data':{'downloadUrl':url}})
            elif self.path=='/api/v1/jobs/createTask':
                payloads.append(('create',body))
                control['created_at']=int(time.time()*1000)
                if control['create_errors']:
                    error=control['create_errors'].pop(0)
                    if error.get('disconnect'):
                        if error.get('accepted'):control['successful_creates']+=1
                        self.close_connection=True;return
                    self.send({'code':error['code'],'msg':'private test-image-only echoed body',
                               'data':{'taskId':error['task_id']} if error.get('task_id') else None},status=error.get('http_status',200))
                else:
                    control['successful_creates']+=1
                    self.send({'code':200,'data':{'taskId':'one-provider-task'}})
            elif self.path=='/api/v1/common/download-url':
                assert body=={'url':base+'/result.png'}
                assert self.headers['Authorization']=='Bearer test-image-only'
                self.send({'code':200,'data':base+'/temporary.png'})
            else:self.send_error(404)
        def do_GET(self):
            records.append(self.path.split('?')[0])
            if self.path.startswith('/api/v1/jobs/recordInfo?'):
                if control['on_poll']:control['on_poll']()
                if control['waiting'] or control.get('waiting_queries',0)>0:
                    control['waiting_queries']=max(0,control.get('waiting_queries',0)-1)
                    self.send({'code':200,'data':{'state':'generating'}})
                    if control['event']:control['event'].set()
                else:
                    submitted=next((body for kind,body in reversed(payloads) if kind=='create'),None)
                    record={'taskId':'one-provider-task','state':'success','resultJson':json.dumps({'resultUrls':[base+'/result.png']})}
                    if submitted:record.update(param=json.dumps(submitted),model=submitted['model'],createTime=control['created_at'])
                    self.send({'code':200,'data':record})
            elif self.path=='/result.png':
                if control['expire'] and records.count('/result.png')==1:self.send_error(403)
                else:self.send_image()
            elif self.path=='/temporary.png':self.send_image()
            else:self.send_error(404)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);base=f'http://127.0.0.1:{server.server_port}'
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    settings=make_settings(tmp_path);settings.key='test-image-only';settings.base=base;settings.upload=base
    reference=tmp_path/'baseline.png';Image.new('RGB',(48,27),'white').save(reference)
    job={'id':'master-D5','kind':'master','prompt':'只画正文“不会的题拍一下”',
         'aspect_ratio':'3:1','model':GPT_IMAGE_26_FLARE,'output':str(tmp_path/'result.png'),
         'simulation':False,'reference_bindings':[{'slot':1,'kind':'confirmed_baseline','path':str(reference),
             'sha256':hashlib.sha256(reference.read_bytes()).hexdigest()}],
         'poll_timeout':3,'upload_cache':str(tmp_path/'uploads.json')}
    yield LearningExecutor(settings),job,records,payloads,control
    server.shutdown();server.server_close();thread.join(3)


@pytest.mark.parametrize('expired',[False,True])
@pytest.mark.transport
def test_actual_image_adapter_submits_once_and_resumes_existing_receipt(image_server,expired):
    executor,job,records,payloads,control=image_server;control['expire']=expired
    result=executor.generate_image(job,threading.Event())
    assert result['provider_task_id']=='one-provider-task' and not result['simulated']
    assert result['sha256']==hashlib.sha256(Path(result['source']).read_bytes()).hexdigest()
    request=next(body for kind,body in payloads if kind=='create')
    assert request['model']==GPT_IMAGE_26_FLARE and request['input']['aspect_ratio']=='3:1'
    assert request['input']['resolution']=='1K' and request['input']['prompt']==job['prompt']
    assert request['input']['input_urls']==[executor.settings.base+'/ref.png']
    assert 'test-image-only' not in json.dumps(result)
    if expired:
        assert records[-3:]==['/result.png','/api/v1/common/download-url','/temporary.png']
    count=len(records);executor.generate_image(job,threading.Event());assert len(records)==count
    Path(job['output']).unlink();executor.generate_image(job,threading.Event())
    assert records.count('/api/v1/jobs/createTask')==1
    assert records.count('/api/file-base64-upload')==1


@pytest.mark.transport
def test_learning_recovery_without_receipt_never_creates(image_server):
    executor,job,records,_,_=image_server
    with pytest.raises(LearningExecutionError,match='回执缺失') as caught:
        executor.generate_image({**job,'recover_existing':True},threading.Event())
    assert caught.value.query_required
    assert records==[]


@pytest.mark.transport
@pytest.mark.parametrize('outcome',['timeout','attach','legacy_attach','unaccepted'])
def test_learning_baseline_kie_recovery_keeps_one_billable_request(image_server,api,monkeypatch,outcome):
    from local_app.learning_runtime import LearningRuntime
    from tests_local.test_learning_runtime import params, settled

    executor,_,records,_,control=image_server
    engine,request=api
    for attr in ('key','base','upload'):setattr(engine.settings,attr,getattr(executor.settings,attr))
    engine.settings.planning_key='offline-planning'
    control['native_size']=(320,180)
    plan=executor.plan_scene
    monkeypatch.setattr(executor,'plan_scene',lambda run,event:plan({**run,'mode':'simulation'},event))
    if outcome=='timeout':
        generate=executor.generate_image
        monkeypatch.setattr(executor,'generate_image',lambda job,event:generate({**job,'poll_timeout':.20},event))
        monkeypatch.setattr(render,'QUERY_RETRY_DELAYS',(.02,.03))
        control['waiting_queries']=1
    else:
        control['create_errors']=[{'disconnect':True,'accepted':outcome!='unaccepted'}]
    service=LearningRuntime(engine,executor)
    engine.learning_runtime=service
    try:
        status,created=request('/api/learning-machine/runs','POST',{'params':params(['learning-ruishi-rect-580x320']),
                                                                    'idempotency_key':'kie-recovery-create'})
        assert status==200,created
        rid=created['id'];base='/api/learning-machine/runs/'+rid
        assert request(base+'/baseline','POST',{'idempotency_key':'kie-recovery-first'})[0]==200
        run=settled(service,rid)
        if outcome!='timeout':
            assert run['baseline']['submission_unverified'] and records.count('/api/v1/jobs/createTask')==1
            reconcile={'kind':'baseline','image_id':'baseline','expected_version':1,'idempotency_key':'kie-recovery-major'}
            route=base+'/kie-receipt'
            if outcome=='unaccepted':
                assert request(route,'POST',{**reconcile,'action':'confirm_unaccepted'})[0]==400
                status,value=request(route,'POST',{**reconcile,'action':'confirm_unaccepted','confirmed_unaccepted':True})
            else:
                if outcome=='legacy_attach':
                    path=render.task_state_path(Path(service.runs[rid]['baseline']['raw_path']))
                    old=render.load_task_state(path);old.pop('submission_signature')
                    render.atomic_write_json(path,old)
                wrong_status,wrong=request(route,'POST',{**reconcile,'action':'attach','task_id':'wrong-task'})
                assert wrong_status==409 and '不一致' in wrong['message_zh']
                assert records.count('/api/v1/jobs/createTask')==1
                status,value=request(route,'POST',{**reconcile,'action':'attach','task_id':'one-provider-task'})
            assert status==200,value
            run=settled(service,rid)
        assert run['baseline']['status']=='done',run.get('error')
        assert run['baseline']['version']==1
        assert records.count('/api/file-base64-upload')==1
        assert records.count('/api/v1/jobs/createTask')==(2 if outcome=='unaccepted' else 1)
        assert control['successful_creates']==1
        if outcome=='timeout':
            assert records.count('/api/v1/jobs/recordInfo')==2
    finally:
        service.close()


@pytest.mark.transport
def test_changed_prompt_cannot_replace_existing_provider_execution(image_server):
    executor,job,records,_,_=image_server
    executor.generate_image(job);before=list(records)
    changed={**job,'prompt':'不同文案'}
    with pytest.raises(LearningExecutionError) as error:executor.generate_image(changed)
    assert error.value.reason_code=='fingerprint_mismatch' and error.value.query_required
    assert records==before


@pytest.mark.transport
def test_uncertain_submission_has_no_second_create_or_upload(image_server):
    executor,job,records,_,_=image_server
    render.atomic_write_json(render.task_state_path(Path(job['output'])),{
        'status':'submit_uncertain','fingerprint':'retained','attempt_history':[],'timeout_restarts':0})
    with pytest.raises(LearningExecutionError) as error:executor.generate_image(job)
    assert error.value.query_required and error.value.state['status']=='submit_uncertain'
    assert records==[]


@pytest.mark.transport
def test_cancellation_preserves_task_and_next_attempt_only_queries(image_server):
    executor,job,records,_,control=image_server
    event=threading.Event();control.update(waiting=True,event=event)
    with pytest.raises(PlanningStopped):executor.generate_image(job,event)
    receipt=render.load_task_state(render.task_state_path(Path(job['output'])))
    assert receipt['task_id']=='one-provider-task' and not Path(job['output']).exists()
    control.update(waiting=False,event=None)
    executor.generate_image(job,threading.Event())
    assert records.count('/api/v1/jobs/createTask')==1


@pytest.mark.transport
def test_cancel_immediately_before_create_is_retryable_without_an_uncertain_receipt(image_server,monkeypatch):
    executor,job,records,_,_=image_server;event=threading.Event()
    original=render.atomic_write_json
    def persist(path,value):
        original(path,value)
        if value.get('status')=='submitting':event.set()
    monkeypatch.setattr(render,'atomic_write_json',persist)
    with pytest.raises(PlanningStopped):executor.generate_image(job,event)
    assert records==['/api/file-base64-upload']
    assert not render.task_state_path(Path(job['output'])).exists()
    monkeypatch.setattr(render,'atomic_write_json',original)
    executor.generate_image(job,threading.Event())
    assert records.count('/api/v1/jobs/createTask')==1


@pytest.mark.transport
def test_no_reference_baseline_uses_explicit_neutral_canvas(image_server):
    executor,job,_,payloads,_=image_server
    job={**job,'kind':'baseline','reference_bindings':[]}
    result=executor.generate_image(job)
    request=next(body for kind,body in payloads if kind=='create')
    assert '纯白画幅辅助图' in request['input']['prompt']
    assert result['actual_prompt']==request['input']['prompt']
    assert result['reference_bindings'][0]['kind']=='neutral_canvas'
    neutral=Path(job['output']).with_suffix('.neutral-reference.png')
    with Image.open(neutral) as image:
        assert image.width==image.height*3 and image.getpixel((0,0))==(255,255,255)


@pytest.mark.transport
def test_wrong_first_reference_or_changed_frozen_asset_never_reaches_provider(image_server):
    executor,job,records,_,_=image_server
    changed=copy.deepcopy(job);changed['reference_bindings'][0]['kind']='previous_master'
    with pytest.raises(UserError,match='已确认基准图'):executor.generate_image(changed)
    changed=copy.deepcopy(job);changed['reference_bindings'][0]['sha256']='0'*64
    with pytest.raises(UserError,match='校验失败'):executor.generate_image(changed)
    assert records==[]


@pytest.mark.parametrize('http_status,code,reason',[
    (429,429,'rate_limited'),(200,429,'rate_limited'),
    (401,401,'authentication_failed'),(200,402,'insufficient_credits'),
])
@pytest.mark.transport
def test_explicit_provider_rejection_is_retryable_without_a_second_successful_create(image_server,http_status,code,reason):
    executor,job,records,_,control=image_server
    control['create_errors']=[{'http_status':http_status,'code':code}]
    with pytest.raises(LearningExecutionError) as error:executor.generate_image(job)
    assert error.value.reason_code==reason and not error.value.query_required
    assert 'test-image-only' not in str(error.value)
    state=render.load_task_state(render.task_state_path(Path(job['output'])))
    assert state['status']=='rejected' and state['definite_rejection'] is True and not state.get('task_id')
    assert state['http_status']==(http_status if http_status!=200 else None)
    assert state['provider_code']==(code if http_status==200 else None)
    assert records.count('/api/v1/jobs/createTask')==1 and control['successful_creates']==0
    result=executor.generate_image(job)
    assert result['provider_task_id']=='one-provider-task'
    assert records.count('/api/v1/jobs/createTask')==2 and control['successful_creates']==1
    assert records.count('/api/file-base64-upload')==1


@pytest.mark.parametrize('http_status,code',[(500,500),(200,500)])
@pytest.mark.transport
def test_ambiguous_create_failure_stays_unknown_and_never_retries_submission(image_server,http_status,code):
    executor,job,records,_,control=image_server
    control['create_errors']=[{'http_status':http_status,'code':code}]
    with pytest.raises(LearningExecutionError) as error:executor.generate_image(job)
    assert error.value.query_required and error.value.reason_code=='unknown'
    count=len(records)
    with pytest.raises(LearningExecutionError) as again:executor.generate_image(job)
    assert again.value.query_required
    assert len(records)==count and records.count('/api/v1/jobs/createTask')==1


@pytest.mark.transport
def test_429_with_a_provider_task_id_is_only_resumed_not_resubmitted(image_server):
    executor,job,records,_,control=image_server
    control['create_errors']=[{'http_status':429,'code':429,'task_id':'one-provider-task'}]
    with pytest.raises(LearningExecutionError) as error:executor.generate_image(job)
    assert error.value.query_required and error.value.state['task_id']=='one-provider-task'
    state=render.load_task_state(render.task_state_path(Path(job['output'])))
    assert state['status']=='waiting'
    assert executor.generate_image(job)['provider_task_id']=='one-provider-task'
    assert records.count('/api/v1/jobs/createTask')==1


@pytest.mark.transport
def test_create_connection_loss_remains_unknown_and_cannot_be_resubmitted(image_server):
    executor,job,records,_,control=image_server
    control['create_errors']=[{'disconnect':True}]
    with pytest.raises(LearningExecutionError) as error:executor.generate_image(job)
    assert error.value.query_required and error.value.reason_code=='unknown'
    count=len(records)
    with pytest.raises(LearningExecutionError) as again:executor.generate_image(job)
    assert again.value.query_required and len(records)==count
    assert records.count('/api/v1/jobs/createTask')==1


def background_job(image_server,tmp_path):
    """Use the production guide builder, not a hand-written lookalike job."""
    from local_app.learning_background import prepare_job
    _,initial,_,_,control=image_server
    source=Path(initial['reference_bindings'][0]['path'])
    job=prepare_job({'mode':'real','params':{'image_model':GPT_IMAGE_26_FLARE}},source,
                    tmp_path/'backgrounds'/'one-operation'/'native.png',1400,340,
                    allowed_text={'t1':'不会的题拍一下'})
    job.update(id='background-'+job['reuse_key'],upload_cache=initial['upload_cache'],poll_timeout=1)
    control['distinct_upload_urls']=True
    return job


@pytest.mark.transport
def test_background_guide_first_job_resumes_after_known_task_timeout_without_creating_again(image_server,tmp_path,monkeypatch):
    from types import SimpleNamespace
    import local_app.learning_executor as boundary
    executor,_,records,payloads,control=image_server
    job=background_job(image_server,tmp_path);original_job=copy.deepcopy(job)
    assert [r['kind'] for r in job['reference_bindings']]==['adaptation_canvas','source_picture']
    original_time=boundary.time;expired=[False]
    clock=SimpleNamespace(time=original_time.time,sleep=original_time.sleep,
                          monotonic=lambda:original_time.monotonic()+(60 if expired[0] else 0))
    monkeypatch.setattr(boundary,'time',clock)
    # Advance only after a real local HTTP query has observed the already
    # created task, so the timeout boundary is deterministic and has no sleeps.
    control.update(waiting=True,on_poll=lambda:expired.__setitem__(0,True))
    with pytest.raises(LearningExecutionError) as error:executor.generate_image(job,threading.Event())
    assert error.value.query_required and error.value.state['task_id']=='one-provider-task'
    receipt=render.load_task_state(render.task_state_path(Path(job['output'])))
    assert receipt['task_id']=='one-provider-task' and not Path(job['output']).exists()
    assert records.count('/api/v1/jobs/createTask')==1 and records.count('/api/v1/jobs/recordInfo')==1
    request=next(value for kind,value in payloads if kind=='create')
    expected_urls=[executor.settings.base+'/reference-'+ref['sha256']+'.png' for ref in job['reference_bindings']]
    assert request['input']['input_urls']==expected_urls
    assert request['input']['prompt']==job['prompt'] and request['input']['aspect_ratio']==job['aspect_ratio']
    expired[0]=False;control.update(waiting=False,on_poll=None)
    result=executor.generate_image(job,threading.Event())
    assert result['provider_task_id']=='one-provider-task'
    assert [r['kind'] for r in result['reference_bindings']]==['adaptation_canvas','source_picture']
    assert records.count('/api/v1/jobs/createTask')==1
    assert records.count('/api/file-base64-upload')==2  # Guide and source once each.
    assert control['successful_creates']==1 and job==original_job
    assert all(hashlib.sha256(Path(r['path']).read_bytes()).hexdigest()==r['sha256'] for r in job['reference_bindings'])


@pytest.mark.transport
@pytest.mark.parametrize('status',['submitting','submit_uncertain'])
def test_background_submission_without_task_id_cannot_be_blindly_recreated(image_server,tmp_path,status):
    executor,_,records,_,_=image_server
    job=background_job(image_server,tmp_path)
    fingerprint=render.request_fingerprint(job['model'],job['prompt'],
        [Path(r['path']) for r in job['reference_bindings']],job['aspect_ratio'],'1K')
    render.atomic_write_json(render.task_state_path(Path(job['output'])),{
        'status':status,'fingerprint':fingerprint,'model':job['model'],'attempt_history':[],'timeout_restarts':0})
    for _ in range(2):
        with pytest.raises(LearningExecutionError) as error:executor.generate_image(job,threading.Event())
        assert error.value.query_required and error.value.state['status']==status
    assert records==[] and not Path(job['output']).exists()


@pytest.mark.transport
@pytest.mark.parametrize('invalid',['order','missing_guide','missing_plan','ratio','guide_size','source_size'])
def test_background_reference_roles_and_frozen_geometry_are_checked_before_upload(image_server,tmp_path,invalid):
    executor,_,records,_,_=image_server
    job=background_job(image_server,tmp_path)
    if invalid=='order':
        job['reference_bindings']=[{**ref,'slot':index} for index,ref in enumerate(reversed(job['reference_bindings']),1)]
    elif invalid=='missing_guide':job['reference_bindings']=[{**job['reference_bindings'][1],'slot':1}]
    elif invalid=='missing_plan':job.pop('background_plan')
    elif invalid=='ratio':job['background_plan']['aspect_ratio']='2:1'
    else:job['background_plan'][invalid]=[1,1]
    with pytest.raises(UserError,match='背景扩展'):executor.generate_image(job,threading.Event())
    assert records==[]
    assert not Path(job['output']).exists() and not render.task_state_path(Path(job['output'])).exists()


def canvas_job(image_server,tmp_path):
    from local_app import master_canvas
    _,initial,_,_,control=image_server
    source=Path(initial['reference_bindings'][0]['path'])
    group=master_canvas.plan([{'id':'wide','width':1200,'height':400,
                              'allowed_text':{'t1':'不会的题拍一下'}}],GPT_IMAGE_26_FLARE)['groups'][0]
    guide=master_canvas.build_guide(source,tmp_path/'canvas-guide.png',group)
    control['distinct_upload_urls']=True
    return {'id':group['id'],'kind':'shared_canvas_master','model':GPT_IMAGE_26_FLARE,
        'aspect_ratio':group['aspect_ratio'],'output':str(tmp_path/'canvas-native.png'),'simulation':False,
        'prompt':master_canvas.repair_prompt(group['allowed_text'],group),'canvas_plan':group,
        'reference_bindings':[{'slot':1,'kind':'canvas_guide','path':guide['path'],'sha256':guide['sha256']},
                              {**initial['reference_bindings'][0],'slot':2,'kind':'source_picture'}],
        'upload_cache':initial['upload_cache'],'poll_timeout':3,'allowed_text':group['allowed_text']}


@pytest.mark.transport
def test_shared_full_canvas_request_keeps_guide_first_without_changing_prompt(image_server,tmp_path):
    executor,_,records,payloads,_=image_server;job=canvas_job(image_server,tmp_path)
    result=executor.generate_image(job)
    request=next(value for kind,value in payloads if kind=='create')
    assert request['input']['prompt']==job['prompt']
    assert request['input']['input_urls']==[executor.settings.base+'/reference-'+r['sha256']+'.png' for r in job['reference_bindings']]
    assert result['reference_bindings'][0]['kind']=='canvas_guide'
    assert records.count('/api/v1/jobs/createTask')==1


@pytest.mark.transport
@pytest.mark.parametrize('invalid',['order','missing_guide','missing_plan','ratio','guide_size','guide_pixels'])
def test_shared_canvas_role_and_native_geometry_guards_reject_before_network(image_server,tmp_path,invalid):
    executor,_,records,_,_=image_server;job=canvas_job(image_server,tmp_path)
    if invalid=='order':job['reference_bindings']=[{**r,'slot':i} for i,r in enumerate(reversed(job['reference_bindings']),1)]
    elif invalid=='missing_guide':job['reference_bindings']=[{**job['reference_bindings'][1],'slot':1}]
    elif invalid=='missing_plan':job.pop('canvas_plan')
    elif invalid=='ratio':job['canvas_plan']['aspect_ratio']='2:1'
    elif invalid=='guide_size':job['canvas_plan']['guide_size']=[12,12]
    else:
        guide=Path(job['reference_bindings'][0]['path']);Image.new('RGB',(30,11),'white').save(guide)
        job['reference_bindings'][0]['sha256']=hashlib.sha256(guide.read_bytes()).hexdigest()
        job['canvas_plan']['guide_size']=[30,11]
    with pytest.raises(UserError,match='共享母版'):executor.generate_image(job)
    assert records==[] and not render.task_state_path(Path(job['output'])).exists()
