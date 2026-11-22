"""Durable learning-machine runs, explicit approval, and versioned local delivery."""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
from urllib.parse import quote
import uuid
import zipfile

from PIL import Image

from .config import UserError
from .learning_logo import RETIRED_LOGO_PLACEMENTS

PREFIX='learning-run:'
INDEX='learning-runs-index'
ACTIVE={'queued','generating','processing'}
MAX_ACTIVE_RUNS=8
CHANNEL_PACKAGE_LAYOUT='channel-placement-v1'


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _removed_module(entry):
    framing=entry.get('main_visual_framing') or {}
    return framing.get('removed_ad_module') or {'pure':'body','remove_cta':'cta'}.get(entry.get('concept_route'))


def _package_paths(run,rows):
    """Archive hierarchy comes from the run's frozen rules, never today's catalog."""
    from .planning import safe_filename
    grouped=run.get('target_kind')!='ordinary'
    paths=[]
    for row in rows:
        spec=run['placement_snapshots'][row['placement_id']]
        filename=row['placement_id']+'_'+str(row['image_index'])+('.jpg' if spec.get('output_format')=='JPEG' else '.png')
        if grouped:
            channel=safe_filename(spec.get('platform') or '其他渠道')
            placement=safe_filename(spec.get('name') or '图片')+'_'+str(spec['target_width'])+'x'+str(spec['target_height'])
            filename=channel+'/'+placement+'/'+filename
        paths.append(filename)
    if len(paths)!=len(set(paths)):raise UserError('交付图包路径重复，请检查版位与图片序号',409)
    return paths


def _key(value):
    if not isinstance(value,str) or not 8<=len(value)<=128 or any(ord(c)<32 for c in value):
        raise UserError('缺少有效操作标识，请刷新后重试')
    return value


class LearningRuntime:
    def __init__(self,engine,executor=None):
        self.engine=engine
        if executor is None:
            from .learning_executor import LearningExecutor
            executor=LearningExecutor(engine.settings)
        self.executor=executor
        self.stop_event=threading.Event()
        self.visual_pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix='learning-visual')
        self._closed=False
        self._threads=set()
        self.runs={}
        self.reload()

    def reload(self):
        with self.engine.lock:
            if self.is_active():raise UserError('学习机任务正在运行，请稍后重载',409)
            self.runs={}
            index=self.engine.document(INDEX,{'creates':{}})
            for name, in self.engine.db.execute('SELECT name FROM documents WHERE name LIKE ?',(PREFIX+'%',)):
                run=self.engine.document(name)
                if not isinstance(run.get('id'),str) or not re.fullmatch('[a-f0-9]{32}',run['id']):continue
                self.runs[run['id']]=run
                if run.get('busy'):
                    run.update(busy=False,status='interrupted',error='本机服务已中断，已有图片和版本已保留，请恢复本次操作')
                    if run.get('suite',{}).get('status')=='generating':run['suite']['status']='interrupted'
                    for row in [run.get('baseline',{}),*run.get('masters',[]),*run.get('outputs',[])]:
                        if row.get('status') in ACTIVE:row.update(status='interrupted',query_required=self._has_receipt(row))
                    self._save(run)
                if run.get('create_key') and run['create_key'] not in index['creates']:
                    index['creates'][run['create_key']]={'id':run['id'],'signature':run['create_signature']}
            self.engine.put_document(INDEX,index)

    def _save(self,run):
        if self._closed:return
        run['revision']=run.get('revision',0)+1;run['updated_at']=time.time()
        self.engine.put_document(PREFIX+run['id'],run)

    def _run(self,rid):
        if self._closed:raise UserError('学习机服务已关闭',503)
        run=self.runs.get(rid)
        if run is None:raise UserError('学习机任务不存在',404)
        return run

    def _maintenance(self):
        if self.engine.maintenance_active:raise UserError('正在进行本机数据维护，请稍后操作',409)

    def _has_receipt(self,row):
        repair=row.get('visual_review',{}).get('repair') or {}
        path=repair.get('job',{}).get('output') if repair and not repair.get('result') else row.get('raw_path')
        if not path:return False
        from scripts.render import task_state_path
        receipt=task_state_path(Path(path))
        try:
            data=json.loads(receipt.read_text())
            return bool(data.get('task_id') or data.get('status') in ('submitting','submit_uncertain'))
        except (OSError,ValueError):return False

    def _public_row(self,run,row,kind):
        keep=('id','group_id','master_id','placement_id','platform','name','image_index','width','height','version','status',
              'baseline_version','sha256','prompt','scene_plan','error','query_required','reuse_baseline','content_mode',
              'source_master_id','source_master_version','processing','inherited','inherited_from','logo_template',
              'background_repair_pending','background_repair_key','regeneration_key','uploaded','concept_route')
        result={k:copy.deepcopy(row[k]) for k in keep if k in row}
        if review:=row.get('visual_review'):
            from .learning_visual import clean, composition_issue, TYPOGRAPHY
            candidate=review.get('repair',{}).get('result')
            stage='after' if candidate else 'before'
            current=[review.get(stage),review.get(stage+'_verify')]
            original=review['original']
            result['visual_review']={
                'status':review['status'], 'model':review['model'], 'first':review.get('before'), 'verification':review.get('before_verify'),
                'after':review.get('after'), 'after_verification':review.get('after_verify'),
                'before_focus':copy.deepcopy(review.get('before_focus')), 'after_focus':copy.deepcopy(review.get('after_focus')),
                'before_brush':copy.deepcopy(review.get('before_brush')), 'after_brush':copy.deepcopy(review.get('after_brush')),
                'review_sha256':(candidate or original)['sha256'],
                'can_accept':review['status']=='needs_review' and (not candidate or any(clean(r) for r in current)),
                'can_recompose':kind=='master' and review['status']=='needs_review'
                    and bool(review.get('removed_ad_module')) and composition_issue(*current),
                'can_repair':review['status']=='needs_review' and review.get('text_expected',True) and not review.get('repair')
                    and not (review.get('removed_ad_module') and composition_issue(*current)) and any(
                    i['kind'] in TYPOGRAPHY for r in current if r for i in r['issues']),
                'can_clean_lettering':kind=='master' and run['mode']=='real' and row['status']=='done'
                    and review['status']=='approved' and review.get('text_expected',True),
                'repaired':bool(candidate), 'approved_by':review.get('approved_by'),
                'original_url':self._url(run,'visual-'+kind+'-original',row['id'],row['version']),
                'repair_url':self._url(run,'visual-'+kind+'-repair',row['id'],row['version']) if candidate else None,
            }
        result['logo_refresh_pending']=bool(row.get('logo_refresh_source'))
        if kind=='baseline':result['aspect_ratio']=run['compiled']['baseline']['aspect_ratio']
        elif kind=='master':
            spec=next((m for m in run['compiled']['masters'] if m['id']==row['id']),None)
            if spec:result['aspect_ratio']=spec['aspect_ratio']
        elif kind=='output':
            spec=run['placement_snapshots'].get(row.get('placement_id'))
            mapping=next((o for o in run['compiled']['outputs'] if o['output_id']==row['id']),None)
            if mapping:result['aspect_ratio']=mapping['aspect_ratio']
            if spec:
                result.update(logo_required=bool(spec['modules']['logo']),cta_required=bool(spec['modules']['cta']),main_copy_required=bool(spec['modules']['main_copy']))
                if row['placement_id'] in RETIRED_LOGO_PLACEMENTS:
                    result['logo_refresh_supported']=False
                result['cta_text']=(mapping.get('allowed_text',{}).get('cta',run['params'].get('cta','')) if mapping else run['params'].get('cta','')) if result['cta_required'] else ''
            if row.get('background_repair_pending'):
                request=row.get('background_request') or {}
                operation=run.get('background_operations',{}).get(request.get('operation_id'),{})
                retired=request.get('kind')=='ai' and operation.get('job',{}).get('background_plan',{}).get('version')!=3
                result['recovery_action']=('retired_flow' if retired else ('retry_export' if request.get('kind')=='local' or
                                            request.get('kind')=='ai' and operation.get('status')=='done' else 'resume_background'))
        result['image_url']=None
        if row.get('status')=='done' and row.get('sha256'):
            result['image_url']=self._url(run,kind,row['id'],row['version'])
        result['versions']=[self._public_row(run,v,kind) for v in row.get('versions',[])]
        return result

    def _url(self,run,kind,image_id,version=None):
        url='/api/learning-machine/runs/'+run['id']+'/images/'+kind+'/'+quote(image_id,safe='')
        return url+(('?version='+str(version)) if version is not None else '')

    def _public(self,run,summary=False):
        value={k:copy.deepcopy(run[k]) for k in ('id','name','kind','target_kind','source_summary','revision','mode','status','busy','created_at','updated_at','error') if k in run}
        compiled=run['compiled']
        value['counts']={
            'output_count':len(run['outputs']),'completed_outputs':sum(o['status']=='done' for o in run['outputs']),
            'master_count':len(run['masters']),'completed_masters':sum(m['status']=='done' for m in run['masters']),
            'planned_image_calls':compiled['counts']['planned_image_calls'],
        }
        inherited=bool(run['baseline'].get('inherited'))
        uploaded=bool(run['baseline'].get('uploaded'))
        backgrounds=compiled['counts'].get('background_image_calls',0)
        calls=compiled['counts']['image_model_master_calls']+backgrounds+(0 if inherited or uploaded else 1)
        value['counts'].update(baseline_reused=inherited,background_image_calls=backgrounds,expected_new_calls=calls,planned_image_calls=calls)
        if summary:return value
        if run['params'].get('concept'):value['concept']=copy.deepcopy(run['params']['concept'])
        value['params']={k:copy.deepcopy(run['params'][k]) for k in ('t1','t2','s1','s2','s3','cta','pids','image_model','ip','style','font','feature_note','product_facts') if k in run['params']}
        value['visual_config']=copy.deepcopy(run['plan'].get('visual_config',{}))
        if run.get('kind')=='shared_canvas_adaptation':
            value['crop_plan']=[{k:copy.deepcopy(g[k]) for k in ('id','aspect_ratio','target_ids','shared_keep_box','content_safe_box','source_index','allowed_text','content_mode') if k in g} for g in compiled['masters']]
            value['source_summary']=copy.deepcopy(run.get('source_summary'))
            value['source_images']=[dict(image_index=s['image_index'],width=s['width'],height=s['height'],
                                        source_contains_logo=s.get('source_contains_logo',False),
                                        image_url=self._url(run,'source',str(s['image_index']))) for s in run['sources']]
        value['baseline']=self._public_row(run,run['baseline'],'baseline')
        value['baseline_versions']=[self._public_row(run,v,'baseline') for v in run.get('baseline_versions',[])]
        value['approval']=copy.deepcopy(run.get('approval'))
        value['baseline_source']=copy.deepcopy(run.get('baseline_source')) if inherited else None
        value['suite']=copy.deepcopy(run['suite'])
        value['masters']=[self._public_row(run,m,'master') for m in run['masters']]
        value['outputs']=[self._public_row(run,o,'output') for o in run['outputs']]
        value['packages']=[{k:copy.deepcopy(p[k]) for k in ('id','version','image_count','download_url','sha256','mode','created_at','logo_asset_id','archive_layout') if k in p} for p in run['packages']]
        value['warnings']=[{'group_id':m['group_id'],'reason':'当前模型不支持本组真实生图比例'} for m in compiled['masters'] if m.get('unsupported_model_ratio')]
        if hasattr(self.engine,'queue_status'):value['queue']=copy.deepcopy(self.engine.queue_status())
        return value

    def get(self,rid,revision=None):
        with self.engine.lock:
            run=self._run(rid)
            if type(revision) is int and revision==run['revision']:
                result={'unchanged':True,'id':rid,'revision':run['revision']}
                if hasattr(self.engine,'queue_status'):result['queue']=copy.deepcopy(self.engine.queue_status())
                return result
            return self._public(run)

    def list(self):
        with self.engine.lock:
            return [self._public(r,True) for r in sorted(self.runs.values(),key=lambda r:-r['updated_at'])]

    def is_active(self):
        with self.engine.lock:return bool(self._threads) or any(r.get('busy') for r in self.runs.values())

    def create(self,params,mode='simulation',idempotency_key=None,*,_confirmed_source=None):
        key=_key(idempotency_key)
        if not isinstance(params,dict):raise UserError('请填写学习机配置')
        if mode not in ('simulation','real'):raise UserError('请选择本地演练或真实生成')
        if mode=='real' and not _confirmed_source and (not self.engine.settings.key or not self.engine.settings.planning_key):
            raise UserError('真实生成需要先配置规划和图片服务Key')
        identity={'params':params,'mode':mode}
        if _confirmed_source:
            identity['source']={key:_confirmed_source['baseline'].get(key) for key in ('version','sha256')}
            identity['source'].update(run_id=_confirmed_source['id'],request_signature=_confirmed_source['_inheritance_request_signature'])
        signature=hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with self.engine.lock:
            self._maintenance()
            index=self.engine.document(INDEX,{'creates':{}})
            old=index.get('creates',{}).get(key)
            if old:
                if old['signature']!=signature:raise UserError('重复操作标识对应的配置已改变，请重新提交',409)
                return self._public(self._run(old['id']))
        from .learning_runtime_support import freeze_run
        rid=uuid.uuid4().hex
        directory=Path(self.engine.settings.output)/'.cache'/'learning-runs'/rid
        directory.mkdir(parents=True,exist_ok=True)
        try:
            frozen=freeze_run(self.engine,params,directory,confirmed_source=_confirmed_source) if _confirmed_source else freeze_run(self.engine,params,directory)
            compiled=frozen.get('compiled') or frozen['plan']['prompt_plan']
            if mode=='real' and any(m.get('unsupported_model_ratio') for m in compiled['masters']):
                raise UserError('当前模型不支持所选固定母版比例，请先调整图片模型')
        except Exception:
            shutil.rmtree(directory,ignore_errors=True)
            raise
        now=time.time()
        masters=[dict(id=m['id'],group_id=m['group_id'],status='not_generated',version=0,versions=[],
                      prompt=m['prompt'],reuse_baseline=m.get('reuse_baseline',False),content_mode=m['content_mode']) for m in compiled['masters']]
        mapping={o['output_id']:o for o in compiled['outputs']}
        outputs=[]
        for row in frozen['plan']['outputs']:
            outputs.append(dict(id=row['id'],placement_id=row['placement_id'],platform=row['platform'],name=row['name'],
                                image_index=row['image_index'],width=row['width'],height=row['height'],
                                master_id=mapping[row['id']]['master_id'],version=0,status='waiting_for_baseline_confirmation',versions=[]))
        for master,entry in zip(masters,compiled['masters']):
            if 'concept_route' in entry:master['concept_route']=entry['concept_route']
        for output in outputs:
            if 'concept_route' in mapping[output['id']]:output['concept_route']=mapping[output['id']]['concept_route']
        # The freeze helper returns convenient aliases for compilation. Store
        # each authoritative template and layer snapshot once, not in every
        # embedded preview representation.
        for field in ('prompt_plan','params','normalized_params','saved_configuration'):
            frozen['plan'].pop(field,None)
        frozen.pop('placements',None)
        for field in ('learning_logo_snapshot','learning_mask_snapshot'):
            frozen['params'].pop(field,None)
        run={**frozen,'id':rid,'directory':str(directory),'name':frozen['params']['t1'][:24],
             'compiled':compiled,'mode':mode,'revision':0,'created_at':now,'updated_at':now,'busy':False,'status':'configured',
             'baseline':dict(id='baseline',version=0,status='not_generated'), 'baseline_versions':[],
             'approval':None,'suite':{'status':'not_started','baseline_version':None},'masters':masters,'outputs':outputs,'packages':[],
             'operation_keys':{},'create_key':key,'create_signature':signature}
        if run.get('uploaded_baseline'):
            run.update(baseline=run.pop('uploaded_baseline'),status='waiting_for_confirmation')
        if _confirmed_source:
            provenance=dict(run_id=_confirmed_source['id'],baseline_version=_confirmed_source['baseline']['version'],
                            sha256=_confirmed_source['baseline']['sha256'],mode=_confirmed_source['mode'],
                            confirmed_at=_confirmed_source['approval']['confirmed_at'])
            run['baseline']=run.pop('inherited_baseline')
            run['baseline']['inherited_from']=copy.deepcopy(provenance)
            run.update(status='baseline_confirmed',name=run['name']+' · 重新构图',baseline_source=provenance,
                       from_baseline_request_signature=_confirmed_source['_inheritance_request_signature'])
            run['approval']=dict(confirmed=True,baseline_version=1,sha256=provenance['sha256'],mode=mode,
                                 confirmed_at=provenance['confirmed_at'],inherited_from=copy.deepcopy(provenance))
        with self.engine.lock:
            self._maintenance()
            index=self.engine.document(INDEX,{'creates':{}})
            if key in index.get('creates',{}):
                previous=index['creates'][key]
                shutil.rmtree(directory,ignore_errors=True)
                if previous['signature']!=signature:raise UserError('重复操作标识对应的配置已改变，请重新提交',409)
                return self._public(self._run(previous['id']))
            if _confirmed_source:
                try:
                    current=self._inheritance_source(_confirmed_source['id'])
                    if current['revision']!=_confirmed_source['revision']:raise UserError('来源批次已变化，请刷新后重新创建',409)
                except Exception:
                    shutil.rmtree(directory,ignore_errors=True)
                    raise
            self.runs[rid]=run;self._save(run)
            index.setdefault('creates',{})[key]={'id':rid,'signature':signature}
            self.engine.put_document(INDEX,index)
            return self._public(run)

    def _inheritance_source(self,rid):
        run=self._run(rid);base=run['baseline'];approval=run.get('approval') or {}
        if run['busy'] or any(row.get('query_required') for row in [base,*run['masters'],*run['outputs']]):
            raise UserError('来源批次正在运行或状态不明，请先完成已有操作',409)
        if (base.get('status')!='done' or not approval.get('confirmed') or approval.get('baseline_version')!=base.get('version')
                or approval.get('sha256')!=base.get('sha256') or approval.get('mode')!=run['mode']
                or not isinstance(approval.get('confirmed_at'),(int,float))):
            raise UserError('请先查看并确认来源批次的当前基准图',409)
        return run

    def create_from_confirmed_baseline(self,source_rid,idempotency_key,pids=None):
        key='from-baseline-'+hashlib.sha256(_key(idempotency_key).encode()).hexdigest()
        request_signature=hashlib.sha256(json.dumps({'source':source_rid,'pids':pids},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with self.engine.lock:
            self._maintenance()
            index=self.engine.document(INDEX,{'creates':{}})
            existing=index['creates'].get(key)
            if existing:
                target=self._run(existing['id'])
                if target.get('from_baseline_request_signature')!=request_signature:
                    raise UserError('重复操作标识对应的来源或版位已改变',409)
                return self._public(target)
            source=copy.deepcopy(self._inheritance_source(source_rid))
        source['_inheritance_request_signature']=request_signature
        params=copy.deepcopy(source['params'])
        if pids is not None:params['pids']=copy.deepcopy(pids)
        return self.create(params,mode=source['mode'],idempotency_key=key,_confirmed_source=source)

    def _claim(self,run,scope,key,*,resume_existing=False):
        op=scope+':'+_key(key)
        if op in run['operation_keys'] and (not resume_existing or run['busy']):return False
        self._maintenance()
        if run['busy']:raise UserError('当前操作尚未结束，请稍候',409)
        if sum(bool(r.get('busy')) for r in self.runs.values())>=MAX_ACTIVE_RUNS:
            raise UserError('当前学习机任务较多，请等待已有任务完成后重试',429)
        run['operation_keys'][op]={'at':time.time()};run.update(busy=True,error='')
        return True

    def create_shared_canvas(self,params,idempotency_key):
        """Select frozen source art, then plan one natural mother per crop family."""
        key='shared-canvas-'+hashlib.sha256(_key(idempotency_key).encode()).hexdigest()
        if not isinstance(params,dict):raise UserError('请选择来源图片和目标版位')
        signature=hashlib.sha256(json.dumps(params,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with self.engine.lock:
            self._maintenance();index=self.engine.document(INDEX,{'creates':{}})
            old=index['creates'].get(key)
            if old:
                if old['signature']!=signature:raise UserError('重复操作标识对应的来源或目标已改变',409)
                return self._public(self._run(old['id']))
        from .master_canvas_support import freeze_adaptation
        rid=uuid.uuid4().hex;directory=Path(self.engine.settings.output)/'.cache'/'learning-runs'/rid
        directory.mkdir(parents=True,exist_ok=True)
        try:
            frozen=freeze_adaptation(self.engine,params,directory,source_runtime=self)
            if frozen['target_kind']=='learning' and frozen['mode']!='real':
                raise UserError('制作学习机共用母版请选择正式制作的来源图片',409)
        except Exception:
            shutil.rmtree(directory,ignore_errors=True);raise
        compiled=frozen['compiled'];baseline=frozen.pop('inherited_baseline');now=time.time()
        approval={**frozen.pop('source_approval'), 'baseline_version':1,'sha256':baseline['sha256'],
                  'mode':frozen['mode'],'confirmed_at':now}
        masters=[dict(id=m['id'],group_id=m['group_id'],version=0,status='not_generated',versions=[],
                      prompt=m['prompt'],reuse_baseline=False,content_mode=m['content_mode']) for m in compiled['masters']]
        outputs=[dict(id=o['output_id'],placement_id=o['placement_id'],platform=o['platform'],name=o['name'],
                      image_index=o['image_index'],width=o['target_width'],height=o['target_height'],
                      master_id=o['master_id'],version=0,status='waiting_for_baseline_confirmation',versions=[]) for o in compiled['outputs']]
        label=frozen.get('source_summary',{}).get('name') or frozen['params'].get('t1') or '来源图片'
        run={**frozen,'id':rid,'directory':str(directory),'name':label[:24]+' · 共用母版',
             'created_at':now,'updated_at':now,'revision':0,'busy':False,'status':'baseline_confirmed',
             'baseline':baseline,'baseline_versions':[],'approval':approval,'masters':masters,'outputs':outputs,
             'suite':{'status':'not_started','baseline_version':None},'packages':[],'operation_keys':{},
             'create_key':key,'create_signature':signature}
        with self.engine.lock:
            self._maintenance();index=self.engine.document(INDEX,{'creates':{}})
            old=index['creates'].get(key)
            if old:
                shutil.rmtree(directory,ignore_errors=True)
                if old['signature']!=signature:raise UserError('重复操作标识对应的来源或目标已改变',409)
                return self._public(self._run(old['id']))
            self.runs[rid]=run;self._save(run)
            index['creates'][key]={'id':rid,'signature':signature};self.engine.put_document(INDEX,index)
            return self._public(run)

    def _launch(self,run,work):
        def invoke():
            try:work()
            except Exception as exc:
                with self.engine.lock:
                    if not self._closed:run.update(status='failed',error=exc.message if isinstance(exc,UserError) else '学习机操作未完成，请检查配置后重试')
            finally:
                with self.engine.lock:
                    if not self._closed:run['busy']=False;self._save(run)
                    self._threads.discard(threading.current_thread())
        thread=threading.Thread(target=invoke,name='learning-run-'+run['id'],daemon=True)
        self._threads.add(thread);thread.start()

    def _checked_file(self,run,row,path_key='raw_path'):
        path=Path(row.get(path_key,''))
        roots=(Path(run['directory']).resolve(),(Path(self.engine.settings.output)/'.restored').resolve())
        if not any(path.resolve().is_relative_to(root) for root in roots):raise UserError('图片来源不属于本任务',409)
        if not path.is_file() or _digest(path)!=row.get('sha256'):raise UserError('图片文件缺失或校验失败，请重新生成',409)
        return path

    def _image_result(self,run,result,output,ratio):
        if result.get('simulated') is not (run['mode']=='simulation'):
            raise UserError('图片生成模式与本任务不一致，不能确认或导出')
        source=Path(result['source']);root=Path(run['directory']).resolve()
        try:source.resolve().relative_to(root)
        except ValueError:raise UserError('生成图片没有保存在本任务目录') from None
        if source.resolve()!=Path(output).resolve():raise UserError('生成图片与本次请求的输出身份不一致')
        if not source.is_file():raise UserError('生成图片尚未落盘')
        a,b=map(int,ratio.split(':'))
        with Image.open(source) as image:
            if image.width*image.height>40000000 or abs(image.width/image.height-a/b)>1e-6:
                raise UserError('生成图片与固定母版比例不一致，请重新生成')
            image.verify()
        digest=_digest(source)
        if result.get('sha256') and result['sha256']!=digest:raise UserError('生成图片校验失败')
        changes={'raw_path':str(source),'sha256':digest,'status':'done','simulated':run['mode']=='simulation',
                 'provider_task_id':result.get('provider_task_id'),'query_required':False}
        if result.get('actual_prompt'):changes['prompt']=result['actual_prompt']
        if result.get('reference_bindings') is not None:changes['reference_bindings']=copy.deepcopy(result['reference_bindings'])
        if result.get('provider_original_path'):
            original=Path(result['provider_original_path'])
            allowed=(root,(Path(self.engine.settings.output)/'.restored').resolve())
            if not any(original.resolve().is_relative_to(folder) for folder in allowed) or not original.is_file() or _digest(original)!=result.get('provider_original_sha256'):
                raise UserError('供应商原图校验失败')
            changes.update(provider_original_path=str(original),provider_original_sha256=result['provider_original_sha256'])
        return changes

    def _execution_path(self,run,row,expected):
        """Resume a restored receipt in a fresh execution area, never its archive."""
        expected=Path(expected);old=Path(row.get('raw_path',expected))
        if old.resolve()!=expected.resolve() and (row.get('query_required') or self._has_receipt(row)):
            restored=(Path(self.engine.settings.output)/'.restored').resolve()
            if not old.resolve().is_relative_to(restored):raise UserError('待恢复图片不属于已验证恢复目录',409)
            from scripts.render import task_state_path
            before,after=task_state_path(old),task_state_path(expected)
            expected.parent.mkdir(parents=True,exist_ok=True)
            if before.exists() and not after.exists():shutil.copyfile(before,after)
            if old.is_file() and not expected.exists():shutil.copyfile(old,expected)
        return expected

    def _canvas_job(self,run,entry,output,kind):
        from .master_canvas import build_guide
        index=entry['source_index'];source=run['sources'][index-1]
        path=self._checked_file(run,{'raw_path':source['path'],'sha256':source['sha256']})
        guide_path=Path(run['directory'])/'canvas-guides'/entry['id']/(source['sha256']+'.png')
        group=entry.get('canvas_plan') or entry
        with getattr(self.engine,'processing_slots',nullcontext()):guide=build_guide(path,guide_path,group)
        guide_purpose=('目标画幅与共同安全区；主体位置按删减内容后的构图重新安排' if _removed_module(entry)
                       else '布局草稿，原图缩小位置与共同安全区；色块只是待画满的背景')
        refs=[dict(slot=1,kind='canvas_guide',path=guide['path'],sha256=guide['sha256'],purpose=guide_purpose),
              dict(slot=2,kind='source_picture',path=str(path),sha256=source['sha256'],purpose='本张已选来源的人物、画风、场景与文字；旧Logo和制作辅助标记不作为保留项')]
        return dict(id=entry['id'],kind='shared_canvas_master',prompt=entry['prompt'],aspect_ratio=entry['aspect_ratio'],
                    model=run['params']['image_model'],output=str(output),reference_bindings=refs,canvas_plan=copy.deepcopy(group),
                    simulation=run['mode']=='simulation',allowed_text=entry['allowed_text'],
                    content_safe_area=group['content_safe_box'],shared_safe_area=group['shared_keep_box'],
                    stop_marker=str(Path(run['directory'])/'STOP'),
                    upload_cache=str(self.engine.settings.state_dir/'learning-reference-upload-cache.json'))

    def _job(self,run,entry,output,kind,baseline=None):
        from .learning_runtime_support import resolve_bindings
        if run.get('kind')=='shared_canvas_adaptation':return self._canvas_job(run,entry,output,kind)
        if kind=='master' and entry.get('concept_route')=='background':
            from .learning_background import prepare_job
            width,height=(n*96 for n in map(int,entry['aspect_ratio'].split(':')))
            with getattr(self.engine,'processing_slots',nullcontext()):
                job=prepare_job(run,self._checked_file(run,baseline),output,width,height,entry['allowed_text'])
            return {**job,'id':entry['id'],'stop_marker':str(Path(run['directory'])/'STOP'),
                    'upload_cache':str(self.engine.settings.state_dir/'learning-reference-upload-cache.json')}
        refs=resolve_bindings(run,entry.get('reference_bindings',[]),
                              baseline_path=baseline.get('raw_path') if baseline else None,
                              baseline_sha256=baseline.get('sha256') if baseline else None)
        return dict(id=entry.get('id',kind),kind=kind,prompt=entry['prompt'],aspect_ratio=entry['aspect_ratio'],
                    model=run['params']['image_model'],output=str(output),reference_bindings=refs,
                    simulation=run['mode']=='simulation',allowed_text=entry.get('allowed_text',{}),
                    content_safe_area=entry.get('content_safe_area') or entry.get('shared_safe_area'),
                    main_visual_framing=copy.deepcopy(entry.get('main_visual_framing')),
                    shared_safe_area=entry.get('shared_safe_area'),stop_marker=str(Path(run['directory'])/'STOP'),
                    upload_cache=str(self.engine.settings.state_dir/'learning-reference-upload-cache.json'))

    def _submit_image(self,run,function,*args):
        submit_for=getattr(self.engine.pool,'submit_for',None)
        if submit_for is not None:return submit_for('learning:'+run['id'],function,*args)
        return self.engine.pool.submit(function,*args)

    def _failure(self,row,exc):
        if getattr(exc,'reason_code',None)=='rate_limited' and hasattr(self.engine,'note_rate_limit'):
            self.engine.note_rate_limit()
        row.update(status='failed',error=exc.message if isinstance(exc,UserError) else '图片处理未完成，请重试',
                   query_required=bool(getattr(exc,'query_required',False)),
                   reason_code=getattr(exc,'reason_code','processing_failed'))

    def _record_generated(self,run,row,entry,changes,*,single=False):
        from .learning_visual import MODEL
        with self.engine.lock:
            row.update(changes)
            allowed=entry.get('allowed_text',{})
            text_expected=bool(allowed.get('t1') or allowed.get('cta'))
            removed=_removed_module(entry)
            if run['mode']=='real' and run.get('target_kind')!='ordinary' and (text_expected or removed or run['params'].get('concept')):
                row['visual_review']=dict(status='reviewing',model=MODEL,original=copy.deepcopy(changes),
                                          text_expected=text_expected,removed_ad_module=removed)
            if single or row.get('visual_review'):row['status']='processing'
            self._save(run)

    def _visual_update(self,run,review,**fields):
        with self.engine.lock:
            review.update(fields)
            self._save(run)

    def _visual_checks(self,run,row,entry,stage,source,reference=None):
        from .learning_visual import brush_mark_target, clean, focus_targets
        review=row['visual_review'];allowed=entry['allowed_text']
        removed=_removed_module(entry)
        inspection={'removed_module':removed} if removed else {}
        verify=stage+'_verify'
        first=review.get(stage)
        if not first:
            first=self.executor.inspect_typography(source,allowed,False,reference,self.stop_event,**inspection)
            self._visual_update(run,review,**{stage:first})
        second=review.get(verify)
        retrying=any(r['stage'] in (stage,verify) and r['verdict']!='unavailable' for r in review.get('history',[]))
        if first['verdict']!='unavailable' and not second and (not clean(first) or retrying):
            layout_issues={'crop','overlap','composition'}
            compare=reference if any(i['kind'] in layout_issues for i in first['issues']) else None
            second=self.executor.inspect_typography(source,allowed,True,compare,self.stop_event,**inspection)
            self._visual_update(run,review,**{verify:second})
        field=stage+'_focus'
        focus=review.get(field)
        if not focus:
            targets=focus_targets(allowed,first,second)
            if targets:
                focus=self.executor.inspect_suspect_text(source,targets,self.stop_event)
                self._visual_update(run,review,**{field:focus})
        field=stage+'_brush'
        brush=review.get(field)
        if not brush and run['params'].get('concept') and not entry.get('reuse_baseline'):
            target=brush_mark_target(allowed,first,second)
            if target:
                original=self._checked_file(run,run['baseline'])
                brush=self.executor.inspect_brush_mark(source,original,target,self.stop_event)
                self._visual_update(run,review,**{field:brush})
        return first,second,focus,brush

    def _repair_typography(self,run,row,entry):
        from .learning_visual import repair_job, fit_repair
        from scripts.render import task_state_path
        review=row['visual_review']
        operation=review.get('repair')
        if not operation:
            directory=Path(run['directory'])/'typography'/row['id']/f"v{row['version']}"
            job=repair_job(directory/'native.png',review['original'],entry,review['confirmed_issues'],
                           str(Path(run['directory'])/'STOP'),
                           str(self.engine.settings.state_dir/'learning-reference-upload-cache.json'))
            operation=dict(job=job,receipt_path=str(task_state_path(Path(job['output']))))
            self._visual_update(run,review,repair=operation,status='repairing')
        if operation.get('result'):
            return operation['result']
        job=copy.deepcopy(operation['job'])
        job['stop_marker']=str(Path(run['directory'])/'STOP')
        job['upload_cache']=str(self.engine.settings.state_dir/'learning-reference-upload-cache.json')
        restored=(Path(self.engine.settings.output)/'.restored').resolve()
        receipt=Path(operation['receipt_path'])
        native=Path(job['output'])
        if receipt.resolve().is_relative_to(restored):
            # Backup keeps the receipt independently of the provider image.
            native=Path(run['directory'])/'typography'/row['id']/f"v{row['version']}"/'native.png'
            journal=task_state_path(native)
            native.parent.mkdir(parents=True,exist_ok=True)
            if not journal.exists():shutil.copyfile(receipt,journal)
            if Path(job['output']).is_file() and not native.exists():shutil.copyfile(job['output'],native)
            job['output']=str(native)
            with self.engine.lock:
                operation.update(job=copy.deepcopy(job),receipt_path=str(journal));self._save(run)
        if not native.resolve().is_relative_to(Path(run['directory']).resolve()):
            raise UserError('已恢复的修复任务缺少可用回执，请检查备份记录',409)
        if row.get('query_required') and not task_state_path(native).is_file():
            raise UserError('原修复任务回执缺失，请检查备份记录',409)
        result=self._submit_image(run,self.executor.generate_image,job,self.stop_event).result()
        if (result.get('simulated') is not False or Path(result['source']).resolve()!=native.resolve()
                or not native.is_file() or _digest(native)!=result.get('sha256')):
            raise UserError('文字修复图校验失败')
        fitted=fit_repair(native,native.with_name('fitted.png'),entry['aspect_ratio'])
        candidate=self._image_result(run,{**result,'source':str(fitted),'sha256':_digest(fitted),
                                          'provider_original_path':str(native),'provider_original_sha256':result['sha256']},
                                     fitted,entry['aspect_ratio'])
        with self.engine.lock:
            operation['result']=candidate
            row['query_required']=False
            self._save(run)
        return candidate

    def _visual_hold(self,run,row,review,status,message):
        with self.engine.lock:
            row.update(status='visual_hold',error=message,query_required=False)
            review['status']=status
            self._save(run)
        return False

    def _visual_gate(self,run,row,entry,*,single=False):
        from .learning_visual import composition_issue, confirmed_issues, review_passed
        review=row.get('visual_review')
        if not review or review['status']=='approved':return True
        original=review['original']
        source=self._checked_file(run,original)
        with self.engine.lock:
            row.update(status='processing',error='')
            if not review.get('repair'):row['query_required']=False
            self._save(run)
        allowed=entry['allowed_text']
        removed=_removed_module(entry)
        stage='before'
        approved=original
        def audit_image(path,digest):
            box=entry.get('concept_audit_box')
            if not box or single and not removed:return path
            from .learning_background import _atomic_image
            audit=Path(run['directory'])/'typography'/'audit-crops'/row['id']/(digest+'.png')
            with Image.open(path) as image:
                bounds=tuple(round(n*d) for n,d in zip(box,(*image.size,*image.size)))
                _atomic_image(image.crop(bounds),audit,immutable=True)
            return audit
        manual=review.get('manual',{}).get('before',{})
        if not review.get('repair') and manual.get('action')=='repair':
            self._visual_update(run,review,confirmed_issues=manual['issues'])
        elif not review.get('repair'):
            first,second,focus,brush=self._visual_checks(run,row,entry,stage,audit_image(source,original['sha256']))
            if not review_passed(first,second,focus,allowed,brush) and manual.get('action')!='accept':
                if 'unavailable' in (first['verdict'],(second or {}).get('verdict'),(focus or {}).get('verdict'),(brush or {}).get('verdict')):
                    return self._visual_hold(run,row,review,'unavailable','Luna 审核暂未完成，请重试审核。')
                if removed and composition_issue(first,second):
                    return self._visual_hold(run,row,review,'needs_review','删减内容后构图需调整，请查看主体、正文和留白。')
                if not review.get('text_expected',True):
                    return self._visual_hold(run,row,review,'needs_review','无字母版仍有疑点，请检查残字、按钮或主视觉。')
                issues=confirmed_issues(first,second,allowed,focus)
                if not issues:
                    return self._visual_hold(run,row,review,'needs_review','Luna 发现疑点，请核对原图。')
                self._visual_update(run,review,confirmed_issues=issues)
        needs_repair=bool(review.get('confirmed_issues'))
        if needs_repair:
            self._visual_update(run,review,status='repairing')
            approved=self._repair_typography(run,row,entry)
            repaired=self._checked_file(run,approved)
            stage='after'
            self._visual_update(run,review,status='reviewing_repair')
            first,second,focus,brush=self._visual_checks(run,row,entry,stage,audit_image(repaired,approved['sha256']),source)
            if not review_passed(first,second,focus,allowed,brush) and review.get('manual',{}).get(stage,{}).get('action')!='accept':
                if 'unavailable' in (first['verdict'],(second or {}).get('verdict'),(focus or {}).get('verdict'),(brush or {}).get('verdict')):
                    return self._visual_hold(run,row,review,'unavailable','修复图已保存，请重试 Luna 审核。')
                return self._visual_hold(run,row,review,'needs_review','修复图仍有疑点，请核对后再扩版。')
        with self.engine.lock:
            review['status']='approved'
            review['approved_by']='human' if review.get('manual',{}).get(stage,{}).get('action')=='accept' else 'luna'
            row.update(approved,status='processing' if single else 'done',error='',query_required=False)
            self._save(run)
        return True

    def resolve_visual_review(self,rid,kind,image_id,action,version,sha256,key):
        from .learning_visual import brush_mark_target, clean, composition_issue, focus_targets, TYPOGRAPHY
        _key(key)
        with self.engine.lock:
            run=self._run(rid);self._maintenance();self._approved(run)
            rows=run['masters'] if kind=='master' else run['outputs']
            row=next((r for r in rows if r['id']==image_id),None)
            review=(row or {}).get('visual_review')
            if review and review.get('decision_key')==key:return self._public(run)
            if action=='recompose' and 'canvas-master-'+image_id+':'+key in run['operation_keys']:
                return self._public(run)
            if run['busy']:raise UserError('本批仍在制作，请稍后复核',409)
            if not review or row['version']!=version:
                raise UserError('审核版本已更新，请重新读取',409)
            if sum(bool(r.get('busy')) for r in self.runs.values())>=MAX_ACTIVE_RUNS:
                raise UserError('当前学习机任务较多，请等待已有任务完成后重试',429)
            if action=='clean_lettering' and kind=='master' and run['mode']=='real' and row['status']=='done' \
                    and review['status']=='approved' and review.get('text_expected',True):
                if row.get('sha256')!=sha256:raise UserError('审核图片已更新，请重新读取',409)
                targets=[o for o in run['outputs'] if o['master_id']==image_id]
                if any(o.get('background_repair_pending') or o.get('query_required') for o in targets):
                    raise UserError('请先恢复本组已有处理',409)
                self._checked_file(run,row)
                saved={field:copy.deepcopy(row[field]) for field in (
                    'raw_path','sha256','prompt','reference_bindings','provider_task_id',
                    'provider_original_path','provider_original_sha256','baseline_version','reuse_baseline') if field in row}
                self._new_version(row)
                row.update(saved,status='visual_hold')
                issues=[dict(kind='glyph',target='',where='正文和按钮',detail='已确认存在需清理的字面或描边问题')]
                row['visual_review']=dict(status='needs_review',model=review['model'],original=saved,text_expected=True,
                    removed_ad_module=review.get('removed_ad_module'),decision_key=key,
                    manual={'before':dict(action='repair',issues=issues,sha256=sha256,at=time.time())})
                for output in targets:
                    self._new_version(output)
                self._save(run)
                return self.regenerate_canvas_master(rid,image_id,key,row['version'],_review_resume=True)
            if review['status']=='approved':raise UserError('审核已通过，请重新读取当前版本',409)
            candidate=review.get('repair',{}).get('result')
            stage='after' if candidate else 'before'
            item=candidate or review['original']
            if item['sha256']!=sha256:raise UserError('审核图片已更新，请重新读取',409)
            first,second=review.get(stage),review.get(stage+'_verify')
            if action=='recompose' and kind=='master' and review['status']=='needs_review' \
                    and review.get('removed_ad_module') and composition_issue(first,second):
                return self.regenerate_canvas_master(rid,image_id,key,version,_review_resume=True,_redraw_review=True)
            if action=='retry' and review['status'] in ('unavailable','needs_review'):
                if kind=='master':
                    entry=next(m for m in run['compiled']['masters'] if m['id']==image_id)
                else:
                    from .learning_runtime_support import compile_single
                    entry=compile_single(run,image_id)
                allowed=entry['allowed_text']
                if run['params'].get('concept') and not entry.get('reuse_baseline') and brush_mark_target(allowed,first,second):
                    fields=(stage+'_brush',)
                elif focus_targets(allowed,first,second):
                    fields=(stage+'_focus',)
                else:
                    fields=(stage,stage+'_verify',stage+'_focus',stage+'_brush')
                for field in fields:
                    result=review.get(field)
                    if result and (review['status']=='needs_review' or result['verdict']=='unavailable'):
                        review.setdefault('history',[]).append(dict(stage=field,**review.pop(field)))
            elif action=='accept' and review['status']=='needs_review' and (not candidate or any(clean(r) for r in (first,second))):
                review.setdefault('manual',{})[stage]=dict(action=action,sha256=sha256,at=time.time())
            elif action=='repair' and stage=='before' and review.get('text_expected',True) and not review.get('repair') and review['status']=='needs_review':
                if review.get('removed_ad_module') and composition_issue(first,second):
                    raise UserError('请先处理构图问题，再确认文字清修',409)
                issues=[i for r in (first,second) if r for i in r['issues'] if i['kind'] in TYPOGRAPHY]
                if not issues:raise UserError('请先确认可见的文字问题',409)
                review.setdefault('manual',{})[stage]=dict(action=action,issues=issues,sha256=sha256,at=time.time())
            else:
                raise UserError('当前审核状态不支持这个操作',409)
            review['decision_key']=key
            self._save(run)
            if kind=='output':return self.regenerate_output(rid,image_id,key,expected_version=version)
            return self.regenerate_canvas_master(rid,image_id,key,version,_review_resume=True)

    def generate_baseline(self,rid,idempotency_key,resume=False):
        with self.engine.lock:
            run=self._run(rid)
            if run['params'].get('concept'):raise UserError('本批来源是上传概念图，请查看并确认原图',409)
            if run.get('kind')=='shared_canvas_adaptation':raise UserError('来源图片已冻结，请选择新的来源创建母版批次',409)
            if any(row.get('query_required') for row in [*run['masters'],*run['outputs']]):
                raise UserError('仍有图片状态不明，请先恢复已有图片查询，再重新生成基准图',409)
            if not self._claim(run,'baseline',idempotency_key):return self._public(run)
            old=run['baseline'];recover=bool(old.get('query_required') or old.get('status')=='interrupted' and self._has_receipt(old))
            if resume and not recover:
                run['busy']=False;raise UserError('当前基准图没有待恢复的供应商任务',409)
            if recover:
                baseline=old
                path=self._execution_path(run,baseline,Path(run['directory'])/'baselines'/f"v{baseline['version']}.png")
                baseline.update(status='queued',raw_path=str(path))
            else:
                if old.get('version'):run['baseline_versions'].append(copy.deepcopy(old))
                baseline=dict(id='baseline',version=old.get('version',0)+1,status='queued',raw_path=str(Path(run['directory'])/'baselines'/f"v{old.get('version',0)+1}.png"))
                run['baseline']=baseline
            run.update(status='generating_baseline',approval=None);self._save(run)
            def work():
                try:
                    if not recover:
                        scene=self.engine.planning_pool.submit(self.executor.plan_scene,run,self.stop_event).result()
                        from .learning_runtime_support import compile_baseline
                        entry=compile_baseline(run,scene)
                        with self.engine.lock:baseline.update(scene_plan=scene,prompt=entry['prompt'],entry=entry,status='generating');self._save(run)
                    else:entry=baseline['entry']
                    if self.stop_event.is_set():return
                    job=self._job(run,entry,baseline['raw_path'],'baseline')
                    result=self._submit_image(run,self.executor.generate_image,job,self.stop_event).result()
                    changes=self._image_result(run,result,baseline['raw_path'],entry['aspect_ratio'])
                    with self.engine.lock:
                        if not self._closed:baseline.update(changes);run['status']='waiting_for_confirmation';self._save(run)
                except Exception as exc:
                    with self.engine.lock:
                        if not self._closed:self._failure(baseline,exc);run.update(status='failed',error=baseline['error']);self._save(run)
            self._launch(run,work)
            return self._public(run)

    def confirm_baseline(self,rid,baseline_version):
        with self.engine.lock:
            run=self._run(rid);self._maintenance();baseline=run['baseline']
            if run['busy'] or type(baseline_version) is not int or baseline_version!=baseline['version'] or baseline['status']!='done':
                raise UserError('请先查看本次已完成的基准图，再确认当前版本',409)
            self._checked_file(run,baseline)
            run['approval']=dict(confirmed=True,baseline_version=baseline_version,sha256=baseline['sha256'],mode=run['mode'],confirmed_at=time.time())
            run['status']='baseline_confirmed';self._save(run)
            return self._public(run)

    def _approved(self,run):
        baseline=run['baseline'];approval=run.get('approval') or {}
        if (baseline['status']!='done' or not approval.get('confirmed') or approval.get('baseline_version')!=baseline['version']
                or approval.get('sha256')!=baseline.get('sha256') or approval.get('mode')!=run['mode']):
            raise UserError('请先查看并确认当前基准图',409)
        self._checked_file(run,baseline)
        return copy.deepcopy(baseline)

    def _new_version(self,row):
        if row.get('version'):row.setdefault('versions',[]).append({k:copy.deepcopy(v) for k,v in row.items() if k!='versions'})
        row.update(version=row.get('version',0)+1,status='queued',error='',query_required=False)
        for key in ('raw_path','path','sha256','raw_sha256','provider_task_id','provider_original_path','provider_original_sha256',
                    'reason_code','baseline_version','prompt','reference_bindings','source_master_id','source_master_version','reuse_baseline','processing','logo_template','logo_refresh_source',
                    'export_crop_box','background_processing','background_repair_pending','background_repair_key','background_operation_id','background_native_path','background_source','background_original','background_force_ai','visual_review'):
            row.pop(key,None)
        row.pop('background_request',None)

    def _export_geometry(self,run,output,mapping,source):
        box=output.get('export_crop_box',mapping['crop_box'])
        policy=output.get('sizing_policy',mapping.get('sizing_policy'))
        if policy=='shared_canvas_crop':return box,'fixed_crop'
        if policy=='natural_if_needed':
            with Image.open(source) as image:
                ratio=Fraction(image.width,image.height);target=Fraction(output['width'],output['height'])
            difference=float(100*(1-min(ratio/target,target/ratio)))
            threshold=mapping.get('natural_background_threshold_percent',8)
            if output.get('export_crop_box') is None and difference>threshold+1e-9:
                raise UserError('该版位需要自然背景扩展，尚未完成；不会用色条代替成品',409)
            policy='fixed_crop'
        return box,policy

    def _export(self,run,output,master,source,baseline_version):
        from .learning_output import export_output
        mapping=next(o for o in run['compiled']['outputs'] if o['output_id']==output['id'])
        placement=run['placement_snapshots'][output['placement_id']]
        ext='.jpg' if placement.get('output_format')=='JPEG' else '.png'
        path=Path(run['directory'])/'outputs'/output['placement_id']/str(output['image_index'])/(f"v{output['version']}"+ext)
        with self.engine.lock:
            if not self._closed:
                output.update(prompt=master.get('prompt',''),reference_bindings=copy.deepcopy(master.get('reference_bindings',[])),
                              baseline_version=baseline_version,source_master_id=master['id'],source_master_version=master['version'],
                              reuse_baseline=bool(master.get('reuse_baseline')))
                self._save(run)
        logo_snapshot=output.get('logo_snapshot') or run['logo_snapshot']
        crop_box,policy=self._export_geometry(run,output,mapping,source)
        with getattr(self.engine,'processing_slots',nullcontext()):
            result=export_output(source,path,output['placement_id'],logo_snapshot,mask_snapshot=run['mask_snapshot'],
                                 crop_box=crop_box,placement_snapshot=placement,sizing_policy=policy)
            raw_sha256=_digest(source)
        compression = {}
        if result['format'] == 'PNG':
            compression['compression'] = {key: result[key] for key in
                                          ('bytes', 'pixel_lossless', 'palette_colors', 'alpha_palette_quantized')}
            compression['compression'].update({key: result[key] for key in ('compressor','dither') if key in result})
        with self.engine.lock:
            if not self._closed:
                output.update(status='done',path=str(path),sha256=result['sha256'],baseline_version=baseline_version,
                              raw_path=str(source),raw_sha256=raw_sha256,prompt=master.get('prompt',''),
                              reference_bindings=copy.deepcopy(master.get('reference_bindings',[])),
                              provider_task_id=master.get('provider_task_id'),
                              provider_original_path=master.get('provider_original_path'),provider_original_sha256=master.get('provider_original_sha256'),
                              sizing_policy=output.get('sizing_policy',mapping.get('sizing_policy')) or result['sizing']['sizing_policy'],
                              processing={**copy.deepcopy(result['sizing']),**compression,**copy.deepcopy(output.get('background_processing') or {}),**({'method':'shared_canvas_crop','source_box_scope':'generated_shared_canvas','full_source_preserved':False,'cv_detection_performed':False,'background_fill':'model_full_canvas','visual_review_required':True} if run.get('kind')=='shared_canvas_adaptation' else {})},
                              logo_template=copy.deepcopy(logo_snapshot['placements'][output['placement_id']]['logo_template']),
                              source_master_id=master['id'],source_master_version=master['version'],error='',query_required=False)
                self._save(run)

    def _background_request(self,run,output,source,source_sha,master,baseline_version,*,force_ai=False,force_nonce=None):
        from . import learning_background as helper
        spec=run['placement_snapshots'][output['placement_id']]
        text=({'t1':run['params']['t1']} if spec['modules']['main_copy'] else {})
        if spec['modules']['cta']:text['cta']=run['params']['cta']
        with Image.open(source) as image:sw,sh=image.size
        mapping=next(o for o in run['compiled']['outputs'] if o['output_id']==output['id'])
        threshold=mapping.get('natural_background_threshold_percent',8)
        planned=helper.plan(sw,sh,output['width'],output['height'],run['params']['image_model'],threshold_percent=threshold)
        proof={key:copy.deepcopy(master.get(key)) for key in ('id','version','prompt','reference_bindings','reuse_baseline',
                'provider_task_id','provider_original_path','provider_original_sha256')}
        if not planned['background_needed'] and not force_ai:
            box=self._center_box(sw,sh,output['width'],output['height'])
            return dict(kind='local',source=str(source),source_sha256=source_sha,master=proof,
                        baseline_version=baseline_version,crop_box=box,threshold_percent=threshold)
        simple_background=mapping.get('simple_background',False)
        base_key=helper.reuse_key(source_sha,planned,text,simple_background=simple_background)
        key=hashlib.sha256((base_key+'\0'+str(force_nonce)).encode()).hexdigest() if force_ai else base_key
        with self.engine.lock:existing=run.setdefault('background_operations',{}).get(key)
        if existing:return dict(kind='ai',operation_id=key,master=proof,baseline_version=baseline_version)
        native=Path(run['directory'])/'backgrounds'/key/'native.png'
        with getattr(self.engine,'processing_slots',nullcontext()):
            job=helper.prepare_job(run,source,native,output['width'],output['height'],allowed_text=text,
                                   simple_background=simple_background)
        if job['reuse_key']!=base_key:raise UserError('背景扩展复用身份不一致')
        job['id']='background-'+key;job['upload_cache']=str(Path(run['directory'])/'reference-upload-cache.json')
        from render import task_state_path
        operation=dict(id=key,status='queued',job=job,source=str(source),source_sha256=source_sha,
                       master=proof,baseline_version=baseline_version,receipt_path=str(task_state_path(native)))
        with self.engine.lock:
            run['background_operations'][key]=operation;self._save(run)
        return dict(kind='ai',operation_id=key,master=proof,baseline_version=baseline_version)

    @staticmethod
    def _center_box(sw,sh,width,height):
        source=Fraction(sw,sh);target=Fraction(width,height)
        x=min(Fraction(1),target/source);y=min(Fraction(1),source/target)
        return [float((1-x)/2),float((1-y)/2),float((1+x)/2),float((1+y)/2)]

    def _finish_background(self,run,output,request):
        if request['kind']=='local':
            source=self._checked_file(run,{'raw_path':request['source'],'sha256':request['source_sha256']})
            with self.engine.lock:
                output.update(export_crop_box=request['crop_box'],sizing_policy='fixed_crop',
                              background_processing={'background_repair_kind':'local_micro_crop','ai_background_repaired':False,
                                  'content_detection':'not_performed','natural_background_threshold_percent':request['threshold_percent']})
            self._export(run,output,request['master'],source,request['baseline_version'])
        else:
            from .learning_background import crop_ai_result
            operation=run['background_operations'][request['operation_id']]
            native=self._checked_file(run,operation['result'])
            target=Path(run['directory'])/'backgrounds'/operation['id']/output['placement_id']/str(output['image_index'])/f"v{output['version']}.png"
            with getattr(self.engine,'processing_slots',nullcontext()):
                final=crop_ai_result(native,target,operation['job']['background_plan'],output['width'],output['height'])
            with self.engine.lock:
                output.update(export_crop_box=[0,0,1,1],sizing_policy='natural_if_needed',
                              background_native_path=str(native),background_source={'path':operation['source'],'sha256':operation['source_sha256']},
                              background_processing={'method':'ai_background_expansion_then_exact_export','ai_background_repaired':run['mode']=='real',
                                  'ai_repair_performed':run['mode']=='real','full_source_preserved':False,
                                  'full_source_preserved_by':'model_instruction_and_user_review','source_box_scope':'final_ai_picture',
                                  'background_fill':'ai_generated' if run['mode']=='real' else 'simulation','content_detection':'not_performed','seam_review_required':True,
                                  'ai_final_crop_box':final['actual_source_crop_box'],'guide_padding_percent':operation['job']['background_plan']['padding_percent']})
            actual=operation['result']
            proof={key:copy.deepcopy(actual.get(key)) for key in ('prompt','reference_bindings','provider_task_id','provider_original_path','provider_original_sha256')}
            parent=request.get('master') or operation['master']
            master={**parent,**proof,'id':parent['id'],'version':parent['version']}
            self._export(run,output,master,Path(final['source']),request.get('baseline_version',operation['baseline_version']))
        with self.engine.lock:
            output.update(background_repair_pending=False,query_required=False)
            output.pop('background_repair_key',None);self._save(run)

    def _background_batch(self,run,items):
        """Queue deduplicated AI extensions, then finish exact local exports."""
        failures=[];futures={};targets={}
        for output,request in items:
            try:
                if request['kind']=='local':self._finish_background(run,output,request);continue
                key=request['operation_id'];operation=run['background_operations'][key]
                targets.setdefault(key,[]).append((output,request))
                with self.engine.lock:
                    output.update(background_native_path=operation['job']['output'],raw_path=operation['job']['output'],
                                  prompt=operation['job']['prompt'],reference_bindings=copy.deepcopy(operation['job']['reference_bindings']));self._save(run)
                if operation.get('status')=='done':continue
                if operation.get('restore_query_blocked'):raise UserError('待恢复的背景供应商记录缺失，不能安全重新提交',409)
                if key in futures.values():continue
                frozen=copy.deepcopy(operation['job'])
                expected=Path(run['directory'])/'backgrounds'/key/'native.png'
                native=self._execution_path(run,{'raw_path':frozen['output'],'query_required':operation.get('query_required',False)},expected)
                frozen['output']=str(native)
                with self.engine.lock:
                    operation['job']['output']=str(native)
                    output.update(background_native_path=frozen['output'],raw_path=frozen['output']);self._save(run)
                def execute(job=frozen,operation=operation):
                    with self.engine.lock:operation['status']='generating';self._save(run)
                    return self.executor.generate_image(job,self.stop_event)
                futures[self._submit_image(run,execute)]=key
            except Exception as exc:
                failures.append(output['id'])
                with self.engine.lock:self._failure(output,exc);self._save(run)
        for future in as_completed(futures):
            key=futures[future];operation=run['background_operations'][key]
            try:
                result=future.result();changes=self._image_result(run,result,operation['job']['output'],operation['job']['aspect_ratio'])
                changes.setdefault('prompt',operation['job']['prompt']);changes.setdefault('reference_bindings',operation['job']['reference_bindings'])
                with self.engine.lock:operation.update(status='done',result=changes,error='',query_required=False);self._save(run)
            except Exception as exc:
                with self.engine.lock:
                    self._failure(operation,exc)
                    for output,_ in targets[key]:self._failure(output,exc);failures.append(output['id'])
                    self._save(run)
        for key,rows in targets.items():
            if run['background_operations'][key].get('status')!='done':continue
            for output,request in rows:
                try:self._finish_background(run,output,request)
                except Exception as exc:
                    failures.append(output['id'])
                    with self.engine.lock:self._failure(output,exc);self._save(run)
        return failures

    def _process_exports(self,run,items):
        """The normal workflow shares the same explicit background machinery."""
        failures=[];requests=[];key='automatic-background-'+uuid.uuid4().hex
        for output,master,source,baseline_version in items:
            if output['status']=='done':continue
            mapping=next(o for o in run['compiled']['outputs'] if o['output_id']==output['id'])
            policy=output.get('sizing_policy',mapping.get('sizing_policy'))
            try:
                if policy!='natural_if_needed':
                    self._export(run,output,master,source,baseline_version);continue
                digest=_digest(source)
                if master.get('sha256') and master['sha256']!=digest:raise UserError('来源母版校验失败')
                original=dict(raw_path=str(source),raw_sha256=digest,source_master_id=master['id'],
                              source_master_version=master['version'],baseline_version=baseline_version,
                              prompt=master.get('prompt',''),reference_bindings=copy.deepcopy(master.get('reference_bindings',[])))
                with self.engine.lock:
                    output.update(background_repair_pending=True,background_repair_key=key,background_original=original)
                    self._save(run)
                request=self._background_request(run,output,source,digest,master,baseline_version)
                with self.engine.lock:output['background_request']=copy.deepcopy(request);self._save(run)
                requests.append((output,request))
            except Exception as exc:
                failures.append(output['id'])
                with self.engine.lock:self._failure(output,exc);self._save(run)
        pending=[o['id'] for o,_,_,_ in items if o.get('background_repair_pending')]
        if pending:
            with self.engine.lock:
                run['operation_keys']['background:'+key]={'at':time.time(),'output_ids':pending};self._save(run)
        return failures+self._background_batch(run,requests)

    def repair_backgrounds(self,rid,idempotency_key,output_ids=None,*,force_ai=False):
        key=_key(idempotency_key)
        if type(force_ai) is not bool:raise UserError('背景重新生成选项不正确')
        if force_ai and output_ids is None:raise UserError('请明确选择要重新生成背景的图片')
        with self.engine.lock:
            run=self._run(rid);record=run['operation_keys'].get('background:'+key)
            available={row['id']:row for row in run['outputs']}
            if record:
                ids=record['output_ids']
                if output_ids is not None and (not isinstance(output_ids,list) or not output_ids or any(not isinstance(oid,str) for oid in output_ids) or not set(output_ids)<=set(ids)):
                    raise UserError('重复背景操作的图片范围已改变',409)
            else:
                ids=[row['id'] for row in run['outputs'] if row.get('background_repair_pending') or row['status']=='done' and row.get('processing',{}).get('padding_percent',0)>0] if output_ids is None else output_ids
            if (not isinstance(ids,list) or not ids or any(not isinstance(oid,str) or oid not in available for oid in ids)
                    or len(ids)!=len(set(ids))):raise UserError('请选择本批次需要背景处理的图片')
            targets=[available[oid] for oid in ids]
            for row in targets:
                if run['placement_snapshots'][row['placement_id']].get('artwork_width'):
                    raise UserError('该版位右侧为固定纯色区域，请使用重出本图调整主画面',409)
                request=row.get('background_request') or {}
                if request.get('kind')=='ai':
                    operation=run.get('background_operations',{}).get(request.get('operation_id'),{})
                    if operation.get('job',{}).get('background_plan',{}).get('version')!=3:
                        raise UserError('此画幅制作流程已停用，请按新规则重新配置制作',409)
            if force_ai and not record and any(row.get('background_repair_pending') for row in targets):
                raise UserError('请先恢复尚未完成的背景任务，再重新生成背景',409)
            if any(row.get('query_required') and not row.get('background_repair_pending') for row in targets):
                raise UserError('请先恢复原图片的供应商查询',409)
            if any(row['status']!='done' and not row.get('background_repair_pending') for row in targets):
                raise UserError('请先完成所选图片，再处理背景',409)
            resume=bool(record and any(row.get('background_repair_pending') for row in targets))
            if not self._claim(run,'background',key,resume_existing=resume):return self._public(run)
            if record:targets=[row for row in targets if row.get('background_repair_pending')]
            run['operation_keys']['background:'+key]['output_ids']=list(ids)
            originals={}
            for output in targets:
                if output.get('background_repair_pending'):continue
                originals[output['id']]=copy.deepcopy(output)
                self._new_version(output)
                output.update(status='processing',background_repair_pending=True,background_repair_key=key,background_force_ai=force_ai)
            run['status']='generating_suite';self._save(run)
            def work():
                requests=[]
                for output in targets:
                    if output['status']=='done' and not output.get('background_repair_pending'):continue
                    try:
                        request=output.get('background_request')
                        if request is None:
                            old=originals.get(output['id']) or output.get('background_original') or output['versions'][-1]
                            original=None
                            if output.get('background_force_ai'):
                                original=old.get('background_source') or next((v['background_source'] for v in reversed(old.get('versions',[])) if v.get('background_source')),None)
                            source=self._checked_file(run,{'raw_path':original['path'] if original else old['raw_path'],
                                                          'sha256':original['sha256'] if original else old['raw_sha256']})
                            source_sha=original['sha256'] if original else old['raw_sha256']
                            master={**old,'id':old['source_master_id'],'version':old['source_master_version']}
                            request=self._background_request(run,output,source,source_sha,master,old['baseline_version'],
                                                             force_ai=output.get('background_force_ai',False),force_nonce=key)
                            with self.engine.lock:output['background_request']=copy.deepcopy(request);self._save(run)
                        requests.append((output,request))
                    except Exception as exc:
                        with self.engine.lock:self._failure(output,exc);self._save(run)
                self._background_batch(run,requests)
                with self.engine.lock:
                    run['status']='completed' if all(row['status']=='done' for row in run['outputs']) else 'failed'
                    if run['status']=='completed':run['suite']['status']='completed'
                    self._save(run)
            self._launch(run,work)
            return self._public(run)

    def expand_suite(self,rid,idempotency_key):
        with self.engine.lock:
            run=self._run(rid);baseline=self._approved(run)
            if any(o.get('background_repair_pending') for o in run['outputs']):raise UserError('请先恢复未完成的背景处理',409)
            if any(o.get('query_required') for o in run['outputs']):raise UserError('请先恢复状态不明的单张图片查询',409)
            if any(o.get('visual_review') and o['status']!='done' for o in run['outputs']):
                raise UserError('请先在相应图片卡片处理单张重出的文字审核',409)
            if (run['suite'].get('status')=='completed' and run['suite'].get('baseline_version')==baseline['version']
                    and all(o['status']=='done' for o in run['outputs'])):
                return self._public(run)
            if not self._claim(run,'expand',idempotency_key):return self._public(run)
            # A new request after an uncertain interrupted suite uses the same
            # immutable master filenames and receipts, rather than resubmitting.
            recovering=run['suite'].get('baseline_version')==baseline['version'] and run['suite'].get('status') in ('failed','interrupted','completed','generating')
            run['suite']={'status':'generating','baseline_version':baseline['version']};run['status']='generating_suite'
            for master in run['masters']:
                if not recovering or master['status']=='failed' and not master.get('query_required') and not master.get('visual_review'):
                    self._new_version(master)
            for output in run['outputs']:
                if not recovering:self._new_version(output)
            self._save(run)
            def work():
                failures=[]
                pending={}
                reviews={}
                exports=[]
                def block(master,targets):
                    failures.append(master['id'])
                    with self.engine.lock:
                        for output in targets:
                            if output['status']!='done':
                                output.update(status='blocked',error=master['error'] if master.get('visual_review') else '来源母版尚未完成')
                        self._save(run)
                def queue_review(master,entry,targets):
                    reviews[self.visual_pool.submit(self._visual_gate,run,master,entry)]=(master,targets)
                for master in run['masters']:
                    if self.stop_event.is_set():return
                    entry=next(m for m in run['compiled']['masters'] if m['id']==master['id'])
                    targets=[o for o in run['outputs'] if o['master_id']==master['id']]
                    try:
                        if master.get('status')=='done':
                            source=self._checked_file(run,master)
                        elif master.get('visual_review'):
                            queue_review(master,entry,targets)
                            continue
                        elif entry.get('reuse_baseline'):
                            source=self._checked_file(run,baseline)
                            changes=dict(status='done',raw_path=str(source),sha256=baseline['sha256'],
                                         baseline_version=baseline['version'],prompt=entry['prompt'],reuse_baseline=True)
                            if entry.get('concept_route')=='direct':
                                self._record_generated(run,master,entry,changes)
                                if master.get('visual_review'):
                                    queue_review(master,entry,targets)
                                    continue
                            else:
                                with self.engine.lock:master.update(changes);self._save(run)
                        else:
                            raw=self._execution_path(run,master,Path(run['directory'])/'masters'/master['id']/f"v{master['version']}.png")
                            with self.engine.lock:master.update(status='queued',raw_path=str(raw),baseline_version=baseline['version'],
                                                               prompt=entry['prompt'],reuse_baseline=False);self._save(run)
                            job=self._job(run,entry,raw,'master',baseline)
                            def execute(job=job,master=master):
                                with self.engine.lock:
                                    if not self._closed:master['status']='generating';self._save(run)
                                return self.executor.generate_image(job,self.stop_event)
                            pending[self._submit_image(run,execute)]=(master,entry,targets,raw)
                            continue
                        for output in targets:
                            if output['status']=='done':continue
                            exports.append((output,master,source,baseline['version']))
                    except Exception as exc:
                        with self.engine.lock:self._failure(master,exc)
                        block(master,targets)
                for future in as_completed(pending):
                    if self.stop_event.is_set():return
                    master,entry,targets,raw=pending[future]
                    try:
                        changes=self._image_result(run,future.result(),raw,entry['aspect_ratio'])
                        self._record_generated(run,master,entry,changes)
                        if master.get('visual_review'):
                            queue_review(master,entry,targets)
                            continue
                        for output in targets:
                            if output['status']=='done':continue
                            exports.append((output,master,Path(master['raw_path']),baseline['version']))
                    except Exception as exc:
                        with self.engine.lock:self._failure(master,exc)
                        block(master,targets)
                for future in as_completed(reviews):
                    master,targets=reviews[future]
                    if self.stop_event.is_set():return
                    try:
                        if future.result():
                            source=self._checked_file(run,master)
                            exports.extend((o,master,source,baseline['version']) for o in targets if o['status']!='done')
                            continue
                    except Exception as exc:
                        with self.engine.lock:self._failure(master,exc)
                    block(master,targets)
                failures+=self._process_exports(run,exports)
                with self.engine.lock:
                    if not self._closed:
                        run['suite']['status']='failed' if failures else 'completed'
                        run['status']='failed' if failures else 'completed'
                        if failures:
                            if any(m['status']=='visual_hold' for m in run['masters']):
                                run['error']='部分母版需要复核。可在制作进度查看原图和审核结果。'
                            else:
                                run['error']='部分背景处理尚未完成，请恢复背景任务' if any(o.get('background_repair_pending') for o in run['outputs']) else '部分图片尚未完成，可恢复整套或单张重出'
                        self._save(run)
            self._launch(run,work)
            return self._public(run)

    def regenerate_canvas_master(self,rid,master_id,idempotency_key,expected_version=None,*,_review_resume=False,_redraw_review=False):
        key=_key(idempotency_key);scope='canvas-master-'+master_id
        with self.engine.lock:
            run=self._run(rid)
            if not _review_resume and run.get('kind')!='shared_canvas_adaptation':
                raise UserError('该操作仅用于共用母版批次')
            baseline=self._approved(run)
            master=next((m for m in run['masters'] if m['id']==master_id),None)
            if not master:raise UserError('共用母版不存在',404)
            if _review_resume and not master.get('visual_review'):
                raise UserError('该母版没有可恢复的审核',409)
            if _redraw_review and master.get('query_required'):
                raise UserError('请先恢复已有图片查询',409)
            recovering=bool(master.get('query_required') or master.get('status')=='interrupted' and self._has_receipt(master)
                            or master.get('visual_review') and master['visual_review']['status']!='approved') and not _redraw_review
            if scope+':'+key in run['operation_keys'] and (run['busy'] or not recovering):return self._public(run)
            if expected_version is not None and (type(expected_version) is not int or expected_version!=master['version']):
                raise UserError('母版版本已更新，请刷新后重试',409)
            targets=[o for o in run['outputs'] if o['master_id']==master_id]
            if any(o.get('background_repair_pending') or o.get('query_required') for o in targets):
                raise UserError('请先恢复该组尚未完成的图片处理',409)
            if not self._claim(run,scope,key,resume_existing=recovering):return self._public(run)
            if not recovering:
                self._new_version(master)
                for output in targets:
                    self._new_version(output)
                    if run.get('kind')=='shared_canvas_adaptation':output['sizing_policy']='shared_canvas_crop'
            review_pending=recovering and bool(master.get('visual_review'))
            raw=Path(master['raw_path']) if review_pending else self._execution_path(run,master,Path(run['directory'])/'masters'/master_id/f"v{master['version']}.png")
            entry=next(m for m in run['compiled']['masters'] if m['id']==master_id)
            master.update(raw_path=str(raw),status='queued',prompt=entry['prompt'],regeneration_key=key)
            run.update(status='generating_suite');self._save(run)
            def work():
                try:
                    if not review_pending:
                        job=self._job(run,entry,raw,'master',baseline)
                        with self.engine.lock:master['status']='generating';self._save(run)
                        result=self._submit_image(run,self.executor.generate_image,job,self.stop_event).result()
                        self._record_generated(run,master,entry,self._image_result(run,result,raw,entry['aspect_ratio']))
                    if not self.visual_pool.submit(self._visual_gate,run,master,entry).result():
                        with self.engine.lock:
                            for output in targets:output.update(status='blocked',error=master['error'])
                            run.update(status='failed',error=master['error']);run['suite']['status']='failed';self._save(run)
                        return
                    with self.engine.lock:master.pop('regeneration_key',None);self._save(run)
                    errors=self._process_exports(run,[(o,master,Path(master['raw_path']),baseline['version']) for o in targets])
                    with self.engine.lock:
                        done=not errors and all(o['status']=='done' for o in run['outputs'])
                        run['status']='completed' if done else 'failed';run['suite']['status']=run['status'];self._save(run)
                except Exception as exc:
                    with self.engine.lock:
                        self._failure(master,exc)
                        for output in targets:output.update(status='blocked',error='来源母版未完成，请恢复本组母版')
                        run.update(status='failed',error=master['error']);self._save(run)
            self._launch(run,work);return self._public(run)

    def refresh_logos(self,rid,idempotency_key,placement_ids=None):
        """Re-export existing raw pixels with current logo templates; no models."""
        with self.engine.lock:
            run=self._run(rid)
            available={pid for pid,spec in run['placement_snapshots'].items() if spec['modules']['logo'] and pid not in RETIRED_LOGO_PLACEMENTS}
            ids=sorted(available) if placement_ids is None else placement_ids
            if (not isinstance(ids,list) or not ids or any(not isinstance(pid,str) or pid not in available for pid in ids)
                    or len(ids)!=len(set(ids))):raise UserError('请选择本批次已有Logo的版位')
            targets=[o for o in run['outputs'] if o['placement_id'] in ids]
            if any(o['status']!='done' and not (o['status'] in ('failed','interrupted') and o.get('logo_refresh_source')) for o in targets):
                raise UserError('请先完成这些图片再更新Logo',409)
            if not self._claim(run,'refresh-logos',idempotency_key):return self._public(run)
            old_rows={o['id']:copy.deepcopy(o.get('logo_refresh_source') or o) for o in targets}
            for old in old_rows.values():old.pop('versions',None);old.pop('logo_refresh_source',None)
            previous_status=run['status'];self._save(run)
            def work():
                from .learning_logo import freeze_templates
                try:
                    snapshot=freeze_templates(self.engine.settings,ids,cache=Path(run['directory'])/'logo-layers'/uuid.uuid4().hex)
                    sources={oid:self._checked_file(run,{'raw_path':old['raw_path'],'sha256':old['raw_sha256']}) for oid,old in old_rows.items()}
                    for output in targets:
                        old=old_rows[output['id']];pid=output['placement_id']
                        old_snapshot=old.get('logo_snapshot') or run['logo_snapshot']
                        if output['status']=='done' and old_snapshot['placements'][pid]['logo_template']==snapshot['placements'][pid]['logo_template']:continue
                        with self.engine.lock:
                            self._new_version(output);output.update(status='processing',logo_snapshot=copy.deepcopy(snapshot),logo_refresh_source=copy.deepcopy(old))
                            for field in ('export_crop_box','sizing_policy','background_processing','background_operation_id','background_native_path','background_source'):
                                if field in old:output[field]=copy.deepcopy(old[field])
                            self._save(run)
                        master={**old,'id':old['source_master_id'],'version':old['source_master_version']}
                        self._export(run,output,master,sources[output['id']],old['baseline_version'])
                        with self.engine.lock:output.pop('logo_refresh_source',None);self._save(run)
                    with self.engine.lock:
                        run['status']='completed' if all(o['status']=='done' for o in run['outputs']) else previous_status
                        self._save(run)
                except Exception as exc:
                    with self.engine.lock:
                        for output in targets:
                            if output['status']=='processing':self._failure(output,exc)
                        run.update(status='failed',error=exc.message if isinstance(exc,UserError) else 'Logo更新未完成，原图片版本已保留')
                        self._save(run)
            self._launch(run,work)
            return self._public(run)

    def regenerate_output(self,rid,output_id,idempotency_key,resume=False,expected_version=None):
        with self.engine.lock:
            run=self._run(rid);baseline=self._approved(run)
            output=next((o for o in run['outputs'] if o['id']==output_id),None)
            if output is None:raise UserError('图片不存在',404)
            if output.get('background_repair_pending'):raise UserError('该图片仍需恢复背景处理，请使用背景修复操作',409)
            if not output.get('query_required') and any(m['id']==output['master_id'] and m.get('query_required') for m in run['masters']):
                raise UserError('来源母版状态不明，请先恢复整套查询',409)
            if expected_version is not None and (type(expected_version) is not int or output['version']!=expected_version):
                raise UserError('图片版本已更新，请刷新后重试',409)
            if not self._claim(run,'output-'+output_id,idempotency_key):return self._public(run)
            review_pending=bool(output.get('visual_review') and output['status']!='done')
            recovering=bool(output.get('query_required') or review_pending)
            if resume and not recovering:
                run['busy']=False;raise UserError('该图片没有待恢复的供应商任务',409)
            if not recovering:self._new_version(output)
            run['status']='generating_suite'
            raw=Path(output['raw_path']) if review_pending else self._execution_path(run,output,Path(run['directory'])/'singles'/output['placement_id']/str(output['image_index'])/f"v{output['version']}.png")
            output.update(raw_path=str(raw),status='generating');self._save(run)
            def work():
                try:
                    from .learning_runtime_support import compile_single
                    entry=compile_single(run,output_id)
                    with self.engine.lock:
                        if not self._closed:
                            output.update(prompt=entry['prompt'],baseline_version=baseline['version'],
                                          source_master_id='single-'+output_id,source_master_version=output['version'],reuse_baseline=False)
                            self._save(run)
                    if not review_pending:
                        job=self._job(run,entry,raw,'single',baseline)
                        result=self._submit_image(run,self.executor.generate_image,job,self.stop_event).result()
                        self._record_generated(run,output,entry,self._image_result(run,result,raw,entry['aspect_ratio']),single=True)
                    if not self.visual_pool.submit(self._visual_gate,run,output,entry,single=True).result():
                        with self.engine.lock:run.update(status='failed',error=output['error']);self._save(run)
                        return
                    self._process_exports(run,[(output,{**output,'id':'single-'+output_id},Path(output['raw_path']),baseline['version'])])
                    with self.engine.lock:
                        if not self._closed:run['status']='completed' if all(o['status']=='done' for o in run['outputs']) else 'failed';self._save(run)
                except Exception as exc:
                    with self.engine.lock:
                        if not self._closed:self._failure(output,exc);run.update(status='failed',error=output['error']);self._save(run)
            self._launch(run,work)
            return self._public(run)

    def visual_image(self,rid,kind,image_id,version,variant):
        with self.engine.lock:
            run=self._run(rid)
            rows=run['masters'] if kind=='master' else run['outputs']
            current=next((r for r in rows if r['id']==image_id),None)
            if current is None:raise UserError('审核图片不存在',404)
            row=next((r for r in [current,*current.get('versions',[])] if r['version']==version),{})
            review=row.get('visual_review',{})
            proof=review.get('original') if variant=='original' else review.get('repair',{}).get('result')
            if not proof:raise UserError('审核图片尚不可查看',404)
        return self._checked_file(run,proof)

    def image(self,rid,kind,image_id,version=None):
        if kind=='source':
            with self.engine.lock:
                run=self._run(rid)
                row=next((s for s in run.get('sources',[]) if str(s['image_index'])==image_id),None)
                if not row:raise UserError('来源图片不存在',404)
                identity={'directory':run['directory']};chosen={'raw_path':row['path'],'sha256':row['sha256']}
            return self._checked_file(identity,chosen)
        with self.engine.lock:
            run=self._run(rid)
            if kind=='package':row=next((p for p in run['packages'] if p['id']==image_id),None);path_key='path'
            else:
                candidates=([run['baseline'],*run.get('baseline_versions',[])] if kind=='baseline' else run['masters'] if kind=='master' else run['outputs'] if kind=='output' else [])
                row=next((r for r in candidates if r['id']==image_id and (version is None or r['version']==version)),None)
                if row is None:
                    row=next((v for r in candidates for v in r.get('versions',[]) if v['id']==image_id and v['version']==version),None)
                path_key='path' if kind=='output' else 'raw_path'
            if row is None or kind!='package' and row.get('status')!='done':raise UserError('该图片版本尚不可查看',404)
            identity={'directory':run['directory']}
            selected={key:row[key] for key in (path_key,'sha256') if key in row}
        return self._checked_file(identity,selected,path_key)

    def _logo_export_rows(self,run,rows,asset_id):
        from .learning_logo import variant_snapshot
        from .learning_output import export_output
        result=[]
        for row in rows:
            pid=row['placement_id'];spec=run['placement_snapshots'][pid]
            if not spec['modules']['logo']:
                result.append(row);continue
            original=row.get('logo_snapshot') or run['logo_snapshot']
            snapshot=variant_snapshot(original,asset_id,Path(run['directory'])/'export-logos'/asset_id)
            source=self._checked_file(run,{'raw_path':row['raw_path'],'sha256':row['raw_sha256']})
            mapping=next(o for o in run['compiled']['outputs'] if o['output_id']==row['id'])
            sizing_policy=row.get('sizing_policy',mapping.get('sizing_policy'))
            crop_box,sizing_policy=self._export_geometry(run,row,mapping,source)
            identity=[row['raw_sha256'],snapshot['placements'][pid],snapshot['assets'][asset_id]['sha256'],
                      spec,run['mask_snapshot'][pid],crop_box,sizing_policy]
            stamp=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
            ext='.jpg' if spec.get('output_format')=='JPEG' else '.png'
            target=Path(run['directory'])/'logo-exports'/(stamp+ext);receipt=target.with_suffix('.json')
            cached=None
            if target.is_file() and receipt.is_file():
                try:
                    saved=json.loads(receipt.read_text())
                    if saved.get('sha256')==_digest(target):cached=saved
                except (OSError,ValueError):pass
            if cached is None:
                with getattr(self.engine,'processing_slots',nullcontext()):
                    cached=export_output(source,target,pid,snapshot,mask_snapshot=run['mask_snapshot'],placement_snapshot=spec,
                                         crop_box=crop_box,sizing_policy=sizing_policy)
                receipt.write_text(json.dumps({'sha256':cached['sha256']}))
            result.append({**row,'path':str(target),'sha256':cached['sha256'],
                           'logo_template':copy.deepcopy(snapshot['placements'][pid]['logo_template']),
                           'logo_asset_sha256':snapshot['assets'][asset_id]['sha256']})
        return result

    def package(self,rid,logo_asset_id=None):
        from .learning_logo import ASSET_IDS
        if logo_asset_id not in (None,*ASSET_IDS):raise UserError('请选择黑字标准版或白字APP版Logo')
        with self.engine.lock:
            run=self._run(rid);self._maintenance()
            if run['busy'] or any(o['status']!='done' for o in run['outputs']):raise UserError('请等待全部图片完成并通过规格检查后保存',409)
            rows=copy.deepcopy(run['outputs'])
            run['busy']=True;self._save(run)
        try:
            if logo_asset_id is not None:rows=self._logo_export_rows(run,rows,logo_asset_id)
            paths=_package_paths(run,rows)
            layout=CHANNEL_PACKAGE_LAYOUT if run.get('target_kind')!='ordinary' else None
            values=[(o['id'],o['sha256']) for o in rows]
            identity=values if logo_asset_id is None else {'images':values,'logo_asset_id':logo_asset_id}
            if layout:identity={'images':values,'logo_asset_id':logo_asset_id,'archive_layout':layout,'paths':paths}
            fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
            for existing in run['packages']:
                if existing['fingerprint']==fingerprint:
                    try:self._checked_file(run,existing,'path');return {k:v for k,v in existing.items() if k!='path'}
                    except UserError:pass
            manifest=[]
            for row,archive_path in zip(rows,paths):
                path=self._checked_file(run,row,'path');spec=run['placement_snapshots'][row['placement_id']]
                with Image.open(path) as image:
                    if image.format!=spec.get('output_format','PNG') or image.size!=(spec['target_width'],spec['target_height']):raise UserError('交付图片规格不符',409)
                    image.verify()
                limit=spec.get('max_file_size_kb')
                if limit is not None and (path.stat().st_size>limit*1024 or path.stat().st_size==limit*1024 and spec.get('file_size_operator')=='lt'):
                    raise UserError('交付图片超过固定大小限制',409)
                layer=row.get('logo_snapshot') or run['logo_snapshot']
                template=row.get('logo_template') or layer['placements'][row['placement_id']]['logo_template']
                actual_logo=template['asset_id'] if spec['modules']['logo'] else None
                logo_sha=row.get('logo_asset_sha256') or (layer['assets'].get(actual_logo) or {}).get('sha256')
                manifest.append(dict(placement_id=row['placement_id'],image_index=row['image_index'],version=row['version'],
                                     baseline_version=row['baseline_version'],width=row['width'],height=row['height'],sha256=row['sha256'],
                                     path=archive_path,platform=spec.get('platform'),placement_name=spec.get('name'),logo_asset_id=actual_logo,
                                     logo_asset_sha256=logo_sha,logo_template=copy.deepcopy(template)))
            version=len(run['packages'])+1;pid=uuid.uuid4().hex
            target=Path(run['directory'])/'packages'/f'v{version:03d}-{pid}.zip';target.parent.mkdir(parents=True,exist_ok=True)
            temporary=target.with_suffix('.tmp.zip')
            try:
                with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
                    for row,item in zip(rows,manifest):archive.write(row['path'],item['path'])
                    archive.writestr('交付清单.json',json.dumps({'run_id':rid,'mode':run['mode'],'logo_asset_id':logo_asset_id,'images':manifest,**({'archive_layout':layout} if layout else {})},ensure_ascii=False,indent=2))
                with zipfile.ZipFile(temporary) as archive:
                    if archive.testzip() is not None:raise UserError('图包文件校验失败')
                    for item in manifest:
                        if hashlib.sha256(archive.read(item['path'])).hexdigest()!=item['sha256']:raise UserError('图包图片哈希核验失败')
                os.replace(temporary,target)
            finally:temporary.unlink(missing_ok=True)
            package=dict(id=pid,version=version,image_count=len(rows),download_url='/api/learning-machine/runs/'+rid+'/packages/'+pid,
                         logo_asset_id=logo_asset_id,sha256=_digest(target),mode=run['mode'],created_at=time.time(),path=str(target),fingerprint=fingerprint)
            if layout:package['archive_layout']=layout
            with self.engine.lock:run['packages'].append(package);self._save(run)
            return {k:v for k,v in package.items() if k!='path'}
        finally:
            with self.engine.lock:run['busy']=False;self._save(run)

    def package_file(self,rid,package_id):
        return self.image(rid,'package',package_id)

    def close(self):
        with self.engine.lock:
            if self._closed:return
            for run in self.runs.values():
                if run.get('busy'):
                    run.update(busy=False,status='interrupted',error='本机服务已停止，已有图片和版本已保留')
                    if run['suite']['status']=='generating':run['suite']['status']='interrupted'
                    for row in [run['baseline'],*run['masters'],*run['outputs']]:
                        if row['status'] in ACTIVE:row.update(status='interrupted',query_required=self._has_receipt(row))
                    self._save(run)
            self._closed=True;self.stop_event.set();threads=list(self._threads)
        for thread in threads:thread.join(timeout=2)
        self.visual_pool.shutdown(wait=False,cancel_futures=True)
