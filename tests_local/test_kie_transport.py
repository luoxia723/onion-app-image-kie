"""Actual HTTP calls through the production adapter to a loopback KIE stub."""
import io,json,threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import pytest
from PIL import Image
from local_app.kie_client import generate
from kie_model import MODEL,GPT_IMAGE_2,GPT_IMAGE_26_FLARE
import render
from types import SimpleNamespace

pytestmark=pytest.mark.transport


def test_known_timeout_cannot_create_a_replacement_even_with_legacy_limit(tmp_path,monkeypatch):
    state={'task_id':'existing-task','status':'generating'}
    def poll(*args,**kwargs):
        assert args[2]=='existing-task'
        state.update(status='poll_timeout',timeout_confirmed=True)
        raise render.GenerationTimeout('offline timeout')
    def fail(*args,**kwargs):
        pytest.fail('A timeout must never upload references or create a replacement')
    monkeypatch.setattr(render,'poll_task',poll)
    args=SimpleNamespace(image_model=MODEL,retries=1,poll_timeout=240,max_timeout_restarts=1)
    with pytest.raises(render.GenerationTimeout):
        render.obtain_result(args,'https://unused.invalid','https://unused.invalid','test-only','prompt',[],
            'identity',tmp_path/'receipt.json',state,'16:9','1K',request_fn=fail,upload_fn=fail)
    assert state['task_id']=='existing-task'


@pytest.mark.parametrize('host,proxy,expected',[
    ('api.kie.ai','http://127.0.0.1:7897','direct'),
    ('api.kie.ai','http://proxy.example.invalid:8080','normal'),
    ('custom-kie.example.invalid','http://127.0.0.1:7897','normal'),
])
def test_only_kie_official_api_bypasses_the_loopback_proxy(monkeypatch,host,proxy,expected):
    calls=[]
    def opened(route):
        def exchange(request,*,timeout):
            calls.append(route)
            return io.BytesIO(b'{"code":200}')
        return exchange
    def opener(handler):
        assert handler.proxies=={}
        return SimpleNamespace(open=opened('direct'))
    monkeypatch.setattr(render.urllib.request,'getproxies',lambda:{'https':proxy})
    monkeypatch.setattr(render.urllib.request,'urlopen',opened('normal'))
    monkeypatch.setattr(render.urllib.request,'build_opener',opener)
    request=render.build_status_request('https://'+host,'fixture-key','receipt')
    assert render.request_json(request,1)=={'code':200}
    assert calls==[expected]


@pytest.mark.parametrize('stop_waiting',[False,True])
def test_ximalaya_serializes_create_acknowledgements_without_blocking_polling(tmp_path,monkeypatch,stop_waiting):
    first_sent=threading.Event();allow_first_ack=threading.Event();first_polling=threading.Event()
    second_prepared=threading.Event();second_sent=threading.Event();allow_first_finish=threading.Event()
    saving_first_receipt=threading.Event();allow_first_receipt=threading.Event()
    original_request=render.build_create_request
    original_save=render.atomic_write_json
    first_receipt=render.task_state_path(tmp_path/'first.png')
    second_receipt=render.task_state_path(tmp_path/'second.png')
    ref=tmp_path/'root.png';Image.new('RGB',(80,45),'white').save(ref)

    def prepare(*args,**kwargs):
        if args[2]=='second':second_prepared.set()
        return original_request(*args,**kwargs)

    def request(req,*args,**kwargs):
        if req.full_url.endswith('/createTask'):
            name=json.loads(req.data)['input']['prompt']
            if name=='first':
                first_sent.set();assert allow_first_ack.wait(5)
            else:second_sent.set()
            return {'data':{'taskId':name}}
        if req.full_url.endswith('taskId=first'):
            first_polling.set();assert allow_first_finish.wait(5)
        return {'data':{'state':'success','resultJson':'{"resultUrls":["https://unused.invalid/result"]}'}}

    def save(path,state):
        if path==first_receipt and state.get('task_id')=='first' and state['status']=='waiting':
            saving_first_receipt.set();assert allow_first_receipt.wait(5)
        return original_save(path,state)

    monkeypatch.setattr(render,'build_create_request',prepare)
    monkeypatch.setattr(render,'request_json',request)
    monkeypatch.setattr(render,'atomic_write_json',save)
    monkeypatch.setattr(render,'upload_references',lambda *args,**kwargs:['https://unused.invalid/reference.png'])
    monkeypatch.setattr(render,'download_image',lambda url,path:Image.new('RGB',(80,45),'white').save(path))
    def run(name):
        job={'slot':{'idx':1,'refs':[{'label':'参考图1','path':str(ref),'role':'首图'}],
                     'prompt':name,'prompt_origin':'manual','output':str(tmp_path/(name+'.png')),'ximalaya_source':'one-base'},
             'placement':{'target_width':960,'target_height':540},'base':'https://unused.invalid','upload':'https://unused.invalid',
             'image_model':MODEL,'upload_cache':str(tmp_path/'cache.json'),'stop_marker':str(tmp_path/'STOP'),'query_only':False}
        return generate(job,'fixture-key',[],lambda stage:None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(run,'first')
        try:
            assert first_sent.wait(5)
            second=pool.submit(run,'second')
            assert second_prepared.wait(5)
            assert not second_sent.wait(.25)
            assert not second_receipt.exists()
            allow_first_ack.set()
            assert saving_first_receipt.wait(5)
            assert not second_sent.wait(.25)
            assert not second_receipt.exists()
            if stop_waiting:(tmp_path/'STOP').touch()
            allow_first_receipt.set()
            assert first_polling.wait(5)
            assert render.load_task_state(first_receipt)['task_id']=='first'
            if stop_waiting:
                with pytest.raises(RuntimeError,match='onion_stopped'):second.result(timeout=5)
                assert not second_sent.is_set() and not second_receipt.exists()
            else:
                assert second_sent.wait(5)
                assert second.result(timeout=5)['ok'] and not first.done()
        finally:
            allow_first_ack.set();allow_first_receipt.set();allow_first_finish.set()
        assert first.result(timeout=5)['ok']


def test_create_connection_reset_reports_type_without_retrying(monkeypatch):
    calls=[]
    def disconnect(request,*,timeout):
        calls.append(request)
        raise ConnectionResetError(54,'socket closed')
    monkeypatch.setattr(render.urllib.request,'urlopen',disconnect)
    request=render.build_create_request('https://unused.invalid','fixture-key','测试','1:1','1K',
                                        ['https://unused.invalid/reference.png'])
    with pytest.raises(render.KieError) as failure:
        render.request_json(request,1,operation='create KIE image task',retry_network=False)
    assert calls==[request]
    assert failure.value.uncertain_submit
    assert failure.value.transport_error=='ConnectionResetError' and failure.value.transport_errno==54


@pytest.mark.parametrize('error,expected',[
    (render.KieError('限流',provider_code=429),'rate_limited'),
    (render.KieError('返回任务号',http_status=429,provider_task_id='original-task'),'waiting'),
    (render.KieError('积分不足',provider_code=402),'rejected'),
    (render.KieError('连接中断',uncertain_submit=True,transport_error='ConnectionResetError',transport_errno=54),'submit_uncertain'),
])
def test_create_errors_record_recoverable_receipt_without_a_second_post(tmp_path,error,expected):
    receipt=tmp_path/'receipt.json';posts=[]
    def request(req,*args,**kwargs):
        posts.append(req.full_url)
        raise error
    args=SimpleNamespace(image_model=MODEL,retries=1,poll_timeout=240,max_timeout_restarts=0)
    with pytest.raises(render.KieError):
        render.obtain_result(args,'https://unused.invalid','https://unused.invalid','fixture-key','测试',[],
                             'fingerprint',receipt,{},'1:1','1K',request_fn=request,
                             upload_fn=lambda *a,**kw:['https://unused.invalid/reference.png'])
    state=render.load_task_state(receipt)
    assert state['status']==expected
    assert len(posts)==1 and posts[0].endswith('/createTask')
    assert state.get('task_id')==error.provider_task_id
    if expected=='submit_uncertain':
        assert state['transport_error']=='ConnectionResetError' and state['transport_errno']==54


@pytest.mark.parametrize('expired',[False,True,'missing_endpoint'])
@pytest.mark.parametrize('model',[MODEL,GPT_IMAGE_2,GPT_IMAGE_26_FLARE])
@pytest.mark.parametrize('natural',[False,True])
def test_upload_create_poll_download_and_resume_without_new_task(tmp_path,model,expired,natural):
    from local_app import natural_canvas
    placement={'id':'transport-natural','image_form':'单图','target_width':1200 if natural else 960,'target_height':480 if natural else 540}
    canvas=natural_canvas.plan(placement,model) if natural else None
    native_size=canvas['group']['guide_size'] if natural else (80,45)
    png=io.BytesIO();Image.new('RGB',native_size,'white').save(png,'PNG');image=png.getvalue()
    requests=[];payloads=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def send(self,data,content_type='application/json'):
            raw=json.dumps(data).encode() if content_type=='application/json' else data
            self.send_response(200);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_POST(self):
            requests.append(urlsplit(self.path).path);body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/api/file-base64-upload':
                assert body['base64Data'].startswith('data:image/png;base64,');self.send({'code':200,'data':{'downloadUrl':base+'/reference.png'}})
            elif self.path=='/api/v1/jobs/createTask':
                payloads.append(body);self.send({'code':200,'data':{'taskId':'one-paid-task'}})
            elif self.path=='/api/v1/common/download-url':
                assert body=={'url':base+'/result.png'}
                assert self.headers['Authorization']=='Bearer fake-local-key'
                if expired=='missing_endpoint':self.send_error(404)
                else:self.send({'code':200,'data':base+'/temporary.png'})
            else:self.send_error(404)
        def do_GET(self):
            requests.append(urlsplit(self.path).path)
            if self.path.startswith('/api/v1/jobs/recordInfo?'):
                self.send({'code':200,'data':{'state':'success','resultJson':json.dumps({'resultUrls':[base+'/result.png']})}})
            elif self.path=='/result.png':
                if expired and requests.count('/result.png')==1:self.send_error(403)
                else:self.send(image,'image/png')
            elif self.path=='/temporary.png':self.send(image,'image/png')
            else:self.send_error(404)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);base='http://127.0.0.1:'+str(server.server_port)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    ref=tmp_path/'reference.png';ref.write_bytes(image);output=tmp_path/'result.png'
    job={'slot':{'idx':1,'refs':[{'label':'参考图1','path':str(ref),'role':'参考素材'}],
                 'prompt':'主标题："真实调用链"\n自由编辑','prompt_origin':'manual','output':str(output)},
         'placement':placement,'base':base,'upload':base,'image_model':model,
         'upload_cache':str(tmp_path/'cache.json'),'stop_marker':str(tmp_path/'STOP'),'query_only':False}
    if natural:
        job['slot']['natural_canvas_plan']=canvas
        job['slot']['prompt']+='\n'+natural_canvas.prompt_rule(canvas)
    stages=[]
    try:
        result=generate(job,'fake-local-key',[],stages.append)
        assert result['ok'] and output.read_bytes()==image
        expected=['/api/file-base64-upload','/api/v1/jobs/createTask','/api/v1/jobs/recordInfo','/result.png']
        if expired:
            expected+=['/api/v1/common/download-url']
            expected+=['/api/v1/jobs/recordInfo','/result.png'] if expired=='missing_endpoint' else ['/temporary.png']
        assert requests==expected
        assert payloads[0]['model']==model and payloads[0]['input']['resolution']=='1K'
        assert payloads[0]['input']['prompt']==job['slot']['prompt']
        assert payloads[0]['input']['input_urls']==[base+'/reference.png']
        if natural:
            assert payloads[0]['input']['aspect_ratio']==canvas['group']['aspect_ratio']
            assert '蓝框' not in payloads[0]['input']['prompt']
            cropped=tmp_path/'exact.png';natural_canvas.crop(output,cropped,canvas,placement)
            with Image.open(cropped) as exact:assert exact.size==(1200,480)
        assert ('background' in payloads[0]['input'])==(model!=GPT_IMAGE_2)
        if model == GPT_IMAGE_26_FLARE:
            assert 'output_format' not in payloads[0]['input']
        assert {'uploading','submitting','generating','downloading','processing'}<=set(stages)
        # A lost local download resumes the existing receipt; it cannot create again.
        output.unlink();job['query_only']=True;job['placement']['category']='学习机';result=generate(job,'fake-local-key',[],stages.append)
        assert result['state']['task_id']=='one-paid-task' and output.read_bytes()==image
        assert requests.count('/api/v1/jobs/createTask')==1
    finally:server.shutdown();server.server_close()
