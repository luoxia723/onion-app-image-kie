"""Read-only, paginated presentation of existing tasks, runs and delivery records.

The workspace never creates a second execution/selection state. All actions
continue through the registered source task or run endpoints.
"""
from __future__ import annotations

import base64
import copy
from collections import OrderedDict
import math
import hashlib
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import quote
import zipfile

from PIL import Image

from .config import UserError
from .quality import verify_saved_package


def _query(q, kind, state, cursor, limit):
    if not isinstance(q,str) or len(q)>200:raise UserError('搜索内容最多200字')
    if kind not in ('','ordinary','learning','shared'):raise UserError('制作类型不正确')
    if state not in ('','draft','running','attention','ready','completed'):raise UserError('任务状态不正确')
    if type(limit) is not int or not 1<=limit<=100:raise UserError('分页数量不正确')
    signature=hashlib.sha256(json.dumps([q,kind,state],ensure_ascii=False).encode()).hexdigest()[:16]
    after=None
    if cursor:
        try:
            if not isinstance(cursor,str) or len(cursor)>512:raise ValueError()
            saved=json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
            if saved['query']!=signature or type(saved['at']) not in (int,float) or not math.isfinite(saved['at']) or not isinstance(saved['key'],str):raise ValueError()
            after=(-saved['at'],saved['key'])
        except (ValueError,TypeError,KeyError,UnicodeError):raise UserError('分页已失效，请刷新列表') from None
    return q.casefold(),signature,after


def _page(rows,q,kind,state,cursor,limit):
    search,signature,after=_query(q,kind,state,cursor,limit)
    rows=[r for r in rows if (not kind or r['type']==kind) and (not search or search in r['_search'].casefold())]
    counts={name:sum(r.get('status')==name for r in rows) for name in ('draft','running','attention','ready','completed')}
    counts['all']=len(rows)
    selected=[r for r in rows if not state or r.get('status')==state]
    selected.sort(key=lambda r:(-r['updated_at'],r['key']))
    total=len(selected)
    if after is not None:selected=[r for r in selected if (-r['updated_at'],r['key'])>after]
    page=selected[:limit];next_cursor=None
    if len(selected)>limit:
        last=page[-1]
        next_cursor=base64.urlsafe_b64encode(json.dumps({'query':signature,'at':last['updated_at'],'key':last['key']}).encode()).decode()
    return dict(items=[{k:v for k,v in row.items() if not k.startswith('_')} for row in page],
                next_cursor=next_cursor,total=total,counts=counts)


def items(engine,runtime,*,q='',kind='',state='',cursor='',limit=20):
    rows=[]
    with engine.lock:
        for task in engine.tasks.values():
            if task.get('deleted_at'):continue
            summary=engine.task_summary(task);round=task['rounds'][task['ri']];params=round['params']
            status=('running' if summary['active'] else 'attention' if summary['paused'] or summary['status'] in ('需要处理','已停止后续')
                    else 'completed' if summary['last_version'] and not summary['has_changes'] else 'ready')
            type='learning' if params.get('channel')=='学习机' else 'ordinary'
            rows.append(dict(key='task:'+task['id'],id=task['id'],source_type='task',type=type,
                name=summary['name'],channel=params.get('channel') or '多渠道',image_form=summary['image_form'],
                status=status,status_label=summary['status'],done=summary['done'],total=summary['total'],
                updated_at=summary['updated_at'],thumbnail_url=summary['thumbnail_url'],active=summary['active'],
                _search=summary['name']+json.dumps([r['params'] for r in task['rounds']],ensure_ascii=False)))
        for draft in engine.list_drafts():
            params=draft['draft'];type='learning' if params.get('channel')=='学习机' else 'ordinary'
            rows.append(dict(key='draft:'+draft['id'],id=draft['id'],source_type='draft',type=type,name=draft['name'],
                channel=params.get('channel') or '待选择渠道',image_form=params.get('image_form','单图'),
                status='draft',status_label='草稿',done=0,total=0,updated_at=draft['updated_at'],thumbnail_url=None,active=False,
                _search=draft['name']+json.dumps(params,ensure_ascii=False)))
        for run in runtime.runs.values():
            outputs=run.get('outputs',[]);baseline=run.get('baseline',{});suite=run.get('suite',{})
            done=sum(o.get('status')=='done' for o in outputs);shared=run.get('kind')=='shared_canvas_adaptation'
            unknown=any(o.get('query_required') for o in [baseline,*run.get('masters',[]),*outputs])
            failed=run.get('status') in ('failed','interrupted') or any(o.get('status') in ('failed','interrupted','blocked') for o in outputs)
            status='running' if run.get('busy') else 'attention' if unknown or failed else 'completed' if outputs and done==len(outputs) else 'ready'
            label=('制作中' if run.get('busy') else '待恢复查询' if unknown else '需要处理' if failed else '已完成' if status=='completed'
                   else '待生成共用母版' if shared else '待确认基准图' if baseline.get('status')=='done' and not (run.get('approval') or {}).get('confirmed')
                   else '待扩展整套' if (run.get('approval') or {}).get('confirmed') else '待生成基准图')
            image=next((o for o in outputs if o.get('status')=='done'),None)
            thumb=('/api/learning-machine/runs/'+run['id']+'/images/output/'+quote(image['id'],safe='')+'?version='+str(image['version']) if image else
                   '/api/learning-machine/runs/'+run['id']+'/images/baseline/baseline?version='+str(baseline.get('version',1)) if baseline.get('status')=='done' else None)
            rows.append(dict(key='run:'+run['id'],id=run['id'],source_type='run',type='shared' if shared else 'learning',name=run['name'],
                channel='多尺寸适配' if shared else '学习机',image_form='单图',status=status,status_label=label,done=done,total=len(outputs),
                updated_at=run.get('updated_at',run.get('created_at',0)),thumbnail_url=thumb,active=bool(run.get('busy')),mode=run['mode'],
                _search=run['name']+json.dumps(run.get('params',{}),ensure_ascii=False)))
    result=_page(rows,q,kind,state,cursor,limit);result['queue']=engine.queue_status();return result


def _task_package_format(engine,task,package):
    rules=engine.package_rules(task,package)
    selected={im['pid'] for im in package['images']}
    formats={str(rules[pid].get('output_format') or 'JPEG').upper() for pid in selected}
    formats={'JPEG' if f in ('JPG','JPEG') else f for f in formats}
    return next(iter(formats)) if len(formats)==1 else '混合'


def packages(engine,runtime,*,q='',kind='',cursor='',limit=20):
    rows=[]
    with engine.lock:
        sources=[('task',t) for t in engine.tasks.values() if not t.get('deleted_at')]+[('run',r) for r in runtime.runs.values()]
        for source,obj in sources:
            type='ordinary' if source=='task' else 'shared' if obj.get('kind')=='shared_canvas_adaptation' else 'learning'
            for package in obj.get('pkgs' if source=='task' else 'packages',[]):
                pid=package['id'];version=package['v' if source=='task' else 'version'];type=('learning' if any(engine.find_image(obj,im['id'])[0]['params'].get('channel')=='学习机' for im in package['images']) else 'ordinary') if source=='task' else type;name=obj.get('name') or obj.get('direction','未命名任务')
                rows.append(dict(key=f'{source}:{obj["id"]}:{pid}',id=pid,source_type=source,source_id=obj['id'],type=type,name=name,
                    version=version,image_count=len(package.get('images',[])) if source=='task' else package['image_count'],
                    format=_task_package_format(engine,obj,package) if source=='task' else 'JPEG' if obj.get('target_kind')=='ordinary' else 'PNG',logo_asset_id=package.get('logo_asset_id'),
                    updated_at=package['created_at'],download_url=f'/api/tasks/{obj["id"]}/packages/{pid}' if source=='task' else f'/api/learning-machine/runs/{obj["id"]}/packages/{pid}',
                    _search=name+' '+str(version)+' '+str(package.get('zip',''))))
    return _page(rows,q,kind,'',cursor,limit)


def _archive(engine,runtime,source,source_id,package_id):
    with engine.lock:
        if source=='task':
            obj=engine.task(source_id);package=next((p for p in obj['pkgs'] if p['id']==package_id),None)
            rules=engine.package_rules(obj,package) if package else None
        elif source=='run':
            obj=runtime._run(source_id);package=next((p for p in obj['packages'] if p['id']==package_id),None);rules=None
        else:raise UserError('图包来源不正确',404)
        if not package:raise UserError('图包不存在',404)
        package=copy.deepcopy(package)
    path=Path(package['path'])
    try:stat=path.stat()
    except OSError:raise UserError('图包文件不存在',404) from None
    cache_key=(source,source_id,package_id,str(path),package.get('fingerprint'),package.get('sha256'),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
    with engine.lock:
        cache=getattr(engine,'workspace_preview_cache',None)
        if cache is None:cache=engine.workspace_preview_cache=OrderedDict()
        if cache_key in cache:
            cache.move_to_end(cache_key)
            return path,copy.deepcopy(cache[cache_key])
    if source=='task':verify_saved_package(path,package['fingerprint'],rules)
    elif not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=package['sha256']:raise UserError('图包文件校验失败',409)
    try:
        with zipfile.ZipFile(path) as archive:manifest=json.loads(archive.read('交付清单.json'))
        if not isinstance(manifest.get('images'),list):raise ValueError()
    except (OSError,ValueError,KeyError,zipfile.BadZipFile):raise UserError('图包清单无法读取',409) from None
    with engine.lock:
        cache[cache_key]=copy.deepcopy(manifest)
        while len(cache)>64:cache.popitem(last=False)
    return path,manifest


def package_details(engine,runtime,source,source_id,package_id):
    _,manifest=_archive(engine,runtime,source,source_id,package_id)
    return {'images':[dict(index=i,placement_id=row['placement_id'],width=row.get('width'),height=row.get('height'),
        version=row.get('version',row.get('image_version')),sha256=row['sha256'],
        image_url=f'/api/workbench/packages/{source}/{source_id}/{package_id}/images/{i}') for i,row in enumerate(manifest['images'])]}


def package_image(engine,runtime,source,source_id,package_id,index):
    path,manifest=_archive(engine,runtime,source,source_id,package_id)
    if type(index) is not int or not 0<=index<len(manifest['images']):raise UserError('图包图片不存在',404)
    row=manifest['images'][index]
    try:
        with zipfile.ZipFile(path) as archive:data=archive.read(row['path'])
        if hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError()
        with Image.open(BytesIO(data)) as image:
            if image.format not in ('JPEG','PNG'):raise ValueError()
            mime='image/jpeg' if image.format=='JPEG' else 'image/png';image.verify()
    except (OSError,ValueError,KeyError,zipfile.BadZipFile):raise UserError('图包图片校验失败',409) from None
    return data,mime
