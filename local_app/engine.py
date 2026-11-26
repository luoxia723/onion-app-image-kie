from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import copy
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from .config import ROOT, Settings, UserError, DEFAULT_IMAGE_MODEL, IMAGE_MODELS
from .state import StateMixin, content_fingerprint
from .scheduler import SchedulerMixin
from .workbench import WorkbenchMixin
from .delivery import DeliveryMixin
from .maintenance import MaintenanceMixin
from .safety import require_space,valid_task
from .instance import InstanceLock
from .kie_recovery import BLOCKED_RECEIPT_MESSAGE, receipt_recovery_action
from .scene_planner import ApiScenePlanner, PlanningRequestError, PlanningStopped
from .planning import BY_ID, ASSETS, make_round, validate, normalize_form, copy_signature, requested_pairs, compile_plans, suite_metadata
from . import learning_workflow, learning_source, ximalaya
sys.path.insert(0,str(ROOT/'scripts'))
import positive_prompt
import render
from image_compress import compress

ACTIVE=('queued','generating')
QUERY_RETRY_DELAYS=render.QUERY_RETRY_DELAYS
LIMIT_RETRY_DELAYS=(10,30,60)
REVIEW_RETRY_DELAYS=(8,20,45)
LOCAL_RETRY_DELAYS=(3,10)
PLANNING_RETRY_DELAYS=(5,15)
XIMALAYA_PENDING=('pending','export_pending')

def selection_key(pid,number): return str(pid)+'::'+str(number)

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def atomic(path, value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(path)

class Engine(StateMixin, SchedulerMixin, WorkbenchMixin, DeliveryMixin, MaintenanceMixin):
    def __init__(self, settings=None, start=True, planner=None):
        self.settings=settings or Settings()
        self.instance_lock=InstanceLock(self.settings.state_dir/'service.lock')
        self.lock=threading.RLock()
        self.db=sqlite3.connect(self.settings.state_dir/'index.sqlite3',check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, body TEXT NOT NULL, idem TEXT UNIQUE)')
        self.db.execute('CREATE TABLE IF NOT EXISTS documents(name TEXT PRIMARY KEY, body TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS quarantined_tasks(id TEXT PRIMARY KEY,body TEXT,reason TEXT,created_at REAL)')
        self.db.commit()
        if self.db.execute('PRAGMA user_version').fetchone()[0]<2:
            if self.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]:
                backups=self.settings.state_dir/'backups';backups.mkdir(exist_ok=True)
                target=sqlite3.connect(backups/('schema-1-before-upgrade-'+uuid.uuid4().hex+'.sqlite3'))
                try:self.db.backup(target)
                finally:target.close()
            self.db.execute('PRAGMA user_version=2');self.db.commit()
        self.planner=planner or ApiScenePlanner(self.settings)
        self.planning_running=set()
        self.planning_pool=ThreadPoolExecutor(max_workers=1)
        self.tasks={}
        for tid,body in self.db.execute('SELECT id,body FROM tasks').fetchall():
            try:
                value=json.loads(body)
                if not valid_task(value,tid):raise ValueError('invalid task')
                self.tasks[tid]=value
            except (ValueError,KeyError,TypeError):
                self.db.execute('INSERT OR REPLACE INTO quarantined_tasks VALUES(?,?,?,?)',(tid,body,'记录损坏或字段缺失',time.time()))
                self.db.execute('DELETE FROM tasks WHERE id=?',(tid,))
        self.db.commit()
        self.running=set()
        self.closed=threading.Event()
        self.throttle=20
        self.image_backoff_until=0
        from .work_dispatch import FairImagePool
        self.pool=FairImagePool(max_workers=20,limit_provider=lambda:0 if not self.closed.is_set() and time.monotonic()<self.image_backoff_until else min(self.throttle,self.settings.concurrency),max_pending=512)
        self.processing_slots=threading.BoundedSemaphore(4)
        self.next_submit=0
        self.audit_path=self.settings.state_dir/'submissions.jsonl'
        self.summary_cache={}
        self.last_dispatched=None
        self.last_planned=None
        self.progress_reads={}
        self.package_locks={}
        self.workspace_lock=threading.Lock()
        self.maintenance_lock=threading.Lock()
        self.maintenance_active=False
        self.last_scheduler_error=None
        self.last_rate_limit=0
        self.last_rate_limit_cut=None
        self.next_throttle_recovery=0
        self.recover_recycle()
        self.recover()
        self.cleanup()
        if start:
            self.scheduler=threading.Thread(target=self.loop,daemon=True)
            self.scheduler.start()

    def persist(self,t,idem=None):
        t['revision']=t.get('revision',0)+1
        t['updated_at']=time.time()
        self.db.execute('INSERT INTO tasks VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body', (t['id'],json.dumps(t,ensure_ascii=False),idem))
        self.db.commit()
        self.tasks[t['id']]=t

    def recover(self):
        for tid,t in list(self.tasks.items()):
            try:self.recover_task(t)
            except (KeyError,TypeError,ValueError,IndexError,UserError):
                self.db.execute('INSERT OR REPLACE INTO quarantined_tasks VALUES(?,?,?,?)',(tid,json.dumps(t,ensure_ascii=False),'恢复记录字段异常，原数据已隔离保留',time.time()))
                self.db.execute('DELETE FROM tasks WHERE id=?',(tid,));self.db.commit();self.tasks.pop(tid,None)

    def recover_task(self,t):
        for pkg in t.get('pkgs',[]):
            if pkg.get('fingerprint_schema') not in (2,3) and Path(pkg['path']).is_file():
                try:
                    with zipfile.ZipFile(pkg['path']) as archive:
                        manifest=json.loads(archive.read('交付清单.json'))
                    pkg['fingerprint']=content_fingerprint([{'pid':x['placement_id'],'set':x['set'],'idx':x['image'],'sha256':x['sha256']} for x in manifest['images']])
                    pkg['fingerprint_schema']=2
                except (OSError,ValueError,KeyError,zipfile.BadZipFile): pass
        t.pop('exporting',None)
        for r in t['rounds']:
            if any(s.get('frame') for s in r['slots']):
                r['generation_disabled']=True
                if r.get('planning_status') in ('queued','running'):r['planning_status']='stopped'
                for slot in r['slots']:
                    if slot['state'] in ACTIVE:
                        slot.update(state='stopped',reason_code='protocol_retired',msg='此制作流程已停用，请重新提交配置制作');slot.pop('resume',None)
            r.setdefault('created_at',None)
            r.setdefault('stop_marker',str(Path(r['slots'][0]['output']).parent/'STOP'))
            r.setdefault('planning_status','done')
            if r['planning_status']=='running': r['planning_status']='queued'
            for number in list(r['sel']):
                if str(number).isdigit():
                    adopted=r['sel'].pop(number)
                    versions=r['adopted_versions'].pop(number,{})
                    for pid in r['params']['pids']:
                        key=selection_key(pid,number)
                        r['sel'][key]=adopted
                        r['adopted_versions'][key]={s['id']:versions[s['id']] for s in r['slots'] if s['pid']==pid and s['id'] in versions}
            for s in r['slots']:
                s.pop('local_processing',None)
                if s['state']=='generating':
                    if s.get('ximalaya_review',{}).get('status') in XIMALAYA_PENDING or s.get('local_result_sha256'):
                        s.update(state='queued');s.pop('resume',None);continue
                    output=Path(s['output'])
                    state_path=render.task_state_path(output)
                    action=receipt_recovery_action(state_path)
                    if action is None and not state_path.exists() and not s.get('provider_task_ids') and not output.exists():
                        try:progress=render.load_task_state(output.with_suffix('.progress.json'))
                        except render.KieError:progress={}
                        if progress.get('stage') in ('uploading','awaiting_submit'):
                            # The worker records a submission journal before sending any POST.
                            s.update(state='queued',stage=progress['stage'],resume=False);continue
                    if r['simulation'] or s.get('production_mode')=='local_resize' or action=='resume':
                        s['state']='queued'
                        s['resume']=action=='resume'
                    else:
                        s.update(state='failed',reason_code='unknown',msg=BLOCKED_RECEIPT_MESSAGE)
        if self.delivery_state(t,t['rounds'][t['ri']])['incomplete_sets']: t['downloaded']=False
        self.persist(t)

    def task(self,tid,deleted=False):
        t=self.tasks.get(tid)
        if not t or (t.get('deleted_at') and not deleted): raise UserError('任务不存在或已删除',404)
        return t

    def create(self,pr,idem,tid=None,draft_id=None):
        with self.lock:
            if self.maintenance_active:raise UserError('正在进行本机数据维护，请稍后提交')
            require_space(self.settings.output,self.settings.concurrency*16*1024*1024)
            if draft_id:
                if not isinstance(draft_id,str) or len(draft_id)!=32: raise UserError('草稿标识不正确')
                closed=self.document('closed-draft:'+draft_id)
                if closed.get('task_id'):
                    result=self.public(self.task(closed['task_id']));result['recovered_submission']=True;return result
                if closed: raise UserError('草稿已删除，请新建草稿',409)
            if not isinstance(idem,str) or not 8<=len(idem)<=128: raise UserError('缺少提交标识，请刷新后重试')
            row=self.db.execute('SELECT id FROM tasks WHERE idem=?',(idem,)).fetchone()
            if row: return self.public(self.task(row[0]))
            for t in self.tasks.values():
                if idem in t.get('submission_keys',[]): return self.public(t)
            from .learning_setup import is_learning_request, generation_unavailable
            if is_learning_request(pr): generation_unavailable()
            if isinstance(pr,dict):
                pr=json.loads(json.dumps(pr))
                from .natural_canvas import PROTOCOL
                pr['canvas_protocol']=PROTOCOL
                pr=self.freeze_product(pr,self.document('draft:'+draft_id).get('draft') if draft_id else None)
                pr.setdefault('image_model',self.settings.image_model)
            existing_references=[ref for rr in self.task(tid)['rounds'] for ref in rr['params'].get('references',[])] if tid else []
            existing_sources=[rr['params'].get('learning_source') for rr in self.task(tid)['rounds']] if tid else []
            learning_source.registered(pr,self.settings,existing_sources)
            direction=validate(pr,self.settings.output,existing_references=existing_references)
            pr=normalize_form(pr)
            if self.settings.real and not self.settings.key: raise UserError('请先在设置中填写 KIE Key')
            if tid:
                t=self.task(tid)
                current=t['rounds'][t['ri']]
                # Removed placements retain their history; their overrides cannot change retained content.
                previous={**current['params'],'image_model':current.get('image_model',DEFAULT_IMAGE_MODEL)}
                previous['cta_overrides']={pid:value for pid,value in previous.get('cta_overrides',{}).items() if pid in pr['pids']}
                if (not current.get('generation_disabled') and not any(s.get('frame') for s in current['slots'])
                        and copy_signature(previous)==copy_signature(pr) and current['simulation']==(not self.settings.real)):
                    return self.extend(t,current,pr,idem,draft_id=draft_id)
            else:
                now=datetime.now(timezone(timedelta(hours=8)))
                task_name='APP_'+direction+'_APP图片_'+now.strftime('%H%M%S')
                t=dict(id=uuid.uuid4().hex,pkg=task_name,name=(pr.get('s1') if any(BY_ID[i]['image_count']>1 for i in pr['pids']) else pr.get('t1',''))[:16],
                    direction=direction,date=time.time()*1000,rounds=[],ri=0,pkgs=[],downloaded=False,output_dir=str(self.settings.output))
            # Every task keeps its original workspace even if settings later change.
            cache=Path(t['output_dir'])/'.cache'/t['id']/uuid.uuid4().hex
            pr=json.loads(json.dumps(pr))
            pr['direction']=direction
            remembered_references=self.document('form_defaults').get(pr['image_form'],{}).get('references',[])
            for ref in pr.get('references',[]):
                path=Path(ref.get('path','')).resolve()
                uploads=(self.settings.state_dir/'uploads').resolve()
                valid_task_upload=any(path==Path(old['path']).resolve() for old in [*existing_references,*remembered_references])
                if not path.is_file() or (uploads not in path.parents and not valid_task_upload): raise UserError('参考图不存在，请重新上传')
                dest=cache/'references'/path.name
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(path,dest)
                ref['path']=str(dest)
            from .logo_templates import snapshot as logo_template_snapshot
            try: r=make_round(pr,t['id'],cache,self.settings.concurrency,not self.settings.real,defer_planning=True,brand_logo_templates=logo_template_snapshot(self))
            except UserError:
                shutil.rmtree(cache,ignore_errors=True)
                raise
            except Exception:
                shutil.rmtree(cache,ignore_errors=True)
                raise UserError('提示词未通过校验，请检查文案和参考素材')
            pr=r['params']
            if tid:
                for previous in t['rounds']:
                    if previous.get('planning_status') in ('queued','running') or any(s['state']=='queued' for s in previous['slots']):
                        previous['stopped']=True;Path(previous['stop_marker']).touch()
                        if previous.get('planning_status') in ('queued','running'): previous['planning_status']='stopped'
                        for image in previous['slots']:
                            if image['state']=='queued': image['state']='stopped'
            t['archived']=False
            t['rounds'].append(r)
            t['ri']=len(t['rounds'])-1
            t['downloaded']=False
            t.setdefault('submission_keys',[]).append(idem)
            t['last_work_at']=time.time()
            self.persist(t,idem if not tid else None)
            self.remember_form(pr)
            if draft_id: self.delete_draft(draft_id,t['id'])
            with self.audit_path.open('a',encoding='utf-8') as f:
                f.write(json.dumps({'at':time.time(),'task':t['id'],'image_count':len(r['slots']),'simulation':r['simulation']})+'\n')
            return self.public(t)

    def is_running(self,t): return any(r.get('planning_status') in ('queued','running') or any(s['state'] in ACTIVE for s in r['slots']) for r in t['rounds'])

    def image_kie_recovery(self,s):
        if s['state']!='failed' or s.get('local_result_sha256'):return None
        if s.get('ximalaya_review',{}).get('status') in ('needs_review','unavailable','rejected','export_failed'):
            return None
        path=render.task_state_path(Path(s['output'])) if s.get('output') else None
        action=receipt_recovery_action(path,expected=s.get('reason_code') in ('unknown','timeout','receipt_corrupt'))
        return 'retry' if action=='reconcile' and self.definitely_unsent(s) else action

    def public_image_kie_recovery(self,s):
        action=self.image_kie_recovery(s)
        result={'kie_recovery_action':action,'query_required':action=='resume','submission_unverified':action=='reconcile'}
        if action=='retry':result.update(reason_code='not_submitted',msg='生图请求未发出，可重试本张')
        if action=='reconcile':result.update(reason_code='submit_uncertain',msg='请在 KIE 任务记录核对这张图的受理情况。')
        if action=='blocked':result.update(reason_code='receipt_missing',msg=BLOCKED_RECEIPT_MESSAGE)
        return result

    def query_required(self,s):
        return self.image_kie_recovery(s) in ('resume','reconcile','blocked')

    def submission_unverified(self,s):
        return self.image_kie_recovery(s)=='reconcile'

    def attach_kie_receipt(self,tid,data):
        from .kie_recovery import claim_receipt, pending_receipt, verify_task

        def target():
            if self.maintenance_active:raise UserError('本机正在维护，请稍后再操作',409)
            t=self.task(tid)
            r=self.round(t,data.get('round',t['ri']))
            s=next((row for row in r['slots'] if row['id']==data.get('image_id')),None)
            if (not s or type(data.get('expected_att')) is not int or s['att']!=data['expected_att']
                    or r.get('generation_disabled') or r['simulation'] or not self.submission_unverified(s)):
                raise UserError('这张图已更新或无需接回 KIE 任务，请刷新后核对',409)
            output=Path(s['output'])
            return output,s['prompt']

        with self.lock:
            output,prompt=target()
            path=render.task_state_path(output)
            pending=pending_receipt(path)
            if not pending:raise UserError('这张图没有待核对的 KIE 回执',409)
        task_id=verify_task(self.settings,data.get('task_id'),pending,prompt)
        with self.lock:
            if target()[0]!=output:raise UserError('图片版本已更新，请刷新后再操作',409)
            claim_receipt(self,output,path,pending,task_id)
            return self.mutate(tid,'resume',data)

    def definitely_unsent(self,s):
        if s.get('state')!='failed' or s.get('reason_code')!='unknown':return False
        out=Path(s['output'])
        try:
            state=json.loads(render.task_state_path(out).read_text())
            progress=json.loads(out.with_suffix('.progress.json').read_text())
            result=json.loads(out.with_suffix('.job.result.json').read_text())
            return state.get('status')=='submitting' and not state.get('task_id') and progress.get('stage')=='uploading' and result.get('reason')=='unknown'
        except (OSError,ValueError,TypeError):return False

    def remember_form(self,pr):
        saved=self.document('form_defaults')
        saved[pr['image_form']]={k:pr[k] for k in ('channel','pids','sets','ip','style','font','noLogo','logo_asset_id','cta','cta_enabled','cta_overrides','references','ximalaya_suite') if k in pr}
        self.put_document('form_defaults',saved)

    def extend(self,t,r,pr,idem,*,draft_id=None,pairs=None):
        wanted=pairs or requested_pairs(pr)
        existing={(s['pid'],s['set']) for s in r['slots']}
        extra=[pair for pair in wanted if pair not in existing]
        if extra:
            t['archived']=False
            if r.get('planning_status') in ('queued','running'):
                raise UserError('正在规划新增画面，请等规划结束后再补充')
            cache=Path(r['stop_marker']).parent
            assignments={selection_key(pid,n):suite_metadata(r['set_metadata'],pid,n) for pid,n in existing}
            part=make_round(r['params'],t['id'],cache,r['concurrency'],r['simulation'],defer_planning=True,
                            assignments=assignments,pairs=extra,round_id=r['id'],placements_override={**BY_ID,**self.placement_rules(t,r)},brand_logo_templates=r.get('brand_logo_templates'))
            offset=len(r['configs'])
            for slot in part['slots']: slot['config_idx']+=offset
            if learning_source.uploaded(r['params']):
                for slot in part['slots']:slot['plan_ready']=False
            r['slots'].extend(part['slots']);r['configs'].extend(part['configs'])
            r['set_metadata']=part['set_metadata'];r['planning_targets']=part['planning_targets']
            learning_workflow.bind(r,[s['id'] for s in part['slots']])
            ximalaya.bind(r)
            if r.get('learning_workflow_version'):
                # New targets of an existing scheme use its saved plan. A new
                # scheme still goes through the planner exactly once.
                work={**r,'planning_targets':[]}
                compile_plans(work,{'plans':[]})
            r.update(planning_status='queued' if r['planning_targets'] else 'done',planning_error='',stopped=False)
            Path(r['stop_marker']).unlink(missing_ok=True)
            for pid,n in extra:
                if pid not in r['params']['pids']: r['params']['pids'].append(pid)
                r['params']['sets']=max(r['params']['sets'],n)
            r['params']['variants_by_placement']={pid:max(s['set'] for s in r['slots'] if s['pid']==pid) for pid in r['params']['pids']}
            t['downloaded']=False;t['last_work_at']=time.time()
        t.setdefault('submission_keys',[]).append(idem)
        self.persist(t);self.remember_form(r['params'])
        if draft_id: self.delete_draft(draft_id,t['id'])
        result=self.public(t);result['added_image_count']=sum(self.placement(t,r,{'pid':pid})['image_count'] for pid,n in extra)
        return result

    def plan_round(self,t,r,key):
        try:
            with self.lock:
                chunk=list(r['planning_targets'][:3])
                snapshot=json.loads(json.dumps(r));snapshot['planning_targets']=chunk
            from .learning_setup import is_learning_request, generation_unavailable
            if is_learning_request(snapshot['params']):generation_unavailable()
            from .learning_delivery import require_confirmed_sample
            for entry in snapshot['configs']:
                if entry['pid']+'::'+str(entry['set']) in chunk:require_confirmed_sample(entry['config']['placements'][0])
            result=self.planner.plan(snapshot,lambda value:compile_plans(snapshot,value,apply=False),self.closed)
            with self.lock:
                if not r['stopped'] and not self.closed.is_set():
                    work={**r,'planning_targets':chunk}
                    compile_plans(work,result)
                    r['planning_targets']=[target for target in r['planning_targets'] if target not in chunk]
                    r.update(planning_status='queued' if r['planning_targets'] else 'done',planning_error='',planning_provenance=result.get('_provenance',{}))
                    r.pop('planning_retry_after',None);r.pop('planning_attempts',None)
                    for s in r['slots']:
                        if s.get('plan_ready') and s.get('reason_code')=='planning_failed': s.update(state='queued',reason_code=None,msg='')
                    atomic(Path(r['stop_marker']).parent/'visual-plans.json',{'plans':[{'placement_id':c['pid'],'set_number':c['set'],'concept':c['concept']} for c in r['configs'] if c.get('concept')],
                        'provenance':r.get('planning_provenance',{})})
        except PlanningStopped:
            with self.lock: r['planning_status']='stopped'
        except Exception as exc:
            with self.lock:
                attempt=r.get('planning_attempts',0)
                if isinstance(exc,PlanningRequestError) and exc.retryable and attempt<len(PLANNING_RETRY_DELAYS) and not r['stopped'] and not self.closed.is_set():
                    r.update(planning_status='queued',planning_attempts=attempt+1,planning_retry_after=time.time()+PLANNING_RETRY_DELAYS[attempt]);return
                r['planning_status']='failed'
                r['planning_error']=exc.message if isinstance(exc,UserError) else '画面规划未完成，请重试规划'
                for s in r['slots']:
                    if not s.get('plan_ready',True): s.update(state='failed',reason_code='planning_failed',msg=r['planning_error'])
        finally:
            with self.lock:
                self.planning_running.discard(key)
                self.persist(t)

    def public(self,t):
        result=json.loads(json.dumps(t))
        result.pop('deleted_at',None)
        for source,r in zip(t['rounds'],result['rounds']):
            r.setdefault('paused',False)
            r.pop('configs',None)
            r.pop('set_metadata_private',None)
            r.pop('skill_rules_path',None)
            r['delivery']=self.delivery_state(t,source)
            r['placement_rules']=self.placement_rules(t,source)
            from .brand_logo import capability as logo_capability, review_query, review_switchable, reviewed_image, switchable as logo_switchable
            def selected_key(slot):return selection_key(ximalaya.selection_pid(source,slot['pid']),slot['set'])
            selected=[s for s in source['slots'] if source.get('sel',{}).get(selected_key(s))]
            r['logo_export_capability']=logo_capability(selected or source['slots'])
            r['logo_export_switchable']=r['logo_export_capability']['editable']
            originals={s['id']:s for s in source['slots']}
            for s in r['slots']:
                original=originals[s['id']]
                s['logo_switchable']=logo_switchable(original)
                s['logo_review_switchable']=review_switchable(original)
                s['logo_review_active']=bool(s.pop('logo_review',None))
                if s['logo_review_active']:
                    preview=reviewed_image(original)
                    s.update({key:preview[key] for key in ('jpeg','sha256','delivery_logo_asset_id')})
                s.pop('brand_logo_layer',None);s.pop('logo_base',None);s.pop('natural_canvas_plan',None)
                s.update(self.public_image_kie_recovery(original))
                s['set_id']=selection_key(ximalaya.selection_pid(r,s['pid']),s['set'])
                s.pop('output',None)
                for removed in ('frame','frame_processing','frame_status'):s.pop(removed,None)
                s.pop('job_path',None)
                s.pop('versions',None)
                s['original_image_url']=f"/api/tasks/{t['id']}/images/{s['id']}?v={s['att']}&raw=1" if s['state']=='done' else None
                s['preview_kind']='raw' if s.get('delivery_eligible') is False else 'processed'
                s['image_url']=(s['original_image_url'] if s['preview_kind']=='raw' else f"/api/tasks/{t['id']}/images/{s['id']}?v={s['att']}"+review_query(original)) if s['state']=='done' else None
                if s.get('ximalaya_review',{}).get('status') in (*XIMALAYA_PENDING,'needs_review','rejected','unavailable','export_failed'):
                    s['review_image_url']=f"/api/tasks/{t['id']}/images/{s['id']}?v={s['att']}&review=1"
                if s['preview_kind']=='raw' and not s.get('ximalaya_review'):s.update(msg='当前原图未通过交付规格，请重新制作')
                s['reference_images']=[{'label':ref.get('label','参考图'+str(i+1)),'name':ref.get('role','参考图'),'type':ref.get('role','参考图'),'upload_status':s.get('up',{}).get(str(i),'ok'),
                    'thumbnail_url':f"/api/tasks/{t['id']}/references/{s['id']}/{i}"} for i,ref in enumerate(s['refs'])]
                s.pop('refs',None)
            done=sum(s['state']=='done' for s in r['slots'])
            r['completed_count']=done
            r['generation']={'completed':done,'total':len(r['slots']),'planning':r.get('planning_status','done'),'stopped':r['stopped']}
            if source.get('learning_workflow_version'):
                local=sum(s.get('production_mode')=='local_resize' for s in r['slots'])
                r['generation'].update(model_tasks=len(r['slots'])-local,local_outputs=local)
            r['status']='stopped' if r['stopped'] else 'generating' if any(s['state'] in ACTIVE for s in r['slots']) else 'done'
            if r['params'].get('ximalaya_suite'):
                missing=[{**item,'reason':'尚未选择可交付的整套'} for item in r['delivery']['missing_placements']]
            else:
                missing=[{'placement_id':pid,'name':self.placement(t,source,{'pid':pid})['platform']+' '+self.placement(t,source,{'pid':pid})['name'],'reason':'尚未采纳完整套图'} for pid in r['params']['pids'] if not any(r['sel'].get(selection_key(pid,n)) and all(s['state']=='done' and r['adopted_versions'].get(selection_key(pid,n),{}).get(s['id'])==s['att'] for s in r['slots'] if s['pid']==pid and s['set']==n) for n in range(1,r['params']['sets']+1))]
            r['pending_placements']=missing
            r['counts']={'total':len(r['slots']),'adopted':sum(bool(r['sel'].get(selected_key(s))) and s['state']=='done' for s in r['slots']),
                'not_adopted':sum(not r['sel'].get(selected_key(s)) and s['state']=='done' for s in r['slots']),
                'needs_attention':sum(s['state'] in ('failed','blocked_first_failed') for s in r['slots']),'pending':len(missing)}
            for pid,g in {(s['pid'],s['set']) for s in r['slots']}:
                sl=[s for s in r['slots'] if s['set']==g and s['pid']==pid]
                status='失败' if any(s['state'] in ('failed','blocked_first_failed') for s in sl) else '生成中' if any(s['state']=='generating' for s in sl) else '等待中' if any(s['state']=='queued' for s in sl) else '已停止' if any(s['state']=='stopped' for s in sl) else '已完成'
                for s in sl: s['set_status']=status
        result['background_running']=sum(s['state']=='generating' for i,r in enumerate(t['rounds']) if i!=t['ri'] for s in r['slots'])
        result['delivery']=result['rounds'][result['ri']]['delivery']
        result['downloaded']=bool(result['delivery']['last_version']) and not result['delivery']['has_changes']
        for p in result['pkgs']:
            p.pop('path',None)
            for index,image in enumerate(p['images']):
                image['thumbnail_url']=f"/api/workbench/packages/task/{t['id']}/{p['id']}/images/{index}"
        result['revision']=t.get('revision',0)
        result['summary']=self.task_summary(t)
        return result

    def list_tasks(self,q='',cursor=0,limit=50):
        with self.lock:
            ts=[t for t in self.tasks.values() if not t.get('deleted_at')]
            if q:
                ts=[t for t in ts if q.lower() in (t.get('name','')+json.dumps([r['params'] for r in t['rounds']],ensure_ascii=False)).lower()]
            def in_progress(t): return self.is_running(t) or (not t['downloaded'] and any(s['state']=='done' for s in t['rounds'][t['ri']]['slots']))
            ts.sort(key=lambda t:(not in_progress(t),-t['date']))
            batch=ts[cursor:cursor+limit]
            return dict(tasks=[self.public(t) for t in batch],next_cursor=str(cursor+limit) if len(ts)>cursor+limit else None)

    def round(self,t,index):
        if type(index) is not int or not 0<=index<len(t['rounds']): raise UserError('任务轮次不存在')
        return t['rounds'][index]

    def mutate(self,tid,action,data):
        with self.lock:
            if self.maintenance_active:raise UserError('正在进行本机数据维护，请稍后操作')
            t=self.task(tid,deleted=action=='restore')
            if action=='rename':
                name=str(data.get('name','')).strip()
                if not name or len(name)>80: raise UserError('任务名请填写 1–80 字')
                t['name']=name
            elif action=='delete':
                if self.is_running(t) or t.get('exporting'): raise UserError('请先等待正在执行或保存的工作结束')
                t['deleted_at']=time.time()
            elif action=='restore':
                if time.time()-t.get('deleted_at',time.time())>300: raise UserError('撤销时间已过，任务已删除')
                t.pop('deleted_at',None)
            elif action in ('archive','unarchive'):
                if action=='archive' and (self.is_running(t) or t.get('exporting')): raise UserError('请先等任务完成或停止后续提交，再归档')
                t['archived']=action=='archive'
            elif action=='duplicate':
                source=self.round(t,data.get('round',t['ri']))
                params=json.loads(json.dumps(source['params']))
                params['image_model']=source.get('image_model',DEFAULT_IMAGE_MODEL)
                uploads=self.settings.state_dir/'uploads'
                uploads.mkdir(exist_ok=True)
                for ref in params.get('references',[]):
                    source=Path(ref['path'])
                    if not source.is_file(): raise UserError('参考图不存在，请重新上传')
                    target=uploads/(digest(source)+source.suffix.lower())
                    if source.resolve()!=target.resolve(): shutil.copy2(source,target)
                    ref['path']=str(target)
                if learning_source.uploaded(params):
                    source=learning_source.check(params['learning_source'])
                    target=uploads/(params['learning_source']['id']+source.suffix.lower())
                    if source.resolve()!=target.resolve():shutil.copy2(source,target)
                    params['learning_source']['path']=str(target)
                return {'params':params}
            else:
                r=self.round(t,data.get('round',t['ri']))
                if r.get('generation_disabled') or any(s.get('frame') for s in r['slots']):
                    if action in ('continue','retry-planning','add-variant','repair-set','regenerate','resume','retry-confirmed-submission','retry-image-export','retry-ximalaya-review','rebrief-round'):raise UserError('此制作流程已停用，请重新提交配置制作',409)
                from .learning_setup import is_learning_request, generation_unavailable
                if is_learning_request(r['params']) and action in ('continue','rebrief-round','retry-planning','add-variant','repair-set','regenerate'):
                    generation_unavailable()
                if action in ('pause','continue'):
                    if r.get('stopped'): raise UserError('本轮已停止，请明确选择需要重出的图片')
                    r['paused']=action=='pause'
                elif action=='stop':
                    r['paused']=False
                    r['stopped']=True
                    Path(r['stop_marker']).touch()
                    if r.get('planning_status') in ('queued','running'): r['planning_status']='stopped'
                    for s in r['slots']:
                        if s['state']=='queued': s['state']='stopped'
                elif action=='rebrief-round':
                    existing=next((x for x in t['rounds'] if x.get('reformatted_from')==r['id']),None)
                    if existing:
                        t['ri']=t['rounds'].index(existing)
                    else:
                        if self.is_running(t): raise UserError('请等当前任务结束后再改写重出')
                        if not r['simulation'] and not self.settings.key: raise UserError('请先配置 KIE Key')
                        from .rebrief import rebrief
                        updated=rebrief(t,r,self.settings.concurrency)
                        t['rounds'].append(updated);t['ri']=len(t['rounds'])-1
                        t['downloaded']=False;t['last_work_at']=time.time()
                elif action=='retry-planning':
                    if r.get('planning_status') in ('queued','running'): raise UserError('正在规划画面，请稍候')
                    if all(s.get('plan_ready',True) for s in r['slots']): raise UserError('画面规划已完成，无需重试')
                    r.update(planning_status='queued',planning_error='',stopped=False)
                    r.pop('planning_retry_after',None);r.pop('planning_attempts',None)
                    Path(r['stop_marker']).unlink(missing_ok=True)
                    for s in r['slots']:
                        if not s.get('plan_ready',True): s.update(state='queued',reason_code=None,msg='')
                elif action=='add-variant':
                    if learning_source.uploaded(r['params']):raise UserError('图片扩展任务每个版位生成 1 张，请在原图上重出或复制为新任务')
                    if r.get('planning_source')!='codex_skill': raise UserError('历史模拟任务请复制为新任务，使用原 Skill 重新规划')
                    pid=data.get('placement_id')
                    if pid not in r['params']['pids']: raise UserError('渠道版位不存在')
                    n=max(s['set'] for s in r['slots'] if s['pid']==pid)+1
                    if n>20: raise UserError('每个版位最多 20 套')
                    ids=ximalaya.placements(r['params']) if ximalaya.is_grouped(r,pid) else (pid,)
                    return self.extend(t,r,r['params'],str(uuid.uuid4()),pairs=[(placement,n) for placement in ids])
                elif action=='repair-set':
                    pid=data.get('placement_id');n=data.get('set')
                    group=[s for s in r['slots'] if s['pid']==pid and s['set']==n]
                    if not group: raise UserError('套图不存在')
                    head=next(s for s in group if s['idx']==1)
                    targets=[head] if head['state'] in ('failed','stopped') else [s for s in group if s['state'] in ('failed','blocked_first_failed','stopped')]
                    if not targets: raise UserError('这套图片无需补齐；未通过规格的图片请重新制作')
                    recovery=[(s,self.image_kie_recovery(s)) for s in targets]
                    if any(action in ('reconcile','blocked') for _,action in recovery):
                        raise UserError('请先核对这套图片的 KIE 回执，再补齐',409)
                    for s,next_action in recovery:
                        operation='retry-image-export' if s.get('reason_code')=='local_export' else 'resume' if next_action=='resume' else 'regenerate'
                        self.mutate(tid,operation,{'round':data.get('round',t['ri']),'image_id':s['id']})
                elif action in ('adopt','adopt-bulk'):
                    choices=[data] if action=='adopt' else data.get('sets')
                    if not isinstance(choices,list) or len(choices)>400: raise UserError('选择范围不正确，请刷新后重试')
                    if type(data.get('adopted')) is not bool: raise UserError('请选择或取消选择')
                    adopted=data['adopted']
                    groups={}
                    for choice in choices:
                        if not isinstance(choice,dict): raise UserError('选择范围不正确，请刷新后重试')
                        n=choice.get('set')
                        pid=choice.get('placement_id')
                        if pid is None and len(r['params']['pids'])==1: pid=r['params']['pids'][0]
                        if pid not in r['params']['pids']: raise UserError('请指定要选择的渠道版位')
                        pid=ximalaya.selection_pid(r,pid)
                        sl=[s for s in r['slots'] if s['set']==n and ximalaya.selection_pid(r,s['pid'])==pid]
                        if not sl: raise UserError('所选套图不存在，请刷新后重试')
                        if adopted and not any(s['state']=='done' for s in sl): raise UserError('这一套还没有可选择的图片')
                        if adopted and ximalaya.is_grouped(r,pid) and not ximalaya.only(r['params']):
                            from .delivery import require_reviewed_versions
                            if any(s['state']!='done' or not s.get('delivery_eligible',True) for s in sl):
                                raise UserError('请先完成喜马拉雅套图的已选尺寸',409)
                            require_reviewed_versions(choice.get('reviewed_versions'),{s['id']:s['att'] for s in sl})
                        groups[selection_key(pid,n)]=sl
                    # Validate the entire scope before changing any selection.
                    for selection,sl in groups.items():
                        r['sel'][selection]=adopted
                        r['adopted_versions'][selection]={s['id']:s['att'] for s in sl} if adopted else {}
                    if groups: t['downloaded']=False
                elif action in ('regenerate','resume','retry-ximalaya-review','retry-image-export','retry-confirmed-submission'):
                    s=next((s for s in r['slots'] if s['id']==data.get('image_id')),None)
                    if not s: raise UserError('图片不存在',404)
                    if data.get('expected_att',s['att'])!=s['att']: raise UserError('图片已在另一窗口更新，草稿已保留，请重新打开当前版本后提交',409)
                    if action=='retry-ximalaya-review':
                        review_status=s.get('ximalaya_review',{}).get('status')
                        if not (s['state']=='failed' and review_status in ('needs_review','unavailable') or s['state']=='stopped' and review_status=='pending'):
                            raise UserError('首图当前无需重试审核',409)
                        s['ximalaya_review'].update(status='pending',message='',auto_attempts=0)
                        s.pop('review_attempts',None);s.pop('retry_after',None)
                        s.update(state='queued',stage='visual_review',reason_code=None,msg='')
                        for child in learning_workflow.descendants(r,s):
                            if child['state']=='blocked_first_failed':child.update(state='queued',reason_code=None,msg='')
                    elif action=='retry-image-export':
                        proof=s.get('ximalaya_review',{})
                        if s['state']!='failed' or s.get('reason_code')!='local_export':raise UserError('这张图当前无需重试导出',409)
                        if proof.get('status')=='export_failed':proof.update(status='export_pending',message='')
                        elif not s.get('local_result_sha256'):raise UserError('没有可恢复的原图',409)
                        s.pop('local_attempts',None);s.pop('retry_after',None)
                        s.update(state='queued',stage='processing',reason_code=None,msg='')
                        for child in learning_workflow.descendants(r,s):
                            if child['state']=='blocked_first_failed':child.update(state='queued',reason_code=None,msg='')
                    elif action=='resume':
                        if self.image_kie_recovery(s)!='resume':raise UserError('当前图片没有可查询的任务号，请根据页面状态处理',409)
                        s.pop('query_attempts',None);s.pop('retry_after',None)
                        s.update(state='queued',resume=True,reason_code=None,msg='')
                        if s['idx']==1:
                            for child in learning_workflow.descendants(r,s):
                                if child is not s and child['state']=='blocked_first_failed':
                                    child.update(state='queued',reason_code=None,msg='')
                    else:
                        reconciled=action=='retry-confirmed-submission'
                        if reconciled and (data.get('confirmed_unaccepted') is not True or type(data.get('expected_att')) is not int or not self.submission_unverified(s)):
                            raise UserError('请先在供应商记录确认原请求未受理',409)
                        if r.get('planning_source')!='codex_skill': raise UserError('历史模拟任务请复制为新任务，使用原 Skill 重新规划')
                        if s.get('reason_code')=='planning_failed': raise UserError('请先重试画面规划')
                        if s['state']=='blocked_first_failed': raise UserError('请先处理图 1；后续图不能替代图 1 发起重出')
                        group=learning_workflow.descendants(r,s)
                        if any(x['state'] in ACTIVE or x.get('local_processing') for x in group): raise UserError('图片仍在生成，请等待结束')
                        if any(self.query_required(x) for x in group if x is not s or not reconciled): raise UserError('这套存在状态未确定的图片，请先恢复查询，不能重复提交')
                        if any(x['state']!='done' or not x.get('delivery_eligible',True) for x in learning_workflow.dependencies(r,s)):
                            raise UserError('请先处理图 1，再重出本张')
                        from .learning_delivery import require_confirmed_sample
                        require_confirmed_sample(self.placement(t,r,s))
                        prompt=data.get('prompt',s['prompt'])
                        if ximalaya.is_grouped(r,s['pid']) and prompt!=s['prompt']:
                            raise UserError('喜马拉雅整套沿用确认文案。修改文案请重新提交整套配置')
                        if s.get('ximalaya_review',{}).get('status')=='rejected':prompt=ximalaya.repair_prompt(s)
                        local=s.get('production_mode')=='local_resize'
                        if local and 'prompt' in data:raise UserError('本机缩放不使用提示词，请修改母版后重新适配')
                        manual='prompt' in data or s.get('prompt_origin')=='manual'
                        from poster_prompt import validate_text
                        try:
                            validate_text(prompt)
                            if s.get('brand_logo_layer'):
                                from .brand_logo import validate_prompt as validate_brand_prompt
                                validate_brand_prompt(prompt,s['brand_logo_layer'])
                            if s.get('natural_canvas_plan'):
                                from .natural_canvas import validate_prompt as validate_canvas_prompt
                                validate_canvas_prompt(prompt,s['natural_canvas_plan'])
                            if not manual and not local:
                                plan=r['configs'][s['config_idx']]
                                cfg=plan['config']
                                if cfg.get('prompt_layout')!='poster_sections_v1': positive_prompt.validate_paragraph(prompt)
                                texts=positive_prompt.approved_copy(cfg['copy_refs'][0],s['idx'],self.placement(t,r,s)['image_count'])
                                positive_prompt.validate_visual_contract(cfg,prompt,s['refs'],s['idx'],texts[0])
                                if any(text and text not in prompt for text in texts): raise ValueError()
                                render.validate_reference_labels(prompt,s['refs'])
                                render.validate_logo_prompt_rule(prompt,s['refs'])
                        except (ValueError,TypeError) as exc:
                            raise UserError(str(exc) if manual else '系统提示词校验未通过，请检查文案和参考素材')
                        if s.get('reason_code')=='prompt_rejected' and prompt==s['prompt']: raise UserError('请修改提示词后再生成')
                        if reconciled:
                            output=Path(s['output'])
                            InstanceLock(output.with_suffix(output.suffix+'.execution.lock')).close()
                        for x in group:
                            select_key=selection_key(ximalaya.selection_pid(r,x['pid']),x['set'])
                            r['sel'].pop(select_key,None)
                            r['adopted_versions'].pop(select_key,None)
                            x['versions'].append(json.loads(json.dumps({k:x.get(k) for k in ('att','prompt','output','jpeg','sha256','raw_sha256','state','refs','reason_code','quality_review','prompt_origin','head_version','pinned','source_versions','brand_logo_layer','logo_base','delivery_logo_asset_id','logo_review','natural_canvas_plan','natural_processing')})))
                            if x is s: x.update(prompt=prompt,prompt_origin='local' if local else 'manual' if manual else 'system')
                            x['att']+=1
                            x.update(state='queued',reason_code=None,msg='',up={})
                            x.pop('resume',None);x.pop('pinned',None);x.pop('logo_review',None)
                            for field in ('retry_after','query_attempts','limit_attempts','review_attempts','local_attempts','local_result_sha256'):
                                x.pop(field,None)
                            if ximalaya.is_grouped(r,x['pid']):
                                for field in ('ximalaya_review','source_versions','head_version','jpeg','sha256','raw_sha256','delivery_eligible'):
                                    x.pop(field,None)
                            x['output']=str(Path(x['output']).with_name(x['id']+f"-v{x['att']}.png"))
                            if x['idx']>1:
                                head=next(y for y in r['slots'] if y['id']==x['first_id'])
                                x['refs'][0]['path']=head['output']
                                x['head_version']=head['att']
                        t['downloaded']=False
                        if reconciled:
                            s['submission_reconciliation']={'previous_version':s['att']-1,'confirmed_unaccepted_at':time.time()}
                    r['stopped']=False
                    Path(r['stop_marker']).unlink(missing_ok=True)
                else: raise UserError('操作不存在',404)
            if action in ('regenerate','retry-confirmed-submission','rebrief-round','retry-planning','adopt','adopt-bulk'):t['archived']=False
            self.persist(t)
            return self.public(t)

    def sync_provider_ids(self,t,s):
        if s.get('ximalaya_review',{}).get('status') in XIMALAYA_PENDING or s.get('local_result_sha256'):return
        now=time.monotonic()
        if now-self.progress_reads.get(s['id'],0)<.5:return
        self.progress_reads[s['id']]=now
        progress=Path(s['output']).with_suffix('.progress.json')
        if progress.exists():
            try:
                stage=json.loads(progress.read_text()).get('stage')
                if stage and stage!=s.get('stage'): s['stage']=stage;self.persist(t)
            except (OSError,ValueError): pass
        receipt=render.task_state_path(Path(s['output']))
        if not receipt.exists(): return
        try: state=json.loads(receipt.read_text())
        except (OSError,ValueError): return
        ids=[x.get('task_id') for x in state.get('attempt_history',[])]+[state.get('task_id')]
        ids=[i for i in ids if i]
        new=[i for i in ids if i not in s.get('provider_task_ids',[])]
        if new:
            s['provider_task_ids']=ids
            with self.audit_path.open('a',encoding='utf-8') as f:
                f.write(json.dumps({'at':time.time(),'task':t['id'],'image':s['id'],'task_ids':new})+'\n')
            self.persist(t)

    def generate(self,t,r,s,key):
        try:
            if self.closed.is_set():
                with self.lock:s.update(state='queued',stage='queued')
                return
            if r.get('generation_disabled') or s.get('frame'):raise UserError('此制作流程已停用，请重新提交配置制作',409)
            if s.get('ximalaya_review',{}).get('status')=='pending':
                self.review_ximalaya(t,r,s)
                return
            if s.get('ximalaya_review',{}).get('status')=='export_pending':
                self.export_ximalaya(t,r,s)
                return
            if s.get('local_result_sha256'):
                self.finish_downloaded_image(t,r,s)
                return
            from .learning_setup import is_learning_request, generation_unavailable
            if is_learning_request(r['params']) and not s.get('resume'):
                generation_unavailable()
            from .learning_delivery import require_confirmed_sample
            if not s.get('resume'):require_confirmed_sample(self.placement(t,r,s))
            head=next((x for x in r['slots'] if x['id']==s['first_id']),s)
            if s['idx']>1 and (not Path(head['output']).exists() or digest(head['output'])!=head.get('raw_sha256')):
                raise UserError('图 1 校验失败，请重新生成图 1')
            out=Path(s['output'])
            if s.get('ximalaya_source'):
                source=Path(head['output']);review=head.get('ximalaya_review',{})
                if review.get('status')!=('simulated' if r['simulation'] else 'approved') or review.get('att')!=head['att']:
                    raise UserError('请先完成本套首图审核')
                if not source.is_file() or digest(source)!=review.get('raw_sha256'):
                    raise UserError('首图文件已变化，请重出并审核首图')
                binding={head['id']:dict(att=head['att'],sha256=review['raw_sha256'],path=str(source))}
                with self.lock:
                    if s.get('resume') and s.get('source_versions')!=binding:
                        raise UserError('首图版本已变化，不能恢复以前的请求')
                    s.update(source_versions=binding,head_version=head['att'])
                    s['refs'][0]['path']=str(source)
                    self.persist(t)
            if s.get('production_mode'):
                with self.lock:
                    if not s.get('resume'):learning_workflow.freeze_sources(r,s)
                    self.persist(t)
                if s['production_mode']=='local_resize':
                    result=learning_workflow.resize_local(r,s,self.placement(t,r,s))
                    updates=self.materialize_image(s,result,out,self.placement(t,r,s))
                    with self.lock:s.update(updates)
                    return
            job=out.with_suffix('.job.json')
            atomic(job,dict(slot=s,placement=self.placement(t,r,s),params=r['params'],simulation=r['simulation'],base=self.settings.base,upload=self.settings.upload,image_model=r.get('image_model',DEFAULT_IMAGE_MODEL),query_only=s.pop('resume',False),stop_marker=r['stop_marker'],upload_cache=str(self.settings.state_dir/'reference-upload-cache.json')))
            env={**os.environ,'KIE_API_KEY':self.settings.key}
            proc=subprocess.Popen([sys.executable,str(ROOT/'local_app/worker.py'),str(job)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            # Drain bounded worker output off-thread; raw provider text is never exposed.
            stdout,stderr=proc.communicate()
            result_path=job.with_suffix('.result.json')
            result=json.loads(result_path.read_text()) if result_path.exists() else dict(ok=False,reason='unknown')
            state=result.get('state',{})
            if not result['ok'] and not state.get('task_id'):
                try:state=render.load_task_state(render.task_state_path(out)) or state
                except render.KieError:pass
            ids=[x.get('task_id') for x in state.get('attempt_history',[])]+[state.get('task_id')]
            with self.lock:
                s['provider_task_ids']=[i for i in ids if i]
                s['restarted']=bool(state.get('timeout_restarts'))
                if ids and any(ids):
                    with self.audit_path.open('a',encoding='utf-8') as f: f.write(json.dumps({'at':time.time(),'task':t['id'],'image':s['id'],'task_ids':s['provider_task_ids']})+'\n')
            if not result['ok'] and result.get('reason')=='rate_limited':
                with self.lock:
                    self.note_rate_limit()
                    if self.defer_image(r,s,'limit_attempts',LIMIT_RETRY_DELAYS,'submit_retry','图片服务限流，后台将重试已明确被拒的请求。'):
                        s.update(reason_code=None)
                    else:s.update(state='failed',reason_code='rate_limited',msg='图片服务持续限流，请稍后重试。')
            elif not result['ok'] and result.get('reason')=='busy':
                with self.lock:s.update(state='queued',retry_after=time.time()+3,resume=bool(state.get('task_id')),msg='等待已有执行器完成')
            elif not result['ok'] and result.get('reason')=='stopped':
                with self.lock: s.update(state='stopped',reason_code=None,msg='')
            elif not result['ok']:
                code=result.get('reason','no_image')
                messages={'prompt_rejected':'提示词未通过校验，请修改后重新生成','unknown':'状态不明，请恢复查询','timeout':'生成超时，请恢复查询','no_image':'未返回图片，请检查连接后重试','disk_full':'磁盘空间不足，请释放空间后恢复查询','busy':'已有执行器正在处理','download_failed':'图片已生成但下载未完成，请恢复查询'}
                messages.update(authentication_failed='生图接口拒绝访问，请检查 Key 和权限。',insufficient_credits='生图账户积分不足，请检查账户。',request_rejected='生图接口拒绝了请求，请检查模型和素材设置。')
                with self.lock:
                    resumable=code in ('timeout','unknown','download_failed') and state.get('task_id') and state.get('status')!='fail'
                    if resumable and self.defer_image(r,s,'query_attempts',QUERY_RETRY_DELAYS,'query_retry','后台将继续查询原生图任务。'):
                        s.update(resume=True,reason_code=None)
                    else:
                        s.update(state='failed',reason_code=code,msg='参考图上传失败，请检查连接后重试' if result.get('failed_references') else messages.get(code,messages['no_image']),up={str(i):'failed' for i in result.get('failed_references',[])})
            else:
                if Path(result['source']).resolve()!=out.resolve():raise UserError('供应商返回的本机原图路径不一致')
                source_sha=digest(out)
                with self.lock:
                    s.update(stage='processing',local_result_sha256=source_sha)
                    self.persist(t)
                self.finish_downloaded_image(t,r,s)
        except Exception as exc:
            with self.lock: s.update(state='failed',reason_code='oversize' if isinstance(exc,UserError) and '大小' in exc.message else 'no_image',msg=exc.message if isinstance(exc,UserError) else '生成失败，请检查连接后重试')
        finally:
            with self.lock:
                self.running.discard(key)
                self.persist(t)

    def defer_image(self,r,s,counter,delays,stage,message):
        count=s.get(counter,0)
        if count>=len(delays) or r['stopped'] or self.closed.is_set():return False
        s.update(state='queued',stage=stage,retry_after=time.time()+delays[count],msg=message)
        s[counter]=count+1
        return True

    def finish_downloaded_image(self,t,r,s):
        out=Path(s['output']);p=self.placement(t,r,s)
        raw_sha=s['local_result_sha256']
        head_review=ximalaya.placements(r['params'])[:1]==(s['pid'],)
        try:
            if digest(out)!=raw_sha:raise UserError('已下载的原图校验失败，请重出本图')
            if head_review and not r['simulation']:
                from .natural_canvas import crop
                target=out.with_suffix('.logo-base.png')
                with self.processing_slots:geometry=crop(out,target,s['natural_canvas_plan'],p)
                base=dict(path=str(target),sha256=digest(target),width=p['target_width'],height=p['target_height'],without_logo=True)
                updates=dict(raw_sha256=raw_sha,logo_base=base,stage='visual_review',delivery_eligible=False,
                             natural_processing={k:v for k,v in geometry.items() if k not in ('path','source')},
                             ximalaya_review=dict(status='pending',att=s['att'],raw_sha256=raw_sha,base_sha256=base['sha256']))
            else:
                updates=self.materialize_image(s,{'source':str(out)},out,p)
                if head_review:updates['ximalaya_review']=dict(status='simulated',att=s['att'],raw_sha256=raw_sha,sha256=updates['sha256'])
        except (UserError,OSError) as exc:
            with self.lock:
                if isinstance(exc,OSError):
                    if not self.defer_image(r,s,'local_attempts',LOCAL_RETRY_DELAYS,'processing_retry','后台将重试本机处理。'):
                        s.update(state='failed',reason_code='local_export',msg='本机处理未完成，可沿用原图重试。')
                else:
                    s.update(state='failed',reason_code='oversize' if '大小' in exc.message else 'local_validation',msg=exc.message)
            return
        with self.lock:
            s.update(updates)
            s.pop('local_result_sha256',None);s.pop('retry_after',None)
            self.persist(t)
        if head_review and not r['simulation']:self.review_ximalaya(t,r,s)

    def review_ximalaya(self,t,r,s):
        proof=s['ximalaya_review']
        cfg=r['configs'][s['config_idx']]['config']
        copy_text={'t1':r['params']['t1'],'subtitle':r['params']['t2'],'cta':cfg['cta']}
        file_valid=False
        try:
            base=s.get('logo_base',{})
            proof.setdefault('base_sha256',base.get('sha256'))
            file_valid=proof['att']==s['att'] and base.get('without_logo') and digest(base['path'])==proof['base_sha256'] and digest(s['output'])==proof['raw_sha256']
            result=ximalaya.review(self.settings,s,copy_text,self.closed.is_set) if file_valid else {'verdict':'repair','issues':[]}
            file_valid=file_valid and digest(base['path'])==proof['base_sha256'] and digest(s['output'])==proof['raw_sha256']
        except (OSError,UserError,PlanningStopped):
            result={'verdict':'unavailable','issues':[]}
        status={'pass':'approved','repair':'rejected','review':'needs_review','unavailable':'unavailable'}[result['verdict']]
        if not file_valid:status='rejected'
        issues=result['issues']
        message={'approved':'','rejected':'首图有问题，请修复首图后再扩套。','needs_review':'首图有疑点，请重试审核。',
                 'unavailable':'审核暂未完成，请重试审核。'}[status]
        if not file_valid:message='首图文件校验失败，请重出首图。'
        elif issues:message=issues[0]['detail'] or message
        with self.lock:
            passed=status=='approved'
            if status in ('unavailable','needs_review') and result.get('retryable',True) and self.defer_image(r,s,'review_attempts',REVIEW_RETRY_DELAYS,'visual_review_retry','后台将用同一张原图重试审核。'):
                proof.update(status='pending',message=s['msg'],issues=issues,auto_attempts=s['review_attempts'])
                return
            proof.update(status='export_pending' if passed else status,message='' if passed else result.get('message') or message,issues=issues)
            if passed:
                s.update(stage='processing',msg='');self.persist(t)
            else:
                s.update(state='failed',delivery_eligible=False,reason_code='ximalaya_review',msg=proof['message'])
                for child in learning_workflow.descendants(r,s):
                    if child is not s and child['state']=='queued':child.update(state='blocked_first_failed',reason_code='first_failed',msg='等待首图通过审核')
        if passed:self.export_ximalaya(t,r,s)

    def export_ximalaya(self,t,r,s):
        from .brand_logo import render_delivery

        proof=s['ximalaya_review'];base=s['logo_base'];target=Path(s['output']).with_suffix('.jpg')
        try:
            if digest(base['path'])!=proof['base_sha256'] or digest(s['output'])!=proof['raw_sha256']:
                raise UserError('已审核的原图校验失败，请重出首图')
            with self.processing_slots:
                rendered=render_delivery(base['path'],target,self.placement(t,r,s),s['brand_logo_layer'])
        except (OSError,ValueError,UserError) as exc:
            with self.lock:
                if isinstance(exc,OSError) and self.defer_image(r,s,'local_attempts',LOCAL_RETRY_DELAYS,'processing_retry','首图已过审，后台正在重试导出。'):
                    return
                code='local_export' if isinstance(exc,OSError) else 'oversize' if isinstance(exc,ValueError) else 'local_validation'
                message=exc.message if isinstance(exc,UserError) else '成品超过版位文件大小限制。' if isinstance(exc,ValueError) else '首图已过审，导出未完成。'
                proof.update(status='export_failed',message=message)
                s.update(state='failed',reason_code=code,msg=proof['message'])
            return
        with self.lock:
            proof.update(status='approved',sha256=rendered['sha256'],message='')
            s.update(state='done',delivery_eligible=True,sha256=proof['sha256'],jpeg=str(target),
                     delivery_encoding=rendered['encoding'],delivery_logo_asset_id=rendered['asset_id'],reason_code=None,msg='')
            s.pop('retry_after',None)

    def materialize_image(self,s,result,out,placement=None):
        with self.processing_slots:
            return self._materialize_image(s,result,out,placement)

    def note_rate_limit(self):
        """One burst reduces shared admission once, then holds new work briefly."""
        with self.lock:
            now=time.time()
            stamp=time.monotonic()
            if self.last_rate_limit_cut is None or stamp-self.last_rate_limit_cut>=5:
                self.throttle=max(1,min(self.throttle,self.settings.concurrency)//2);self.last_rate_limit_cut=stamp
            self.last_rate_limit=now;self.next_throttle_recovery=now+30
            self.next_submit=max(self.next_submit,now+5)
            self.image_backoff_until=max(self.image_backoff_until,stamp+5)

    def _materialize_image(self,s,result,out,placement=None):
        p=placement or BY_ID[s['pid']]
        if s.get('natural_canvas_plan'):
            from .natural_canvas import crop
            import tempfile
            with tempfile.TemporaryDirectory(prefix='.natural-canvas-',dir=Path(out).parent) as folder:
                processed=crop(result['source'],Path(folder)/'exact.png',s['natural_canvas_plan'],p)
                output=self._encode_delivery(s,{**result,'source':processed['path']},out,p)
            output['natural_processing']={k:v for k,v in processed.items() if k not in ('path','source')}
            return output
        return self._encode_delivery(s,result,out,p)

    def _encode_delivery(self,s,result,out,placement):
        source=Path(result['source']);p=placement or BY_ID[s['pid']];png=p.get('output_format')=='PNG';target=out.with_suffix('.delivery.png' if png else '.jpg')

        kb=(p.get('max_file_size_kb') or 200)-(1/1024 if p.get('file_size_operator')=='lt' else 0)
        encoding={}
        layer=s.get('brand_logo_layer');logo_metadata={}
        try:
            if layer:
                from .brand_logo import prepare_base,render_delivery
                base=prepare_base(source,out.with_suffix('.logo-base.png'),p)
                applied=render_delivery(base['path'],target,p,layer)
                encoding=applied['encoding']
                logo_metadata=dict(logo_base=base,delivery_logo_asset_id=applied['asset_id'])
            elif png:
                from .learning_delivery import save_png
                encoding=save_png(source,target,p)
            else:compress(str(source),str(target),kb,p['target_width'],p['target_height'])
        except ValueError as exc: raise UserError(str(exc) if png else '图片超过渠道大小限制，请重新生成')
        return dict(state='done',raw_sha256=digest(out),sha256=digest(target),jpeg=str(target),
                    delivery_eligible=True,delivery_encoding=encoding,reason_code=None,msg='',**logo_metadata)

    def cleanup(self,immediate=False):
        with self.lock:
            if self.maintenance_active:return dict(freed_bytes=0)
            freed=0;now=time.time()
            uploads=self.settings.state_dir/'uploads'
            for staged in self.cleanup_candidates():
                if staged.exists():freed+=staged.stat().st_size;staged.unlink()
            for t in list(self.tasks.values()):
                deleted=t.get('deleted_at') and now-t['deleted_at']>=300
                if self.is_running(t) or not deleted: continue
                cache=Path(t['output_dir'])/'.cache'/t['id']
                freed+=sum(p.stat().st_size for p in cache.rglob('*') if p.is_file()) if cache.exists() else 0
                shutil.rmtree(cache,ignore_errors=True)
                self.db.execute('DELETE FROM tasks WHERE id=?',(t['id'],));self.db.commit()
                del self.tasks[t['id']]
                self.summary_cache.pop(t['id'],None)
                self.db.execute('DELETE FROM documents WHERE name LIKE ?',('prompt:'+t['id']+':%',));self.db.commit()
            return dict(freed_bytes=freed)

    def storage(self):
        roots={Path(t['output_dir'])/'.cache'/t['id'] for t in self.tasks.values()}
        roots.add(self.settings.state_dir/'uploads')
        roots.add(self.settings.output/'.cache'/'learning-runs')
        used=sum(p.stat().st_size for root in roots if root.exists() for p in root.rglob('*') if p.is_file())
        return dict(used_bytes=used)

    def close(self):
        self.closed.set()
        runtime=getattr(self,'learning_runtime',None)
        if runtime:runtime.close()
        if hasattr(self,'scheduler'): self.scheduler.join(timeout=2)
        self.planning_pool.shutdown(wait=True)
        self.pool.shutdown(wait=True)
        self.db.close()
        self.instance_lock.close()
