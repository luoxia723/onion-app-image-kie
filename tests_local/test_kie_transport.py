"""Actual HTTP calls through the production adapter to a loopback KIE stub."""
import io,json,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import pytest
from PIL import Image
from local_app.kie_client import generate
from kie_model import MODEL,GPT_IMAGE_2,GPT_IMAGE_26_FLARE
import render

pytestmark=pytest.mark.transport


@pytest.mark.parametrize('expired',[False,True])
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
            else:self.send_error(404)
        def do_GET(self):
            requests.append(urlsplit(self.path).path)
            if self.path.startswith('/api/v1/jobs/recordInfo?'):
                self.send({'code':200,'data':{'state':'success','resultJson':json.dumps({'resultUrls':[base+'/result.png']})}})
            elif self.path=='/result.png':
                if expired and requests.count('/result.png')==1:self.send_error(403)
                else:self.send(image,'image/png')
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
        assert requests==['/api/file-base64-upload','/api/v1/jobs/createTask','/api/v1/jobs/recordInfo','/result.png']+(['/api/v1/jobs/recordInfo','/result.png'] if expired else [])
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
