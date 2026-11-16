"""Deterministic PNG delivery rules from the frozen learning-machine placement."""
import hashlib
import os
from pathlib import Path
from PIL import Image
from .config import ROOT,UserError
from image_compress import resize_cover


def checked_asset(record):
    path=Path(record['path']);path=path if path.is_absolute() else ROOT/path
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:
        raise ValueError('版位原素材缺失或校验失败')
    return path


def require_confirmed_sample(placement):
    if placement.get('category')!='学习机':return None
    record=placement.get('sample_reference')
    if placement.get('enabled') is False or not isinstance(record,dict) or record.get('reviewed') is not True:
        raise UserError('缺少明确对应的已确认样图，学习机版位暂不可生成')
    try:
        path=checked_asset(record)
        with Image.open(path) as image:
            if image.size!=(placement['target_width'],placement['target_height']):raise ValueError('样图尺寸不符')
    except (ValueError,OSError,KeyError):
        raise UserError('学习机样图缺失、尺寸不符或校验失败，暂不可生成') from None
    return path


def save_png(source,target,placement,*,raw_preview=False):
    """Keep dimensions and source PNG intact; quantize colors only if a KB limit requires it."""
    with Image.open(source) as opened:image=opened.convert('RGB')
    if not raw_preview:image=resize_cover(image,placement['target_width'],placement['target_height'])
    assets=placement.get('delivery_assets',{}) if not raw_preview else {}
    mask=None;badge=None
    if assets.get('alpha_mask'):
        with Image.open(checked_asset(assets['alpha_mask'])) as opened:mask=opened.convert('L')
        if mask.size!=image.size:raise ValueError('版位圆角蒙版尺寸不符')
    if assets.get('badge'):
        with Image.open(checked_asset(assets['badge'])) as opened:badge=opened.convert('RGBA')
    kb=placement.get('max_file_size_kb');limit=kb*1024 if kb else None
    target=Path(target);temporary=target.with_suffix('.tmp.png');target.parent.mkdir(parents=True,exist_ok=True)
    try:
        for colors in (None,256,128,64,32,16):
            candidate=image.copy() if colors is None else image.quantize(colors=colors,method=Image.Quantize.MEDIANCUT).convert('RGB')
            if badge is not None:
                candidate=candidate.convert('RGBA');candidate.alpha_composite(badge,(0,0))
            if mask is not None:candidate=candidate.convert('RGBA');candidate.putalpha(mask)
            # Exact indexed encoding saves bytes without changing alpha or badge pixels.
            rgba=candidate.convert('RGBA');unique=rgba.getcolors(maxcolors=256)
            if unique is not None:
                colors_rgba=[color for _,color in unique];indices={color:i for i,color in enumerate(colors_rgba)}
                pixels=iter(rgba.tobytes())
                indexed=Image.new('P',rgba.size);indexed.putdata([indices[pixel] for pixel in zip(pixels,pixels,pixels,pixels)])
                palette=[channel for color in colors_rgba for channel in color[:3]]
                indexed.putpalette(palette+[0]*(768-len(palette)))
                indexed.info['transparency']=bytes(color[3] for color in colors_rgba)
                candidate=indexed
            candidate.save(temporary,'PNG',optimize=True)
            size=temporary.stat().st_size
            if limit is None or size<limit or size==limit and placement.get('file_size_operator')!='lt':
                os.replace(temporary,target)
                return {'format':'PNG','colors':colors,'bytes':size,'alpha_mask_applied':mask is not None,'badge_applied':badge is not None}
        raise ValueError('PNG无法同时满足尺寸与大小限制，请简化画面后重出')
    finally:temporary.unlink(missing_ok=True)
