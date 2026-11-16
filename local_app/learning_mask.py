"""Deterministic bottom-gray mask shared by review previews and final export.

Only the masked 840×404 placement receives this overlay. The parameter values
are an initial visual choice under the user's rule, not measured platform limits.
No image provider, prompt planner, or sample bitmap is involved in compositing.
"""
from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile

from PIL import Image, ImageColor

from .config import ROOT, UserError

CONFIG_PATH = ROOT / 'config/learning-machine-mask-templates.json'
MASKED_PLACEMENT_ID = 'learning-youxuepai-masked-840x404'


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise UserError(name + '必须是有限数值')
    return float(value)


def _validated(value):
    if not isinstance(value, dict) or type(value.get('enabled')) is not bool:
        raise UserError('遮罩启用标记必须是布尔值')
    enabled = value['enabled']
    fraction = _number(value.get('height_fraction', 0 if not enabled else None), '遮罩高度比例')
    opacity = _number(value.get('max_opacity', 0 if not enabled else None), '遮罩透明度')
    if not (0 <= fraction <= 1) or (enabled and fraction <= 0) or not (0 <= opacity <= 1):
        raise UserError('遮罩高度和透明度必须在允许范围内')
    color = value.get('color', '#000000')
    if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        raise UserError('遮罩颜色必须为六位十六进制颜色')
    if value.get('curve', 'linear') != 'linear':
        raise UserError('当前仅支持线性底部渐变遮罩')
    preset_id = value.get('preset_id')
    if preset_id is not None and (not isinstance(preset_id, str) or not re.fullmatch(r'[a-zA-Z0-9._-]{1,100}', preset_id)):
        raise UserError('遮罩预设标识不正确')
    return {'enabled': enabled, 'preset_id': preset_id, 'height_fraction': fraction,
            'max_opacity': opacity, 'color': color.lower(), 'curve': 'linear',
            'parameter_basis': str(value.get('parameter_basis', 'frozen'))[:80]}


def config():
    """Return a fresh read-only preset description, with no user file paths."""
    value = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    presets = []
    for item in value['mask_presets']:
        checked = _validated({'enabled': True, 'preset_id': item['id'], **item})
        presets.append({'id': item['id'], 'label': item['label'],
                        **{key: checked[key] for key in ('height_fraction', 'max_opacity', 'color', 'curve', 'parameter_basis')}})
    return {'mask_presets': presets, 'mask_read_only': True, 'mask_parameter_note': value['basis']}


def preset_for(placement_id):
    """Get the placement's fixed mask policy; all other placements are disabled."""
    if not isinstance(placement_id, str):
        raise UserError('学习机遮罩版位不正确')
    if placement_id != MASKED_PLACEMENT_ID:
        return {'enabled': False, 'preset_id': None, 'height_fraction': 0.0,
                'max_opacity': 0.0, 'color': '#000000', 'curve': 'linear', 'parameter_basis': 'not_required'}
    value = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    placement = value['placements'][MASKED_PLACEMENT_ID]
    preset = next(p for p in config()['mask_presets'] if p['id'] == placement['preset_id'])
    return _validated({'enabled': placement['enabled'], 'preset_id': preset['id'], **preset})


# Kept as a convenience alias for callers using the originally discussed name.
presetFor = preset_for


def alpha_rows(height, template):
    """Per-row uint8 alpha. Coordinates match the front-end gradient endpoints."""
    if type(height) is not int or height <= 0:
        raise UserError('遮罩画布高度必须为正整数')
    selected = _validated(template)
    if not selected['enabled']:
        return [0] * height
    start = height * (1 - selected['height_fraction'])
    end = height - 1
    denominator = end - start
    rows = []
    for y in range(height):
        progress = (1 if y == end else 0) if denominator <= 0 else min(1, max(0, (y-start)/denominator))
        rows.append(math.floor(255 * selected['max_opacity'] * progress + 0.5))
    return rows


def apply_mask(source, target, placement_id, *, template=None,expected_size=None):
    """Apply the current or frozen preset once, after exact target sizing.

    A disabled mask preserves PNG bytes, or converts a non-PNG decoded image to
    PNG without resizing. Enabled masks preserve the source alpha silhouette.
    Callers should always pass their unmasked source, not reprocess a delivery.
    """
    source, target = Path(source), Path(target)
    if source.resolve() == target.resolve():
        raise UserError('遮罩处理需要独立输出文件，不能覆盖来源图')
    selected = preset_for(placement_id) if template is None else _validated(copy.deepcopy(template))
    if selected['enabled'] and placement_id != MASKED_PLACEMENT_ID:
        raise UserError('该版位固定不使用底部灰色遮罩')
    with Image.open(source) as opened:
        size = opened.size
        is_png = opened.format == 'PNG'
        original = opened.copy()
    if selected['enabled']:
        registered = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))['placements'][MASKED_PLACEMENT_ID]
        expected = expected_size if expected_size is not None else (registered['target_width'], registered['target_height'])
        if not isinstance(expected,(tuple,list)) or len(expected)!=2 or any(type(v) is not int or v<=0 for v in expected):
            raise UserError('冻结遮罩尺寸不正确')
        expected=tuple(expected)
        if size != expected:
            raise UserError('请先适配为'+str(expected[0])+'×'+str(expected[1])+'精确尺寸，再应用学习机遮罩')
    result = original
    if selected['enabled']:
        rgba = original.convert('RGBA')
        rows = alpha_rows(size[1], selected)
        alpha = Image.frombytes('L', size, b''.join(bytes([a])*size[0] for a in rows))
        color = Image.new('RGB', size, ImageColor.getrgb(selected['color']))
        result = Image.composite(color, rgba.convert('RGB'), alpha).convert('RGBA')
        result.putalpha(rgba.getchannel('A'))
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=target.parent, prefix='.learning-mask-', suffix='.png')
    os.close(fd)
    try:
        if not selected['enabled'] and is_png:
            shutil.copyfile(source, temporary)
        else:
            result.save(temporary, 'PNG', optimize=True)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {'mask_applied': selected['enabled'], 'preset_id': selected['preset_id'],
            'mask_template': copy.deepcopy(selected), 'width': size[0], 'height': size[1], 'format': 'PNG'}
