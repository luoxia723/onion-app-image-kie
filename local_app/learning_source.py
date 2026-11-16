"""Validate, freeze and describe a user-supplied learning-machine master image."""
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
from PIL import Image
from .config import UserError

COPY_KEYS=('feature_label','t1','t2','cta','extra_heading','extra_description')

def uploaded(pr):return isinstance(pr,dict) and pr.get('learning_mode','generate')=='upload'

def check(source):
    if not isinstance(source,dict) or not isinstance(source.get('id'),str) or not re.fullmatch('[a-f0-9]{64}',source['id']):
        raise UserError('请上传要扩展的母图')
    try:
        path=Path(source['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=source['id']:raise ValueError()
        with Image.open(path) as image:
            if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height>40000000:raise ValueError()
    except (ValueError,OSError,KeyError):raise UserError('上传母图缺失或校验失败，请重新上传') from None
    return path

def validate(pr,placements):
    mode=pr.get('learning_mode','generate')
    learning=bool(placements) and all(p['category']=='学习机' for p in placements)
    if mode=='upload':raise UserError('学习机统一先生成基准图，再生成整套，不再提供上传母图替代路径')
    if mode not in ('generate','baseline_then_suite'):raise UserError('学习机仅支持先生成基准图，再生成整套')
    if learning and (pr.get('sets')!=1 or any(n!=1 for n in pr.get('variants_by_placement',{}).values())):
        raise UserError('学习机固定生成一整套，每个版位不再选择多套候选')

def registered(pr,settings,existing=()):
    """Resolve a content id to an owned upload or the task's own frozen copy."""
    if not uploaded(pr):return
    supplied=pr.get('learning_source')
    if not isinstance(supplied,dict) or not isinstance(supplied.get('id'),str) or not re.fullmatch('[a-f0-9]{64}',supplied['id']):
        raise UserError('请上传要扩展的母图')
    rid=supplied['id']
    path=next((settings.state_dir/'uploads'/(rid+suffix) for suffix in ('.png','.jpg','.webp') if (settings.state_dir/'uploads'/(rid+suffix)).is_file()),None)
    if path is None:
        path=next((Path(x['path']) for x in existing if isinstance(x,dict) and x.get('id')==rid),None)
    if path is None and isinstance(supplied.get('path'),str):
        candidate=Path(supplied['path']).resolve()
        if (settings.output/'.restored').resolve() in candidate.parents:path=candidate
    if path is None:raise UserError('请重新上传母图，不能使用未登记的本机文件')
    record={'id':rid,'sha256':rid,'path':str(path),'name':str(supplied.get('name') or '上传母图')[:120],'thumbnail_url':'/api/uploads/'+rid}
    for key in ('layout_id','original_logo_asset_id'):
        if isinstance(supplied.get(key),str):record[key]=supplied[key][:160]
    record['layout_confirmed']=supplied.get('layout_confirmed') is True
    baseline=supplied.get('copy_snapshot')
    if isinstance(baseline,dict) and set(baseline)==set(COPY_KEYS) and all(isinstance(v,str) and len(v)<=1000 for v in baseline.values()):record['copy_snapshot']=copy.deepcopy(baseline)
    from .planning import BY_ID
    known=next((p for p in BY_ID.values() if p.get('sample_reference',{}).get('sha256')==rid),None)
    if known:record.update(layout_id=known['id'],layout_confirmed=True,known_sample=True,original_logo_asset_id='logo.onion.standard.001')
    preview=supplied.get('preview','')
    if isinstance(preview,str) and preview.startswith('data:image/jpeg;base64,') and len(preview)<40000:record['preview']=preview
    check(record)
    with Image.open(path) as image:record.update(width=image.width,height=image.height)
    pr['learning_source']=record

def freeze(pr,cache):
    value=copy.deepcopy(pr)
    if not uploaded(value):return value
    source=check(value['learning_source']);target=Path(cache)/'uploaded-master'/(value['learning_source']['id']+source.suffix.lower())
    target.parent.mkdir(parents=True,exist_ok=True)
    if source.resolve()!=target.resolve():shutil.copy2(source,target)
    value['learning_source'].update(path=str(target),sha256=value['learning_source']['id'])
    return value

def concept(style_id):
    return dict(name='上传母图扩展',style_id=style_id,prompt='完整沿用上传母图已有的人物、动作、道具、场景和视觉主题，仅适配目标版位的布局与确认文案。',
                slot_actions=['保留上传母图当前瞬间的人物动作、表情、物体关系和镜头。'],
                art_direction={'world':'上传母图的原有视觉世界','scene':'上传母图的原有场景','story':'保留上传母图已有的画面含义','composition':'按目标版位样图调整主体占比与文字留白','lighting_materials':'沿用上传母图的配色、笔触、材质和光影'},
                learner_story={'protagonist':'上传母图中的原有人物或主体','pain_point':'保留母图已有主题，不新增功能或承诺','product_action':'沿用母图的可见动作与物体关系','visible_change':'仅调整目标版位的布局与文案模块'},screen_text=[])
