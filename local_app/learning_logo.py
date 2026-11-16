"""Learning-machine logo templates and deterministic, post-size logo compositing.

Logo presence belongs to the placement contract. This module only lets a user
choose one registered logo and its bounds where that placement requires one.
It never calls an image or planning provider and never changes a saved task.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading

from PIL import Image

from .config import ROOT, UserError

CONTENT_PATH = ROOT / 'config/learning-machine-content-rules.json'
DEFAULTS_PATH = ROOT / 'config/learning-machine-logo-templates.json'
STATE_NAME = 'learning-machine-logo-templates.json'
ASSET_IDS = frozenset(('learning.logo.black', 'learning.logo.white-app'))
_LOCK = threading.RLock()


def _defaults():
    return json.loads(DEFAULTS_PATH.read_text(encoding='utf-8'))


def _placements():
    return {p['id']: p for p in json.loads(CONTENT_PATH.read_text(encoding='utf-8'))['placements']}


def _asset(asset_id):
    if not isinstance(asset_id, str) or asset_id not in ASSET_IDS:
        raise UserError('请选择黑字标准版或白字 APP 版 Logo')
    return next(a for a in _defaults()['assets'] if a['id'] == asset_id)


def asset_path(asset_id):
    """Resolve a registered id, never a client-supplied local path."""
    asset = _asset(asset_id)
    path = (ROOT / asset['path']).resolve()
    if path.parent != (ROOT / 'assets/logos').resolve() or not path.is_file():
        raise UserError('Logo 素材缺失，请恢复项目内置素材')
    if hashlib.sha256(path.read_bytes()).hexdigest() != asset['sha256']:
        raise UserError('Logo 素材校验失败，请恢复项目内置素材')
    return path


def _sample_records(placements=None):
    """Register project-local references from the current content evidence.

    The source sample filename is provenance, not a client-controlled filesystem
    path. Canonical project files are named by the already-registered placement.
    A one-pixel-different reference remains usable for logo positioning only.
    """
    records = {}
    for pid, placement in (placements if placements is not None else _placements()).items():
        evidence = placement.get('evidence', {})
        filename = evidence.get('sample_file')
        if evidence.get('kind') != 'sample_review' or not filename:
            records[pid] = None
            continue
        if (not isinstance(pid, str) or not re.fullmatch(r'learning-[a-z0-9-]+', pid) or not isinstance(filename, str)
                or '/' in filename or '\\' in filename or Path(filename).name != filename
                or not filename.lower().endswith('.png')):
            raise UserError('学习机样图注册信息不正确')
        records[pid] = {
            'path': 'assets/learning-machine/samples/' + pid + '.png',
            'sha256': evidence.get('sha256'),
            'sample_size': evidence.get('sample_size'),
            'target_size_matches': evidence.get('target_size_matches', True),
        }
    return records


def _sample_file(record):
    if not isinstance(record, dict):
        return None
    relative = record.get('path')
    if not isinstance(relative, str) or not relative:
        return None
    candidate = (ROOT / relative).resolve()
    if candidate.parent != (ROOT / 'assets/learning-machine/samples').resolve() or not candidate.is_file():
        return None
    if hashlib.sha256(candidate.read_bytes()).hexdigest() != record.get('sha256'):
        raise UserError('学习机样图校验失败')
    return candidate


def sample_path(placement_id):
    """Optional read-only registered sample, never an arbitrary supplied path."""
    placements = _placements()
    if not isinstance(placement_id, str) or placement_id not in placements:
        raise UserError('学习机版位不存在', 404)
    return _sample_file(_sample_records(placements).get(placement_id))


def _public_assets():
    values = []
    for asset in _defaults()['assets']:
        asset_path(asset['id'])
        values.append({key: asset[key] for key in ('id', 'label', 'width', 'height')} |
                      {'url': '/api/learning-machine/logo-assets/' + asset['id'],
                       'aspect_ratio': asset['width'] / asset['height'],
                       'note': '白字 APP 组合，与黑字标准版不是同款反色' if asset['id'].endswith('white-app') else '原版黑字标准组合'})
    return values


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise UserError(label + '必须是有限数值')
    return float(value)


def _validated_template(placement, value,*,asset_metadata=None):
    if not placement['modules']['logo']:
        raise UserError('该版位固定无 Logo，不能配置或启用 Logo')
    if not isinstance(value, dict) or set(value) - {'asset_id', 'x', 'y', 'width', 'basis'}:
        raise UserError('Logo 模板只允许选择素材、位置和宽度；Logo 有无由版位固定')
    asset = _asset(value.get('asset_id'))
    if asset_metadata is not None:
        if any(type(asset_metadata.get(k)) is not int or asset_metadata[k]<=0 for k in ('width','height')):
            raise UserError('冻结Logo尺寸不正确')
        asset={**asset,**{k:asset_metadata[k] for k in ('width','height')}}
    x = _number(value.get('x'), '横向位置')
    y = _number(value.get('y'), '纵向位置')
    width = _number(value.get('width'), 'Logo 宽度')
    target_width, target_height = placement['target_width'], placement['target_height']
    height = width * target_width / target_height * asset['height'] / asset['width']
    if x < 0 or y < 0 or width <= 0 or width * target_width < 1:
        raise UserError('Logo 位置不能为负，宽度至少为 1 像素')
    if x + width > 1 + 1e-9 or y + height > 1 + 1e-9:
        raise UserError('Logo 超出目标画布，请调整位置或大小')
    return {'asset_id': asset['id'], 'x': x, 'y': y, 'width': width}


def _load_state(settings):
    path = Path(settings.state_dir) / STATE_NAME
    if not path.exists():
        return {'schema_version': 1, 'revision': 0, 'templates': {}}
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(value, dict) or type(value.get('revision')) is not int or value['revision'] < 0
                or value.get('schema_version') != 1 or not isinstance(value.get('templates'), dict)):
            raise ValueError()
        return value
    except (OSError, ValueError, TypeError):
        raise UserError('学习机 Logo 配置无法读取，请先保留并检查配置文件') from None


def _resolved(settings):
    defaults = _defaults()
    placements = _placements()
    state = _load_state(settings)
    templates = {}
    for pid, placement in placements.items():
        if not placement['modules']['logo']:
            templates[pid] = None
            continue
        value = state['templates'].get(pid, defaults['templates'].get(pid))
        if value is None:
            raise UserError('该学习机版位缺少初始 Logo 模板：' + pid)
        templates[pid] = _validated_template(placement, value)
    for pid in state['templates']:
        if pid not in placements or not placements[pid]['modules']['logo']:
            raise UserError('已保存的 Logo 模板包含无效或固定无 Logo 的版位')
    return state, placements, templates


def config(settings):
    with _LOCK:
        state, placements, templates = _resolved(settings)
        sample_records = _sample_records(placements)
        rows = []
        for pid, placement in placements.items():
            row = {key: copy.deepcopy(placement[key]) for key in
                   ('id', 'platform', 'name', 'target_width', 'target_height', 'image_count', 'category', 'category_label')}
            row.update(logo_required=placement['modules']['logo'], content_modules=copy.deepcopy(placement['modules']),
                       logo_template=copy.deepcopy(templates[pid]))
            try:
                reference = sample_records.get(pid)
                if _sample_file(reference) is not None:
                    row['sample_url'] = '/api/learning-machine/samples/' + pid
                    row['sample_size'] = copy.deepcopy(reference['sample_size'])
                    row['sample_reference_only'] = True
                    row['sample_note'] = '样图含原Logo，仅供位置参考，不作为直接成品替代。'
                    if reference.get('target_size_matches') is False:
                        sw, sh = reference['sample_size']
                        row['sample_note'] = (f'近尺寸参考：样图 {sw}×{sh}，目标 '
                                              f'{placement["target_width"]}×{placement["target_height"]}；'
                                              '仅供Logo位置参考，不作为直接成品替代。')
            except UserError:
                pass  # An optional reference must not block configuring a placement.
            rows.append(row)
        return {'revision': state['revision'], 'logo_assets': _public_assets(), 'placements': rows}


def _write_state(settings, state):
    directory = Path(settings.state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=directory, prefix='.learning-logo-', suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        os.replace(temporary, directory / STATE_NAME)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save_templates(settings, data):
    """Atomically save a partial set of per-placement templates with revision checking."""
    if not isinstance(data, dict) or type(data.get('revision')) is not int or not isinstance(data.get('templates'), list):
        raise UserError('请提交当前配置版本和 Logo 模板列表')
    if len(data['templates']) > 44:
        raise UserError('Logo 模板数量不正确')
    with _LOCK:
        state, placements, _ = _resolved(settings)
        if data['revision'] != state['revision']:
            raise UserError('另一窗口已更新 Logo 模板，请重新载入后保存', 409)
        updates = {}
        for row in data['templates']:
            if not isinstance(row, dict) or set(row) - {'placement_id', 'asset_id', 'x', 'y', 'width'}:
                raise UserError('Logo 模板字段不正确，不接受本机路径或有无开关')
            pid = row.get('placement_id')
            if not isinstance(pid, str) or pid not in placements or pid in updates:
                raise UserError('Logo 版位不存在或重复')
            updates[pid] = _validated_template(placements[pid], {k: v for k, v in row.items() if k != 'placement_id'})
        next_templates = {**state['templates'], **updates}
        if next_templates != state['templates']:
            _write_state(settings, {'schema_version': 1, 'revision': state['revision'] + 1, 'templates': next_templates})
        return config(settings)


def freeze_templates(settings, placement_ids, cache=None):
    """Snapshot placement settings; optional assets are copied into the round cache."""
    with _LOCK:
        public = config(settings)
        by_id = {p['id']: p for p in public['placements']}
        if not isinstance(placement_ids, (list, tuple)) or any(not isinstance(pid, str) or pid not in by_id for pid in placement_ids):
            raise UserError('学习机 Logo 快照的版位不正确')
        snapshot = {'schema_version': 1, 'revision': public['revision'], 'placements': {}, 'assets': {}}
        for pid in dict.fromkeys(placement_ids):
            row = by_id[pid]
            snapshot['placements'][pid] = {key: copy.deepcopy(row[key]) for key in
                                          ('id', 'target_width', 'target_height', 'logo_required', 'logo_template')}
            if not row['logo_required']:
                continue
            aid = row['logo_template']['asset_id']
            if aid in snapshot['assets']:
                continue
            asset = _asset(aid)
            source = asset_path(aid)
            if cache is not None:
                folder = Path(cache) / 'learning-logo-assets'
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / (aid + '.png')
                if source.resolve() != target.resolve():
                    shutil.copy2(source, target)
                source = target
            snapshot['assets'][aid] = {key: asset[key] for key in ('id', 'width', 'height', 'sha256')} | {'path': str(source)}
        return snapshot


def composite(source, target, placement_id, snapshot):
    """Apply the frozen logo after exact sizing, without mutating the source file."""
    if Path(source).resolve() == Path(target).resolve():
        raise UserError('Logo 合成需要独立输出文件，不能覆盖来源图')
    try:
        row = snapshot['placements'][placement_id]
        width, height = row['target_width'], row['target_height']
    except (KeyError, TypeError):
        raise UserError('学习机 Logo 冻结配置不完整') from None
    with Image.open(source) as opened:
        if opened.size != (width, height):
            raise UserError('请先适配到目标精确尺寸，再叠加 Logo')
        image = opened.convert('RGBA')
    metadata = {'logo_applied': False, 'logo_template_revision': snapshot['revision'], 'width': width, 'height': height}
    if row['logo_required']:
        template = row['logo_template'];asset = _asset(template['asset_id'])
        frozen = snapshot['assets'].get(asset['id'], {})
        path = Path(frozen.get('path', ''))
        cached=path.parent.name == 'learning-logo-assets' and path.name == asset['id'] + '.png'
        allowed=cached or path.resolve() == asset_path(asset['id']).resolve()
        expected=frozen.get('sha256')
        if not isinstance(expected,str) or not re.fullmatch('[a-f0-9]{64}',expected):raise UserError('冻结Logo校验信息不完整')
        if not allowed or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise UserError('冻结 Logo 素材缺失或校验失败')
        checked = _validated_template({'modules': {'logo': True}, 'target_width': width, 'target_height': height}, template,asset_metadata=frozen)
        asset={**asset,**{k:frozen[k] for k in ('width','height')}}
        logo_width = max(1, round(checked['width'] * width))
        logo_height = max(1, round(logo_width * asset['height'] / asset['width']))
        x = min(width-logo_width, round(checked['x'] * width));y = min(height-logo_height, round(checked['y'] * height))
        with Image.open(path) as opened:
            logo = opened.convert('RGBA').resize((logo_width, logo_height), Image.Resampling.LANCZOS)
        image.alpha_composite(logo, (x, y))
        metadata.update(logo_applied=True, logo_asset_id=asset['id'], pixel_box=[x, y, logo_width, logo_height])
    target = Path(target);target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.logo-tmp.png')
    try:
        image.save(temporary, 'PNG', optimize=True)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return metadata


def variant_snapshot(snapshot,asset_id,cache):
    """Choose a registered export mark while preserving per-placement bounds."""
    asset=_asset(asset_id);source=asset_path(asset_id)
    result=copy.deepcopy(snapshot)
    folder=Path(cache)/'learning-logo-assets';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(asset_id+'.png')
    if not path.exists():shutil.copy2(source,path)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=asset['sha256']:raise UserError('导出Logo素材校验失败')
    result['assets'][asset_id]={key:asset[key] for key in ('id','width','height','sha256')}|{'path':str(path)}
    for row in result['placements'].values():
        if not row['logo_required']:continue
        template=row['logo_template'];template['asset_id']=asset_id
        height=template['width']*row['target_width']/row['target_height']*asset['height']/asset['width']
        if height>1:template['width']/=height;height=1
        template['y']=min(template['y'],max(0,1-height))
    return result
