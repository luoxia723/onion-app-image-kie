"""Configuration-only learning-machine pipeline.

A visual baseline is an internal artifact, separate from every deliverable.
The user must see and explicitly confirm that image before suite expansion.
No image/planning provider is imported or called from this module. Setup adds
deterministic prompt previews; explicit run execution uses its separate API.
"""
from __future__ import annotations

import copy
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

from .config import ROOT, UserError

PIPELINE = 'baseline_then_suite'
DEFAULT_CTA = '点击下载'
CONTENT_PATH = ROOT/'config/learning-machine-content-rules.json'
CONTENT = json.loads(CONTENT_PATH.read_text(encoding='utf-8'))
CONTENT_BY_ID = {p['id']:p for p in CONTENT['placements']}
BASELINE_ID = 'learning-visual-baseline'
BASELINE_CONFIRMATION_ID = 'learning-baseline-confirmation'


def placement_contracts():
    """Public task-form records, independent from the former sample gate."""
    result=[]
    for p in CONTENT['placements']:
        modules=copy.deepcopy(p['modules'])
        result.append(dict(id=p['id'], platform=p['platform'], name=p['name'],
            category='学习机', content_category=p['category'], content_category_label=p['category_label'],
            image_form='单图', image_count=p['image_count'], target_width=p['target_width'],
            target_height=p['target_height'], target_size=f"{p['target_width']}x{p['target_height']}",
            output_format='PNG', enabled=True, logo_required=modules['logo'],
            cta_required=modules['cta'], logo_policy='required' if modules['logo'] else 'forbidden',
            cta_policy='required' if modules['cta'] else 'forbidden', content_modules=modules,
            corner_radius=p['corner_radius'], mask=p['mask'], max_file_size_kb=p['max_file_size_kb'],
            **({'artwork_width':p['artwork_width']} if 'artwork_width' in p else {}),
            file_size_operator=p['file_size_operator'],
            rule_summary=p['category_label']+' · '+('有Logo' if modules['logo'] else '无Logo')+' · PNG'))
    return result


def public_contract():
    return dict(version=2, pipeline=PIPELINE, modes=[PIPELINE],
        baseline=dict(aspect_ratio='16:9', advertising_copy=False, logo=False, cta=False, is_delivery=False,
                      needs_user_confirmation=True),
        confirmation=dict(required=True,source='explicit_user_action_for_current_baseline',
                          requires_real_baseline_image=True,automatic=False),
        suite=dict(sets=1, variants_per_placement=1, select_candidates=False, freeze_visual_once=True,
                   requires_baseline_confirmation=True,automatic_after_baseline=False),
        cta=dict(default_text=DEFAULT_CTA, editable=True, presence='fixed_by_placement', shared_per_task=True),
        logo=dict(presence='fixed_by_placement', placement_template_editable=True, model_draws_logo=False),
        execution=dict(enabled=False, real_generation_enabled=False, prompt_generation_ready=False,
                       fixed_prompt_templates_ready=True,scene_planning_execution_ready=True,
                       scope='offline_preview',runtime_available=True,
                       requires_baseline_confirmation=True,auto_expand=False,
                       reason='本接口仅保存配置与预览；通过独立制作入口生成基准图，用户查看确认后才扩展整套。默认本地演练，真实制作需明确选择。'),
        placements=placement_contracts())


def _selected(params, placements=None):
    available=placement_contracts() if placements is None else list(placements.values()) if isinstance(placements,dict) else placements
    available={p['id']:p for p in available if p.get('id') in CONTENT_BY_ID}
    ids=params.get('pids',list(available))
    if not isinstance(ids,list) or not ids or any(not isinstance(pid,str) or pid not in available for pid in ids):
        raise UserError('请选择学习机渠道和版位')
    if len(ids)!=len(set(ids)):raise UserError('学习机版位重复，请重新选择')
    return [copy.deepcopy(available[pid]) for pid in ids]


def _asset_catalog():
    # Loaded only when a preview freezes choices; the planner module itself does
    # not call a provider on import. Use its existing enabled asset/style catalog.
    from .planning import ASSETS, STYLES, BUILTIN_STYLE_REFERENCES
    return ASSETS, STYLES, BUILTIN_STYLE_REFERENCES


def freeze_visual(params, *, seed=None,trusted_visual=None):
    if trusted_visual is not None:
        if not isinstance(trusted_visual,dict) or not isinstance(trusted_visual.get('seed'),str):
            raise UserError('来源批次的冻结视觉配置不完整')
        return copy.deepcopy(trusted_visual)
    assets,styles,builtins=_asset_catalog()
    references=params.get('references',[])
    if not isinstance(references,list) or len(references)>3 or any(not isinstance(r,dict) for r in references):
        raise UserError('参考图最多3张，请选择有效参考图')
    visual_input={k:params.get(k,default) for k,default in [('ip','random'),('style','random'),('font','random')]}
    visual_input['references']=[{k:r.get(k) for k in ('id','purpose','note','points')} for r in references]
    fingerprint=hashlib.sha256(json.dumps(visual_input,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    chosen_seed=str(seed or params.get('learning_seed') or fingerprint)
    rng=random.Random(chosen_seed)
    ips=defaultdict(list)
    for a in assets:
        if a['kind']=='ip' and a.get('enabled',True):ips[a['asset_id'].split('.')[1]].append(a)
    ip_choice=params.get('ip','random')
    if ip_choice in ('random','full_random'):
        roles=list(ips)+([''] if ip_choice=='full_random' else [])
        if not roles:raise UserError('没有可用的IP素材')
        role=rng.choice(roles);ip=rng.choice(ips[role]) if role else None
    elif ip_choice=='none':ip=None
    else:
        ip=next((a for pool in ips.values() for a in pool if a['asset_id']==ip_choice),None)
        if ip is None:raise UserError('指定IP不可用，请重新选择')
    style_ref=next((r for r in references if r.get('purpose')=='style'),None)
    if style_ref:
        style=dict(id='reference',name='参考图画风');style_source='reference'
    else:
        pool=[s for s in styles if ip is None or s.get('supports_ip')]
        style_choice=params.get('style','random')
        if style_choice=='random':
            pool += [dict(id=b['id'],name=b['name'],builtin_reference=True) for b in builtins]
            if not pool:raise UserError('没有可用画风')
            style=rng.choice(pool);style_source='builtin_reference' if style.get('builtin_reference') else 'random'
        else:
            style=next((s for s in pool if s['name']==style_choice or s['id']==style_choice),None)
            if style is None:raise UserError('指定画风不可用，请重新选择')
            style_source='specified'
    fonts=[a for a in assets if a['kind']=='font' and a.get('enabled',True)]
    font_choice=params.get('font','random')
    if font_choice=='none':font=None
    elif font_choice=='random':font=rng.choice(fonts) if fonts else None
    else:
        font=next((a for a in fonts if a['asset_id']==font_choice),None)
        if font is None:raise UserError('指定字体不可用，请重新选择')
    return dict(seed=chosen_seed,selection_fingerprint=fingerprint,randomized_once=True,
        ip_id=ip['asset_id'] if ip else '',ip_name=(ip.get('asset_name_zh') or ip['display_name']) if ip else '无IP',
        style_id=style['id'],style_name=style['name'],style_source=style_source,
        font_id=font['asset_id'] if font else '',font_name=font.get('display_name','') if font else '无字体参考',
        references=copy.deepcopy(visual_input['references']))


def normalize(params, placements=None, *, seed=None,trusted_visual=None):
    if not isinstance(params,dict):raise UserError('请填写学习机配置')
    selected=_selected(params,placements)
    if params.get('channel','学习机')!='学习机':raise UserError('该配置仅支持学习机渠道')
    if params.get('learning_mode') not in (None,'generate',PIPELINE) or params.get('learning_pipeline') not in (None,PIPELINE):
        raise UserError('学习机统一先生成基准图，再生成整套，不再提供上传母图替代路径')
    text=params.get('copy',params.get('t1',''))
    if not isinstance(text,str) or not text.strip():raise UserError('请填写一句学习机文案')
    if len(text)>1000:raise UserError('文案最多1000字')
    cta=params.get('cta',DEFAULT_CTA)
    if not isinstance(cta,str):raise UserError('CTA文案请填写纯文本')
    if len(cta)>1000:raise UserError('CTA文案最多1000字')
    for field,limit in {'feature_label':1000,'extra_heading':1000,'extra_description':1000,
                        'feature_note':200,'product_facts':20000}.items():
        optional=params.get(field)
        if optional is not None and (not isinstance(optional,str) or len(optional)>limit):
            raise UserError(f'{field} 请填写最多{limit}字的纯文本')
    value=copy.deepcopy(params)
    value.update(channel='学习机',image_form='单图',pids=[p['id'] for p in selected],sets=1,
                 variants_by_placement={p['id']:1 for p in selected},t1=text.strip(),t2='',
                 learning_mode=PIPELINE,learning_pipeline=PIPELINE,cta=cta.strip() or DEFAULT_CTA,
                 feature_label='',extra_heading='',extra_description='',
                 cta_enabled=True,cta_overrides={},noLogo=False,
                 learning_pipeline_version=2,learning_requires_baseline_confirmation=True,learning_auto_expand=False)
    # Configuration is not an image or an approval record. These states must
    # eventually originate from server-owned artifacts and an explicit user
    # action, not from a form, preview or restored configuration payload.
    for key in ('learning_source','visual_concepts','logo_asset_id','baseline','confirmation','suite',
                'baseline_confirmed','confirmed_baseline_id','baseline_confirmation','baseline_approval',
                'learning_baseline','learning_baseline_confirmation','learning_baseline_approval',
                'baseline_artifact','confirmation_receipt','confirmed','approval','baseline_ready','suite_ready',
                'has_image','artifact_ready','can_confirm','can_expand','auto_expand','execution',
                'prompt_generation_ready','real_generation_enabled'):
        value.pop(key,None)
    for key in ('scene_plan','scene_planning','prompt_plan','masters','master_groups','learning_master_groups','aspect_ratio',
                'framing_node','main_visual_framing','stages'):
        value.pop(key,None)
    value['learning_visual_config']=freeze_visual(value,seed=seed,trusted_visual=trusted_visual)
    value['learning_seed']=value['learning_visual_config']['seed']
    return value


def preview(params, placements=None, *, seed=None,trusted_visual=None):
    normalized=normalize(params,placements,seed=seed,trusted_visual=trusted_visual)
    selected=_selected(normalized,placements)
    baseline=dict(id=BASELINE_ID,type='visual_baseline',name='本套基准图',aspect_ratio='16:9',
        advertising_copy=False,logo=False,cta=False,is_delivery=False,state='not_generated',depends_on=[],
        has_image=False,artifact_ready=False,needs_user_confirmation=True,preview_only=True,
        approval=dict(required=True,status='waiting_for_image',confirmed=False,can_confirm=False))
    confirmation=dict(id=BASELINE_CONFIRMATION_ID,baseline_id=BASELINE_ID,required=True,
                      status='waiting_for_image',confirmed=False,can_confirm=False,can_expand=False,
                      depends_on=[BASELINE_ID],reason='尚无真实基准图；配置预览不能代替用户查看和确认图片。')
    outputs=[]
    for p in selected:
        rule=CONTENT_BY_ID[p['id']];modules=copy.deepcopy(rule['modules'])
        for index in range(1,rule['image_count']+1):
            outputs.append(dict(id=p['id']+'::'+str(index),placement_id=p['id'],pid=p['id'],platform=p['platform'],
                name=p['name'],image_index=index,idx=index,width=p['target_width'],height=p['target_height'],
                target_size=f"{p['target_width']}x{p['target_height']}",output_format='PNG',state='waiting_for_baseline_confirmation',
                depends_on=[BASELINE_ID,BASELINE_CONFIRMATION_ID],dependency_ids=[BASELINE_ID,BASELINE_CONFIRMATION_ID],
                requires_baseline_confirmation=True,can_expand=False,artifact_ready=False,
                content_modules=copy.deepcopy(modules),
                logo_required=modules['logo'],cta_required=modules['cta'],cta_text=normalized['cta'] if modules['cta'] else '',
                logo_template=copy.deepcopy(p.get('logo_template'))))
    return dict(version=2,pipeline=PIPELINE,normalized_params=normalized,baseline=baseline,confirmation=confirmation,
        suite=dict(status='waiting_for_baseline_confirmation',requires_baseline_confirmation=True,can_expand=False,
                   automatic_after_baseline=False),outputs=outputs,
        placements=selected,sets=1,output_count=len(outputs),delivery_image_count=len(outputs),
        total_image_count=1+len(outputs),visual_config=normalized['learning_visual_config'],
        stages=[dict(id='baseline',name='先生成一张基准图',depends_on=[],status='not_generated'),
                dict(id='baseline_confirmation',name='用户查看并确认基准图',kind='user_action',
                     depends_on=['baseline'],required=True,automatic=False,status='waiting_for_image',can_confirm=False),
                dict(id='main_visual_framing',name='按版位计算主视觉安全区',kind='code',depends_on=['baseline_confirmation'],
                     status='configuration_ready',additional_image_calls=0),
                dict(id='suite',name='带构图约束扩展母版',depends_on=['main_visual_framing'],
                     status='waiting_for_baseline_confirmation',automatic=False,can_start=False),
                dict(id='background_adaptation',name='小误差轻裁；大误差AI自然延展',kind='conditional',depends_on=['suite'],
                     threshold_percent=8,status='waiting_for_masters'),
                dict(id='export',name='精确尺寸与图层导出，再审核主视觉',kind='code',depends_on=['background_adaptation'],
                     inspection='user_visual_review',status='waiting_for_masters')],
        execution=public_contract()['execution'],prompt_generation_ready=False)


def simulate(params, placements=None, *, seed=None):
    """Check configuration and stop at approval; never simulate user consent.

    No real image exists in this mode. Even an otherwise complete plan cannot
    confirm the baseline or start suite outputs merely by running a simulation.
    """
    plan=preview(params,placements,seed=seed)
    events=[dict(sequence=1,node_id=BASELINE_ID,stage='baseline',state='configuration_checked',
                 simulated=True,artifact_ready=False),
            dict(sequence=2,node_id=BASELINE_CONFIRMATION_ID,stage='baseline_confirmation',
                 state='waiting_for_real_image',confirmed=False,simulated=True)]
    for output in plan['outputs']:
        output.update(simulated=True,artifact_ready=False,started=False,can_expand=False)
    plan.update(simulated=True,artifacts_generated=False,network_requests=0,events=events,
                blocked_at='baseline_confirmation')
    return plan
