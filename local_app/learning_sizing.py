"""Model-aware size contracts and exact PNG export; no provider calls."""
from __future__ import annotations

from fractions import Fraction
import math
import os
from pathlib import Path
import re

from PIL import Image,ImageStat

from .config import UserError
from kie_model import aspect_ratios, normalize_model


def plan(width, height, model=None, *, aspect_ratio=None):
    if type(width) is not int or type(height) is not int or min(width, height) <= 0:
        raise UserError('目标图片宽高必须是正整数')
    try:
        model=normalize_model(model)
    except ValueError as exc:
        raise UserError(str(exc)) from None
    target=Fraction(width,height)
    choices={label:Fraction(label.replace(':','/')) for label in aspect_ratios(model)}
    costs={label:1-min(target/ratio,ratio/target) for label,ratio in choices.items()}
    if aspect_ratio is not None and (not isinstance(aspect_ratio,str) or not re.fullmatch(r'[1-9]\d*:[1-9]\d*',aspect_ratio)):
        raise UserError('固定母版比例不正确')
    label=aspect_ratio or min(costs,key=costs.get)
    source=Fraction(label.replace(':','/'))
    cost=1-min(target/source,source/target)
    keep_x=min(Fraction(1),target/source);keep_y=min(Fraction(1),source/target)
    return dict(model=model,source_ratio=label,target_width=width,target_height=height,
                model_supports_ratio=label in choices,
                ratio_source='fixed_master_group' if aspect_ratio else 'nearest_supported_ratio',
                crop_percent=float(cost*100),
                crop_axis='上下' if target>source else '左右' if target<source else '无',
                crop_box=[float((1-keep_x)/2),float((1-keep_y)/2),float((1+keep_x)/2),float((1+keep_y)/2)],
                content_must_fit_crop=True,logo_is_protected=False,
                strategy='target_safe_area_recompose' if cost>=Fraction(5,100) else 'reuse_or_target_safe_area_recompose',
                method_label=label+'目标安全区构图 → 精确尺寸 → 固定Logo图层',
                resolution='可调参数，生成时按目标清晰度选择',
                seam_repair='仅有明显拼接时处理；复杂背景由AI编辑，最后重新核验尺寸')


def _color_gradient(image,size):
    """A new color field, not a stretched or repeated copy of the artwork."""
    source=Image.new('RGBA',image.size,'white');source.alpha_composite(image)
    source=source.convert('RGB');sw,sh=source.size
    pw,ph=max(1,round(sw*.08)),max(1,round(sh*.08))
    patches=((0,0,pw,ph),(sw-pw,0,sw,ph),(0,sh-ph,pw,sh),(sw-pw,sh-ph,sw,sh))
    colors=[tuple(round(c) for c in ImageStat.Stat(source.crop(box)).mean) for box in patches]
    small=Image.new('RGB',(2,2));small.putdata(colors)
    return small.resize(size,Image.Resampling.BILINEAR).convert('RGBA')


def _contain_source(image,width,height):
    sw,sh=image.size;scale=min(width/sw,height/sh)
    content_width,content_height=sw*scale,sh*scale
    left,top=(width-content_width)/2,(height-content_height)/2
    # One scale factor in both dimensions. Transparent fill belongs outside
    # the complete source rectangle; no source crop is applied.
    foreground=image.transform((width,height),Image.Transform.AFFINE,
        (1/scale,0,-left/scale,0,1/scale,-top/scale),Image.Resampling.BICUBIC,fillcolor=(0,0,0,0))
    canvas=_color_gradient(image,(width,height));canvas.alpha_composite(foreground)
    padding=max(0.0,100*(1-content_width*content_height/(width*height)))
    return canvas,dict(source_box=[0.0,0.0,1.0,1.0],crop_box=[0.0,0.0,1.0,1.0],
        target_content_box=[left/width,top/height,(left+content_width)/width,(top+content_height)/height],
        scale=scale,crop_percent=0.0,padding_percent=padding,method='contain_full_source_color_gradient',
        sizing_policy='preserve_source',full_source_preserved=True,content_detection='not_performed',
        protection_source='full_source_fallback',background_fill='sampled_corner_color_gradient',
        seam_review_required=padding>1e-9,ai_repair_performed=False)


def export_exact(source, target, width, height, *, crop_box=None, protected_regions=(),sizing_policy=None):
    """Use a frozen crop, or explicitly fit the complete source on an exact canvas.

    All boxes use normalized source coordinates. Detecting the meaningful
    regions belongs to the subsequent planning/inspection stage, not this
    deterministic exporter. Historical inputs are never overwritten.
    """
    if type(width) is not int or type(height) is not int or min(width,height)<=0:
        raise UserError('目标图片宽高必须是正整数')
    if sizing_policy not in (None,'fixed_crop','preserve_source'):raise UserError('尺寸处理策略不正确')
    source,target=Path(source),Path(target)
    if source.resolve()==target.resolve():raise UserError('不能覆盖来源图片')
    with Image.open(source) as opened:
        image=opened.convert('RGBA')
    sw,sh=image.size
    if crop_box is None:
        ratio=width/height
        cw,ch=(sh*ratio,sh) if sw/sh>ratio else (sw,sw/ratio)
        crop_box=[(sw-cw)/2/sw,(sh-ch)/2/sh,(sw+cw)/2/sw,(sh+ch)/2/sh]
    if (not isinstance(crop_box,(list,tuple)) or len(crop_box)!=4
            or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in crop_box)):
        raise UserError('裁切框必须为有限坐标')
    x1,y1,x2,y2=crop_box
    if not(0<=x1<x2<=1 and 0<=y1<y2<=1):raise UserError('裁切框超出来源图片')
    if sizing_policy!='preserve_source' and abs((x2-x1)*sw/((y2-y1)*sh)-width/height)>1e-8:
        raise UserError('裁切框与目标比例不一致，不能拉伸主体')
    for box in protected_regions:
        if (not isinstance(box,(list,tuple)) or len(box)!=4
                or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in box)):
            raise UserError('内容保护框不正确')
        a,b,c,d=box
        if not(0<=a<c<=1 and 0<=b<d<=1):raise UserError('内容保护框不正确')
        if sizing_policy!='preserve_source' and (a<x1-1e-9 or b<y1-1e-9 or c>x2+1e-9 or d>y2+1e-9):
            raise UserError('重要内容超出裁切安全区，请先重构画面或扩背景')
    if sizing_policy=='preserve_source':
        result,metadata=_contain_source(image,width,height)
        metadata['requested_crop_box']=list(crop_box)
    else:
        pixels=[x1*sw,y1*sh,x2*sw,y2*sh]
        result=image.transform((width,height),Image.Transform.EXTENT,pixels,Image.Resampling.BICUBIC)
        metadata=dict(source_box=list(crop_box),crop_box=list(crop_box),crop_percent=100*(1-(x2-x1)*(y2-y1)),
            padding_percent=0.0,method='fixed_crop_resize',sizing_policy='fixed_crop',
            full_source_preserved=list(crop_box)==[0,0,1,1],content_detection='not_performed',
            protection_source='caller_supplied' if protected_regions else 'not_supplied',
            seam_review_required=False,ai_repair_performed=False)
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix('.sizing-tmp.png')
    try:
        result.save(temporary,'PNG',optimize=True)
        with Image.open(temporary) as check:
            if check.format!='PNG' or check.size!=(width,height):raise UserError('目标图片尺寸核验失败')
            check.verify()
        os.replace(temporary,target)
    finally:temporary.unlink(missing_ok=True)
    return dict(path=str(target),format='PNG',width=width,height=height,exact_size_verified=True,**metadata)
