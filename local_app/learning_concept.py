"""Compile destinations for a confirmed, text-bearing 16:9 upload."""
from fractions import Fraction
from pathlib import Path

from PIL import Image

from kie_model import GPT_IMAGE_26_FLARE
from .config import UserError
from .learning_pipeline import CONTENT_BY_ID, DEFAULT_CTA
from .learning_sizing import content_size
from .learning_prompts import _crop, _intersection, _reference_prompt, NATURAL_BACKGROUND_THRESHOLD_PERCENT
from .learning_source import registered

RATIO = '16:9'
DIRECT_LIMIT = NATURAL_BACKGROUND_THRESHOLD_PERCENT
BACKGROUND_LIMIT = 20
LABELS = dict(direct='原图适配', background='GPT 扩背景', reflow='GPT 重新排版',
              remove_cta='GPT 去按钮并排版', add_cta='GPT 加按钮并排版', pure='GPT 去字并重排构图')


def check_ratio(image):
    if image.width*9 != image.height*16 or image.getexif().get(274, 1) not in (1, None):
        raise UserError('请上传横向 16:9 概念图，例如 1600×900')


def resolve(settings, value):
    if not isinstance(value, dict):
        raise UserError('请上传 16:9 概念图')
    button=value.get('button_text','')
    if not isinstance(button,str) or len(button)>12:
        raise UserError('图上按钮文字最多 12 字')
    request={'learning_mode':'upload','learning_source':{'id':value.get('id'), 'name':value.get('name','概念图'),
                                                        'path':value.get('source_path')}}
    registered(request,settings)
    item=request['learning_source']
    path=Path(item['path'])
    with Image.open(path) as image:
        check_ratio(image)
    return dict(id=item['id'],name=item['name'],width=item['width'],height=item['height'],
                button_text=button.strip(),source_path=str(path)),path


def params_for_concept(settings, params):
    concept,_=resolve(settings,params['concept'])
    params.update(concept=concept,cta=concept['button_text'] or DEFAULT_CTA, image_model=GPT_IMAGE_26_FLARE,
                  references=[],ip='none',style='random',font='none')
    # The form's explicit transcription is the source copy and the target copy.
    params.pop('copy',None)


def _loss(width,height):
    ratio=Fraction(width,height)
    source=Fraction(16,9)
    return 100*(1-min(ratio/source,source/ratio))


def group_route(mode, ratio, placements, mask_snapshot, has_button):
    if mode=='pure':
        return 'pure'
    if mode=='copy' and has_button:
        return 'remove_cta'
    if mode=='copy_cta' and not has_button:
        return 'add_cta'
    has_special=any(content_size(p)!=(p['target_width'],p['target_height'])
                    or mask_snapshot.get(p['id'],{}).get('enabled') for p in placements)
    losses=[_loss(*content_size(p)) for p in placements]
    # A single compatible raster is shared by all selected members of this group.
    if not has_special and max(losses)<=DIRECT_LIMIT:
        return 'direct'
    if not has_special and DIRECT_LIMIT < _loss(*map(int,ratio.split(':'))) <= BACKGROUND_LIMIT and max(losses)<=BACKGROUND_LIMIT:
        return 'background'
    return 'reflow'


def configure_plan(plan, compiled):
    concept=plan['normalized_params']['concept']
    mask=plan['normalized_params']['learning_mask_snapshot']
    compiled['baseline'].update(prompt='使用已上传的 16:9 概念图作为整套来源。',reference_bindings=[],
                                status='uploaded_concept',missing_inputs=[])
    compiled['scene_planning']['enabled']=False
    maps={row['output_id']:row for row in compiled['outputs']}
    for master in compiled['masters']:
        pids=master['placement_ids']
        route=group_route(master['content_mode'],master['aspect_ratio'],[CONTENT_BY_ID[pid] for pid in pids],
                          mask,bool(concept['button_text']))
        if route in ('direct','background') and plan['normalized_params'].get('feature_note','').strip():
            route='reflow'
        master['concept_route']=route
        master['reuse_baseline']=route=='direct'
        master['source_kind']='confirmed_baseline_reuse' if route=='direct' else 'confirmed_baseline_image_to_image'
        master['image_generation_required']=master['needs_image_model_call']=route!='direct'
        master['reference_bindings'][0]['purpose']='用户确认的有字概念图；沿用人物、场景、色彩和标题字形、描边与字号层级。'
        prefix={
            'pure':'移除概念图中的广告正文、按钮和仅承载这些字的底框，按纯画面重排原有场景。保留作为教学内容的题板、公式及原有分镜。',
            'remove_cta':'移除原按钮整体和按钮文字，保留完整正文。',
            'add_cta':'沿用原有标题字形、层级和描边，为指定按钮留出独立空间。',
            'reflow':'沿用参考图标题的字形、描边和字色。按目标画幅重排换行、文字位置及主体大小。',
        }.get(route,'沿用参考图标题的字形、描边和字色，保证完整文字与主体处于安全区。')
        # The last paragraph of the standard prompt describes the unlettered
        # baseline reference. Replace it with the concept reference contract.
        base=master['single_regeneration_prompt'].rsplit('\n参考图1',1)[0]
        regeneration=prefix+'\n'+base+'\n'+_reference_prompt(master['reference_bindings'])
        master['single_regeneration_prompt']=regeneration
        master['prompt']=('复用已确认的概念图，审核通过后本机按版位裁切缩放。' if route=='direct'
                          else '延续概念图背景至目标画幅，保留字块的排版、字风和主体。' if route=='background'
                          else regeneration)
        if route=='direct':
            master['aspect_ratio']=RATIO
            boxes=[]
            for output_id in master['output_ids']:
                row=maps[output_id]
                box=_crop(RATIO,*content_size(CONTENT_BY_ID[row['placement_id']]))
                boxes.append(box)
                row.update(aspect_ratio=RATIO,crop_box=box,sizing_policy='fixed_crop',requires_image_model_call=False,
                           processing_kind='local_export',background_image_required=False)
            master['concept_audit_box']=_intersection(boxes)
            for crop in master['crops']:
                if crop['placement_id'] in pids:
                    box=_crop(RATIO,*content_size(CONTENT_BY_ID[crop['placement_id']]))
                    crop.update(crop_box=box,crop_percent=round(float(_loss(*content_size(CONTENT_BY_ID[crop['placement_id']]))),6))
        if master['main_visual_framing'].get('removed_ad_module'):
            targets=[maps[output_id] for output_id in master['output_ids']]
            if not any(row['background_image_required'] for row in targets):
                master['concept_audit_box']=_intersection([row['crop_box'] for row in targets])
        for output_id in master['output_ids']:
            maps[output_id]['concept_route']=route
    direct=sum(m['reuse_baseline'] for m in compiled['masters'])
    backgrounds={(row['master_id'],Fraction(row['target_width'],row['target_height']),row['simple_background'])
                 for row in maps.values() if row['background_image_required']}
    generation=len(compiled['masters'])-direct
    compiled['counts'].update(baseline_image_calls=0,image_model_master_calls=generation,baseline_reused_master_count=direct,
                             background_image_calls=len(backgrounds),planned_image_calls=generation+len(backgrounds))
    plan['baseline'].update(name='上传的概念图',aspect_ratio=RATIO,advertising_copy=True,cta=bool(concept['button_text']),
                            state='uploaded_concept',has_image=True)
    plan['stages'][0].update(name='上传 16:9 概念图',status='uploaded_concept')
    plan['confirmation']['reason']='请查看并确认上传概念图和填写的图上文案。'
