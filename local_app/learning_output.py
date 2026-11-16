"""Local learning-machine export from existing pixels; never generates images."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile

from PIL import Image, ImageChops, ImageDraw

from .config import UserError
from . import learning_logo, learning_mask
from .learning_pipeline import CONTENT_BY_ID
from .learning_sizing import export_exact


def _indexed_picture(image,logo,snapshot,*,colors=256,brand_colors=128):
    """Use a dedicated brand palette so a tiny logo survives global indexing."""
    if not logo.get('logo_applied'):return image.quantize(colors=colors,method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE)
    aid=logo['logo_asset_id'];_,_,width,height=logo['pixel_box']
    with Image.open(snapshot['assets'][aid]['path']) as opened:
        mark=opened.convert('RGBA').resize((width,height),Image.Resampling.LANCZOS)
    pixels=mark.get_flattened_data()
    opaque=[pixel[:3] for pixel in pixels if pixel[3]==255]
    if not opaque:opaque=[pixel[:3] for pixel in pixels if pixel[3]>0]
    if not opaque:return image.quantize(colors=colors,method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE)
    samples=Image.new('RGB',(len(opaque),1));samples.putdata(opaque)
    brand=samples.quantize(colors=brand_colors,method=Image.Quantize.MEDIANCUT)
    picture=image.quantize(colors=colors-brand_colors,method=Image.Quantize.MEDIANCUT)
    entries=brand.getpalette()[:brand_colors*3]+picture.getpalette()[:(colors-brand_colors)*3]
    palette=Image.new('P',(1,1));palette.putpalette(entries+entries[-3:]*(256-colors))
    indexed=image.quantize(palette=palette,dither=Image.Dither.NONE)
    return indexed.point([i if i<colors else colors-1 for i in range(256)])


def _indexed_transparent_picture(image,logo,snapshot):
    """Keep the rounded alpha mask exact; reserve palette entries for its fringe.

    Only subpixel fringe colors are averaged. Opaque art uses median-cut and a
    dedicated brand palette, avoiding coarse octree bands over the whole image.
    """
    alpha=image.getchannel('A');levels=[i for i,n in enumerate(alpha.histogram()) if n and i<255]
    if len(levels)>192:
        return None
    colors=min(192,256-len(levels));picture=_indexed_picture(image.convert('RGB'),logo,snapshot,colors=colors,brand_colors=min(48,colors//3))
    samples={a:[0,0,0,0] for a in levels};pixels=image.tobytes()
    for r,g,b,a in zip(pixels[0::4],pixels[1::4],pixels[2::4],pixels[3::4]):
        if a<255:
            sums=samples[a];sums[0]+=r;sums[1]+=g;sums[2]+=b;sums[3]+=1
    fringe={a:colors+i for i,a in enumerate(levels)}
    palette=picture.getpalette()[:colors*3]
    for a in levels:palette.extend(round(v/samples[a][3]) for v in samples[a][:3])
    result=Image.new('P',image.size);result.putpalette(palette+[0]*(768-len(palette)))
    result.putdata([i if a==255 else fringe[a] for i,a in zip(picture.tobytes(),alpha.tobytes())])
    result.info['transparency']=bytes([255]*colors+levels)
    return result


def _indexed_rgba_fallback(image):
    result=image.quantize(colors=256,method=Image.Quantize.FASTOCTREE,dither=Image.Dither.NONE)
    # Octree averages can turn opaque art into alpha254. Keep opaque/clear
    # endpoints exact while allowing only fringe color/alpha quantization.
    opaque=set();clear=set()
    for index,alpha in zip(result.tobytes(),image.getchannel('A').tobytes()):
        if alpha==255:opaque.add(index)
        elif alpha==0:clear.add(index)
    palette=result.getpalette('RGBA')
    for index in opaque:palette[index*4+3]=255
    for index in clear:palette[index*4+3]=0
    result.putpalette(palette,rawmode='RGBA')
    return result


def export_output(source,target,placement_id,logo_snapshot,*,mask_snapshot=None,placement_snapshot=None,crop_box=None,protected_regions=(),sizing_policy=None):
    """Size → gray gradient → logo → rounded alpha, atomically saved as PNG.

    Use the plan's frozen logo/mask snapshots for both review and delivery.
    The historical exporter, including its old featured badge, is independent.
    """
    if placement_snapshot is None and placement_id not in CONTENT_BY_ID:raise UserError('学习机版位不存在',404)
    source,target=Path(source),Path(target)
    if source.resolve()==target.resolve():raise UserError('不能覆盖来源图片')
    row=placement_snapshot if placement_snapshot is not None else CONTENT_BY_ID[placement_id]
    if not isinstance(row,dict) or row.get('id')!=placement_id:raise UserError('学习机冻结版位不完整')
    width,height=row['target_width'],row['target_height']
    if type(width) is not int or type(height) is not int or min(width,height)<=0 or width*height>40000000:raise UserError('学习机冻结尺寸不正确')
    if row.get('output_format')=='JPEG':
        return _export_jpeg(source,target,placement_id,logo_snapshot,row,crop_box,protected_regions,sizing_policy)
    if mask_snapshot is not None and (not isinstance(mask_snapshot,dict) or placement_id not in mask_snapshot):
        raise UserError('学习机遮罩冻结配置不完整')
    template=mask_snapshot[placement_id] if mask_snapshot is not None else learning_mask.preset_for(placement_id)
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.learning-export-',dir=target.parent) as folder:
        folder=Path(folder)
        sizing=export_exact(source,folder/'sized.png',width,height,crop_box=crop_box,protected_regions=protected_regions,sizing_policy=sizing_policy)
        mask=learning_mask.apply_mask(folder/'sized.png',folder/'masked.png',placement_id,template=template,expected_size=(width,height))
        with Image.open(folder/'masked.png') as opened:background=opened.convert('RGBA')
        radius=row['corner_radius'];limit=row.get('max_file_size_kb')
        # Try true-color encoding first. Opaque deliveries may use an indexed
        # PNG when RGB storage still exceeds a channel's byte budget; the
        # original layer assets remain unchanged and all dimensions stay exact.
        for colors in (None,256,128,64,32,16):
            image=background.copy()
            if colors:
                image=background.convert('RGB').quantize(colors=colors,method=Image.Quantize.MEDIANCUT).convert('RGBA')
                image.putalpha(background.getchannel('A'))
            image.save(folder/'compressed.png','PNG',optimize=True)
            logo=learning_logo.composite(folder/'compressed.png',folder/'logo.png',placement_id,logo_snapshot)
            with Image.open(folder/'logo.png') as opened:image=opened.convert('RGBA')
            if radius:
                scale=4
                alpha=Image.new('L',(width*scale,height*scale),0)
                ImageDraw.Draw(alpha).rounded_rectangle((0,0,width*scale-1,height*scale-1),radius=radius*scale,fill=255)
                alpha=alpha.resize((width,height),Image.Resampling.LANCZOS)
                image.putalpha(ImageChops.multiply(image.getchannel('A'),alpha))
            finished=folder/'finished.png'
            encoded=image.convert('RGB') if image.getchannel('A').getextrema()==(255,255) else image
            encoded.save(finished,'PNG',optimize=True)
            indexed_colors=None
            alpha_quantized=False
            size=finished.stat().st_size
            if (limit is not None
                    and (size>limit*1024 or size==limit*1024 and row.get('file_size_operator')=='lt')):
                candidates=[(lambda:_indexed_picture(encoded,logo,logo_snapshot),False)] if encoded.mode=='RGB' else [
                    (lambda:_indexed_transparent_picture(encoded,logo,logo_snapshot),False),
                    (lambda:_indexed_rgba_fallback(encoded),True)]
                for encode,quantized_alpha in candidates:
                    indexed=encode()
                    if indexed is None:continue
                    alternative=folder/'indexed.png';indexed.save(alternative,'PNG',optimize=True)
                    if alternative.stat().st_size<size:
                        os.replace(alternative,finished);size=finished.stat().st_size;indexed_colors=256;alpha_quantized=quantized_alpha
                    if size<limit*1024 or size==limit*1024 and row.get('file_size_operator')!='lt':break
            if limit is None or size<limit*1024 or size==limit*1024 and row.get('file_size_operator')!='lt':break
        else:raise UserError('图片已达到精确尺寸，但超过该版位PNG大小限制，请压缩或简化画面；不会缩小交付尺寸')
        with Image.open(finished) as checked:
            if checked.format!='PNG' or checked.size!=(width,height):raise UserError('导出图片尺寸核验失败')
            checked.verify()
        digest=hashlib.sha256(finished.read_bytes()).hexdigest()
        os.replace(finished,target)
    return dict(path=str(target),placement_id=placement_id,width=width,height=height,format='PNG',bytes=size,
                sha256=digest,exact_size_verified=True,crop_box=sizing['crop_box'],sizing={k:v for k,v in sizing.items() if k!='path'},mask=mask,logo=logo,
                corner_radius=radius,palette_colors=indexed_colors or colors,picture_palette_colors=colors,
                encoding_method='indexed' if indexed_colors else 'truecolor',badge_applied=False,feature_label_drawn=False,
                alpha_palette_quantized=alpha_quantized,
                processing_order=['exact_contain_and_resize' if sizing['sizing_policy']=='preserve_source' else 'exact_crop_and_resize',
                                  'bottom_gray_mask','placement_logo','rounded_corners'])


def _export_jpeg(source,target,pid,snapshot,row,crop_box,protected_regions,policy):
    """Ordinary targets share exact geometry and registered post-size Logos."""
    from image_compress import compress
    width,height=row['target_width'],row['target_height'];target=Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.master-export-',dir=target.parent) as folder:
        folder=Path(folder)
        sizing=export_exact(source,folder/'base.png',width,height,crop_box=crop_box,protected_regions=protected_regions,sizing_policy=policy)
        logo=learning_logo.composite(folder/'base.png',folder/'logo.png',pid,snapshot)
        final=folder/'final.jpg';limit=row.get('max_file_size_kb')
        if limit is None:
            with Image.open(folder/'logo.png') as image:image.convert('RGB').save(final,'JPEG',quality=95,optimize=True)
        else:
            budget=limit-(1/1024 if row.get('file_size_operator')=='lt' else 0)
            compress(str(folder/'logo.png'),str(final),budget,width,height)
        with Image.open(final) as checked:
            if checked.format!='JPEG' or checked.size!=(width,height) or checked.mode!='RGB':raise UserError('母版JPEG交付规格不符')
            checked.verify()
        data=final.read_bytes()
        if limit is not None and (len(data)>limit*1024 or row.get('file_size_operator')=='lt' and len(data)==limit*1024):
            raise UserError('母版JPEG超过版位大小限制')
        digest=hashlib.sha256(data).hexdigest();os.replace(final,target)
    return dict(path=str(target),placement_id=pid,width=width,height=height,format='JPEG',bytes=len(data),sha256=digest,
                exact_size_verified=True,crop_box=sizing['crop_box'],sizing={**{k:v for k,v in sizing.items() if k!='path'},'format':'JPEG'},
                logo=logo,mask={'mask_applied':False},corner_radius=0,
                processing_order=['exact_crop_and_resize','placement_logo','jpeg_encoding'])
