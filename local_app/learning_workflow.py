"""Reviewed learning-machine content and durable, per-scheme image dependencies.

Only explicitly verified families use local pixels. Other placements inherit one
creative plan and the actual first image. Historical rounds are never migrated.
"""
import copy
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageOps
from .config import ROOT, UserError
from . import learning_source, learning_adaptation

CONTRACT=json.loads((ROOT/'config/learning-machine-workflow.json').read_text())
RULES={r['id']:r for r in CONTRACT['enabled']}
COPY_FIELDS=(('feature_label','功能名','feature_label'),('t1','主文案第 1 行','main_copy'),
             ('t2','主文案第 2 行','main_copy'),('extra_heading','底部标题','extra_heading'),
             ('extra_description','底部说明','extra_description'))
COVER_FAMILY=('learning-bbg-cover-400x480','learning-bbg-cover-300x360','learning-bbg-cover-216x260')

def attach_rules(placements):
    from .learning_pipeline import CONTENT_BY_ID
    for p in placements:
        if p['id'] not in CONTENT_BY_ID:continue
        current=CONTENT_BY_ID[p['id']]
        rule=copy.deepcopy(RULES.get(p['id'],dict(id=p['id'],default_parent=CONTRACT['canonical_first_template_for_full_selection'],
            model_call_for_this_derivative=True,production_action='模板扩展')))
        rule.update(modules=copy.deepcopy(current['modules']),layout_class=current['category_label'],
                    max_kb=current['max_file_size_kb'],file_size_operator=current['file_size_operator'])
        p['learning_rule']=copy.deepcopy(rule)
        p['content_modules']=copy.deepcopy(current['modules'])
        p['logo_required']=current['modules']['logo']
        p['cta_required']=current['modules']['cta']
        p.update(enabled=True,name=current['name'],image_form='单图')
        p.pop('disabled_reason',None)
        p['cta_policy']='required' if rule['modules']['cta'] else 'forbidden'
        p['logo_policy']='required' if rule['modules']['logo'] else 'forbidden'
        p['rule_summary']='PNG · '+rule['layout_class']+' · '+('需要Logo' if rule['modules']['logo'] else '无Logo')
        if rule['max_kb'] is not None:p['rule_summary']+=' · '+('<' if rule['file_size_operator']=='lt' else '≤')+str(rule['max_kb'])+'KB'

def copy_fields(placements):
    if placements and all(p.get('category')=='学习机' for p in placements):return [('t1','文案')]
    modules=[p.get('learning_rule',{}).get('modules',{}) for p in placements]
    return [(field,label) for field,label,module in COPY_FIELDS if any(m.get(module) for m in modules)]

def configure_copy(cfg,pr,p):
    rule=p.get('learning_rule')
    if not rule:return
    modules=rule['modules']
    cfg['learning_modules']=copy.deepcopy(modules)
    cfg['learning_copy']={field:pr.get(field,'') if modules[module] else '' for field,_,module in COPY_FIELDS}
    cfg['copy_refs'][0].update(mainTitle=pr.get('t1','') if modules['main_copy'] else '',subtitle=pr.get('t2','') if modules['main_copy'] else '')
    cfg['cta']=(cfg.get('cta','').strip() or pr.get('cta','').strip() or '点击下载') if modules['cta'] else ''
    cfg['learning_logo_required']=bool(modules['logo'])
    if not modules['main_copy'] and not modules['feature_label']:
        cfg['font_reference_enabled']=False

def dependencies(r,s):
    ids=s.get('dependency_ids')
    if ids is None:ids=[s['first_id']] if s['idx']>1 else []
    by_id={x['id']:x for x in r['slots']}
    return [by_id[sid] for sid in ids]

def descendants(r,s):
    ids={s['id']}
    while True:
        following={x['id'] for x in r['slots'] if any(y['id'] in ids for y in dependencies(r,x))}
        if following<=ids:break
        ids|=following
    return [x for x in r['slots'] if x['id'] in ids]

def bind(r,new_ids=None):
    """Bind newly selected outputs without changing any existing mother/version."""
    new_ids=set(new_ids) if new_ids is not None else {s['id'] for s in r['slots']}
    learning=[s for s in r['slots'] if r['configs'][s['config_idx']]['config'].get('learning_modules') is not None]
    source=r['params'].get('learning_source') if learning_source.uploaded(r['params']) else None
    from .planning import BY_ID
    placements={**BY_ID,**{s['pid']:r['configs'][s['config_idx']]['config']['placements'][0] for s in learning}}
    adaptation=learning_adaptation.plan({**r['params'],'pids':list(dict.fromkeys(s['pid'] for s in learning))},placements) if source else None
    routes={row['pid']:row for row in adaptation['rows']} if adaptation else {}
    for n in sorted({s['set'] for s in learning}):
        group=[s for s in learning if s['set']==n];by_pid={s['pid']:s for s in group}
        local={}
        for s in group:
            rule=r['configs'][s['config_idx']]['config']['placements'][0]['learning_rule'];parent=by_pid.get(rule['default_parent'])
            if not rule['model_call_for_this_derivative'] and parent:local[s['id']]=parent
        covers=[by_pid[pid] for pid in COVER_FAMILY if pid in by_pid]
        if covers:
            mother=covers[0]
            for child in covers[1:]:local[child['id']]=mother
        local={sid:parent for sid,parent in local.items() if learning_adaptation.signature(r['params'],placements[next(x['pid'] for x in group if x['id']==sid)])==learning_adaptation.signature(r['params'],placements[parent['pid']])}
        existing=next((s for s in group if s['id'] not in new_ids and s.get('production_mode')=='first_template'),None)
        root=existing or by_pid.get(CONTRACT['canonical_first_template_for_full_selection'])
        if root is None:
            candidates=[s for s in group if s['id'] not in local]
            def rank(s):
                p=r['configs'][s['config_idx']]['config']['placements'][0]
                return (sum(p['learning_rule']['modules'].values()),p['target_width']*p['target_height'],s['pid'])
            root=max(candidates,key=rank)
        for s in group:
            if s['id'] not in new_ids:continue
            cfg=r['configs'][s['config_idx']]['config'];rule=cfg['placements'][0]['learning_rule']
            parent=local.get(s['id']) if s is not root else None
            mode='first_template' if s is root else 'local_resize' if parent else 'template_extension'
            if mode=='template_extension':parent=by_pid.get(rule['default_parent']) or root
            # A previously generated small root remains the creative reference,
            # but never becomes a resize source for a larger new mother.
            if parent is s:parent=root
            ids=[] if s is root else list(dict.fromkeys([root['id'],parent['id']]))
            if source:
                route=routes[s['pid']]
                parent=by_pid.get(route['parent_pid'])
                mode='template_extension' if route['method']=='ai_edit' else 'local_resize'
                ids=[parent['id']] if parent else []
                cfg['learning_uploaded_source']=copy.deepcopy(source)
                s.update(local_source='upload' if route['method']=='source_resize' else 'placement',adaptation_reason=route['reason'],adaptation_method=route['method'])
            s.update(production_mode=mode,template_id='upload:'+source['id'] if source else root['id'],parent_id=parent['id'] if parent else None,dependency_ids=ids)
            if source and s.get('local_source')=='upload':s['parent_id']='upload:'+source['id']
            s['refs']=[ref for ref in s['refs'] if not ref.get('source_slot_id') and ref.get('purpose')!='uploaded_master']
            if mode=='template_extension':
                if source:s['refs'].append({'label':'参考图'+str(len(s['refs'])+1),'path':source['path'],'purpose':'uploaded_master','role':'上传母图：本次扩展的完整视觉母版，保留原有人物、动作、场景、画风、配色和字形；仅按目标规格调整排布和确认文案模块。'})
                for source_id in ids:
                    mother=next(x for x in group if x['id']==source_id)
                    s['refs'].append({'label':'参考图'+str(len(s['refs'])+1),'path':mother.get('jpeg') or str(Path(mother['output']).with_suffix('.delivery.png')),
                                      'source_slot_id':source_id,'role':'本套首模板完整广告成图' if mother is root else '本组母版完整广告成图'})
            if mode=='local_resize':
                refs=[{'label':'参考图1','path':source['path'],'purpose':'uploaded_master','role':'上传原图，直接本机适配'}] if source and s.get('local_source')=='upload' else [{'label':'参考图1','path':parent.get('jpeg') or str(Path(parent['output']).with_suffix('.delivery.png')),'source_slot_id':parent['id'],'role':'本机适配来源母版'}]
                s.update(refs=refs,prompt_origin='local')
            cfg['learning_production_mode']=mode
    r['learning_workflow_version']=CONTRACT['version'] if learning else None
    r['planning_targets']=[s['pid']+'::'+str(s['set']) for s in r['slots'] if s['idx']==1 and s.get('production_mode','first_template')=='first_template' and not s.get('plan_ready')]

def concept_for(r,entry,indexed):
    key=entry['pid']+'::'+str(entry['set'])
    if entry['config'].get('ximalaya_variant'):
        from .ximalaya import placements
        return indexed.get(placements(r['params'])[0]+'::'+str(entry['set']))
    if 'learning_modules' not in entry['config']:return indexed.get(key)
    s=next(s for s in r['slots'] if s['config_idx']==r['configs'].index(entry) and s['idx']==1)
    if entry['config'].get('learning_uploaded_source'):
        return learning_source.concept(entry['config']['visual_direction']['style_id']) if not s.get('plan_ready') else None
    root=next(x for x in r['slots'] if x['id']==s['template_id'])
    first=r['configs'][root['config_idx']]
    root_key=first['pid']+'::'+str(first['set'])
    return indexed.get(root_key) or (first.get('concept') if not s.get('plan_ready') else None)

def freeze_sources(r,s):
    """Check completed final pixels before referencing or resizing them."""
    versions={}
    cfg=r['configs'][s['config_idx']]['config']
    if cfg.get('learning_uploaded_source'):
        source=cfg['learning_uploaded_source'];path=learning_source.check(source)
        versions['upload:'+source['id']]={'att':1,'sha256':source['id'],'path':str(path)}
        for ref in s['refs']:
            if ref.get('purpose')=='uploaded_master':ref['path']=str(path)
    for source in dependencies(r,s):
        from .learning_delivery import require_confirmed_sample
        require_confirmed_sample(r['configs'][source['config_idx']]['config']['placements'][0])
        path=Path(source.get('jpeg') or '')
        if source['state']!='done' or source.get('local_processing') or not source.get('delivery_eligible',True) or not path.is_file():
            raise UserError('首模板或母版尚未完成规格检查，请先处理来源图片')
        sha=hashlib.sha256(path.read_bytes()).hexdigest()
        if sha!=source.get('sha256'):raise UserError('母版文件校验失败，请重新生成母版')
        versions[source['id']]={'att':source['att'],'sha256':sha,'path':str(path)}
    for ref in s['refs']:
        if ref.get('source_slot_id'):ref['path']=versions[ref['source_slot_id']]['path']
    s['source_versions']=versions

def resize_local(r,s,p):
    source=s['source_versions'][s['parent_id']]['path']
    with Image.open(source) as opened:image=opened.convert('RGB')
    size=(p['target_width'],p['target_height'])
    if p['id']=='learning-xiaoyuan-1372x480':
        # Preserve all visible content; fill only the tiny new background edge.
        fitted=ImageOps.contain(image,size,Image.Resampling.LANCZOS)
        canvas=Image.new('RGB',size);x=(size[0]-fitted.width)//2;y=(size[1]-fitted.height)//2
        canvas.paste(fitted,(x,y))
        if x:
            canvas.paste(fitted.crop((0,0,1,fitted.height)).resize((x,fitted.height)),(0,y))
        if size[0]>x+fitted.width:
            canvas.paste(fitted.crop((fitted.width-1,0,fitted.width,fitted.height)).resize((size[0]-x-fitted.width,fitted.height)),(x+fitted.width,y))
        if y:
            canvas.paste(canvas.crop((0,y,size[0],y+1)).resize((size[0],y)),(0,0))
        if size[1]>y+fitted.height:
            canvas.paste(canvas.crop((0,y+fitted.height-1,size[0],y+fitted.height)).resize((size[0],size[1]-y-fitted.height)),(0,y+fitted.height))
        image=canvas
    else:image=image.resize(size,Image.Resampling.LANCZOS)
    image.save(s['output'],'PNG')
    return {'ok':True,'source':s['output']}
