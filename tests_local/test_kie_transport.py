"""Actual HTTP calls through the production adapter to a loopback KIE stub."""
import io,json,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import pytest
from PIL import Image
from local_app.kie_client import generate
from kie_model import MODEL,GPT_IMAGE_2
import render


@pytest.mark.parametrize('expired',[False,True])
@pytest.mark.parametrize('model',[MODEL,GPT_IMAGE_2])
def test_upload_create_poll_download_and_resume_without_new_task(tmp_path,model,expired):
    png=io.BytesIO();Image.new('RGB',(80,45),'white').save(png,'PNG');image=png.getvalue()
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
         'placement':{'target_width':960,'target_height':540},'base':base,'upload':base,'image_model':model,
         'upload_cache':str(tmp_path/'cache.json'),'stop_marker':str(tmp_path/'STOP'),'query_only':False}
    stages=[]
    try:
        result=generate(job,'fake-local-key',[],stages.append)
        assert result['ok'] and output.read_bytes()==image
        assert requests==['/api/file-base64-upload','/api/v1/jobs/createTask','/api/v1/jobs/recordInfo','/result.png']+(['/api/v1/jobs/recordInfo','/result.png'] if expired else [])
        assert payloads[0]['model']==model and payloads[0]['input']['resolution']=='1K'
        assert payloads[0]['input']['prompt']==job['slot']['prompt']
        assert payloads[0]['input']['input_urls']==[base+'/reference.png']
        assert ('background' in payloads[0]['input'])==(model==MODEL)
        assert {'uploading','submitting','generating','downloading','processing'}<=set(stages)
        # A lost local download resumes the existing receipt; it cannot create again.
        output.unlink();job['query_only']=True;result=generate(job,'fake-local-key',[],stages.append)
        assert result['state']['task_id']=='one-paid-task' and output.read_bytes()==image
        assert requests.count('/api/v1/jobs/createTask')==1
    finally:server.shutdown();server.server_close()
