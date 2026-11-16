"""Registered transparent brand layers for new ordinary advertising rounds.

The model receives no Logo image. A frozen, exact-size, unbranded base remains
available so an export can choose another registered Logo without editing art.
Historical baked-in Logos are deliberately not treated as replaceable layers.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import uuid

from PIL import Image

from .config import ROOT, UserError

CONFIG=ROOT/'config/learning-machine-logo-templates.json'
ALIASES={'logo.onion.standard.001':'learning.logo.black','logo.onion.app.002':'learning.logo.white-app',
         'logo.onion.app.001':'learning.logo.white-app'}
DEFAULT='learning.logo.black'
NEUTRAL_ROLE='只定比例，不提供人物、内容或画风；纯白是代码画幅辅助，不是用户参考或品牌素材'


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _records():return {a['id']:a for a in json.loads(CONFIG.read_text(encoding='utf-8'))['assets']}


def normalize_id(value=None):
    if value is None or value=='':return DEFAULT
    if not isinstance(value,str):raise UserError('请选择有效的Logo')
    value=ALIASES.get(value,value)
    if value not in _records():raise UserError('所选Logo不可用，请重新选择')
    return value


def assets():
    return [dict(id=a['id'],label=a['label'],thumb='/api/assets/'+a['id']) for a in _records().values()]


def asset_path(value):
    item=_records()[normalize_id(value)];path=ROOT/item['path']
    if not path.is_file() or digest(path)!=item['sha256']:raise UserError('注册Logo素材校验失败，请恢复项目素材')
    return path


def neutral_canvas(cache,sid,placement,model):
    from kie_model import nearest_aspect_ratio
    ratio=nearest_aspect_ratio(placement['target_width'],placement['target_height'],model)
    a,b=map(int,ratio.split(':'));scale=max(1,round(1024/max(a,b)))
    path=Path(cache)/(sid+'-neutral-canvas.png')
    Image.new('RGB',(a*scale,b*scale),'white').save(path,'PNG')
    return dict(label='参考图1',path=str(path),kind='neutral_canvas',purpose='neutral_canvas',role=NEUTRAL_ROLE)


def default_template(placement):
    records=_records()
    w,h=placement['target_width'],placement['target_height']
    min_ratio=min(a['width']/a['height'] for a in records.values())
    width=min(w*.22,h*.12*min_ratio);margin=min(w,h)*.035
    centered=placement.get('platform') in ('喜马拉雅','ximalaya') and h>w
    x=(w-width)/2 if centered else margin
    return dict(x=x/w,y=margin/h,width=width/w,position='上方居中' if centered else '左上角')


def freeze(placement,selected_id,cache,*,enabled=True,generation_crop=None):
    configured=placement.get('brand_logo_template')
    selected=normalize_id(selected_id or (configured or {}).get('asset_id'));records=_records();frozen={}
    folder=Path(cache)/'brand-logo-assets';folder.mkdir(parents=True,exist_ok=True)
    for aid,record in records.items():
        source=asset_path(aid);target=folder/(record['sha256']+'.png')
        if not target.exists():shutil.copy2(source,target)
        if digest(target)!=record['sha256']:raise UserError('冻结Logo素材校验失败')
        frozen[aid]={k:record[k] for k in ('id','width','height','sha256')}|{'path':str(target)}
    w,h=placement['target_width'],placement['target_height']
    # One fixed rectangle comfortably fits both registered variants, without
    # stretching either or allowing the taller APP mark to leave the canvas.
    template=default_template(placement)
    if configured:
        from .logo_templates import _template
        geometry={k:v for k,v in _template(placement,configured).items() if k!='asset_id'}
        position=template['position'] if all(abs(geometry[k]-template[k])<1e-9 for k in geometry) else '指定品牌位置'
        template={**geometry,'position':position}
    result=dict(version=1,kind='code_layer',model_draws_logo=False,enabled=bool(enabled),
        selected_asset_id=selected,assets=frozen,target_width=w,target_height=h,
        template=template,
        placement_id=placement['id'],source_contract='model_generated_without_logo')
    if generation_crop is not None:
        x1,y1,x2,y2=generation_crop
        height=max(template['width']*w/h*a['height']/a['width'] for a in frozen.values())
        result['generation_box']=[x1+template['x']*(x2-x1),y1+template['y']*(y2-y1),
                                  x1+(template['x']+template['width'])*(x2-x1),y1+(template['y']+height)*(y2-y1)]
    return result


def prompt_rule(snapshot):
    if not snapshot['enabled']:return '画面不出现品牌Logo、品牌标准字或其他品牌标识。'
    template=snapshot['template'];w,h=snapshot['target_width'],snapshot['target_height']
    maximum_height=max(template['width']*w/h*a['height']/a['width'] for a in snapshot['assets'].values())
    box=[template['x'],template['y'],template['x']+template['width'],template['y']+maximum_height]
    box=snapshot.get('generation_box',box)
    return ('绘制无Logo底图，不绘制Logo、品牌标准字或仿造标识。'
            '在'+template['position']+'预留自然连续、纹理简洁的背景，正文、人物脸手和关键道具避开该区域；'
            '不要为留位添加底板、空框或色块。留位归一化区域：'+json.dumps([round(v,3) for v in box],separators=(',',':'))+'。')


def validate_prompt(prompt,snapshot):
    if prompt_rule(snapshot) not in prompt:raise ValueError('prompt缺少本轮无Logo底图与品牌留位约束')


def prepare_base(source,target,placement):
    from image_compress import resize_cover
    with Image.open(source) as original:
        image=resize_cover(original.convert('RGBA' if placement.get('output_format')=='PNG' else 'RGB'),placement['target_width'],placement['target_height'])
        Path(target).parent.mkdir(parents=True,exist_ok=True);image.save(target,'PNG')
    return dict(path=str(target),sha256=digest(target),width=placement['target_width'],height=placement['target_height'],without_logo=True)


def _checked_asset(snapshot,selected_id):
    aid=normalize_id(selected_id or snapshot['selected_asset_id'])
    record=snapshot.get('assets',{}).get(aid)
    if not record:raise UserError('该轮次没有冻结所选Logo素材，请复制为新任务',409)
    path=Path(record['path'])
    if not path.is_file() or digest(path)!=record['sha256']:raise UserError('冻结Logo素材校验失败，未替换图片')
    return aid,record,path


def composite(source,target,snapshot,override_id=None):
    if Path(source).resolve()==Path(target).resolve():raise UserError('Logo叠加不能覆盖来源底图')
    with Image.open(source) as original:
        image=original.convert('RGBA')
    if image.size!=(snapshot['target_width'],snapshot['target_height']):raise UserError('Logo底图尺寸与冻结版位不一致')
    aid=''
    if snapshot['enabled']:
        aid,record,path=_checked_asset(snapshot,override_id)
        with Image.open(path) as original:mark=original.convert('RGBA')
        width=max(1,round(image.width*snapshot['template']['width']))
        height=max(1,round(width*mark.height/mark.width))
        mark=mark.resize((width,height),Image.Resampling.LANCZOS)
        x=round(snapshot['template']['x']*image.width);y=round(snapshot['template']['y']*image.height)
        if x<0 or y<0 or x+width>image.width or y+height>image.height:raise UserError('Logo位置超过图片边界')
        image.alpha_composite(mark,(x,y))
    Path(target).parent.mkdir(parents=True,exist_ok=True);image.save(target,'PNG')
    return dict(asset_id=aid,sha256=digest(target),logo_applied=bool(aid))


def render_delivery(base,target,placement,snapshot,override_id=None):
    """Composite after precise sizing, then meet the frozen output encoding."""
    target=Path(target);intermediate=target.with_suffix(target.suffix+'.layer.png')
    metadata=composite(base,intermediate,snapshot,override_id)
    try:
        if placement.get('output_format')=='PNG':
            from .learning_delivery import save_png
            encoding=save_png(intermediate,target,placement)
        else:
            from image_compress import compress
            limit=(placement.get('max_file_size_kb') or 200)-(1/1024 if placement.get('file_size_operator')=='lt' else 0)
            compress(str(intermediate),str(target),limit,placement['target_width'],placement['target_height']);encoding={}
    finally:intermediate.unlink(missing_ok=True)
    metadata.update(sha256=digest(target),encoding=encoding)
    return metadata


def switchable(slot):
    layer=slot.get('brand_logo_layer');base=slot.get('logo_base')
    return bool(slot.get('state')=='done' and slot.get('delivery_eligible',True)
                and layer and layer.get('kind')=='code_layer' and layer.get('source_contract')=='model_generated_without_logo'
                and base and base.get('without_logo') and Path(base['path']).is_file())


def capability(slots):
    affected=[s for s in slots if s.get('brand_logo_layer',{}).get('enabled',True)]
    editable=bool(affected) and all(switchable(s) for s in affected)
    return dict(editable=editable,asset_ids=[a['id'] for a in assets()],
                reason='' if editable else '旧图或尚未完成的图片没有可替换Logo的无Logo底图；保留原图导出')


def export_variant(slot,placement,asset_id):
    """Make an immutable derived delivery; never edit a candidate or old ZIP."""
    if not switchable(slot):raise UserError('这张历史图片没有无Logo底图，不能直接替换Logo；请重新生成无Logo底图',409)
    value=copy.deepcopy(slot);base=value['logo_base'];snapshot=value['brand_logo_layer']
    if digest(base['path'])!=base['sha256']:raise UserError('无Logo底图校验失败，未替换图片')
    aid=normalize_id(asset_id);_checked_asset(snapshot,aid)
    identity=json.dumps(dict(base=base['sha256'],snapshot=snapshot,asset_id=aid,placement=placement),sort_keys=True,ensure_ascii=False)
    folder=Path(base['path']).parent/'logo-exports';folder.mkdir(exist_ok=True)
    ext='.png' if placement.get('output_format')=='PNG' else '.jpg'
    target=folder/(hashlib.sha256(identity.encode()).hexdigest()+ext)
    # Always compile from frozen bytes. This also makes a corrupted cached
    # derivative detectable instead of trusting a filename as proof of content.
    temporary=target.with_name(target.stem+'-'+uuid.uuid4().hex+target.suffix)
    try:
        result=render_delivery(base['path'],temporary,placement,snapshot,aid)
        temporary.replace(target)
    finally:temporary.unlink(missing_ok=True)
    value.update(jpeg=str(target),sha256=result['sha256'],delivery_logo_asset_id=result['asset_id'])
    return value
