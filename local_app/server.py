from __future__ import annotations
import argparse
import base64
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import build_opener, ProxyHandler
import uuid
import webbrowser
from PIL import Image
from .config import ROOT, Settings, UserError, https_base
from .engine import Engine, digest
from .scene_planner import ApiScenePlanner
from .planning import ASSETS, BY_ID, bootstrap
from .quality import verify_saved_package
import render

class Handler(BaseHTTPRequestHandler):
    server_version='OnionLocal/1.0'
    def log_message(self,*args): pass

    @property
    def engine(self): return self.server.engine

    def json(self,value,status=200):
        data=json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers();self.wfile.write(data)

    def body(self):
        if self.headers.get('X-Onion-Request')!='1': raise UserError('请求来源无效，请刷新页面',403)
        if not self.headers.get('Content-Type','').startswith('application/json'): raise UserError('请求格式不正确',415)
        try: length=int(self.headers.get('Content-Length','0'))
        except ValueError: raise UserError('请求格式不正确')
        if length>15*1024*1024: raise UserError('上传文件超过 10MB',413)
        try: value=json.loads(self.rfile.read(length) or b'{}')
        except (ValueError,UnicodeError): raise UserError('请求格式不正确')
        if not isinstance(value,dict): raise UserError('请求格式不正确')
        return value

    def file(self,path,download=None):
        path=Path(path)
        if not path.is_file(): raise UserError('文件不存在',404)
        self.send_response(200)
        self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        self.send_header('Content-Length',str(path.stat().st_size))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-store')
        if download:
            from urllib.parse import quote
            self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(download))
        self.end_headers()
        with path.open('rb') as f:
            while block:=f.read(65536): self.wfile.write(block)

    def handle_api(self):
        host=self.headers.get('Host','')
        expected=f'127.0.0.1:{self.server.server_port}'
        if host not in (expected,f'localhost:{self.server.server_port}'): raise UserError('请求来源无效',403)
        origin=self.headers.get('Origin')
        if origin and origin not in ('http://'+expected,f'http://localhost:{self.server.server_port}'): raise UserError('请求来源无效',403)
        split=urlsplit(self.path)
        path=unquote(split.path)
        if any(x in path.split('/') for x in ('..','.env')) or '\\' in path or '\x00' in path: raise UserError('文件不存在',404)
        query=parse_qs(split.query)
        get=lambda k,default='':query.get(k,[default])[0]
        method=self.command
        body=self.body() if method in ('POST','PUT','PATCH','DELETE') else {}
        settings=self.engine.settings
        if path in ('/api/workbench/items','/api/workbench/packages') and method=='GET':
            from . import workspace
            try:limit=int(get('limit','20'))
            except ValueError:raise UserError('分页数量不正确') from None
            options=dict(q=get('q'),kind=get('kind'),cursor=get('cursor'),limit=limit)
            if path.endswith('/items'):options['state']=get('state')
            return self.json((workspace.items if path.endswith('/items') else workspace.packages)(self.engine,self.learning_runtime(),**options))
        workspace_package=re.fullmatch(r'/api/workbench/packages/(task|run)/([a-f0-9]{32})/([a-f0-9]{32})(?:/images/([0-9]{1,5}))?',path)
        if workspace_package and method=='GET':
            from . import workspace
            source,sid,pid,index=workspace_package.groups()
            if index is None:return self.json(workspace.package_details(self.engine,self.learning_runtime(),source,sid,pid))
            data,mime=workspace.package_image(self.engine,self.learning_runtime(),source,sid,pid,int(index))
            self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data);return
        if path=='/api/health' and method=='GET': return self.json({'ok':True,'simulation':not settings.real})
        if path=='/api/bootstrap' and method=='GET':
            value=bootstrap();value['form_defaults']=self.engine.document('form_defaults');value['planner']=self.engine.planner.status();product=self.engine.product();value['product']={**product,'configured':bool(product['text'])};return self.json(value)
        if path=='/api/learning-machine/config' and method=='GET':
            from .learning_setup import public_config
            return self.json(public_config(self.engine))
        if path=='/api/logo-templates' and method in ('GET','PUT'):
            from . import logo_templates
            return self.json(logo_templates.public_config(self.engine) if method=='GET' else logo_templates.save_templates(self.engine,body))
        if path=='/api/learning-machine/logo-templates' and method=='PUT':
            from .learning_setup import save_logo_templates
            return self.json(save_logo_templates(self.engine,body))
        if path=='/api/learning-machine/preview' and method=='POST':
            from .learning_setup import save_and_preview
            return self.json(save_and_preview(self.engine,body.get('params')))
        if path=='/api/master-canvases' and method=='POST':
            return self.json(self.learning_runtime().create_shared_canvas(
                {k:v for k,v in body.items() if k!='idempotency_key'},body.get('idempotency_key')))
        if path=='/api/learning-machine/runs':
            runtime=self.learning_runtime()
            if method=='GET':return self.json({'runs':runtime.list()})
            if method=='POST':
                if body.get('mode','real')!='real':raise UserError('学习机新任务仅支持正式制作')
                return self.json(runtime.create(body.get('params'),mode='real',idempotency_key=body.get('idempotency_key')))
        learning_run=re.fullmatch(r'/api/learning-machine/runs/([a-f0-9]{32})(?:/(.*))?',path)
        if learning_run:
            runtime=self.learning_runtime();rid,action=learning_run.groups()
            if method=='GET' and not action:
                revision=get('revision')
                if revision and not re.fullmatch(r'[0-9]{1,20}',revision):raise UserError('任务修订号不正确')
                return self.json(runtime.get(rid,revision=int(revision) if revision else None))
            if method=='POST' and action=='baseline':return self.json(runtime.generate_baseline(rid,idempotency_key=body.get('idempotency_key'),resume=body.get('resume',False)))
            if method=='POST' and action=='confirm':return self.json(runtime.confirm_baseline(rid,body.get('baseline_version')))
            if method=='POST' and action=='expand':return self.json(runtime.expand_suite(rid,idempotency_key=body.get('idempotency_key')))
            if method=='POST' and action=='from-baseline':
                if runtime.get(rid)['mode']!='real':
                    raise UserError('请选择正式制作的基准图',409)
                return self.json(runtime.create_from_confirmed_baseline(rid,idempotency_key=body.get('idempotency_key'),pids=body.get('pids')))
            if method=='POST' and action=='refresh-logos':
                return self.json(runtime.refresh_logos(rid,body.get('idempotency_key'),body.get('placement_ids')))
            if method=='POST' and action=='repair-backgrounds':
                return self.json(runtime.repair_backgrounds(rid,body.get('idempotency_key'),body.get('output_ids'),force_ai=body.get('force_ai',False)))
            canvas_retry=re.fullmatch(r'masters/([^/]+)/regenerate',action or '')
            if method=='POST' and canvas_retry:
                return self.json(runtime.regenerate_canvas_master(rid,unquote(canvas_retry.group(1)),body.get('idempotency_key'),body.get('expected_version')))
            redraw=re.fullmatch(r'outputs/([^/]+)/regenerate',action or '')
            if method=='POST' and redraw:return self.json(runtime.regenerate_output(rid,unquote(redraw.group(1)),idempotency_key=body.get('idempotency_key'),resume=body.get('resume',False),expected_version=body.get('expected_version')))
            if method=='POST' and action=='package':return self.json(runtime.package(rid,logo_asset_id=body.get('logo_asset_id')))
            visual=re.fullmatch(r'visual/(master|output)/([^/]+)',action or '')
            if method=='POST' and visual:
                kind,image_id=visual.groups()
                if type(body.get('version')) is not int:raise UserError('请确认当前图片版本')
                return self.json(runtime.resolve_visual_review(rid,kind,unquote(image_id),body.get('action'),
                    body['version'],body.get('sha256'),body.get('idempotency_key')))
            preview=re.fullmatch(r'images/visual-(master|output)-(original|repair)/([^/]+)',action or '')
            if method=='GET' and preview:
                kind,variant,image_id=preview.groups();version=get('version')
                if not version or not re.fullmatch(r'[1-9]\d*',version):raise UserError('图片版本不正确')
                return self.file(runtime.visual_image(rid,kind,unquote(image_id),int(version),variant))
            if method=='POST' and action=='open-folder':
                with self.engine.lock:folder=Path(runtime._run(rid)['directory'])/'packages'
                folder.mkdir(parents=True,exist_ok=True)
                if sys.platform=='darwin':subprocess.Popen(['open',str(folder)])
                elif os.name=='nt':os.startfile(folder)
                else:subprocess.Popen(['xdg-open',str(folder)])
                return self.json({'ok':True})
            picture=re.fullmatch(r'images/(baseline|master|output|source)/([^/]+)',action or '')
            if method=='GET' and picture:
                version=get('version')
                if version and not re.fullmatch(r'[1-9]\d*',version):raise UserError('图片版本不正确')
                return self.file(runtime.image(rid,picture.group(1),unquote(picture.group(2)),int(version) if version else None))
            package=re.fullmatch(r'packages/([a-f0-9]{32})',action or '')
            if method=='GET' and package:
                return self.file(runtime.package_file(rid,package.group(1)),download='学习机图包-'+rid[:8]+'.zip')
        learning_logo_asset=re.fullmatch(r'/api/learning-machine/logo-assets/([a-zA-Z0-9._-]+)',path)
        if learning_logo_asset and method=='GET':
            from .learning_logo import asset_path
            return self.file(asset_path(learning_logo_asset.group(1)))
        learning_sample=re.fullmatch(r'/api/learning-machine/samples/([a-z0-9-]+)',path)
        if learning_sample and method=='GET':
            from .learning_logo import sample_path
            return self.file(sample_path(learning_sample.group(1)))
        if path=='/api/product':
            if method=='GET': return self.json(self.engine.product())
            if method=='PUT': return self.json(self.engine.save_product(body.get('text','')))
        if path=='/api/drafts' and method=='GET': return self.json({'drafts':self.engine.draft_summaries(get('q')) if get('summary')=='1' else self.engine.list_drafts()})
        draft_match=re.fullmatch(r'/api/drafts/([a-f0-9]{32})',path)
        if draft_match:
            did=draft_match.group(1)
            if method=='GET': return self.json(self.engine.get_draft(did))
            if method=='PUT': return self.json(self.engine.save_draft(did,body))
            if method=='DELETE': return self.json(self.engine.delete_draft(did))
        if path=='/api/settings':
            if method=='GET': return self.json(settings.public())
            if method=='PUT':
                return self.json(self.engine.save_settings(body))
        if path=='/api/settings/test' and method=='POST':
            key=body.get('kie_api_key') or settings.key
            if not key: return self.json({'key_status':'missing','message_zh':'请先填写 KIE Key'})
            try:
                base=https_base(body.get('kie_base_url') or settings.base)
                req=render.json_request(base+'/api/v1/chat/credit',key,method='GET')
                result=render.request_json(req,1,request_timeout=12)
                if result.get('code')!=200: raise ValueError('KIE credit query failed')
                settings.connection='connected'
                return self.json({'key_status':'connected','message_zh':'已连接'})
            except Exception:
                settings.connection='failed'
                return self.json({'key_status':'failed','message_zh':'连接失败，请检查 Key 和接口地址'})
        if path=='/api/settings/test-planning' and method=='POST':
            try:
                result=ApiScenePlanner(settings,timeout=30).test_connection(body)
                settings.planning_connection='connected'
                return self.json(result)
            except UserError as exc:
                settings.planning_connection='failed'
                return self.json({'key_status':'failed','message_zh':exc.message})
        if path=='/api/maintenance' and method=='GET':return self.json(self.engine.maintenance_status())
        if path=='/api/maintenance/backup' and method=='POST':return self.json(self.engine.create_backup())
        if path=='/api/maintenance/prune' and method=='GET':return self.json(self.engine.prune_plan())
        if path=='/api/maintenance/prune' and method=='POST':return self.json(self.engine.prune_versions(body.get('token')))
        if path=='/api/maintenance/restore-preview' and method=='POST':return self.json(self.engine.restore_preview(str(body.get('path',''))))
        if path=='/api/maintenance/restore' and method=='POST':return self.json(self.engine.restore_backup(str(body.get('path','')),body.get('token')))
        if path=='/api/queue' and method=='GET': return self.json(self.engine.queue_status())
        if path=='/api/storage/preview' and method=='GET': return self.json(self.engine.cleanup_preview())
        if path=='/api/storage':
            if method=='GET': return self.json(self.engine.storage())
            if method=='POST': return self.json(self.engine.cleanup(immediate=True))
        if path=='/api/folders/choose' and method=='POST':
            # Native directory chooser, with the browser retaining keyboard focus afterward.
            try:
                if sys.platform=='darwin':
                    p=subprocess.run(['osascript','-e','POSIX path of (choose folder with prompt "选择保存位置")'],capture_output=True,text=True,timeout=120)
                    selected=p.stdout.strip() if p.returncode==0 else ''
                else:
                    script='import tkinter as t;from tkinter import filedialog;r=t.Tk();r.withdraw();print(filedialog.askdirectory());r.destroy()'
                    p=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,timeout=120)
                    selected=p.stdout.strip()
                return self.json({'path':selected})
            except Exception: raise UserError('无法打开目录选择器，请直接填写保存路径')
        if path=='/api/references/points' and method=='POST':
            rid=body.get('id')
            if not isinstance(rid,str) or not re.fullmatch('[a-f0-9]{64}',rid): raise UserError('参考图不存在',404)
            uploaded=next((settings.state_dir/'uploads'/(rid+suffix) for suffix in ('.png','.jpg','.webp') if (settings.state_dir/'uploads'/(rid+suffix)).is_file()),None)
            if uploaded is None: raise UserError('参考图不存在',404)
            return self.json(ApiScenePlanner(settings).reference_points(uploaded,body.get('purpose')))
        if path=='/api/learning-source/copy' and method=='POST':
            from .learning_setup import generation_unavailable
            generation_unavailable()
        if path=='/api/learning-source/plan' and method=='POST':
            from .learning_setup import generation_unavailable
            generation_unavailable()
        sample_match=re.fullmatch('/api/learning-samples/([a-z0-9-]+)',path)
        if sample_match and method=='GET':
            from .learning_delivery import require_confirmed_sample
            placement=BY_ID.get(sample_match.group(1))
            if not placement or placement['category']!='学习机':raise UserError('样图不存在',404)
            return self.file(require_confirmed_sample(placement))
        uploaded_match=re.fullmatch('/api/uploads/([a-f0-9]{64})',path)
        if uploaded_match and method=='GET':
            from . import learning_source
            pr={'learning_mode':'upload','learning_source':{'id':uploaded_match.group(1)}}
            learning_source.registered(pr,settings)
            return self.file(pr['learning_source']['path'])
        if path=='/api/uploads' and method=='POST':
            note=str(body.get('note','')).strip()
            from .planning import REFERENCE_PURPOSES
            purpose=body.get('purpose')
            if purpose=='uploaded_master':
                from .learning_setup import generation_unavailable
                generation_unavailable()
            if not isinstance(purpose,str) or purpose not in (*REFERENCE_PURPOSES,'uploaded_master','learning_concept') or purpose=='legacy':raise UserError('请选择参考图用途')
            if len(note)>200: raise UserError('参考图说明最多 200 字')
            try:
                data=base64.b64decode(body.get('data',''),validate=True)
                if not 0<len(data)<=10*1024*1024: raise ValueError()
                im=Image.open(BytesIO(data));im.verify()
                im=Image.open(BytesIO(data))
                if im.format not in ('PNG','JPEG','WEBP') or im.width*im.height>40000000: raise ValueError()
                suffix={'PNG':'.png','JPEG':'.jpg','WEBP':'.webp'}[im.format]
            except Exception: raise UserError('请选择 10MB 以内的 PNG、JPG 或 WebP 图片')
            if purpose=='learning_concept':
                from .learning_concept import check_ratio
                check_ratio(im)
            import hashlib
            sha=hashlib.sha256(data).hexdigest()
            dest=settings.state_dir/'uploads'/(sha+suffix)
            dest.parent.mkdir(exist_ok=True)
            dest.write_bytes(data)
            result=dict(id=sha,path=str(dest),name=Path(str(body.get('name','参考图片'))).name,note=note,purpose=purpose)
            if purpose=='learning_concept':
                result.update(width=im.width,height=im.height,thumbnail_url='/api/uploads/'+sha)
            if purpose=='uploaded_master':
                from . import learning_source
                pr={'learning_mode':'upload','learning_source':result};learning_source.registered(pr,settings);result.update(pr['learning_source'])
            return self.json(result)
        if path.startswith('/api/assets/') and method=='GET':
            aid=path.rsplit('/',1)[-1]
            if aid in ('learning.logo.black','learning.logo.white-app','logo.onion.standard.001','logo.onion.app.001'):
                from .brand_logo import asset_path
                return self.file(asset_path(aid))
            a=next((a for a in ASSETS if a['asset_id']==aid),None)
            if not a: raise UserError('素材不存在',404)
            return self.file(ROOT/a['path'])
        if path=='/api/tasks':
            if method=='GET':
                try: cursor=max(0,int(get('cursor','0')))
                except ValueError: raise UserError('分页参数不正确')
                return self.json(self.engine.list_summaries(get('q'),cursor) if get('summary')=='1' else self.engine.list_tasks(get('q'),cursor))
            if method=='POST': return self.json(self.engine.create(body.get('params'),body.get('idempotency_key'),draft_id=body.get('draft_id')),201)
        match=re.fullmatch(r'/api/tasks/([a-f0-9]{32})(?:/(.*))?',path)
        if match:
            tid,action=match.groups()
            if not action:
                if method=='GET':
                    if get('view')=='1':
                        return self.json(self.engine.view_task(tid,int(get('round')) if get('round') else None,int(get('revision')) if get('revision') else None))
                    with self.engine.lock: return self.json(self.engine.public(self.engine.task(tid)))
                if method=='PATCH': return self.json(self.engine.mutate(tid,'rename',body))
                if method=='DELETE': return self.json(self.engine.mutate(tid,'delete',body))
            detail=re.fullmatch(r'(image-details|prompt-drafts|pin-version)/([a-f0-9]{32})',action or '')
            if detail:
                kind,sid=detail.groups()
                if kind=='pin-version' and method=='POST':return self.json(self.engine.pin_version(tid,sid,body.get('att'),body.get('pinned')))
                if kind=='image-details' and method=='GET':return self.json(self.engine.image_details(tid,sid,int(get('v')) if get('v') else None,get('editor')))
                if kind=='prompt-drafts' and method in ('PUT','DELETE'):return self.json(self.engine.save_prompt_draft(tid,sid,body,discard=method=='DELETE'))
            if action=='rounds' and method=='POST': return self.json(self.engine.create(body.get('params'),body.get('idempotency_key'),tid,draft_id=body.get('draft_id')))
            if action in ('stop','adopt','adopt-bulk','retry-planning','add-variant','repair-set','regenerate','resume','restore','duplicate','rebrief-round','pause','continue','archive','unarchive') and method=='POST': return self.json(self.engine.mutate(tid,action,body))
            if action=='package-preview' and method=='GET': return self.json(self.engine.package_preview(tid,int(get('round','0')),get('ready_only')=='1',logo_asset_id=get('logo_asset_id') or None))
            if action=='packages' and method=='POST':
                p=self.engine.package(tid,body.get('round',0),body.get('ready_only',False),logo_asset_id=body.get('logo_asset_id'))
                return self.json({'package_id':p['id'],'version':f"v{p['v']:03d}",'download_url':f"/api/tasks/{tid}/packages/{p['id']}",'filename':p['zip']})
            if action and action.startswith('packages/') and method=='GET':
                with self.engine.lock:
                    t=self.engine.task(tid)
                    pkg=next((p for p in t['pkgs'] if p['id']==action.split('/')[-1]),None)
                    if not pkg: raise UserError('图包不存在',404)
                    verify_saved_package(pkg['path'],pkg['fingerprint'],self.engine.package_rules(t,pkg))
                    return self.file(pkg['path'],pkg['zip'])
            if action=='open-folder' and method=='POST':
                t=self.engine.task(tid)
                p=Path(t.get('task_root',t['output_dir']))
                if sys.platform=='darwin': subprocess.Popen(['open',str(p)])
                elif os.name=='nt': os.startfile(p)
                else: subprocess.Popen(['xdg-open',str(p)])
                return self.json({'ok':True})
            if action and action.startswith(('images/','references/')) and method=='GET':
                bits=action.split('/')
                with self.engine.lock:
                    t=self.engine.task(tid);_,s=self.engine.find_image(t,bits[1])
                    version=int(get('v',str(s['att'])))
                    chosen=s if version==s['att'] else next((v for v in s['versions'] if v['att']==version),None)
                    if not chosen:raise UserError('图片版本不存在',404)
                    if bits[0]=='images':
                        if chosen['state']!='done':raise UserError('图片尚未完成',404)
                        file_path=chosen['output'] if get('raw')=='1' else chosen['jpeg']
                    else:
                        try:ref=chosen['refs'][int(bits[2])]
                        except (ValueError,IndexError):raise UserError('参考图不存在',404)
                        p=Path(ref['path']);file_path=p if p.is_absolute() else ROOT/p
                return self.file(file_path)
        if method=='GET' and not path.startswith('/api/'):
            name='index.html' if path=='/' else path.lstrip('/')
            allowed={'index.html','css/app.css','js/views.js','js/learning-machine.js','js/learning-runs.js','js/master-canvases.js','js/drafts.js','js/prompt-drafts.js','js/maintenance.js','js/workspace.js','js/production.js','js/app.js'}
            if name in allowed: return self.file(ROOT/'frontend'/name)
        raise UserError('文件不存在',404)

    def learning_runtime(self):
        from .learning_runtime import LearningRuntime
        with self.engine.lock:
            runtime=getattr(self.engine,'learning_runtime',None)
            if runtime is None:
                runtime=LearningRuntime(self.engine);self.engine.learning_runtime=runtime
            return runtime

    def dispatch(self):
        try: self.handle_api()
        except UserError as e: self.json({'message_zh':e.message},e.status)
        except (BrokenPipeError,ConnectionResetError): pass
        except Exception: self.json({'message_zh':'操作未完成，请刷新后重试'},500)
    do_GET=dispatch
    do_POST=dispatch
    do_PUT=dispatch
    do_PATCH=dispatch
    do_DELETE=dispatch


def main():
    parser=argparse.ArgumentParser(description='洋葱广告图本机工作台')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--state-dir',type=Path)
    parser.add_argument('--env-file',type=Path)
    args=parser.parse_args()
    settings=Settings(args.state_dir,args.env_file)
    try: server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    except OSError:
        url='http://127.0.0.1:'+str(args.port)
        try:
            with build_opener(ProxyHandler({})).open(url+'/api/health',timeout=2) as response:
                existing=response.headers.get('Server','').startswith('OnionLocal/') and json.loads(response.read(4096)).get('ok') is True
        except Exception: existing=False
        if existing:
            print('工作台已启动：'+url,flush=True)
            if not args.no_browser: webbrowser.open(url)
            return 0
        print('端口 '+str(args.port)+' 已被其他程序占用。可运行 python bootstrap.py --port '+str(args.port+1))
        return 1
    try: engine=Engine(settings)
    except UserError as exc:
        server.server_close();print(exc.message);return 1
    server.engine=engine
    url=f'http://127.0.0.1:{server.server_port}'
    print('洋葱广告图工具 · '+('模拟模式' if not settings.real else '真实模式'),flush=True)
    print(url,flush=True)
    if not args.no_browser: webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.server_close();engine.close()
    return 0

if __name__=='__main__': sys.exit(main())
