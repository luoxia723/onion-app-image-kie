"""Freeze registered source pictures and current targets for shared canvases.

This module never submits a model request and never edits the source task. A
source selection is not a new learning baseline generation or semantic review.
"""
from __future__ import annotations

import copy
import hashlib
from fractions import Fraction
from pathlib import Path

from PIL import Image

from .config import UserError, IMAGE_MODELS
from .learning_runtime_support import _copy_checked


def _ordinary(engine, source):
    ids=source.get('image_ids');atts=source.get('atts',{})
    use_raw=source.get('use_raw',False)
    if type(use_raw) is not bool:raise UserError('请选择有效的原图来源方式')
    if not isinstance(ids,list) or not ids or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids):
        raise UserError('请选择同一版位的一套完整来源图片')
    if not isinstance(atts,dict) or any(k not in ids or type(v) is not int or v<1 for k,v in atts.items()):
        raise UserError('来源图片版本不正确')
    task=engine.task(source.get('task_id'));rows=[];identity=None;params=None
    for sid in ids:
        round,slot=engine.find_image(task,sid)
        current=(round['id'],slot['pid'],slot['set'])
        if identity is not None and current!=identity:raise UserError('来源必须属于同一轮次、版位和套图')
        identity=current;params=round['params']
        att=atts.get(sid,slot['att'])
        version=slot if att==slot['att'] else next((v for v in slot.get('versions',[]) if v['att']==att),None)
        if not version or version.get('state')!='done' or version.get('files_cleared'):
            raise UserError('来源图片尚未完成或不可交付',409)
        if version is slot and (slot.get('local_processing') or engine.query_required(slot)):
            raise UserError('来源图片仍有处理中或未知状态任务',409)
        if version.get('delivery_eligible') is False:raise UserError('来源图片未通过交付规格，请先完成制作',409)
        base=version.get('logo_base') or {}
        if use_raw:
            path,sha=version.get('output'),version.get('raw_sha256')
            layer=version.get('brand_logo_layer') or {}
            contains_logo=False if layer.get('model_draws_logo') is False else not bool(params.get('noLogo'))
            if version.get('frame') or slot.get('frame'):raise UserError('此轮次原始画布的制作流程已停用，请选择合格成品或重新制作',409)
        elif base.get('without_logo') is True and base.get('path') and base.get('sha256'):
            path,sha=base['path'],base['sha256'];contains_logo=False
        else:
            path,sha=version.get('jpeg'),version.get('sha256')
            contains_logo=not bool(params.get('noLogo'))
            if version.get('delivery_eligible') is False:raise UserError('来源图片未通过交付规格，请先完成制作',409)
        source_placement=engine.placement(task,round,slot)
        modules=dict(main_copy=bool(params.get('t1') or params.get('t2') or params.get('s'+str(slot['idx']))),
                     cta=bool(_effective_cta(params,source_placement)))
        rows.append(dict(image_index=slot['idx'],path=path,sha256=sha,task_id=task['id'],image_id=sid,ad_modules=modules,
                         att=att,source_kind='ordinary',source_contains_logo=contains_logo,
                         actual_prompt=version.get('prompt',''),
                         mode='simulation' if round.get('simulation',True) else 'real',raw_selected=use_raw))
    placement=engine.placement(task,round,slot);count=placement['image_count']
    if len(rows)!=count or sorted(r['image_index'] for r in rows)!=list(range(1,count+1)):
        raise UserError('双图、三图必须提供同一套的全部来源图片')
    roots=[Path(task['output_dir']),Path(task.get('task_root',task['output_dir'])),engine.settings.output/'.restored']
    return rows,copy.deepcopy(params),roots,dict(kind='ordinary',task_id=task['id'],round_id=identity[0],
        placement_id=identity[1],set_number=identity[2],image_count=count,mode=rows[0]['mode'],name=task.get('name') or task.get('direction',''))


def _learning(engine, source,source_runtime=None):
    rid=source.get('run_id')
    runtime=source_runtime or getattr(engine,'learning_runtime',None)
    run=(runtime.runs.get(rid) if runtime else None) or engine.document('learning-run:'+str(rid))
    if not isinstance(run,dict) or run.get('id')!=rid:raise UserError('来源学习机批次不存在',404)
    if run.get('busy') or any(r.get('query_required') for r in [run.get('baseline',{}),*run.get('masters',[]),*run.get('outputs',[])]):
        raise UserError('来源批次仍有处理中或未知状态任务',409)
    if source.get('baseline') is True:
        row=run.get('baseline',{});approval=run.get('approval') or {}
        expected=source.get('baseline_version',row.get('version'))
        if type(expected) is not int or expected!=row.get('version'):raise UserError('来源基准图版本已更新，请重新选择',409)
        if (row.get('status')!='done' or not approval.get('confirmed') or
            (approval.get('baseline_version'),approval.get('sha256'),approval.get('mode'))!=
            (row.get('version'),row.get('sha256'),run.get('mode'))):
            raise UserError('请先确认来源批次当前基准图',409)
        sha=row.get('sha256');image_id='baseline';kind='learning_baseline';contains=False
        modules=row.get('ad_modules')
        if modules is None:
            concept=run['params'].get('concept') if row.get('uploaded') else None
            modules=dict(main_copy=bool(concept),cta=bool(concept and concept.get('button_text')))
    else:
        ids=source.get('output_ids')
        if not isinstance(ids,list) or len(ids)!=1 or not isinstance(ids[0],str):raise UserError('请选择一张学习机无Logo来源图')
        row=next((r for r in run.get('outputs',[]) if r['id']==ids[0]),None)
        if not row or row.get('status')!='done':raise UserError('来源图片尚未完成',409)
        versions=source.get('versions',{})
        if not isinstance(versions,dict) or any(k not in ids or type(v) is not int or v<1 for k,v in versions.items()):
            raise UserError('来源图片版本不正确')
        if versions.get(row['id'],row['version'])!=row['version']:raise UserError('来源图片版本已更新，请重新选择',409)
        sha=row.get('raw_sha256');image_id=row['id'];kind='learning_output';contains=False
        modules=run.get('placement_snapshots',{}).get(row.get('placement_id'),{}).get('modules',{})
    value=dict(image_index=1,path=row.get('raw_path'),sha256=sha,run_id=rid,image_id=image_id,
               version=row['version'],source_kind=kind,source_contains_logo=contains,ad_modules=copy.deepcopy(modules),
               actual_prompt=row.get('prompt',''),mode=run['mode'])
    return [value],copy.deepcopy(run['params']),[Path(run['directory']),engine.settings.output/'.restored'],dict(
        kind='learning',run_id=rid,image_id=image_id,image_count=1,mode=run['mode'],name=run.get('name') or run['params'].get('t1',''))


def freeze_sources(engine, params, run_dir,*,source_runtime=None):
    """Capture only registered records under lock; copy immutable bytes outside it."""
    source=params.get('source')
    if not isinstance(source,dict):raise UserError('请选择一套来源图片')
    with engine.lock:
        if source.get('kind')=='ordinary':rows,original,roots,summary=_ordinary(engine,source)
        elif source.get('kind')=='learning':rows,original,roots,summary=_learning(engine,source,source_runtime)
        else:raise UserError('来源类型不正确')
        rows=copy.deepcopy(rows)
    roots=[p.resolve() for p in roots];frozen=[]
    for row in sorted(rows,key=lambda r:r['image_index']):
        if not isinstance(row['path'],str) or not isinstance(row['sha256'],str) or len(row['sha256'])!=64:
            raise UserError('来源图片缺少可验证的文件和哈希')
        source_path=Path(row['path']).resolve()
        if not any(source_path.is_relative_to(root) for root in roots):raise UserError('来源图片超出登记工作区')
        target=Path(run_dir)/'sources'/('source-'+str(row['image_index'])+source_path.suffix.lower())
        _copy_checked(source_path,target,row['sha256'])
        try:
            with Image.open(target) as image:
                width,height=image.size;image.verify()
        except (OSError,ValueError):raise UserError('来源文件不是有效图片') from None
        row.update(id='source-'+str(row['image_index']),source_index=row['image_index'],path=str(target),
                   width=width,height=height,selection_confirmed=True,contains_logo=row['source_contains_logo'])
        frozen.append(row)
    summary['copy_basis']='frozen_task_copy'
    return dict(sources=frozen,source_params=original,source_summary=summary)


def _effective_cta(params,p):
    text=params.get('cta','') if params.get('cta_enabled',True) else ''
    override=params.get('cta_overrides',{}).get(p['id'],{'mode':'inherit'})
    if override.get('mode')=='custom':text=override.get('text','')
    elif override.get('mode')=='none':text=''
    return '' if p.get('cta_policy')=='forbidden' else text


def _target_copy(params,p,index,count,learning):
    modules=p['modules'];allowed={}
    if modules['main_copy']:
        allowed['t1']=params.get('t1','') if count==1 else params.get('s'+str(index),'')
        if count==1 and params.get('t2') and not learning:allowed['subtitle']=params['t2']
    if modules['cta']:
        text=_effective_cta(params,p)
        if not text.strip():raise UserError('所选版位要求按钮文案，请先配置来源文案')
        allowed['cta']=text
    return {k:v for k,v in allowed.items() if v}


def freeze_adaptation(engine,params,run_dir,*,source_runtime=None):
    """Return frozen sources, groups and renderer snapshots without generating."""
    from . import master_canvas,brand_logo,learning_logo,learning_mask,learning_prompts
    from .planning import BY_ID
    from .learning_pipeline import CONTENT_BY_ID
    from .learning_sizing import content_size
    frozen=freeze_sources(engine,params,run_dir,source_runtime=source_runtime);original=frozen.pop('source_params');sources=frozen['sources']
    learning=params.get('target_kind',params['source']['kind'])=='learning'
    if params.get('target_kind',params['source']['kind']) not in ('ordinary','learning'):raise UserError('目标渠道类型不正确')
    catalog=CONTENT_BY_ID if learning else {k:p for k,p in BY_ID.items() if p.get('category')!='学习机'}
    ids=params.get('pids')
    if not isinstance(ids,list) or not ids or any(not isinstance(pid,str) or pid not in catalog for pid in ids) or len(ids)!=len(set(ids)):
        raise UserError('请选择有效且不重复的目标版位')
    count=len(sources)
    if (learning and count!=1) or (not learning and any(catalog[pid]['image_count']!=count for pid in ids)):
        raise UserError('目标单图、双图或三图必须与完整来源套图张数一致')
    model=params.get('image_model') or original.get('image_model') or engine.settings.image_model
    if not isinstance(model,str) or model not in IMAGE_MODELS:raise UserError('请选择支持的图片模型')
    normalized=copy.deepcopy(original);normalized.update(pids=ids,image_model=model,sets=1,
        source=copy.deepcopy(params['source']),target_kind='learning' if learning else 'ordinary',bodysource='frozen_source')
    placements={};targets=[];masks={pid:learning_mask.preset_for(pid) for pid in ids}
    for pid in ids:
        p=copy.deepcopy(catalog[pid]);p['output_format']='PNG' if learning else 'JPEG'
        if not learning:
            cta=_effective_cta(original,p)
            p['modules']=dict(main_copy=True,cta=p.get('cta_policy')=='required' or p.get('cta_policy')!='forbidden' and bool(cta),
                logo=p.get('logo_policy')=='required' or p.get('logo_policy')!='forbidden' and not original.get('noLogo',False))
            p.setdefault('corner_radius',0);p.setdefault('mask',False)
        placements[pid]=p
        content_width,content_height=content_size(p)
        for index in range(1,p['image_count']+1):
            source_index=1 if learning else index;source=sources[source_index-1]
            allowed=_target_copy(normalized,p,source_index,count,learning)
            targets.append(dict(id=pid+'::'+str(index),placement_id=pid,image_index=index,
                target_width=content_width,target_height=content_height,source_index=source_index,
                image_form='单图' if count==1 else '双图' if count==2 else '三图',
                source_key=source['sha256'],allowed_text=allowed,content_signature=allowed,
                visible_box=[0,0,1,1-masks[pid]['height_fraction']] if masks[pid]['enabled'] else [0,0,1,1]))
    geometry=master_canvas.plan(targets,model)
    logo=learning_logo.freeze_templates(engine.settings,ids,Path(run_dir)) if learning else dict(schema_version=1,revision=1,assets={},placements={})
    if not learning:
        from .logo_templates import snapshot as logo_template_snapshot
        configured=logo_template_snapshot(engine)
        logo['revision']=configured['revision']
        for pid,p in placements.items():
            if pid in configured['templates']:p['brand_logo_template']=copy.deepcopy(configured['templates'][pid])
            layer=brand_logo.freeze(p,original.get('logo_asset_id'),run_dir,enabled=p['modules']['logo'])
            template={k:layer['template'][k] for k in ('x','y','width')};template['asset_id']=layer['selected_asset_id']
            logo['placements'][pid]=dict(id=pid,target_width=p['target_width'],target_height=p['target_height'],logo_required=p['modules']['logo'],logo_template=template)
            for aid,asset in layer['assets'].items():
                path=Path(run_dir)/'learning-logo-assets'/(aid+'.png');_copy_checked(asset['path'],path,asset['sha256'])
                logo['assets'][aid]={**asset,'path':str(path)}
    outputs=[]
    target_map={t['id']:t for t in targets}
    for o in geometry['outputs']:
        t=target_map[o['output_id']];p=placements[t['placement_id']]
        outputs.append({**o,**{k:t[k] for k in ('placement_id','image_index','allowed_text')},
            'target_width':p['target_width'],'target_height':p['target_height'],
            'platform':p['platform'],'name':p['name'],'sizing_policy':'fixed_crop','output_format':p['output_format']})
    masters=[]
    for group in geometry['groups']:
        source=sources[group['source_index']-1]
        removed=learning_prompts.removed_ad_module(source['ad_modules'],group['allowed_text']) if learning else None
        prompt=master_canvas.prompt(group['allowed_text'],group,source_size=[source['width'],source['height']],removed=removed)
        framing={}
        if removed:
            framing=dict(main_visual_framing=learning_prompts.removal_framing(
                {'main_visual_safe_area':group['content_safe_box']},group['aspect_ratio'],removed),
                concept_audit_box=group['shared_visible_box'])
        masters.append({**group,'group_id':group['id'],'canvas_plan':copy.deepcopy(group),'source_id':source['id'],
            'source_index':group['source_index'],'prompt':prompt,**framing,
            'output_ids':group['target_ids'],'placement_ids':list(dict.fromkeys(target_map[i]['placement_id'] for i in group['target_ids'])),
            'reuse_baseline':False,'needs_image_model_call':True,'image_generation_required':True,
            'single_regeneration_prompt':prompt,
            'reference_bindings':[dict(slot=1,kind='adaptation_canvas'),dict(slot=2,kind='source_picture',source_id=source['id'])]})
    counts=dict(output_count=len(outputs),delivery_count=len(outputs),master_count=len(masters),placement_count=len(placements),image_model_master_calls=len(masters),
                planned_image_calls=len(masters),baseline_image_calls=0,background_image_calls=0,expected_new_calls=len(masters))
    baseline={**sources[0],'id':'baseline','version':1,'status':'done','raw_path':sources[0]['path'],
              'prompt':sources[0]['actual_prompt'],'inherited':True,'source_selection':True,'reference_bindings':[]}
    ratio=Fraction(sources[0]['width'],sources[0]['height'])
    return {**frozen,'mode':sources[0]['mode'],'kind':'shared_canvas_adaptation','target_kind':normalized['target_kind'],'params':normalized,
        'compiled':dict(version=1,mode='shared_canvas',baseline=dict(aspect_ratio=f'{ratio.numerator}:{ratio.denominator}',label='来源图'),masters=masters,outputs=outputs,counts=counts),
        'plan':dict(visual_config={'source':'frozen_source','seed':hashlib.sha256(''.join(s['sha256'] for s in sources).encode()).hexdigest()},outputs=outputs),
        'placement_snapshots':placements,'group_snapshot':geometry,'logo_snapshot':logo,
        'mask_snapshot':copy.deepcopy(masks),'asset_bindings':[],
        'baseline_reference_bindings':[],'inherited_baseline':baseline,
        'source_approval':dict(confirmed=True,source='explicit_source_selection',source_hashes=[s['sha256'] for s in sources])}
