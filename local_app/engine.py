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
from .scene_planner import ApiScenePlanner, PlanningStopped
from .planning import BY_ID, ASSETS, make_round, validate, normalize_form, copy_signature, requested_pairs, compile_plans
sys.path.insert(0,str(ROOT/'scripts'))
import positive_prompt
import render
from image_compress import compress

ACTIVE=('queued','generating')

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
        self.pool=ThreadPoolExecutor(max_workers=20)
        self.throttle=20
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
            if pkg.get('fingerprint_schema')!=2 and Path(pkg['path']).is_file():
                try:
                    with zipfile.ZipFile(pkg['path']) as archive:
                        manifest=json.loads(archive.read('交付清单.json'))
                    pkg['fingerprint']=content_fingerprint([{'pid':x['placement_id'],'set':x['set'],'idx':x['image'],'sha256':x['sha256']} for x in manifest['images']])
                    pkg['fingerprint_schema']=2
                except (OSError,ValueError,KeyError,zipfile.BadZipFile): pass
        t.pop('exporting',None)
        for r in t['rounds']:
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
                    state_path=render.task_state_path(Path(s['output']))
                    try:state=json.loads(state_path.read_text()) if state_path.exists() else {}
                    except (OSError,ValueError):
                        s.update(state='failed',reason_code='receipt_corrupt',msg='生成回执损坏，已保留文件，请先恢复备份');continue
                    if r['simulation'] or state.get('task_id'):
                        s['state']='queued'
                        s['resume']=bool(state.get('task_id'))
                    else: s.update(state='failed',reason_code='unknown',msg='状态不明，请恢复查询')
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
            if isinstance(pr,dict):
                pr=json.loads(json.dumps(pr))
                pr=self.freeze_product(pr,self.document('draft:'+draft_id).get('draft') if draft_id else None)
                pr.setdefault('image_model',self.settings.image_model)
            direction=validate(pr,self.settings.output)
            pr=normalize_form(pr)
            if self.settings.real and not self.settings.key: raise UserError('请先在设置中填写 KIE Key')
            if tid:
                t=self.task(tid)
                current=t['rounds'][t['ri']]
                if copy_signature({**current['params'],'image_model':current.get('image_model',DEFAULT_IMAGE_MODEL)})==copy_signature(pr) and current['simulation']==(not self.settings.real):
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
            for ref in pr.get('references',[]):
                path=Path(ref.get('path','')).resolve()
                uploads=(self.settings.state_dir/'uploads').resolve()
                valid_task_upload=any(path==Path(old['path']).resolve() for rr in t['rounds'] for old in rr['params'].get('references',[]))
                if not path.is_file() or (uploads not in path.parents and not valid_task_upload): raise UserError('参考图不存在，请重新上传')
                dest=cache/'references'/path.name
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(path,dest)
                ref['path']=str(dest)
            try: r=make_round(pr,t['id'],cache,self.settings.concurrency,not self.settings.real,defer_planning=True)
            except UserError:
                shutil.rmtree(cache,ignore_errors=True)
                raise
            except Exception:
                shutil.rmtree(cache,ignore_errors=True)
                raise UserError('提示词未通过校验，请检查文案和参考素材')
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

    def query_required(self,s):
        if s['state']!='failed': return False
        if self.definitely_unsent(s): return False
        if s.get('reason_code') in ('unknown','timeout'): return True
        path=render.task_state_path(Path(s['output']))
        try: state=json.loads(path.read_text()) if path.exists() else {}
        except (OSError,ValueError): return True
        return bool(state.get('task_id') and state.get('status')!='fail')

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
        saved[pr['image_form']]={k:pr[k] for k in ('pids','sets','ip','style','font','noLogo','cta') if k in pr}
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
            part=make_round(r['params'],t['id'],cache,r['concurrency'],r['simulation'],defer_planning=True,
                            assignments=r['set_metadata'],pairs=extra,round_id=r['id'],placements_override={**BY_ID,**self.placement_rules(t,r)})
            offset=len(r['configs'])
            for slot in part['slots']: slot['config_idx']+=offset
            r['slots'].extend(part['slots']);r['configs'].extend(part['configs'])
            r['set_metadata']=part['set_metadata'];r['planning_targets']=part['planning_targets']
            r.update(planning_status='queued',planning_error='',stopped=False)
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
            result=self.planner.plan(snapshot,lambda value:compile_plans(snapshot,value,apply=False),self.closed)
            with self.lock:
                if not r['stopped'] and not self.closed.is_set():
                    work={**r,'planning_targets':chunk}
                    compile_plans(work,result)
                    r['planning_targets']=[target for target in r['planning_targets'] if target not in chunk]
                    r.update(planning_status='queued' if r['planning_targets'] else 'done',planning_error='',planning_provenance=result.get('_provenance',{}))
                    for s in r['slots']:
                        if s.get('plan_ready') and s.get('reason_code')=='planning_failed': s.update(state='queued',reason_code=None,msg='')
                    atomic(Path(r['stop_marker']).parent/'visual-plans.json',{'plans':[{'placement_id':c['pid'],'set_number':c['set'],'concept':c['concept']} for c in r['configs'] if c.get('concept')],
                        'provenance':r.get('planning_provenance',{})})
        except PlanningStopped:
            with self.lock: r['planning_status']='stopped'
        except Exception as exc:
            with self.lock:
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
            for s in r['slots']:
                r['placement_rules']=self.placement_rules(t,source)
                original=next(x for x in source['slots'] if x['id']==s['id'])
                if self.definitely_unsent(original):s.update(reason_code='not_submitted',msg='生图请求未发出，可重试本张')
                s['query_required']=self.query_required(s)
                s['set_id']=selection_key(s['pid'],s['set'])
                s['has_frame']=bool((s.get('frame') or {}).get('enabled'))
                s.pop('output',None)
                s.pop('frame',None)
                s.pop('job_path',None)
                s.pop('versions',None)
                s['original_image_url']=f"/api/tasks/{t['id']}/images/{s['id']}?v={s['att']}&raw=1" if s['state']=='done' else None
                s['preview_kind']='raw' if s.get('delivery_eligible') is False else 'processed'
                s['image_url']=(s['original_image_url'] if s['preview_kind']=='raw' else f"/api/tasks/{t['id']}/images/{s['id']}?v={s['att']}") if s['state']=='done' else None
                if s['preview_kind']=='raw':
                    s.update(reason_code='frame_failed',msg='自动去框失败，当前显示完整原图，暂不合格')
                s['reference_images']=[{'label':ref.get('label','参考图'+str(i+1)),'name':ref.get('role','参考图'),'type':ref.get('role','参考图'),'upload_status':s.get('up',{}).get(str(i),'ok'),
                    'thumbnail_url':f"/api/tasks/{t['id']}/references/{s['id']}/{i}"} for i,ref in enumerate(s['refs'])]
                s.pop('refs',None)
            done=sum(s['state']=='done' for s in r['slots'])
            r['completed_count']=done
            r['generation']={'completed':done,'total':len(r['slots']),'planning':r.get('planning_status','done'),'stopped':r['stopped']}
            r['status']='stopped' if r['stopped'] else 'generating' if any(s['state'] in ACTIVE for s in r['slots']) else 'done'
            missing=[{'placement_id':pid,'name':self.placement(t,source,{'pid':pid})['platform']+' '+self.placement(t,source,{'pid':pid})['name'],'reason':'尚未采纳完整套图'} for pid in r['params']['pids'] if not any(r['sel'].get(selection_key(pid,n)) and all(s['state']=='done' and r['adopted_versions'].get(selection_key(pid,n),{}).get(s['id'])==s['att'] for s in r['slots'] if s['pid']==pid and s['set']==n) for n in range(1,r['params']['sets']+1))]
            r['pending_placements']=missing
            r['counts']={'total':len(r['slots']),'adopted':sum(bool(r['sel'].get(selection_key(s['pid'],s['set']))) and s['state']=='done' for s in r['slots']),
                'not_adopted':sum(not r['sel'].get(selection_key(s['pid'],s['set'])) and s['state']=='done' for s in r['slots']),
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
            for image in p['images']: image['thumbnail_url']=f"/api/tasks/{t['id']}/images/{image['id']}?v={image['att']}"
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
        if action in ('reprocess-frame','fit-image'):return self.process_frame(tid,action,data)
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
                return {'params':params}
            else:
                r=self.round(t,data.get('round',t['ri']))
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
                    Path(r['stop_marker']).unlink(missing_ok=True)
                    for s in r['slots']:
                        if not s.get('plan_ready',True): s.update(state='queued',reason_code=None,msg='')
                elif action=='add-variant':
                    if r.get('planning_source')!='codex_skill': raise UserError('历史模拟任务请复制为新任务，使用原 Skill 重新规划')
                    pid=data.get('placement_id')
                    if pid not in r['params']['pids']: raise UserError('渠道版位不存在')
                    n=max(s['set'] for s in r['slots'] if s['pid']==pid)+1
                    if n>20: raise UserError('每个版位最多 20 套')
                    return self.extend(t,r,r['params'],str(uuid.uuid4()),pairs=[(pid,n)])
                elif action=='repair-set':
                    pid=data.get('placement_id');n=data.get('set')
                    group=[s for s in r['slots'] if s['pid']==pid and s['set']==n]
                    if not group: raise UserError('套图不存在')
                    crop_pending=[s for s in group if s['state']=='done' and not s.get('delivery_eligible',True)]
                    for s in crop_pending:
                        self.mutate(tid,'reprocess-frame',{'round':data.get('round',t['ri']),'image_id':s['id']})
                    head=next(s for s in group if s['idx']==1)
                    targets=[head] if head['state'] in ('failed','stopped') else [s for s in group if s['state'] in ('failed','blocked_first_failed','stopped')]
                    if not targets and not crop_pending: raise UserError('这套图片无需补齐')
                    for s in targets: self.mutate(tid,'resume' if self.query_required(s) else 'regenerate',{'round':data.get('round',t['ri']),'image_id':s['id']})
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
                        sl=[s for s in r['slots'] if s['set']==n and s['pid']==pid]
                        if not sl: raise UserError('所选套图不存在，请刷新后重试')
                        if adopted and not any(s['state']=='done' for s in sl): raise UserError('这一套还没有可选择的图片')
                        groups[selection_key(pid,n)]=sl
                    # Validate the entire scope before changing any selection.
                    for selection,sl in groups.items():
                        r['sel'][selection]=adopted
                        r['adopted_versions'][selection]={s['id']:s['att'] for s in sl} if adopted else {}
                    if groups: t['downloaded']=False
                elif action in ('regenerate','resume'):
                    s=next((s for s in r['slots'] if s['id']==data.get('image_id')),None)
                    if not s: raise UserError('图片不存在',404)
                    if data.get('expected_att',s['att'])!=s['att']: raise UserError('图片已在另一窗口更新，草稿已保留，请重新打开当前版本后提交',409)
                    if action=='resume':
                        if not self.query_required(s): raise UserError('这张图片不需要恢复查询')
                        st=render.task_state_path(Path(s['output']))
                        state=json.loads(st.read_text()) if st.exists() else {}
                        if not state.get('task_id'): raise UserError('未取得任务号，不能自动重提，请核对供应商记录')
                        s.update(state='queued',resume=True,reason_code=None,msg='')
                        if s['idx']==1:
                            for child in r['slots']:
                                if child['first_id']==s['id'] and child['state']=='blocked_first_failed':
                                    child.update(state='queued',reason_code=None,msg='')
                    else:
                        if r.get('planning_source')!='codex_skill': raise UserError('历史模拟任务请复制为新任务，使用原 Skill 重新规划')
                        if s.get('reason_code')=='planning_failed': raise UserError('请先重试画面规划')
                        if s['state']=='blocked_first_failed': raise UserError('请先处理图 1；后续图不能替代图 1 发起重出')
                        group=[x for x in r['slots'] if x['set']==s['set'] and x['pid']==s['pid']] if s['idx']==1 else [s]
                        if any(x['state'] in ACTIVE or x.get('local_processing') for x in group): raise UserError('图片仍在生成，请等待结束')
                        if any(self.query_required(x) for x in group): raise UserError('这套存在状态未确定的图片，请先恢复查询，不能重复提交')
                        if s['idx']>1 and next(x for x in r['slots'] if x['id']==s['first_id'])['state']!='done':
                            raise UserError('请先处理图 1，再重出本张')
                        prompt=data.get('prompt',s['prompt'])
                        manual='prompt' in data or s.get('prompt_origin')=='manual'
                        from poster_prompt import validate_text
                        try:
                            validate_text(prompt)
                            if not manual:
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
                        r['sel'].pop(selection_key(s['pid'],s['set']),None)
                        r['adopted_versions'].pop(selection_key(s['pid'],s['set']),None)
                        for x in group:
                            x['versions'].append(json.loads(json.dumps({k:x.get(k) for k in ('att','prompt','output','jpeg','sha256','raw_sha256','state','refs','frame_status','frame_processing','reason_code','quality_review','prompt_origin','head_version','pinned')})))
                            if x is s: x.update(prompt=prompt,prompt_origin='manual' if manual else 'system')
                            x['att']+=1
                            x.update(state='queued',reason_code=None,msg='',up={})
                            x.pop('resume',None);x.pop('pinned',None)
                            x['output']=str(Path(x['output']).with_name(x['id']+f"-v{x['att']}.png"))
                            if x['idx']>1:
                                head=next(y for y in r['slots'] if y['id']==x['first_id'])
                                x['refs'][0]['path']=head['output']
                                x['head_version']=head['att']
                        t['downloaded']=False
                    r['stopped']=False
                    Path(r['stop_marker']).unlink(missing_ok=True)
                else: raise UserError('操作不存在',404)
            if action in ('regenerate','rebrief-round','retry-planning','adopt','adopt-bulk'):t['archived']=False
            self.persist(t)
            return self.public(t)

    def sync_provider_ids(self,t,s):
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
            head=next((x for x in r['slots'] if x['id']==s['first_id']),s)
            if s['idx']>1 and (not Path(head['output']).exists() or digest(head['output'])!=head.get('raw_sha256')):
                raise UserError('图 1 校验失败，请重新生成图 1')
            out=Path(s['output'])
            job=out.with_suffix('.job.json')
            atomic(job,dict(slot=s,placement=self.placement(t,r,s),params=r['params'],simulation=r['simulation'],base=self.settings.base,upload=self.settings.upload,image_model=r.get('image_model',DEFAULT_IMAGE_MODEL),query_only=s.pop('resume',False),stop_marker=r['stop_marker'],upload_cache=str(self.settings.state_dir/'reference-upload-cache.json')))
            env={**os.environ,'KIE_API_KEY':self.settings.key}
            proc=subprocess.Popen([sys.executable,str(ROOT/'local_app/worker.py'),str(job)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            # Drain bounded worker output off-thread; raw provider text is never exposed.
            stdout,stderr=proc.communicate()
            result_path=job.with_suffix('.result.json')
            result=json.loads(result_path.read_text()) if result_path.exists() else dict(ok=False,reason='unknown')
            state=result.get('state',{})
            ids=[x.get('task_id') for x in state.get('attempt_history',[])]+[state.get('task_id')]
            with self.lock:
                s['provider_task_ids']=[i for i in ids if i]
                s['restarted']=bool(state.get('timeout_restarts'))
                if ids and any(ids):
                    with self.audit_path.open('a',encoding='utf-8') as f: f.write(json.dumps({'at':time.time(),'task':t['id'],'image':s['id'],'task_ids':s['provider_task_ids']})+'\n')
            if not result['ok'] and result.get('reason')=='rate_limited':
                with self.lock:
                    self.throttle=max(1,min(self.throttle,self.settings.concurrency)//2)
                    self.last_rate_limit=time.time();self.next_throttle_recovery=time.time()+30
                    self.next_submit=time.time()+5
                    s.update(state='queued',reason_code=None,msg='')
            elif not result['ok'] and result.get('reason')=='busy':
                with self.lock:s.update(state='queued',retry_after=time.time()+3,resume=bool(state.get('task_id')),msg='等待已有执行器完成')
            elif not result['ok'] and result.get('reason')=='stopped':
                with self.lock: s.update(state='stopped',reason_code=None,msg='')
            elif not result['ok']:
                code=result.get('reason','no_image')
                messages={'prompt_rejected':'提示词未通过校验，请修改后重新生成','unknown':'状态不明，请恢复查询','timeout':'生成超时，请恢复查询','no_image':'未返回图片，请检查连接后重试','disk_full':'磁盘空间不足，请释放空间后恢复查询','busy':'已有执行器正在处理','download_failed':'图片已生成但下载未完成，请恢复查询'}
                with self.lock:
                    s.update(state='failed',reason_code=code,msg='参考图上传失败，请检查连接后重试' if result.get('failed_references') else messages.get(code,messages['no_image']),up={str(i):'failed' for i in result.get('failed_references',[])})
            else:
                with self.lock:s['stage']='processing';self.persist(t)
                updates=self.materialize_image(s,result,out,self.placement(t,r,s))
                with self.lock:
                    s.update(updates)
        except Exception as exc:
            with self.lock: s.update(state='failed',reason_code='oversize' if isinstance(exc,UserError) and '大小' in exc.message else 'no_image',msg=exc.message if isinstance(exc,UserError) else '生成失败，请检查连接后重试')
        finally:
            with self.lock:
                self.running.discard(key)
                self.persist(t)

    def materialize_image(self,s,result,out,placement=None):
        source=Path(result['source']);target=out.with_suffix('.jpg');p=placement or BY_ID[s['pid']]
        failed=result.get('frame_status')=='failed'
        kb=p['max_file_size_kb']-(1/1024 if p.get('file_size_operator')=='lt' else 0)
        try:
            # A failed guide detector must never cover-crop a raw image and present it as a finished candidate.
            compress(str(source),str(target),kb,*(() if failed else (p['target_width'],p['target_height'])))
        except ValueError: raise UserError('图片超过渠道大小限制，请重新生成')
        record=result.get('frame_processing') or {}
        review=bool(result.get('frame_review'))
        message=('自动去框失败，当前显示完整原图，暂不合格' if failed else
                 '已整图适配，保留全部内容；请确认画面比例' if result.get('frame_status')=='full_image_fit' else
                 '已去框并调整画面比例，请确认人物和文字效果' if review and record.get('review_reason')=='aspect_change' else
                 '已去框，框内另有裁切，请确认画面完整' if review else '')
        return dict(state='done',raw_sha256=digest(out),sha256=digest(target),jpeg=str(target),
                    delivery_eligible=not failed,frame_status=result.get('frame_status'),frame_processing=record,
                    reason_code='frame_failed' if failed else 'frame_review' if review else None,msg=message)





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
        used=sum(p.stat().st_size for root in roots if root.exists() for p in root.rglob('*') if p.is_file())
        return dict(used_bytes=used)

    def close(self):
        self.closed.set()
        if hasattr(self,'scheduler'): self.scheduler.join(timeout=2)
        self.planning_pool.shutdown(wait=True)
        self.pool.shutdown(wait=True)
        self.db.close()
        self.instance_lock.close()

    def process_frame(self,tid,action,data):
        with self.lock:
            if self.maintenance_active:raise UserError('正在进行本机数据维护，请稍后处理图片')
            t=self.task(tid);r=self.round(t,data.get('round',t['ri']));_,live=self.find_image(t,data.get('image_id'))
            if live not in r['slots'] or live['state']!='done' or not (live.get('frame') or {}).get('enabled'):
                raise UserError('这张图片没有可处理的蓝框原图')
            if live.get('local_processing'):raise UserError('图片正在本机处理，请稍候')
            s=copy.deepcopy(live);expected=s['att'];live['local_processing']=True;self.persist(t)
        try:
            fitting=action=='fit-image'
            if fitting:
                import cv2
                image=cv2.imread(s['output'])
                if image is None: raise UserError('原图无法读取')
                p=self.placement(t,r,s);h,w=image.shape[:2]
                folder=Path(s['output']).parent/'整图适配';folder.mkdir(exist_ok=True)
                candidate=folder/(Path(s['output']).stem+'-fit.png')
                resized=cv2.resize(image,(p['target_width'],p['target_height']),interpolation=cv2.INTER_AREA)
                if not cv2.imwrite(str(candidate),resized): raise UserError('整图适配结果无法保存')
                aspect=abs((w/h)/(p['target_width']/p['target_height'])-1)*100
                record=dict(method='full_image_fit',source_size=[w,h],crop_xyxy=[0,0,w,h],
                            output_size=[p['target_width'],p['target_height']],candidate_filepath=str(candidate),
                            needs_crop_review=aspect>=4,review_reason='aspect_change',aspect_change_percent=round(aspect,4))
            else:
                from blue_frame import process_candidate
                try: record=process_candidate(s['output'],s['frame']['frame_layout_path'])
                except (ValueError,OSError): raise UserError('无法可靠识别完整蓝框，已保留原图；可选择整图适配，未提交生图')
            previous={k:s.get(k) for k in ('att','prompt','output','jpeg','sha256','raw_sha256','state','refs','frame_status','frame_processing','reason_code','quality_review','prompt_origin','head_version','pinned')}
            new_att=s['att']+1
            out=Path(s['output']).with_name(s['id']+f'-v{new_att}.png')
            shutil.copy2(s['output'],out)
            receipt=render.task_state_path(Path(s['output']))
            if receipt.exists(): shutil.copy2(receipt,render.task_state_path(out))
            result=dict(source=record['candidate_filepath'],frame_status='full_image_fit' if fitting else 'processed',frame_processing=record,frame_review=record['needs_crop_review'])
            updates=self.materialize_image(s,result,out,self.placement(t,r,s))
            with self.lock:
                if live['att']!=expected:raise UserError('图片版本已变化，请重新处理',409)
                live['versions'].append(previous)
                live.pop('pinned',None)
                live.update(updates,att=new_att,output=str(out),version_reason='local_full_image_fit' if fitting else 'local_frame_processing')
                selection=selection_key(live['pid'],live['set'])
                if fitting and r['sel'].get(selection):r['adopted_versions'].setdefault(selection,{})[live['id']]=new_att
                else:r['sel'].pop(selection,None);r['adopted_versions'].pop(selection,None)
                t['downloaded']=False
        finally:
            with self.lock:live['local_processing']=False;self.persist(t)
        return self.public(t)
