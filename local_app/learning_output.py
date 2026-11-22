"""Local learning-machine export from existing pixels; never generates images."""
from __future__ import annotations

import hashlib
from io import BytesIO
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageChops, ImageDraw, ImageStat

from .config import UserError
from . import learning_logo, learning_mask
from .learning_pipeline import CONTENT_BY_ID
from .learning_sizing import content_size, export_exact


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


def _indexed_transparent_picture(image,logo,snapshot,max_colors):
    """Keep the rounded alpha mask exact; reserve palette entries for its fringe.

    Only subpixel fringe colors are averaged. Opaque art uses median-cut and a
    dedicated brand palette, avoiding coarse octree bands over the whole image.
    """
    alpha=image.getchannel('A');levels=[i for i,n in enumerate(alpha.histogram()) if n and i<255]
    if len(levels)>192:
        return None
    colors=min(max_colors,256-len(levels));picture=_indexed_picture(image.convert('RGB'),logo,snapshot,colors=colors,brand_colors=min(48,colors//3))
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


def _png_bytes(image, **options):
    buffer = BytesIO()
    image.save(buffer, 'PNG', optimize=True, **options)
    return buffer.getvalue()


def _exact_palette(image):
    counts = image.getcolors(maxcolors=256)
    if counts is None:
        return None
    colors = [pixel for _, pixel in counts]
    indices = {pixel: index for index, pixel in enumerate(colors)}
    indexed = Image.frombytes('P', image.size, bytes(indices[pixel] for pixel in image.get_flattened_data()))
    indexed.putpalette([channel for color in colors for channel in color[:3]])
    if image.mode == 'RGBA':
        indexed.info['transparency'] = bytes(color[3] for color in colors).rstrip(b'\xff')
    bits = next(depth for depth in (1, 2, 4, 8) if len(colors) <= 2**depth)
    return _png_bytes(indexed, bits=bits), len(colors)


def _optimize_png(data, image, folder):
    """Use OxiPNG when installed, and accept only exactly equivalent pixels."""
    executable = shutil.which('oxipng')
    if executable is None:
        return data
    path = folder / 'lossless.png'
    path.write_bytes(data)
    try:
        subprocess.run([executable, '-o', '2', '--threads', '1', str(path)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        candidate = path.read_bytes()
        if len(candidate) < len(data):
            with Image.open(BytesIO(candidate)) as decoded:
                if (decoded.format == 'PNG' and decoded.size == image.size
                        and decoded.convert(image.mode).tobytes() == image.tobytes()
                        and (image.mode == 'RGBA' or decoded.convert('RGBA').getchannel('A').getextrema() == (255, 255))):
                    return candidate
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return data


def _encode_png(image, logo, snapshot, limit, folder):
    data = _png_bytes(image)
    exact = _exact_palette(image) if limit is not None else None
    colors = None
    if exact and len(exact[0]) < len(data):
        data, colors = exact
    if limit is not None and len(data) > limit:
        data = _optimize_png(data, image, folder)
    if limit is None or len(data) <= limit:
        return data, dict(pixel_lossless=True, palette_colors=colors, alpha_palette_quantized=False,
                          encoding_method='indexed' if colors is not None else 'truecolor')

    alpha = image.mode == 'RGBA'
    candidates = []
    for color_budget in (256, 224, 192, 160, 128, 112, 96, 80, 64, 48, 32, 16):
        picture = (_indexed_transparent_picture(image, logo, snapshot, color_budget) if alpha else
                   _indexed_picture(image, logo, snapshot, colors=color_budget, brand_colors=min(48, color_budget//3)))
        if picture is None:
            break
        encoded = _png_bytes(picture)
        if len(encoded) <= limit:
            candidates.append((picture, encoded, color_budget))
            break
    if alpha:
        # Alpha-preserving indexing may leave too few colors for the picture.
        # Compare its best fitting result with the existing octree fallback.
        for budget in (None, 256, 128, 64, 32, 16):
            candidate = image
            if budget is not None:
                candidate = image.convert('RGB').quantize(colors=budget).convert('RGBA')
                candidate.putalpha(image.getchannel('A'))
            picture = _indexed_rgba_fallback(candidate)
            encoded = _png_bytes(picture)
            if len(encoded) <= limit:
                candidates.append((picture, encoded, budget))
                break
    if not candidates:
        raise UserError('图片已达到精确尺寸，但超过该版位PNG大小限制，请压缩或简化画面；不会缩小交付尺寸')

    reference = image.convert('RGBA')
    neutral = Image.new('RGBA', image.size, (128, 128, 128, 255))
    visible = Image.alpha_composite(neutral, reference).convert('RGB')
    def error(candidate):
        rendered = candidate[0].convert('RGBA')
        composite = Image.alpha_composite(neutral, rendered).convert('RGB')
        rgb_error = ImageStat.Stat(ImageChops.difference(visible, composite)).sum2
        alpha_error = ImageStat.Stat(ImageChops.difference(reference.getchannel('A'), rendered.getchannel('A'))).sum2
        return sum(rgb_error) + sum(alpha_error)
    picture, data, color_budget = min(candidates, key=error)
    alpha_quantized = picture.convert('RGBA').getchannel('A').tobytes() != reference.getchannel('A').tobytes()
    return data, dict(pixel_lossless=False, palette_colors=len(picture.getcolors()), picture_palette_colors=color_budget,
                      alpha_palette_quantized=alpha_quantized, encoding_method='indexed')


def _add_right_panel(artwork, target, width):
    with Image.open(artwork) as opened:
        image = opened.convert('RGBA')
    # Use the dominant color near the join and keep it dark enough for the
    # white app label that the device draws over the panel.
    edge_width = max(1, image.width // 12)
    edge = image.crop((image.width-edge_width, 0, image.width, image.height)).convert('RGB').quantize(colors=8)
    palette_index = max(edge.getcolors())[1]
    rgb = edge.getpalette()[palette_index*3:palette_index*3+3]
    luma = sum(channel*weight for channel, weight in zip(rgb, (.2126, .7152, .0722)))
    color = tuple(round(channel*min(1, 110/max(1, luma))) for channel in rgb)
    canvas = Image.new('RGBA', (width, image.height), (*color, 255))
    canvas.paste(image, (0, 0))
    canvas.save(target, 'PNG')
    return {'artwork_width': image.width, 'fill_width': width-image.width, 'fill_rgb': list(color)}


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
        artwork_width, _ = content_size(row)
        exact_path = folder/'sized.png'
        sizing=export_exact(source,exact_path,artwork_width,height,crop_box=crop_box,protected_regions=protected_regions,sizing_policy=sizing_policy)
        if artwork_width < width:
            panel_path = folder/'with-panel.png'
            sizing.update(width=width, right_panel=_add_right_panel(exact_path, panel_path, width))
            exact_path = panel_path
        mask=learning_mask.apply_mask(exact_path,folder/'masked.png',placement_id,template=template,expected_size=(width,height))
        logo=learning_logo.composite(folder/'masked.png',folder/'logo.png',placement_id,logo_snapshot)
        with Image.open(folder/'logo.png') as opened:image=opened.convert('RGBA')
        radius=row['corner_radius'];limit=row.get('max_file_size_kb')
        if radius:
            scale=4
            alpha=Image.new('L',(width*scale,height*scale),0)
            ImageDraw.Draw(alpha).rounded_rectangle((0,0,width*scale-1,height*scale-1),radius=radius*scale,fill=255)
            alpha=alpha.resize((width,height),Image.Resampling.LANCZOS)
            image.putalpha(ImageChops.multiply(image.getchannel('A'),alpha))
        if image.getchannel('A').getextrema()==(255,255):
            image=image.convert('RGB')
        max_bytes = (limit*1024 - (1 if row.get('file_size_operator')=='lt' else 0)) if limit is not None else None
        data, encoding = _encode_png(image, logo, logo_snapshot, max_bytes, folder)
        finished=folder/'finished.png'
        finished.write_bytes(data)
        size=len(data)
        with Image.open(finished) as checked:
            if checked.format!='PNG' or checked.size!=(width,height):raise UserError('导出图片尺寸核验失败')
            checked.verify()
        digest=hashlib.sha256(data).hexdigest()
        os.replace(finished,target)
    return dict(path=str(target),placement_id=placement_id,width=width,height=height,format='PNG',bytes=size,
                sha256=digest,exact_size_verified=True,crop_box=sizing['crop_box'],sizing={k:v for k,v in sizing.items() if k!='path'},mask=mask,logo=logo,
                corner_radius=radius,badge_applied=False,feature_label_drawn=False,**encoding,
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
