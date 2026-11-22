"""Local learning-machine export from existing pixels; never generates images."""
from __future__ import annotations

import hashlib
from io import BytesIO
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from PIL import Image, ImageChops

from scripts.image_quality import EncodingQuality, logo_bounds, tight_png_budget
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


class _AlphaPalette:
    """Reserve the original alpha coverage and keep local colors on rounded edges."""

    def __init__(self, image, *, local_edge_colors=False):
        alpha = image.getchannel('A')
        self.alpha = alpha.tobytes()
        levels = [level for level, count in enumerate(alpha.histogram()) if count and level < 255]
        samples = {level: [0, 0, 0, 0] for level in levels}
        edges = {level: [] for level in levels if local_edge_colors and level > 0}
        for position, (r, g, b, a) in enumerate(image.get_flattened_data()):
            if a in edges:
                edges[a].append((position, (r, g, b)))
            elif a < 255:
                totals = samples[a]
                totals[0] += r
                totals[1] += g
                totals[2] += b
                totals[3] += 1
        self.levels = []
        self.fringe_colors = []
        self.fringe_defaults = {}
        self.edge_entries = {}
        for level in levels:
            start = len(self.levels)
            self.fringe_defaults[level] = start
            if level in edges:
                points = edges[level]
                strip = Image.new('RGB', (len(points), 1))
                strip.putdata([color for _, color in points])
                # At higher coverage, one color shared by all four corners can
                # draw a colored rim. Two colors retain local edge contrast.
                palette = strip.quantize(colors=min(len(points), 2 if level >= 64 else 1),
                                         method=Image.Quantize.MEDIANCUT)
                indices = palette.tobytes()
                count = max(indices) + 1
                self.levels.extend([level] * count)
                self.fringe_colors.extend(palette.getpalette()[:3 * count])
                self.edge_entries.update((pos, start + index) for (pos, _), index in zip(points, indices) if index)
            else:
                r, g, b, count = samples[level]
                self.levels.append(level)
                self.fringe_colors.extend([0, 0, 0] if local_edge_colors else [round(value / count) for value in (r, g, b)])
        self.max_colors = 256 - len(self.levels)

    def apply(self, indexed):
        indices = indexed.tobytes()
        colors = max(indices) + 1
        if colors > self.max_colors:
            raise ValueError('No palette space left for original alpha values')
        fringe = {a: colors + i for a, i in self.fringe_defaults.items()}
        mapped = bytearray(i if a == 255 else fringe[a] for i, a in zip(indices, self.alpha))
        for position, index in self.edge_entries.items():
            mapped[position] = colors + index
        result = Image.frombytes('P', indexed.size, bytes(mapped))
        result.putpalette(indexed.getpalette()[:colors*3] + self.fringe_colors)
        result.info['transparency'] = bytes([255]*colors + self.levels)
        return result


def _rounded_alpha(width, height, radius, *, coverage_steps):
    """Compute the fraction of each edge pixel covered by the rounded rectangle."""
    radius = min(radius, width // 2, height // 2)
    alpha = Image.new('L', (width, height), 255)
    if not radius:
        return alpha
    radius_squared = radius * radius

    def circle_integral(x):
        return (x * math.sqrt(radius_squared - x*x) + radius_squared * math.asin(x / radius)) / 2

    corner_data = bytearray()
    for y in range(radius):
        # In a single quadrant, the lower and upper bounds of the pixel row
        # determine which columns are entirely outside or inside the circle.
        bottom = radius - y - 1
        full = math.sqrt(radius_squared - (bottom + 1)**2)
        empty = math.sqrt(radius_squared - bottom**2)
        first_partial = radius - math.ceil(empty)
        first_opaque = radius - math.floor(full)
        corner_data.extend(b'\x00' * first_partial)
        for x in range(first_partial, first_opaque):
            left = radius - x - 1
            start = max(left, full)
            end = min(left + 1, empty)
            area = max(0, full - left) + circle_integral(end) - circle_integral(start) - bottom * (end - start)
            level = min(coverage_steps, max(0, round(area * coverage_steps)))
            corner_data.append(round(255 * level / coverage_steps))
        corner_data.extend(b'\xff' * (radius - first_opaque))

    corner = Image.frombytes('L', (radius, radius), bytes(corner_data))
    right = corner.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    alpha.paste(corner, (0, 0))
    alpha.paste(right, (width - radius, 0))
    alpha.paste(corner.transpose(Image.Transpose.FLIP_TOP_BOTTOM), (0, height - radius))
    alpha.paste(right.transpose(Image.Transpose.FLIP_TOP_BOTTOM), (width - radius, height - radius))
    return alpha


class _LogoPalette:
    """Keep a small set of brand colors for the opaque pixels of the Logo."""

    def __init__(self, image, logo, snapshot):
        x, y, width, height = logo['pixel_box']
        with Image.open(snapshot['assets'][logo['logo_asset_id']]['path']) as original:
            mark = original.convert('RGBA').resize((width, height), Image.Resampling.LANCZOS)
        opaque = [(index, pixel[:3]) for index, pixel in enumerate(mark.get_flattened_data()) if pixel[3] == 255]
        self.indices = []
        self.colors = []
        if not opaque:
            return
        samples = Image.new('RGB', (len(opaque), 1))
        samples.putdata([color for _, color in opaque])
        palette = samples.quantize(colors=min(24, len(opaque)), method=Image.Quantize.MEDIANCUT)
        self.colors = palette.getpalette()[:(max(palette.tobytes()) + 1)*3]
        self.indices = [((y + offset // width)*image.width+x+offset % width, index)
                        for (offset, _), index in zip(opaque, palette.tobytes())]

    @property
    def size(self):
        return len(self.colors) // 3

    def apply(self, picture):
        if not self.colors:
            return picture
        indices = bytearray(picture.tobytes())
        offset = max(indices) + 1
        if offset + self.size > 256:
            raise ValueError('No palette space left for Logo colors')
        for position, index in self.indices:
            indices[position] = offset + index
        result = Image.frombytes('P', picture.size, bytes(indices))
        result.putpalette(picture.getpalette()[:offset*3] + self.colors)
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
    if image.info.get('icc_profile'):
        indexed.info['icc_profile'] = image.info['icc_profile']
    if image.mode == 'RGBA':
        indexed.info['transparency'] = bytes(color[3] for color in colors).rstrip(b'\xff')
    bits = next(depth for depth in (1, 2, 4, 8) if len(colors) <= 2**depth)
    return _png_bytes(indexed, bits=bits), len(colors)


def _optimize_png(data, image, folder, *, zopfli=False, timeout=3):
    """Use OxiPNG when installed, and accept only exactly equivalent pixels."""
    executable = shutil.which('oxipng')
    if executable is None:
        return data
    path = folder / 'lossless.png'
    path.write_bytes(data)
    args = [executable, '-o', '3' if zopfli else '2', '--threads', '1']
    if zopfli:
        args.append('-Z')
    try:
        subprocess.run([*args, str(path)], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=timeout)
        candidate = path.read_bytes()
        if len(candidate) < len(data):
            with Image.open(BytesIO(candidate)) as decoded:
                if (decoded.format == 'PNG' and decoded.size == image.size
                        and decoded.info.get('icc_profile') == image.info.get('icc_profile')
                        and decoded.convert('RGBA').tobytes() == image.convert('RGBA').tobytes()):
                    return candidate
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return data


_COLOR_BUDGETS = (16, 24, 32, 40, 48, 56, 64, 72, 80, 96, 112, 128, 144, 160, 192, 224, 256)


def _pngquant_candidates(rgb, alpha, brand, limit, folder):
    executable = shutil.which('pngquant')
    # pngquant's input decoder may transform custom color profiles. Preserve
    # the profile with the Pillow path for those images.
    if executable is None or rgb.info.get('icc_profile'):
        return
    source = folder / 'quantization-source.png'
    rgb.save(source, 'PNG', compress_level=1)
    maximum = (alpha.max_colors if alpha else 256) - (brand.size if brand else 0)
    levels = sorted({min(maximum, budget) for budget in _COLOR_BUDGETS})
    levels = [budget for budget in levels if budget >= 16]
    deadline = time.monotonic() + 8
    env = dict(os.environ, RAYON_NUM_THREADS='1')
    for dither in ('0', '0.35', '1'):
        low, high = 0, len(levels) - 1
        index = high
        while low <= high:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            colors = levels[index]
            target = folder / 'quantization-result.png'
            target.unlink(missing_ok=True)
            try:
                subprocess.run([executable, '--speed', '4', '--floyd='+dither, '--output', str(target),
                                str(colors), '--', str(source)], check=True, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=min(remaining, 2))
                with Image.open(target) as decoded:
                    if decoded.format != 'PNG' or decoded.mode != 'P' or decoded.size != rgb.size:
                        return
                    picture = decoded.copy()
                data = target.read_bytes()
                if brand:
                    picture = brand.apply(picture)
                if alpha:
                    picture = alpha.apply(picture)
                if alpha or brand:
                    data = _png_bytes(picture)
            except (OSError, ValueError, subprocess.SubprocessError):
                return
            if limit < len(data) <= limit * 1.12:
                data = _optimize_png(data, picture, folder)
            if len(data) <= limit:
                yield picture, data, colors, 'pngquant', float(dither)
                low = index + 1
            else:
                high = index - 1
            index = (low + high) // 2


def _joint_png_candidates(rgb, alpha, brand, limit, folder):
    """Try joint palette and scanline optimization on a tightly budgeted export."""
    executable = shutil.which('onion-learning-png')
    if executable is None or rgb.info.get('icc_profile'):
        return
    maximum = (alpha.max_colors if alpha else 256) - (brand.size if brand else 0)
    if maximum < 16:
        return
    source = folder / 'quantization-source.rgb'
    source.write_bytes(rgb.tobytes())
    deadline = time.monotonic() + 8
    env = dict(os.environ, RAYON_NUM_THREADS='1')
    width, height = rgb.size
    budgets = dict.fromkeys(min(maximum, n) for n in (256, 208, 192, 160, 112, 80, 48))
    for budget in budgets:
        for mode in ('min', 'joint'):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            try:
                raw = subprocess.run([executable, str(source), str(width), str(height), str(budget), mode],
                                     check=True, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     timeout=min(remaining, 3)).stdout
            except (OSError, subprocess.CalledProcessError):
                return
            except subprocess.TimeoutExpired:
                continue
            size = int.from_bytes(raw[:2], 'little')
            start = 2 + 3 * size
            if not 1 <= size <= 256 or len(raw) != start + width * height:
                return
            indices = raw[start:]
            used = sorted(set(indices))
            if used[-1] >= size or len(used) > maximum:
                continue
            picture = Image.frombytes('P', rgb.size, indices)
            picture.putpalette(raw[2:start])
            if used[-1] + 1 != len(used):
                picture = picture.remap_palette(used)
            if brand:
                picture = brand.apply(picture)
            if alpha:
                picture = alpha.apply(picture)
            data = _png_bytes(picture)
            remaining = deadline - time.monotonic()
            if limit < len(data) <= limit * 1.12 and remaining > 0:
                data = _optimize_png(data, picture, folder, timeout=min(remaining, 3))
                remaining = deadline - time.monotonic()
                if limit < len(data) <= limit * 1.015 and remaining > 0:
                    data = _optimize_png(data, picture, folder, zopfli=True, timeout=min(remaining, 2))
            if len(data) <= limit:
                yield picture, data, len(used), 'zenquant', None


def _encode_png(image, logo, snapshot, limit, folder, *, local_edge_colors=False):
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

    alpha = _AlphaPalette(image, local_edge_colors=local_edge_colors) if image.mode == 'RGBA' else None
    rgb = image.convert('RGB')
    maximum = alpha.max_colors if alpha else 256
    candidates = []
    for color_budget in sorted({min(maximum, budget) for budget in _COLOR_BUDGETS}, reverse=True):
        if color_budget < 16:
            continue
        picture = _indexed_picture(rgb, logo, snapshot, colors=color_budget, brand_colors=min(48, color_budget//3))
        if alpha:
            picture = alpha.apply(picture)
        encoded = _png_bytes(picture, icc_profile=image.info.get('icc_profile'))
        if len(encoded) <= limit:
            candidates.append((picture, encoded, color_budget, 'pillow', 0))
            break
    brand = _LogoPalette(rgb, logo, snapshot) if logo.get('logo_applied') else None
    candidates.extend(_pngquant_candidates(rgb, alpha, brand, limit, folder))
    if not candidates or tight_png_budget(image.width, image.height, limit):
        candidates.extend(_joint_png_candidates(rgb, alpha, brand, limit, folder))
    quality = EncodingQuality(image, logo_bounds(logo.get('pixel_box')))
    if alpha and not candidates:
        # Exact fringe levels may exhaust the palette. Preserve the fully
        # opaque and transparent silhouette even for a reduced fringe.
        for budget in (None, 256, 128, 64, 32, 16, 8, 4):
            candidate = image
            if budget is not None:
                candidate = image.convert('RGB').quantize(colors=budget).convert('RGBA')
                candidate.putalpha(image.getchannel('A'))
            picture = _indexed_rgba_fallback(candidate)
            encoded = _png_bytes(picture, icc_profile=image.info.get('icc_profile'))
            if len(encoded) <= limit and quality.alpha_status(picture)[0]:
                candidates.append((picture, encoded, budget, 'pillow-octree', 0))
                break
    if not candidates:
        raise UserError('图片已达到精确尺寸，但超过该版位PNG大小限制，请压缩或简化画面；不会缩小交付尺寸')

    picture, data, color_budget, method, dither = min(candidates, key=lambda item: (quality.loss(item[0]), len(item[1])))
    alpha_quantized = not quality.alpha_status(picture)[1]
    return data, dict(pixel_lossless=False, palette_colors=len(picture.getcolors()), picture_palette_colors=color_budget,
                      alpha_palette_quantized=alpha_quantized, encoding_method='indexed', compressor=method, dither=dither)


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
        local_edge_colors=False
        if radius:
            # Limit the number of alpha values needed by indexed PNG, leaving
            # palette entries for the artwork under a channel byte limit.
            alpha=_rounded_alpha(width,height,radius,coverage_steps=32 if limit is not None else 255)
            original_alpha=image.getchannel('A')
            local_edge_colors=original_alpha.getextrema()==(255,255)
            image.putalpha(ImageChops.multiply(original_alpha,alpha))
        if image.getchannel('A').getextrema()==(255,255):
            image=image.convert('RGB')
        max_bytes = (limit*1024 - (1 if row.get('file_size_operator')=='lt' else 0)) if limit is not None else None
        data, encoding = _encode_png(image, logo, logo_snapshot, max_bytes, folder, local_edge_colors=local_edge_colors)
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
            compress(str(folder/'logo.png'),str(final),budget,width,height,pixel_box=logo.get('pixel_box'))
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
