"""Lightweight list views, prompt drafts and historical image metadata."""
import copy
import time
from pathlib import Path
from .config import ROOT,UserError,DEFAULT_IMAGE_MODEL

class WorkbenchMixin:
    def task_summary(self,t):
        cached=self.summary_cache.get(t['id'])
        if cached and cached['revision']==t.get('revision',0):return cached
        r=t['rounds'][t['ri']];d=self.delivery_state(t,r)
        active=any(s['state']=='generating' or s.get('local_processing') or s['state']=='queued' and not rr.get('paused') and not rr.get('stopped') for rr in t['rounds'] for s in rr['slots']) or any(rr.get('planning_status')=='running' or rr.get('planning_status')=='queued' and not rr.get('paused') and not rr.get('stopped') for rr in t['rounds'])
        active=active or t.get('exporting',False)
        done=sum(s['state']=='done' for s in r['slots']);paused=r.get('paused',False)
        errors=sum(s['state'] in ('failed','blocked_first_failed') or s.get('delivery_eligible') is False for s in r['slots'])
        status='正在保存图包' if t.get('exporting') else '正在处理' if active else '已暂停后续' if paused else '需要处理' if errors else '已保存 '+d['last_version'] if d['last_version'] and not d['has_changes'] else '已停止后续' if r.get('stopped') else '待挑选'
        category='running' if active else 'history' if t.get('archived') or d['last_version'] and not d['has_changes'] and not errors else 'attention'
        image=next((s for s in reversed(r['slots']) if s['state']=='done'),None)
        value=dict(is_summary=True,id=t['id'],name=t.get('name') or t['direction'],pkg=t['pkg'],date=t['date'],updated_at=t.get('updated_at',t['date']/1000),revision=t.get('revision',0),
                   active=active or t.get('exporting',False),paused=paused,archived=t.get('archived',False),category=category,status=status,done=done,total=len(r['slots']),round_count=len(t['rounds']),
                   image_form=r['params'].get('image_form'),image_model=r.get('image_model',DEFAULT_IMAGE_MODEL),last_version=d['last_version'],has_changes=d['has_changes'],
                   thumbnail_url=f"/api/tasks/{t['id']}/images/{image['id']}?v={image['att']}" if image else None)
        self.summary_cache[t['id']]=value
        return value

    def list_summaries(self,q='',cursor=0,limit=50):
        with self.lock:
            tasks=[t for t in self.tasks.values() if not t.get('deleted_at')]
            if q:tasks=[t for t in tasks if q.lower() in (t.get('name','')+str([r['params'] for r in t['rounds']])).lower()]
            tasks.sort(key=lambda t:-t.get('updated_at',t['date']/1000))
            page=tasks[cursor:cursor+limit]
            return dict(tasks=[self.task_summary(t) for t in page],next_cursor=str(cursor+limit) if len(tasks)>cursor+limit else None,queue=self.queue_status())

    def view_task(self,tid,index=None,revision=None):
        with self.lock:
            t=self.task(tid);index=t['ri'] if index is None else index;self.round(t,index)
            if revision is not None and revision==t.get('revision',0):return dict(unchanged=True,id=tid,revision=revision)
            r=t['rounds'][index]
            self.task_summary(t)
            value=self.public({**t,'ri':0,'rounds':[r]})
            headers=[]
            for old in t['rounds']:
                headers.append(dict(id=old['id'],params=old['params'],slots=[],created_at=old.get('created_at'),image_model=old.get('image_model',DEFAULT_IMAGE_MODEL),planning_status=old.get('planning_status'),stopped=old.get('stopped'),paused=old.get('paused',False)))
            detail=value['rounds'][0]
            for s in detail['slots']:
                s.pop('prompt',None);s.pop('orig',None)
            headers[index]=detail;value.update(rounds=headers,ri=index,loaded_round=index,revision=t.get('revision',0),summary=self.task_summary(t))
            value['background_running']=sum(s['state']=='generating' for i,rr in enumerate(t['rounds']) if i!=index for s in rr['slots'])
            return value

    def image_details(self,tid,sid,att=None,editor=''):
        with self.lock:
            t=self.task(tid);r,s=self.find_image(t,sid);version=s if att is None or att==s['att'] else next((x for x in s['versions'] if x['att']==att),None)
            if not version:raise UserError('图片版本不存在',404)
            result=copy.deepcopy(version);result.pop('versions',None)
            for key in ('id','pid','set','idx','first_id'):result[key]=s[key]
            for key in ('production_mode','template_id','parent_id','dependency_ids'):
                if key in s:result[key]=copy.deepcopy(s[key])
            if version is s:
                result['query_required']=self.query_required(s)
                if self.definitely_unsent(s):result.update(reason_code='not_submitted',msg='生图请求未发出，可重试本张')
            result['preview_kind']='raw' if version.get('delivery_eligible') is False else 'processed'
            result['reference_images']=[dict(name=x.get('role','参考图'),label=x['label'],thumbnail_url=f"/api/tasks/{tid}/references/{sid}/{i}?v={version['att']}") for i,x in enumerate(version['refs'])]
            from font_library import disabled_names
            for ref,view in zip(version['refs'],result['reference_images']):view['retired']=Path(ref['path']).name in disabled_names()
            result['original_image_url']=f"/api/tasks/{tid}/images/{sid}?v={version['att']}&raw=1" if version['state']=='done' and not version.get('files_cleared') else None
            result['image_url']=f"/api/tasks/{tid}/images/{sid}?v={version['att']}" if version.get('jpeg') and version['state']=='done' and not version.get('files_cleared') else None
            result['history']=[dict(att=x['att'],state=x['state'],image_url=f"/api/tasks/{tid}/images/{sid}?v={x['att']}" if x.get('jpeg') and x['state']=='done' and not x.get('files_cleared') and Path(x['jpeg']).is_file() else None,files_cleared=x.get('files_cleared',False),pinned=x.get('pinned',False),reason=x.get('version_reason','图片版本')) for x in [*s['versions'],s]]
            result['round_index']=t['rounds'].index(r)
            result['is_historical']=version['att']!=s['att']
            result['generation_disabled']=bool(r.get('generation_disabled') or any(row.get('frame') for row in r['slots']))
            from .brand_logo import switchable
            result['logo_switchable']=switchable(version)
            if version.get('brand_logo_layer'):
                from .brand_logo import prompt_rule
                result['logo_fixed_rule']=prompt_rule(version['brand_logo_layer'])
            if version.get('natural_canvas_plan'):
                from .natural_canvas import prompt_rule as canvas_rule
                result['canvas_fixed_rule']=canvas_rule(version['natural_canvas_plan'])
            result['edit_draft']=self.get_prompt_draft(tid,sid,version['att'],editor)
            result['edit_drafts']=[v for v in self.prompt_drafts(tid,sid,version['att']) if not v.get('discarded')]
            for key in ('output','jpeg','refs','frame','frame_status','frame_processing','job_path','brand_logo_layer','logo_base','natural_canvas_plan'):result.pop(key,None)
            return result

    def find_image(self,t,sid):
        for r in t['rounds']:
            for s in r['slots']:
                if s['id']==sid:return r,s
        raise UserError('图片不存在',404)

    def prompt_drafts(self,tid,sid,att):
        import json
        prefix=f'prompt:{tid}:{sid}:{att}:'
        return sorted([v for (name,) in self.db.execute("SELECT name FROM documents WHERE name LIKE ?",(prefix+'%',)).fetchall() for v in [self.document(name)] if v],key=lambda v:v['updated_at'])

    def get_prompt_draft(self,tid,sid,att,editor=''):
        values=self.prompt_drafts(tid,sid,att)
        own=next((v for v in values if v['editor_id']==editor),None)
        value=own or max(values,key=lambda v:v['updated_at'],default=None)
        return None if value and value.get('discarded') else value

    def save_prompt_draft(self,tid,sid,data,discard=False):
        with self.lock:
            t=self.task(tid,deleted=True);_,s=self.find_image(t,sid);att=data.get('att',s['att']);editor=data.get('editor_id','')
            if not isinstance(editor,str) or not 8<=len(editor)<=100:raise UserError('编辑标识不正确')
            if att!=s['att'] and not any(v['att']==att for v in s['versions']):raise UserError('图片版本不存在',404)
            text=data.get('text','')
            if not isinstance(text,str) or len(text)>30000:raise UserError('提示词草稿最多30000字')
            key=f'prompt:{tid}:{sid}:{att}:{editor}';old=self.document(key)
            sequence=data.get('sequence',0)
            if type(sequence) is not int:raise UserError('草稿保存顺序不正确')
            if old and sequence<=old.get('sequence',-1):return old
            value=dict(text=text,att=att,editor_id=editor,sequence=sequence,updated_at=time.time(),discarded=discard)
            self.put_document(key,value);return value

    def cleanup_candidates(self):
        import re
        protected=set()
        folder=self.settings.state_dir/'uploads';now=time.time()
        for draft in self.list_drafts():
            for p in [draft['draft'],*draft.get('form_drafts',{}).values()]:
                protected.update(str(Path(r.get('path','')).resolve()) for r in p.get('references',[]))
                concept=p.get('concept')
                if isinstance(concept,dict) and isinstance(concept.get('id'),str) and re.fullmatch('[a-f0-9]{64}',concept['id']):
                    protected.update(str((folder/(concept['id']+suffix)).resolve()) for suffix in ('.png','.jpg','.webp'))
        for t in self.tasks.values():
            for r in t['rounds']:
                for s in r['slots']:
                    for v in [s,*s.get('versions',[])]:
                        protected.update(str((Path(ref['path']) if Path(ref['path']).is_absolute() else ROOT/ref['path']).resolve()) for ref in v.get('refs',[]))
        restore_root=(self.settings.output/'.restored').resolve()
        def protect_paths(value):
            if isinstance(value,dict):
                for x in value.values():protect_paths(x)
            elif isinstance(value,list):
                for x in value:protect_paths(x)
            elif isinstance(value,str) and value.startswith(str(restore_root)):
                protected.add(str(Path(value).resolve()))
        for t in self.tasks.values():protect_paths(t)
        for (name,) in self.db.execute('SELECT name FROM documents').fetchall():protect_paths(self.document(name))
        candidates=list(folder.iterdir()) if folder.exists() else []
        if restore_root.exists():candidates.extend(restore_root.rglob('*'))
        work=self.settings.output/'工作区'/'产物'
        if work.exists():candidates.extend(work.glob('**/06_打包/*.tmp'))
        return [p for p in candidates if p.is_file() and p.suffix not in ('.lock','.guard') and str(p.resolve()) not in protected and now-p.stat().st_mtime>86400]


    def cleanup_preview(self):
        with self.lock:
            files=self.cleanup_candidates()
            return dict(bytes=sum(p.stat().st_size for p in files),files=len(files),message='仅清理未被任务或草稿引用的过期暂存文件；历史记录、原图和交付包保留。')
