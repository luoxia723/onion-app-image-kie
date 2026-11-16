"""Validate objective delivery requirements; visual choice belongs to the user."""
from pathlib import Path
from io import BytesIO
import hashlib
import json
import zipfile
from PIL import Image
from .config import UserError


def verify_image_bytes(data, placement, expected_sha256):
    limit=placement.get('max_file_size_kb');limit=limit*1024 if limit else None
    if limit is not None and (len(data)>limit or placement.get('file_size_operator')=='lt' and len(data)==limit):
        raise UserError('成品超过渠道文件大小限制')
    try:
        with Image.open(BytesIO(data)) as image:
            expected=placement.get('output_format','JPEG')
            if image.format!=expected: raise UserError('交付文件必须是 '+expected)
            if image.size!=(placement['target_width'],placement['target_height']): raise UserError('成品尺寸不符，请重新适配')
            if image.mode not in (('RGB','RGBA','P') if expected=='PNG' else ('RGB',)): raise UserError('交付文件色彩模式不符')
            if placement.get('alpha_sha256') and hashlib.sha256(image.convert('RGBA').getchannel('A').tobytes()).hexdigest()!=placement['alpha_sha256']:
                raise UserError('成品圆角或透明边缘校验失败')
            image.load()
    except (OSError,ValueError): raise UserError('成品文件无法读取，请重新处理') from None
    if hashlib.sha256(data).hexdigest()!=expected_sha256:
        raise UserError('成品文件校验失败，请重新处理')


def verify_delivery_file(slot, placement):
    try: data=Path(slot.get('jpeg') or '').read_bytes()
    except OSError: raise UserError('成品文件无法读取，请重新处理') from None
    verify_image_bytes(data,placement,slot.get('sha256'))


def verify_saved_package(path, fingerprint, placements):
    """Check the actual archive, not just its index record, without extracting it."""
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.getinfo('交付清单.json').file_size>1024*1024: raise ValueError()
            manifest=json.loads(archive.read('交付清单.json'))
            records=manifest['images']
            if not records or not isinstance(records,list): raise ValueError()
            expected={'交付清单.json',*(x['path'] for x in records)}
            files=[x.filename for x in archive.infolist() if not x.is_dir()]
            if len(files)!=len(records)+1 or set(files)!=expected: raise ValueError()
            for item in records:
                placement=manifest.get('placement_rules',{}).get(item['placement_id']) or placements[item['placement_id']]
                expected_ext='.png' if placement.get('output_format')=='PNG' else '.jpg'
                if Path(item['path']).suffix.lower()!=expected_ext:raise ValueError()
                info=archive.getinfo(item['path'])
                limit=placement.get('max_file_size_kb')
                if info.file_size!=item['bytes'] or limit and info.file_size>limit*1024: raise ValueError()
                verify_image_bytes(archive.read(item['path']),placement,item['sha256'])
            layered=manifest.get('fingerprint_schema')==3
            values=sorted((x['placement_id'],x['set'],x['image'],x['sha256'],x.get('logo_asset_id','')) if layered
                          else (x['placement_id'],x['set'],x['image'],x['sha256']) for x in records)
            actual=hashlib.sha256(json.dumps(values,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
            if actual!=fingerprint: raise ValueError()
    except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile,UserError):
        raise UserError('图包文件校验失败，请重新保存；原文件已保留') from None
    return manifest
