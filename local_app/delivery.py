"""Immutable export snapshots; file work never holds the scheduler lock."""
import copy
import hashlib
import json
import shutil
import threading
import time
from pathlib import Path
from types import SimpleNamespace
import uuid
import zipfile
from .config import UserError
from .planning import BY_ID
from .quality import verify_delivery_file,verify_saved_package
from .state import content_fingerprint, suite_key as selection_key
import artifact_workspace

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def atomic(path,value):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)

class DeliveryMixin:
    def adopted(self,t,index,ready_only=False):
        if type(ready_only) is not bool: raise UserError('图包范围不正确')
        r=self.round(t,index);delivery=self.delivery_state(t,r)
        if not delivery['selected_sets']: raise UserError('请先选中至少一套图片')
        if delivery['incomplete_sets'] and not ready_only: raise UserError('已选套图中有 '+str(delivery['incomplete_sets'])+' 套尚未完整或规格未通过，可先保存可交付套图，或处理后保存全部')
        excluded=set(delivery['incomplete_keys']) if ready_only else set()
        sl=[s for s in r['slots'] if r['sel'].get(selection_key(s['pid'],s['set'])) and selection_key(s['pid'],s['set']) not in excluded]
        if not sl: raise UserError('暂无可交付的已选套图，请先处理图片')
        sl.sort(key=lambda s:(s['pid'],s['set'],s['idx']))
        for s in sl:
            verify_delivery_file(s,self.placement(t,r,s))
        return sl,content_fingerprint(sl)


    def package_preview(self,tid,index,ready_only=False):
        with self.lock:t=copy.deepcopy(self.task(tid))
        sl,fp=self.adopted(t,index,ready_only);old=self.valid_package(t,fp)
        return dict(next_version=None if old else f"v{max([p['v'] for p in t['pkgs']] or [0])+1:03d}",package_id=old['id'] if old else None)


    def package_work(self,tid,index,ready_only=False):
        with self.lock:
            if self.maintenance_active:raise UserError('正在进行本机数据维护，请稍后保存')
            original=self.task(tid)
            t=copy.deepcopy(original)
            self.round(t,index)
            original["exporting"]=True;self.persist(original)
        sl,fp=self.adopted(t,index,ready_only)
        from .safety import require_space
        require_space(t['output_dir'],sum(Path(s['jpeg']).stat().st_size for s in sl)*2)
        excluded=self.delivery_state(t,self.round(t,index))['incomplete_keys'] if ready_only else []
        old=self.valid_package(t,fp)
        if old and Path(old['path']).is_file():
            t['downloaded']=not excluded;t['downloaded_at']=time.time();t['last_exported_package_id']=old['id'];self.commit_package(tid,t,None,index,fp,excluded)
            return old
        with self.workspace_lock:
            if not t.get('task_root'):
                result=artifact_workspace.create_task(SimpleNamespace(code='AIMG',title=t['direction'],business_line='APP',project_root=Path(t['output_dir'])))
                t['task_root']=result['task_root']; v='v001'
                # The original helper owns the task index and version directories.
            else: v=artifact_workspace.new_version(SimpleNamespace(task_root=Path(t['task_root'])))['version']
        vr=Path(t['task_root'])/v
        delivery=vr/'04_交付'
        records=[]
        for s in sl:
            p=self.placement(t,self.round(t,index),s)
            # Placement folders prevent collisions when a channel has several placements.
            rel=Path(p['platform'])/(p['name']+'_'+p['target_size'])/f"APP_{t['direction']}_APP图片_方案{s['set']:03d}_图{s['idx']:02d}_{v}.jpg"
            dest=delivery/rel
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(s['jpeg'],dest)
            records.append(dict(path=rel.as_posix(),bytes=dest.stat().st_size,sha256=digest(dest),placement_id=s['pid'],set=s['set'],image=s['idx'],image_version=s['att']))
        atomic(delivery/'交付清单.json',dict(version=v,task_name=t['pkg'],simulation=self.round(t,index)['simulation'],images=records,
            placement_rules=self.placement_rules(t,self.round(t,index)),export_scope='ready_selected' if excluded else 'all_selected',excluded_suites=excluded))
        name=f"APP_{t['direction']}_APP图片_交付包_{v}.zip"
        zpath=vr/'06_打包'/name
        tmp=zpath.with_suffix('.tmp')
        with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
            for file in delivery.rglob('*'):
                if file.is_file(): z.write(file,file.relative_to(delivery).as_posix())
        verify_saved_package(tmp,fp,self.placement_rules(t,self.round(t,index)))
        tmp.replace(zpath)
        pkg=dict(id=uuid.uuid4().hex,v=int(v[1:]),zip=name,path=str(zpath),fingerprint=fp,fingerprint_schema=2,created_at=time.time(),images=[{'id':s['id'],'att':s['att'],'pid':s['pid']} for s in sl])
        t['pkgs'].append(pkg);t['downloaded']=not excluded;t['downloaded_at']=time.time();t['last_exported_package_id']=pkg['id']
        self.commit_package(tid,t,pkg,index,fp,excluded)
        return pkg


    def valid_package(self,t,fingerprint):
        for pkg in reversed(t['pkgs']):
            if pkg['fingerprint']!=fingerprint: continue
            try: verify_saved_package(pkg['path'],fingerprint,self.package_rules(t,pkg))
            except UserError: continue
            return pkg
        return None


    def commit_package(self,tid,snapshot,pkg,index,fp,excluded):
        with self.lock:
            t=self.task(tid)
            if snapshot.get('task_root'):t['task_root']=snapshot['task_root']
            if pkg:t['pkgs'].append(pkg)
            t['last_exported_package_id']=snapshot.get('last_exported_package_id')
            t['downloaded_at']=time.time()
            delivery=self.delivery_state(t,self.round(t,index))
            t['downloaded']=t['ri']==index and not excluded and delivery['fingerprint']==fp
            self.persist(t)

    def package(self,tid,index,ready_only=False):
        with self.lock:guard=self.package_locks.setdefault(tid,threading.Lock())
        with guard:
            try:return self.package_work(tid,index,ready_only)
            finally:
                with self.lock:
                    t=self.tasks.get(tid)
                    if t:t.pop('exporting',None);self.persist(t)
