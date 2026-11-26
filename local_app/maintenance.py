"""Previewed version pruning and portable, non-overwriting local backup recovery."""
import copy
import hashlib
import json
import shutil
import sqlite3
import threading
import time
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path
from .config import ROOT,UserError
from .instance import InstanceLock
from .safety import require_space,valid_task


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
    return h.hexdigest()


def rewrite(value,mapping):
    if isinstance(value,dict):return {k:rewrite(v,mapping) for k,v in value.items()}
    if isinstance(value,list):return [rewrite(v,mapping) for v in value]
    return mapping.get(value,value) if isinstance(value,str) else value

class MaintenanceMixin:
    @contextmanager
    def maintenance(self):
        with self.maintenance_lock:
            with self.lock:
                runtime=getattr(self,'learning_runtime',None)
                if runtime and runtime.is_active():raise UserError('请等待学习机制作结束后再维护数据')
                if self.running or self.planning_running or any(t.get('exporting') or any(s.get('local_processing') for r in t['rounds'] for s in r['slots']) for t in self.tasks.values()):raise UserError('请等待正在执行的任务结束后再维护数据')
                self.maintenance_active=True
            try:yield
            finally:self.maintenance_active=False

    def placement_rules(self,t,r):
        rules=copy.deepcopy(r.get('placement_rules',{}))
        for e in r.get('configs',[]):
            if e['pid'] not in rules:
                for p in e.get('config',{}).get('placements',[]):rules.setdefault(e['pid'],copy.deepcopy(p))
        from .planning import BY_ID
        for pid in r['params']['pids']:
            if pid not in rules and pid in BY_ID:rules[pid]=copy.deepcopy(BY_ID[pid])
        return rules

    def placement(self,t,r,s):
        pid=s['pid'];p=r.get('placement_rules',{}).get(pid)
        if p is None:
            p=next((p for e in r.get('configs',[]) if e['pid']==pid for p in e.get('config',{}).get('placements',[])),None)
        if p is None:
            from .planning import BY_ID
            p=BY_ID.get(pid) if pid in r['params']['pids'] else None
        if p is None:raise UserError('该历史版位缺少规格快照，请恢复备份中的配置')
        return copy.deepcopy(p)

    def package_rules(self,t,pkg):
        rules={}
        for image in pkg['images']:
            r,_=self.find_image(t,image['id']);rules.update(self.placement_rules(t,r))
        return rules

    def maintenance_status(self):
        with self.lock:
            backups=self.settings.state_dir/'backups'
            return dict(backups=[{'path':str(p),'bytes':p.stat().st_size} for p in sorted(backups.glob('workbench-*.zip'),reverse=True)],
                        quarantined=[dict(id=x[0],reason=x[1],at=x[2]) for x in self.db.execute('SELECT id,reason,created_at FROM quarantined_tasks')],
                        notice=getattr(self,'last_scheduler_error',None),active=self.maintenance_active)

    def prune_plan(self):
        with self.lock:
            tasks=copy.deepcopy([t for t in self.tasks.values() if not t.get('deleted_at')])
        owners={};protected=set();candidates=[];assigned=set()
        def paths(v):
            return {str(Path(x).resolve()) for x in (v.get('output'),v.get('jpeg'),
                                                    (v.get('logo_base') or {}).get('path'),
                                                    (v.get('logo_review') or {}).get('path')) if x}
        for t in tasks:
            used={(i['id'],i['att']) for p in t['pkgs'] for i in p['images']}
            selected={(sid,att) for versions in (r['adopted_versions'] for r in t['rounds']) for vv in versions.values() for sid,att in vv.items()}
            for r in t['rounds']:
                for s in r['slots']:
                    for v in [s,*s['versions']]:
                        key=(t['id'],s['id'],v['att']);owners[key]=(v,paths(v))
                        if v is s or v.get('pinned') or (s['id'],v['att']) in used|selected:protected.add(key)
        changed=True
        while changed:
            changed=False
            refs={str((Path(x['path']) if Path(x['path']).is_absolute() else ROOT/x['path']).resolve()) for k in protected for x in owners[k][0].get('refs',[])}
            refs.update(str(Path(x['path']).resolve()) for k in protected for x in (owners[k][0].get('source_versions') or {}).values())
            files={p for k in protected for p in owners[k][1]}
            for k,(v,pp) in owners.items():
                if k not in protected and (pp&refs or pp&files):protected.add(k);changed=True
        for k,(v,pp) in owners.items():
            if k in protected or v.get('files_cleared'):continue
            allowed=[]
            for p in pp:
                path=Path(p)
                if path.is_file() and (any((Path(t['output_dir'])/'.cache'/t['id']).resolve() in path.resolve().parents for t in tasks) or (self.settings.output/'.restored').resolve() in path.resolve().parents):allowed.append(p)
            if allowed:
                unique=sorted(set(allowed)-assigned);assigned.update(unique)
                task=next(t for t in tasks if t['id']==k[0]);rr,ss=self.find_image(task,k[1]);ppp=self.placement(task,rr,ss)
                label=f"{task.get('name',task['direction'])} / {ppp['platform']} {ppp['name']} / 方案{ss['set']} 图{ss['idx']}"
                candidates.append(dict(task_id=k[0],image_id=k[1],label=label,att=k[2],files=unique,bytes=sum(Path(p).stat().st_size for p in unique)))
        token=hashlib.sha256(json.dumps(candidates,sort_keys=True).encode()).hexdigest()
        return dict(token=token,versions=candidates,bytes=sum(v['bytes'] for v in candidates))

    def prune_versions(self,token):
        with self.maintenance():
            plan=self.prune_plan()
            if token!=plan['token']:raise UserError('版本或选择已变化，请重新预览清理范围',409)
            original_tasks={}
            moved=[];folder=self.settings.state_dir/'recycle'/uuid.uuid4().hex;folder.mkdir(parents=True)
            journal={'versions':plan['versions'],'moves':[{'source':path,'dest':str(folder/str(i))} for i,path in enumerate(path for v in plan['versions'] for path in v['files'])]}
            (folder/'journal.json').write_text(json.dumps(journal,ensure_ascii=False),encoding='utf-8')
            try:
                for v in plan['versions']:
                    for path in v['files']:
                        source=Path(path);guard=InstanceLock(source.with_suffix(source.suffix+'.execution.lock'))
                        try:
                            dest=folder/str(len(moved));shutil.move(source,dest);moved.append((source,dest))
                        finally:guard.close()
                with self.lock:
                    touched=set()
                    original_tasks={item['task_id']:copy.deepcopy(self.task(item['task_id'])) for item in plan['versions']}
                    for item in plan['versions']:
                        t=self.task(item['task_id']);_,s=self.find_image(t,item['image_id']);v=next(v for v in s['versions'] if v['att']==item['att']);v['files_cleared']=True;touched.add(t['id'])
                    try:
                        self.db.execute('BEGIN IMMEDIATE')
                        for tid in touched:
                            t=self.tasks[tid];t['revision']=t.get('revision',0)+1;t['updated_at']=time.time()
                            self.db.execute('UPDATE tasks SET body=? WHERE id=?',(json.dumps(t,ensure_ascii=False),tid))
                        self.db.commit()
                    except Exception:self.db.rollback();raise
            except Exception:
                with self.lock:
                    for tid,t in original_tasks.items():self.tasks[tid]=t;self.summary_cache.pop(tid,None)
                for source,dest in reversed(moved):
                    if dest.exists():source.parent.mkdir(parents=True,exist_ok=True);shutil.move(dest,source)
                raise
            shutil.rmtree(folder)
            return dict(versions=len(plan['versions']),bytes=plan['bytes'])

    def recover_recycle(self):
        root=self.settings.state_dir/'recycle'
        for journal_path in root.glob('*/journal.json'):
            try:
                journal=json.loads(journal_path.read_text(encoding='utf-8'));committed=True
                for item in journal['versions']:
                    t=self.tasks.get(item['task_id'])
                    if not t:committed=False;break
                    _,s=self.find_image(t,item['image_id'])
                    v=next((v for v in s['versions'] if v['att']==item['att']),None)
                    if not v or not v.get('files_cleared'):committed=False;break
                if not committed:
                    for move in journal['moves']:
                        source=Path(move['source']);dest=Path(move['dest'])
                        allowed=any((Path(t['output_dir'])/'.cache').resolve() in source.resolve().parents for t in self.tasks.values()) or (self.settings.output/'.restored').resolve() in source.resolve().parents
                        if not allowed or journal_path.parent.resolve() not in dest.resolve().parents:raise ValueError('invalid recycle journal')
                        if dest.exists() and not source.exists():source.parent.mkdir(parents=True,exist_ok=True);shutil.move(dest,source)
                shutil.rmtree(journal_path.parent)
            except (OSError,ValueError,KeyError,TypeError,UserError):self.last_scheduler_error={'message':'发现需要检查的清理恢复记录，原文件仍在回收目录保留','at':time.time()}

    def pin_version(self,tid,sid,att,pinned):
        with self.lock:
            if type(pinned) is not bool:raise UserError('请选择保留或取消保留')
            if self.maintenance_active:raise UserError('正在维护数据，请稍后操作')
            t=self.task(tid);_,s=self.find_image(t,sid);v=s if s['att']==att else next((v for v in s['versions'] if v['att']==att),None)
            if v is None or v.get('files_cleared'):raise UserError('该版本不存在或文件已清理')
            v['pinned']=bool(pinned);self.persist(t);return {'pinned':v['pinned']}

    def create_backup(self):
        with self.maintenance():
            with self.lock:
                for (name,) in self.db.execute('SELECT name FROM documents').fetchall():self.document(name)
                tasks=copy.deepcopy([t for t in self.tasks.values() if not t.get('deleted_at')]);documents=[dict(name=n,body=b) for n,b in self.db.execute('SELECT name,body FROM documents') if not n.startswith('closed-draft:')]
                quarantined=[list(x) for x in self.db.execute('SELECT id,body,reason,created_at FROM quarantined_tasks')]
            files={};missing=[]
            roots=[ROOT/'assets',self.settings.state_dir/'uploads',self.settings.output,*[Path(t['output_dir']) for t in tasks]]
            for document in documents:
                if not document['name'].startswith('learning-run:'):continue
                run=json.loads(document['body']);directory=Path(run.get('directory',''))
                if (directory.name==run.get('id') and directory.parent.name=='learning-runs'
                        and directory.parent.parent.name=='.cache'):
                    roots.append(directory.parent.parent.parent)
            def walk(v):
                if isinstance(v,dict):
                    for key,x in v.items():
                        if isinstance(x,(dict,list)) or key in ('output','jpeg','path') or key.endswith(('_path','_filepath')):walk(x)
                elif isinstance(v,list):
                    for x in v:walk(x)
                elif isinstance(v,str) and len(v)<2000:
                    try:
                        p=Path(v);p=p if p.is_absolute() else ROOT/p
                        if not p.name.startswith('.env') and p.suffix.lower() not in ('.key','.pem') and any(r.resolve() in p.resolve().parents for r in roots):
                            if p.is_file():files[v]=p.resolve()
                            if p.suffix.lower()=='.png':
                                import render
                                receipt=render.task_state_path(p)
                                if receipt.is_file():files[str(receipt)]=receipt.resolve()
                    except (OSError,ValueError):pass
            walk(tasks)
            for d in documents:
                try:walk(json.loads(d['body']))
                except ValueError:pass
            import render
            for t in tasks:
                for r in t['rounds']:
                    for s in r['slots']:
                        for v in [s,*s['versions']]:
                            p=Path(v['output']);receipt=render.task_state_path(p)
                            if receipt.exists():files[str(receipt)]=receipt
                            if not v.get('files_cleared') and v['state']=='done':
                                for key in ('output','jpeg'):
                                    if v.get(key) and not Path(v[key]).is_file():missing.append(v[key])
                                logo_paths=[(v.get('logo_base') or {}).get('path'),(v.get('logo_review') or {}).get('path')]
                                logo_paths.extend(a.get('path') for a in (v.get('brand_logo_layer') or {}).get('assets',{}).values())
                                missing.extend(p for p in logo_paths if p and not Path(p).is_file())
            indexed={str(Path(p['path']).resolve()) for t in tasks for p in t['pkgs']}
            standalone=[]
            work=self.settings.output/'工作区'/'产物'
            if work.exists():
                for p in work.glob('**/APP图片/**/06_打包/*.zip'):
                    if str(p.resolve()) not in indexed:files[str(p.resolve())]=p.resolve();standalone.append(str(p.resolve()))
            records=[]
            for old,p in files.items():records.append(dict(path=old,sha256=digest(p),bytes=p.stat().st_size))
            require_space(self.settings.state_dir,sum(x['bytes'] for x in records))
            folder=self.settings.state_dir/'backups';folder.mkdir(exist_ok=True)
            path=folder/('workbench-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.zip');temp=path.with_suffix('.tmp')
            try:
                with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
                    written=set()
                    for record in records:
                        key='files/'+record['sha256']
                        if key not in written:z.write(files[record['path']],key);written.add(key)
                    manifest=dict(schema=1,created_at=time.time(),tasks=tasks,documents=documents,files=records,quarantined=quarantined,missing=missing,standalone=standalone)
                    z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
                self.inspect_backup(temp);temp.replace(path)
            except Exception:temp.unlink(missing_ok=True);raise
            return dict(path=str(path),bytes=path.stat().st_size,tasks=len(tasks),drafts=sum(d['name'].startswith('draft:') for d in documents),missing=len(missing),standalone=len(standalone))

    def inspect_backup(self,path):
        try:
            with zipfile.ZipFile(path) as z:
                info=z.getinfo('manifest.json')
                if info.file_size>16*1024*1024:raise ValueError()
                m=json.loads(z.read('manifest.json'))
                if m['schema']!=1 or len(m['files'])>10000 or sum(f['bytes'] for f in m['files'])>16*1024**3:raise ValueError()
                if not all(valid_task(t,t['id']) for t in m['tasks']) or len({t['id'] for t in m['tasks']})!=len(m['tasks']):raise ValueError()
                if len({f['path'] for f in m['files']})!=len(m['files']):raise ValueError()
                for doc in m['documents']:
                    if not isinstance(doc['name'],str):raise ValueError()
                    json.loads(doc['body'])
                if any(len(row)!=4 for row in m.get('quarantined',[])):raise ValueError()
                for f in m['files']:
                    if len(f['sha256'])!=64 or any(c not in '0123456789abcdef' for c in f['sha256']):raise ValueError()
                    name='files/'+f['sha256'];i=z.getinfo(name)
                    if i.file_size!=f['bytes'] or digest_stream(z.open(name))!=f['sha256']:raise ValueError()
            return m
        except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile):raise UserError('备份文件损坏或格式不支持，未恢复任何数据') from None

    def restore_preview(self,path):
        m=self.inspect_backup(path)
        with self.lock:conflicts=[t['id'] for t in m['tasks'] if t['id'] in self.tasks]
        return dict(tasks=len(m['tasks']),drafts=sum(d['name'].startswith('draft:') for d in m['documents']),conflicts=len(conflicts),restorable=len(m['tasks'])-len(conflicts),files=len(m['files']),bytes=sum(f['bytes'] for f in m['files']),missing=len(m.get('missing',[])),standalone=len(m.get('standalone',[])),token=digest(path))

    def restore_backup(self,path,token):
        with self.maintenance():
            try:actual=digest(path)
            except OSError:raise UserError('备份文件不存在，请重新选择') from None
            if actual!=token:raise UserError('备份文件已变化，请重新预览',409)
            m=self.inspect_backup(path)
            with self.lock:
                existing_documents={name for (name,) in self.db.execute('SELECT name FROM documents')}
                existing_bad={name for (name,) in self.db.execute('SELECT id FROM quarantined_tasks')}
                if (not m.get('standalone') or self.document('restored_backup:'+token)) and all(t['id'] in self.tasks for t in m['tasks']) and all(d['name'] in existing_documents for d in m['documents']) and all(row[0] in existing_bad for row in m.get('quarantined',[])):
                    return dict(restored=0,documents_restored=0,skipped=len(m['tasks']),path=None)
            require_space(self.settings.output,sum(f['bytes'] for f in m['files']))
            folder=self.settings.output/'.restored'/uuid.uuid4().hex;folder.mkdir(parents=True)
            mapping={f['path']:str(folder/(str(i)+'-'+f['sha256']+Path(f['path']).suffix)) for i,f in enumerate(m['files'])}
            # Include future outputs: queued images have no file in the archive yet.
            for task in m['tasks']:
                for round_ in task['rounds']:
                    destination=folder/task['id']/round_['id']
                    destination.mkdir(parents=True,exist_ok=True)
                    for slot in round_['slots']:
                        for version in [slot,*slot['versions']]:
                            for field,suffix in (('output','.png'),('jpeg','.delivery.png' if Path(version.get('jpeg') or '').suffix.lower()=='.png' else '.jpg')):
                                if version.get(field):
                                    mapping[version[field]]=str(destination/(slot['id']+f"-v{version['att']}"+suffix))
            # Learning runs live in documents rather than the legacy tasks
            # table. Keep pending PNG receipts adjacent even if no PNG exists.
            import render
            for document in m['documents']:
                if not document['name'].startswith('learning-run:'):continue
                value=json.loads(document['body'])
                def learning_outputs(item):
                    if isinstance(item,dict):
                        raw=item.get('raw_path')
                        if isinstance(raw,str) and raw:
                            if raw not in mapping:
                                destination=folder/'learning-pending'/value['id'];destination.mkdir(parents=True,exist_ok=True)
                                mapping[raw]=str(destination/(hashlib.sha256(raw.encode()).hexdigest()+'.png'))
                            receipt=str(render.task_state_path(Path(raw)))
                            if receipt in mapping:mapping[receipt]=str(render.task_state_path(Path(mapping[raw])))
                        for child in item.values():learning_outputs(child)
                    elif isinstance(item,list):
                        for child in item:learning_outputs(child)
                learning_outputs(value)
            try:
                with zipfile.ZipFile(path) as z:
                    for f in m['files']:
                        target=Path(mapping[f['path']]);
                        if target.exists():continue
                        with z.open('files/'+f['sha256']) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst)
                # Restore receipt names adjacent to PNGs, as required by recovery.
                import render
                for t in m['tasks']:
                    for r in t['rounds']:
                        for s in r['slots']:
                            for v in [s,*s['versions']]:
                                old=str(render.task_state_path(Path(v['output'])))
                                if old in mapping and v['output'] in mapping:
                                    new=str(render.task_state_path(Path(mapping[v['output']])));shutil.copy2(mapping[old],new);mapping[old]=new
                for f in m['files']:
                    if Path(f['path']).suffix.lower()=='.json':
                        target=Path(mapping[f['path']])
                        try:target.write_text(json.dumps(rewrite(json.loads(target.read_text(encoding='utf-8')),mapping),ensure_ascii=False),encoding='utf-8')
                        except (ValueError,UnicodeError):pass
                restored=[];imports=[]
                with self.lock:
                    for t in m['tasks']:
                        if t['id'] in self.tasks:continue
                        t=rewrite(t,mapping);t['output_dir']=str(self.settings.output);t.pop('deleted_at',None);t.pop('task_root',None)
                        for r in t['rounds']:
                            r['paused']=True;r['stop_marker']=str(folder/(r['id']+'-STOP'))
                            if r.get('planning_status')=='running':r['planning_status']='queued'
                            for s in r['slots']:
                                if s['state']=='generating':
                                    if s.get('local_result_sha256') or s.get('ximalaya_review',{}).get('status') in ('pending','export_pending'):
                                        s['state']='queued';s.pop('resume',None)
                                    else:s.update(state='failed',reason_code='unknown',msg='从备份恢复，请先查询原任务')
                        for rr in t['rounds']:
                            for ss in rr['slots']:
                                for vv in [ss,*ss['versions']]:
                                    for ref in vv.get('refs',[]):
                                        if ref.get('asset_id') and Path(ref['path']).is_file():
                                            from .planning import ASSETS
                                            asset=next((a for a in ASSETS if a['asset_id']==ref['asset_id']),None)
                                            if asset:ref.update(original_asset_path=asset['path'],snapshot_sha256=digest(ref['path']))
                        t['revision']=t.get('revision',0)+1;t['updated_at']=time.time();imports.append(t);restored.append(t['id'])
                    docs_restored=0
                    try:
                        self.db.execute('BEGIN IMMEDIATE')
                        for t in imports:self.db.execute('INSERT INTO tasks VALUES(?,?,?)',(t['id'],json.dumps(t,ensure_ascii=False),None))
                        for row in m.get('quarantined',[]):
                            if row[0] not in self.tasks:self.db.execute('INSERT OR IGNORE INTO quarantined_tasks VALUES(?,?,?,?)',tuple(row))
                        for d in m['documents']:
                            value=rewrite(json.loads(d['body']),mapping)
                            if d['name'].startswith('learning-run:') and d['name'] not in existing_documents:
                                from .learning_runtime_support import prepare_restored_run
                                value=prepare_restored_run(self,value)
                            cursor=self.db.execute('INSERT OR IGNORE INTO documents VALUES(?,?)',(d['name'],json.dumps(value,ensure_ascii=False)));docs_restored+=cursor.rowcount
                        self.db.execute('INSERT OR IGNORE INTO documents VALUES(?,?)',('restored_backup:'+token,json.dumps({'files':[mapping[p] for p in m.get('standalone',[])],'at':time.time()})))
                        self.db.commit()
                    except Exception:self.db.rollback();raise
                    for t in imports:self.tasks[t['id']]=t
                    runtime=getattr(self,'learning_runtime',None)
                    if runtime:runtime.reload()
                return dict(restored=len(restored),documents_restored=docs_restored,skipped=len(m['tasks'])-len(restored),path=str(folder))
            except Exception:
                # Keep any files already indexed by a completed task import.
                if not any(str(folder) in json.dumps(t) for t in self.tasks.values()):shutil.rmtree(folder,ignore_errors=True)
                raise


def digest_stream(stream):
    h=hashlib.sha256()
    with stream:
        for data in iter(lambda:stream.read(1024*1024),b''):h.update(data)
    return h.hexdigest()
