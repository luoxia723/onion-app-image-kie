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
from . import ximalaya
import artifact_workspace

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def atomic(path,value):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)

def require_reviewed_versions(reviewed, expected):
    if (not expected or not isinstance(reviewed, dict) or reviewed.keys() != expected.keys()
            or any(type(reviewed[image_id]) is not int or reviewed[image_id] != version
                   for image_id, version in expected.items())):
        raise UserError('请选中整套成品的当前版本后再导出', 409)

class DeliveryMixin:
    def adopted(self,t,index,ready_only=False):
        if type(ready_only) is not bool: raise UserError('图包范围不正确')
        r=self.round(t,index);delivery=self.delivery_state(t,r)
        if not delivery['selected_sets']: raise UserError('请先选中至少一套图片')
        if delivery['incomplete_sets'] and not ready_only: raise UserError('已选套图中有 '+str(delivery['incomplete_sets'])+' 套尚未完整或规格未通过，可先只保存合格的套，或处理后保存全部')
        excluded=set(delivery['incomplete_keys']) if ready_only else set()
        sl=[s for s in r['slots'] if (key:=selection_key(ximalaya.selection_pid(r,s['pid']),s['set'])) not in excluded and r['sel'].get(key)]
        if not sl: raise UserError('暂无合格的已选套图，请先处理图片')
        if any(s.get('local_processing') for s in sl):raise UserError('所选成品正在更新，请稍后再保存图包',409)
        from .brand_logo import reviewed_image
        sl=[reviewed_image(s) for s in sl]
        sl.sort(key=lambda s:(s['pid'],s['set'],s['idx']))
        for s in sl:
            verify_delivery_file(s,self.placement(t,r,s))
        return sl,content_fingerprint(sl)


    def export_slots(self,t,index,ready_only=False,logo_asset_id=None):
        sl,source_fp=self.adopted(t,index,ready_only)
        fp=source_fp
        if logo_asset_id is not None:
            from .brand_logo import normalize_id,export_variant
            selected=normalize_id(logo_asset_id)
            with self.processing_slots:
                sl=[export_variant(s,self.placement(t,self.round(t,index),s),selected) for s in sl]
            fp=content_fingerprint(sl)
        return sl,fp,source_fp

    def package_preview(self,tid,index,ready_only=False,logo_asset_id=None):
        with self.lock:t=copy.deepcopy(self.task(tid))
        _,fp,_=self.export_slots(t,index,ready_only,logo_asset_id);old=self.valid_package(t,fp)
        return dict(next_version=None if old else f"v{max([p['v'] for p in t['pkgs']] or [0])+1:03d}",package_id=old['id'] if old else None)


    def package_work(self,tid,index,ready_only=False,logo_asset_id=None,suite_number=None,reviewed_versions=None):
        with self.lock:
            if self.maintenance_active:raise UserError('正在进行本机数据维护，请稍后保存')
            original=self.task(tid)
            t=copy.deepcopy(original)
            r=self.round(t,index)
            selected=ximalaya.placements(r['params'])
            only_ximalaya=ximalaya.only(r['params'])
            if reviewed_versions is not None and only_ximalaya and suite_number is None:
                raise UserError('请在对应套图中选中全部成品后导出',409)
            if suite_number is not None:
                if type(suite_number) is not int or not selected or ready_only or logo_asset_id is not None:
                    raise UserError('整套下载范围不正确')
                slots=[slot for slot in r['slots'] if slot['set']==suite_number and slot['pid'] in selected]
                if not ximalaya.complete(slots,r['simulation'],selected) or any(slot['state']!='done' or not slot.get('delivery_eligible',True) for slot in slots):
                    raise UserError('请先完成同套的所有已选尺寸',409)
                versions={slot['id']:slot['att'] for slot in slots}
                if reviewed_versions is not None:
                    require_reviewed_versions(reviewed_versions,versions)
                key=selection_key(selected[0],suite_number)
                r['sel']={key:True};r['adopted_versions']={key:versions}
                if only_ximalaya:
                    self.round(original,index).update(sel=copy.deepcopy(r['sel']),adopted_versions=copy.deepcopy(r['adopted_versions']))
            elif selected and not only_ximalaya:
                excluded=set(self.delivery_state(t,r)['incomplete_keys']) if ready_only else set()
                expected={}
                for slot in r['slots']:
                    key=selection_key(selected[0],slot['set'])
                    if slot['pid'] in selected and r['sel'].get(key) and key not in excluded:
                        expected[slot['id']]=slot['att']
                if expected or reviewed_versions:
                    require_reviewed_versions(reviewed_versions,expected)
            original["exporting"]=True;self.persist(original)
        sl,fp,source_fp=self.export_slots(t,index,ready_only,logo_asset_id)
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
            if s.get('ximalaya_source'):
                base=s['source_versions'][s['ximalaya_source']]
                records[-1]['ximalaya_base']=dict(image_id=s['ximalaya_source'],image_version=base['att'],sha256=base['sha256'])
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
        pkg=dict(id=uuid.uuid4().hex,v=int(v[1:]),zip=name,path=str(zpath),fingerprint=fp,fingerprint_schema=3 if layered else 2,created_at=time.time(),images=[{'id':s['id'],'att':s['att'],'pid':s['pid'],'sha256':s['sha256']} for s in sl])
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

    def package(self,tid,index,ready_only=False,logo_asset_id=None,suite_number=None,reviewed_versions=None):
        with self.lock:guard=self.package_locks.setdefault(tid,threading.Lock())
        with guard:
            try:return self.package_work(tid,index,ready_only,logo_asset_id,suite_number,reviewed_versions)
            finally:
                with self.lock:
                    t=self.tasks.get(tid)
                    if t and t.pop('exporting',None):self.persist(t)
