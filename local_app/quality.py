"""Validate objective delivery requirements; visual choice belongs to the user."""
from pathlib import Path
from io import BytesIO
import hashlib
import json
import zipfile
from PIL import Image
from .config import UserError


def verify_image_bytes(data, placement, expected_sha256):
    limit=placement['max_file_size_kb']*1024
    if len(data)>limit or (placement.get('file_size_operator')=='lt' and len(data)==limit):
        raise UserError('成品超过渠道文件大小限制')
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format!='JPEG': raise UserError('交付文件必须是 JPEG')
            if image.size!=(placement['target_width'],placement['target_height']): raise UserError('成品尺寸不符，请重新适配')
            if image.mode!='RGB': raise UserError('交付文件必须使用 RGB 色彩模式')
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
                info=archive.getinfo(item['path'])
                if info.file_size!=item['bytes'] or info.file_size>placement['max_file_size_kb']*1024: raise ValueError()
                verify_image_bytes(archive.read(item['path']),placement,item['sha256'])
            values=sorted((x['placement_id'],x['set'],x['image'],x['sha256']) for x in records)
            actual=hashlib.sha256(json.dumps(values,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
            if actual!=fingerprint: raise ValueError()
    except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile,UserError):
        raise UserError('图包文件校验失败，请重新保存；原文件已保留') from None
    return manifest
