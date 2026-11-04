"""Persistent drafts/product facts and independent delivery summaries."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import time
import tempfile
from .config import UserError


def suite_key(pid,n): return str(pid)+'::'+str(n)

def content_fingerprint(images):
    values=sorted((s['pid'],s['set'],s['idx'],s['sha256']) for s in images)
    return hashlib.sha256(json.dumps(values,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

class StateMixin:
    def document(self,name,default=None):
        with self.lock:
            row=self.db.execute('SELECT body FROM documents WHERE name=?',(name,)).fetchone()
            if row:
                try:
                    value=json.loads(row[0])
                    if not isinstance(value,dict):raise ValueError()
                    if name.startswith('draft:') and (not isinstance(value.get('draft'),dict) or not isinstance(value.get('updated_at'),(int,float))):raise ValueError()
                    if name.startswith('draft:') and not isinstance(value.get('form_drafts',{}),dict):raise ValueError()
                    if name=='product' and (not isinstance(value.get('text'),str) or type(value.get('revision')) is not int):raise ValueError()
                    if name.startswith('prompt:') and (not isinstance(value.get('text'),str) or not isinstance(value.get('editor_id'),str) or not isinstance(value.get('updated_at'),(int,float))):raise ValueError()
                    return value
                except (ValueError,TypeError):
                    self.db.execute('INSERT OR REPLACE INTO quarantined_tasks VALUES(?,?,?,?)',('document:'+name,row[0],'草稿或配置记录异常，原文已隔离保留',time.time()))
                    self.db.execute('DELETE FROM documents WHERE name=?',(name,));self.db.commit()
            return default if default is not None else {}

    def put_document(self,name,value):
        self.db.execute('INSERT INTO documents VALUES(?,?) ON CONFLICT(name) DO UPDATE SET body=excluded.body',(name,json.dumps(value,ensure_ascii=False)))
        self.db.commit()

    def product(self):
        with self.lock: return self.document('product',{'text':'','revision':0})

    def save_product(self,text):
        if not isinstance(text,str) or len(text)>20000: raise UserError('产品资料限 20000 字，请填写已确认的产品信息')
        with self.lock:
            old=self.product()
            value={'text':text.strip(),'revision':old['revision']+(old['text']!=text.strip()),'updated_at':time.time()}
            self.put_document('product',value)
            return value

    def save_settings(self,data):
        """Commit the settings dialog as one operation, rolling back both stores on failure."""
        with self.lock:
            if self.maintenance_active:raise UserError('正在进行本机数据维护，请稍后修改设置')
            old=self.product()
            if 'product_text' not in data:return self.settings.update(data)
            text=data['product_text']
            if not isinstance(text,str) or len(text)>20000:raise UserError('产品资料限 20000 字')
            if type(data.get('product_revision')) is not int or data['product_revision']!=old['revision']:
                raise UserError('另一窗口已更新产品资料，当前修改尚未保存；请保留输入并重新打开设置',409)
            product=dict(text=text.strip(),revision=old['revision']+(old['text']!=text.strip()),updated_at=time.time())
            env=self.settings.env_file;before=env.read_bytes() if env.exists() else None
            settings_before=self.settings.__dict__.copy()
            try:
                self.db.execute('BEGIN IMMEDIATE')
                self.db.execute('INSERT INTO documents VALUES(?,?) ON CONFLICT(name) DO UPDATE SET body=excluded.body',('product',json.dumps(product,ensure_ascii=False)))
                result=self.settings.update(data)
                self.db.commit()
            except Exception:
                self.db.rollback()
                if before is None:env.unlink(missing_ok=True)
                elif not env.exists() or env.read_bytes()!=before:
                    fd,tmp=tempfile.mkstemp(dir=env.parent,prefix='.env-rollback-')
                    try:
                        with os.fdopen(fd,'wb') as f:f.write(before)
                        os.replace(tmp,env)
                    finally:Path(tmp).unlink(missing_ok=True)
                self.settings.__dict__.update(settings_before)
                raise
            return {**result,'product':product}

    def freeze_product(self,pr,previous=None):
        value=dict(pr)
        if 'product_facts' not in value or 'facts_version' not in value:
            frozen=previous if previous and 'product_facts' in previous and 'facts_version' in previous else None
            product=self.product() if frozen is None else None
            value['product_facts']=frozen['product_facts'] if frozen is not None else product['text']
            value['facts_version']=frozen['facts_version'] if frozen is not None else product['revision']
        return value

    def get_draft(self,did):
        with self.lock:
            value=self.document('draft:'+did)
            if not value:
                closed=self.document('closed-draft:'+did)
                if closed.get('task_id'): return {'submitted_task_id':closed['task_id']}
                raise UserError('草稿不存在',404)
            return value

    def save_draft(self,did,data):
        if not re.fullmatch('[a-f0-9]{32}',did): raise UserError('草稿标识不正确')
        draft=data.get('draft');forms=data.get('form_drafts',{})
        if not isinstance(draft,dict) or not isinstance(forms,dict) or len(json.dumps(data,ensure_ascii=False))>100000:
            raise UserError('草稿内容不正确或过长')
        allowed={'image_form','pids','t1','t2','s1','s2','s3','cta','sets','ip','style','font','noLogo','references','feature_note','direction',
                 'product_facts','facts_version','variants_by_placement','image_model'}
        def clean(value): return {k:v for k,v in value.items() if k in allowed}
        with self.lock:
            if self.document('closed-draft:'+did): raise UserError('草稿已提交或删除，请新建草稿',409)
            old=self.document('draft:'+did,{'revision':0})
            editor=str(data.get('editor_id',''))[:80];sequence=data.get('sequence',0)
            if type(sequence) is not int: raise UserError('草稿保存顺序不正确')
            if editor and editor==old.get('editor_id') and sequence<=old.get('sequence',-1): return old
            if data.get('revision',0)!=old['revision'] and editor!=old.get('editor_id'):
                raise UserError('另一窗口已更新此草稿，请重新打开后继续',409)
            value=dict(id=did,draft=self.freeze_product(clean(draft),old.get('draft')),form_drafts={k:self.freeze_product(clean(v),old.get('form_drafts',{}).get(k)) for k,v in forms.items() if k in ('单图','双图','三图') and isinstance(v,dict)},
                editing_task_id=data.get('editing_task_id'),editing_round=data.get('editing_round'),
                revision=old['revision']+1,editor_id=editor,sequence=sequence,updated_at=time.time())
            self.put_document('draft:'+did,value)
            return value

    def list_drafts(self):
        with self.lock:
            values=[value for (name,) in self.db.execute("SELECT name FROM documents WHERE name LIKE 'draft:%'").fetchall() for value in [self.document(name)] if value]
            for value in values:
                pr=value['draft'];form=pr.get('image_form','单图')
                value['name']=(pr.get('t1','') if form=='单图' else pr.get('s1',''))[:16] or '未命名草稿'
            return sorted(values,key=lambda x:-x['updated_at'])

    def draft_summaries(self,q=''):
        values=self.list_drafts()
        if q:values=[v for v in values if q.lower() in json.dumps(v['draft'],ensure_ascii=False).lower()]
        return [{k:v.get(k) for k in ('id','name','updated_at','editing_task_id','editing_round')}|{'draft':{'image_form':v['draft'].get('image_form','单图')}} for v in values]

    def delete_draft(self,did,task_id=None):
        with self.lock:
            self.put_document('closed-draft:'+did,{'closed_at':time.time(),'task_id':task_id})
            self.db.execute('DELETE FROM documents WHERE name=?',('draft:'+did,));self.db.commit()
            return {'ok':True}

    def delivery_state(self,t,r):
        groups={}
        for s in r['slots']: groups.setdefault(suite_key(s['pid'],s['set']),[]).append(s)
        selected=[(k,groups.get(k,[])) for k,chosen in r['sel'].items() if chosen]
        ready=[];incomplete=[]
        for key,sl in selected:
            expected=r['adopted_versions'].get(key,{})
            count=self.placement(t,r,sl[0])['image_count'] if sl else 0
            complete=bool(sl) and len(sl)==count and sorted(s['idx'] for s in sl)==list(range(1,count+1))
            valid=complete and all(s['state']=='done' and expected.get(s['id'])==s['att'] and s.get('delivery_eligible',True)
                      and s.get('jpeg') and Path(s['jpeg']).is_file() for s in sl)
            (ready if valid else incomplete).append((key,sl))
        images=[s for _,sl in ready for s in sl]
        ready_fp=content_fingerprint(images) if images else None
        fp=ready_fp if selected and not incomplete else None
        history=next((p for p in t['pkgs'] if p['id']==t.get('last_exported_package_id')),None)
        if history is None and t['pkgs']: history=t['pkgs'][-1]
        matching=next((p for p in t['pkgs'] if p['fingerprint']==fp),None) if fp else None
        ready_matching=next((p for p in t['pkgs'] if p['fingerprint']==ready_fp),None) if ready_fp else None
        coverage={sl[0]['pid'] for _,sl in ready}
        return dict(selected_sets=len(selected),ready_sets=len(ready),incomplete_sets=len(incomplete),
            ready_images=len(images),can_export=bool(selected) and not incomplete,
            can_export_ready=bool(ready),
            ready_matching_version=f"v{ready_matching['v']:03d}" if ready_matching else None,
            ready_next_version=f"v{max([p['v'] for p in t['pkgs']] or [0])+1:03d}" if ready_fp and not ready_matching else None,
            covered_placements=len(coverage),total_placements=len(r['params']['pids']),
            incomplete_keys=[k for k,_ in incomplete],fingerprint=fp,
            last_version=f"v{history['v']:03d}" if history else None,
            matching_version=f"v{matching['v']:03d}" if matching else None,
            next_version=f"v{max([p['v'] for p in t['pkgs']] or [0])+1:03d}" if fp and not matching else None,
            has_changes=bool(history) and fp!=history['fingerprint'],
            missing_placements=[{'placement_id':pid,'name':self.placement(t,r,{'pid':pid})['platform']+' '+self.placement(t,r,{'pid':pid})['name']} for pid in r['params']['pids'] if pid not in coverage])
