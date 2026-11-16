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
        if delivery['incomplete_sets'] and not ready_only: raise UserError('已选套图中有 '+str(delivery['incomplete_sets'])+' 套尚未完整或规格未通过，可先只保存合格的套，或处理后保存全部')
        excluded=set(delivery['incomplete_keys']) if ready_only else set()
        sl=[s for s in r['slots'] if r['sel'].get(selection_key(s['pid'],s['set'])) and selection_key(s['pid'],s['set']) not in excluded]
        if not sl: raise UserError('暂无合格的已选套图，请先处理图片')
        sl.sort(key=lambda s:(s['pid'],s['set'],s['idx']))
        for s in sl:
            verify_delivery_file(s,self.placement(t,r,s))
        return sl,content_fingerprint(sl)


    def export_slots(self,t,index,ready_only=False,logo_asset_id=None):
        sl,fp=self.adopted(t,index,ready_only)
        if logo_asset_id is not None:
            from .brand_logo import normalize_id,export_variant
            selected=normalize_id(logo_asset_id)
            with self.processing_slots:
                sl=[export_variant(s,self.placement(t,self.round(t,index),s),selected) for s in sl]
            fp=content_fingerprint(sl)
        return sl,fp

    def package_preview(self,tid,index,ready_only=False,logo_asset_id=None):
        with self.lock:t=copy.deepcopy(self.task(tid))
        sl,fp=self.export_slots(t,index,ready_only,logo_asset_id);old=self.valid_package(t,fp)
        return dict(next_version=None if old else f"v{max([p['v'] for p in t['pkgs']] or [0])+1:03d}",package_id=old['id'] if old else None)


    def package_work(self,tid,index,ready_only=False,logo_asset_id=None):
        with self.lock:
            if self.maintenance_active:raise UserError('正在进行本机数据维护，请稍后保存')
            original=self.task(tid)
            t=copy.deepcopy(original)
            self.round(t,index)
            original["exporting"]=True;self.persist(original)
        _,source_fp=self.adopted(t,index,ready_only)
        sl,fp=self.export_slots(t,index,ready_only,logo_asset_id)
        layered=any('delivery_logo_asset_id' in s for s in sl)
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
            else: v=artifact_workspace.new_version(SimpleNamespace(task_root=Path(t['task_root']),minimum_version=max([p['v'] for p in t['pkgs']] or [0])+1))['version']
            if int(v[1:])<=max([p['v'] for p in t['pkgs']] or [0]):
                v=artifact_workspace.new_version(SimpleNamespace(task_root=Path(t['task_root']),minimum_version=max(p['v'] for p in t['pkgs'])+1))['version']
        vr=Path(t['task_root'])/v
        delivery=vr/'04_交付'
        records=[]
        for s in sl:
            p=self.placement(t,self.round(t,index),s)
            # Placement folders prevent collisions when a channel has several placements.
            extension='png' if p.get('output_format')=='PNG' else 'jpg'
            rel=Path(p['platform'])/(p['name']+'_'+p['target_size'])/f"APP_{t['direction']}_APP图片_方案{s['set']:03d}_图{s['idx']:02d}_{v}.{extension}"
            dest=delivery/rel
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(s['jpeg'],dest)
            records.append(dict(path=rel.as_posix(),bytes=dest.stat().st_size,sha256=digest(dest),placement_id=s['pid'],set=s['set'],image=s['idx'],image_version=s['att']))
            if 'delivery_logo_asset_id' in s:records[-1]['logo_asset_id']=s['delivery_logo_asset_id']
            if s.get('brand_logo_layer'):
                layer=s['brand_logo_layer'];chosen=layer['assets'].get(s.get('delivery_logo_asset_id'),{})
                records[-1]['logo_layer']=dict(applied=bool(s.get('delivery_logo_asset_id')),
                    asset_sha256=chosen.get('sha256'),unbranded_base_sha256=(s.get('logo_base') or {}).get('sha256'),
                    template=copy.deepcopy(layer['template']))
            if s.get('production_mode'):
                records[-1].update(production_mode=s['production_mode'],sources={sid:{'image_version':v['att'],'sha256':v['sha256']} for sid,v in s.get('source_versions',{}).items()})
        atomic(delivery/'交付清单.json',dict(version=v,task_name=t['pkg'],simulation=self.round(t,index)['simulation'],images=records,fingerprint_schema=3 if layered else 2,
            placement_rules=self.placement_rules(t,self.round(t,index)),export_scope='ready_selected' if excluded else 'all_selected',excluded_suites=excluded))
        name=f"APP_{t['direction']}_APP图片_交付包_{v}.zip"
        zpath=vr/'06_打包'/name
        tmp=zpath.with_suffix('.tmp')
        with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
            for file in delivery.rglob('*'):
                if file.is_file(): z.write(file,file.relative_to(delivery).as_posix())
        verify_saved_package(tmp,fp,self.placement_rules(t,self.round(t,index)))
        tmp.replace(zpath)
        pkg=dict(id=uuid.uuid4().hex,v=int(v[1:]),zip=name,path=str(zpath),fingerprint=fp,fingerprint_schema=3 if layered else 2,created_at=time.time(),images=[{'id':s['id'],'att':s['att'],'pid':s['pid']} for s in sl])
        if layered:pkg['source_fingerprint']=source_fp
        if logo_asset_id is not None:
            from .brand_logo import normalize_id
            pkg['logo_asset_id']=normalize_id(logo_asset_id)
        t['pkgs'].append(pkg);t['downloaded']=not excluded;t['downloaded_at']=time.time();t['last_exported_package_id']=pkg['id']
        self.commit_package(tid,t,pkg,index,fp,excluded)
        return pkg


    def valid_package(self,t,fingerprint):
        for pkg in reversed(t['pkgs']):
            if pkg['fingerprint']!=fingerprint: continue
            try: verify_saved_package(pkg['path'],fingerprint,self.package_rules(t,pkg))
            except UserError:
                self.invalidate_package(t['id'],pkg['id'])
                continue
            return pkg
        return None


    def invalidate_package(self,tid,pid):
        with self.lock:
            t=self.tasks.get(tid)
            pkg=next((p for p in t['pkgs'] if p['id']==pid),None) if t else None
            if pkg and not pkg.get('invalid'):
                pkg['invalid']=True
                self.persist(t)

    def commit_package(self,tid,snapshot,pkg,index,fp,excluded):
        with self.lock:
            t=self.task(tid)
            if snapshot.get('task_root'):t['task_root']=snapshot['task_root']
            if pkg:t['pkgs'].append(pkg)
            t['last_exported_package_id']=snapshot.get('last_exported_package_id')
            t['downloaded_at']=time.time()
            delivery=self.delivery_state(t,self.round(t,index))
            exported=next((p for p in snapshot['pkgs'] if p['id']==snapshot.get('last_exported_package_id')),None)
            source_fp=(exported or {}).get('source_fingerprint',fp)
            t['downloaded']=t['ri']==index and not excluded and delivery['fingerprint']==source_fp
            self.persist(t)

    def package(self,tid,index,ready_only=False,logo_asset_id=None):
        with self.lock:guard=self.package_locks.setdefault(tid,threading.Lock())
        with guard:
            try:return self.package_work(tid,index,ready_only,logo_asset_id)
            finally:
                with self.lock:
                    t=self.tasks.get(tid)
                    if t:t.pop('exporting',None);self.persist(t)
