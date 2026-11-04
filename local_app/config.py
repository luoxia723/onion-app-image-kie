from __future__ import annotations
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = 'https://api.kie.ai'
sys.path.insert(0,str(ROOT/'scripts'))
from kie_model import MODEL as DEFAULT_IMAGE_MODEL, MODELS as IMAGE_MODELS
DEFAULT_UPLOAD = 'https://kieai.redpandaai.co'
DEFAULT_PLANNING_BASE = 'https://ops-ai-gateway.yc345.tv/v1'
DEFAULT_PLANNING_MODEL = 'gpt-6.1-terra'

def https_base(value):
    url = str(value).strip().rstrip('/')
    try:
        parts = urlsplit(url)
        parts.port  # Validate an explicitly supplied port.
    except ValueError: raise UserError('接口地址请填写完整的 HTTPS 地址')
    if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or any(ord(c) <= 32 for c in url)):
        raise UserError('接口地址请填写完整的 HTTPS 地址')
    return url

class UserError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status

class Settings:
    def __init__(self, state_dir=None, env_file=None):
        self.state_dir = Path(state_dir or ROOT / '.onion-local').resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.env_file = Path(env_file or ROOT / '.env')
        self.connection = 'missing'
        self.planning_connection = 'missing'
        self.reload()

    def reload(self):
        values = {}
        if self.env_file.exists():
            for line in self.env_file.read_text(encoding='utf-8').splitlines():
                if '=' in line and not line.lstrip().startswith('#'):
                    k, v = line.split('=', 1)
                    try: values[k.strip()] = json.loads(v)
                    except (ValueError, TypeError): values[k.strip()] = v.strip().strip('"\'')
        def get(k, default=''): return str(values.get(k, os.environ.get(k, default)))
        self.key = get('KIE_API_KEY')
        self.base = get('KIE_BASE_URL', DEFAULT_BASE)
        self.upload = get('KIE_UPLOAD_BASE_URL', DEFAULT_UPLOAD)
        self.planning_key = get('ONION_PLANNING_API_KEY')
        self.planning_base = get('ONION_PLANNING_BASE_URL', DEFAULT_PLANNING_BASE)
        self.planning_model = get('ONION_PLANNING_MODEL', DEFAULT_PLANNING_MODEL)
        self.image_model=get('ONION_IMAGE_MODEL',DEFAULT_IMAGE_MODEL)
        if self.image_model not in IMAGE_MODELS: self.image_model=DEFAULT_IMAGE_MODEL
        self.real = get('ONION_REAL_MODE', 'false').lower() == 'true'
        self.concurrency = 20
        self.output = Path(get('ONION_IMAGE_WORKSPACE', str(ROOT))).expanduser().resolve()
        self.output.mkdir(parents=True, exist_ok=True)

    def public(self):
        return dict(key_configured=bool(self.key), key_status=self.connection if self.key else 'missing',
                    concurrency=self.concurrency, output_dir=str(self.output),
                    image_model=self.image_model, image_resolution='1K', image_models=[{'id':k,'name':v} for k,v in IMAGE_MODELS.items()],
                    kie_base_url=self.base, kie_upload_base_url=self.upload, simulation=not self.real,
                    planning_key_configured=bool(self.planning_key),
                    planning_key_status=self.planning_connection if self.planning_key else 'missing',
                    planning_base_url=self.planning_base, planning_model=self.planning_model)

    def update(self, data):
        changes = {}
        for field, name in [('kie_api_key','KIE_API_KEY'), ('planning_api_key','ONION_PLANNING_API_KEY')]:
            if data.get(field):
                key = str(data[field]).strip()
                if len(key) > 512 or any(ord(c) < 33 or ord(c) > 126 for c in key): raise UserError('Key 格式不正确，请重新填写')
                changes[name] = key
        if 'simulation' in data:
            if type(data['simulation']) is not bool: raise UserError('请选择真实生图或模拟预览')
            real = not data['simulation']
        else:
            # Saving an image key is sufficient to enable generation; no .env edit is required.
            real = True if 'KIE_API_KEY' in changes else self.real
        if real and not (changes.get('KIE_API_KEY') or self.key):
            raise UserError('请先填写 KIE Key，再启用真实生图')
        changes['ONION_REAL_MODE'] = 'true' if real else 'false'
        if 'image_model' in data:
            if not isinstance(data['image_model'],str) or data['image_model'] not in IMAGE_MODELS: raise UserError('请选择支持的图片模型')
            changes['ONION_IMAGE_MODEL']=data['image_model']
        if 'planning_model' in data:
            model = str(data['planning_model']).strip()
            if not model or len(model) > 128 or any(ord(c) <= 32 for c in model): raise UserError('请填写正确的规划模型名称')
            changes['ONION_PLANNING_MODEL'] = model
        if 'output_dir' in data:
            p = Path(str(data['output_dir'])).expanduser().resolve()
            if not p.is_dir(): raise UserError('保存位置不存在，请选择已有文件夹')
            try:
                with tempfile.NamedTemporaryFile(dir=p): pass
            except OSError: raise UserError('保存位置不可写，请选择其他文件夹')
            changes['ONION_IMAGE_WORKSPACE'] = str(p)
        for field, name, default in [('kie_base_url','KIE_BASE_URL',DEFAULT_BASE), ('kie_upload_base_url','KIE_UPLOAD_BASE_URL',DEFAULT_UPLOAD), ('planning_base_url','ONION_PLANNING_BASE_URL',DEFAULT_PLANNING_BASE)]:
            if field in data:
                changes[name] = https_base(data[field] or default)
        lines = self.env_file.read_text(encoding='utf-8').splitlines() if self.env_file.exists() else []
        for k, v in changes.items():
            line = k + '=' + json.dumps(v, ensure_ascii=False)
            positions = [i for i, s in enumerate(lines) if s.partition('=')[0].strip() == k]
            if positions:
                lines[positions[0]] = line
                for i in reversed(positions[1:]): lines.pop(i)
            else: lines.append(line)
        fd, tmp = tempfile.mkstemp(dir=self.env_file.parent, prefix='.env-')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f: f.write('\n'.join(lines) + '\n')
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.env_file)
        finally:
            Path(tmp).unlink(missing_ok=True)
        if 'KIE_API_KEY' in changes: self.connection = 'missing'
        if any(k.startswith('ONION_PLANNING_') for k in changes): self.planning_connection = 'missing'
        self.reload()
        return self.public()


def safe_direction(value):
    s = str(value)
    if not s or len(s) > 30 or s != s.strip(' .') or re.search(r'[\\/:*?"<>|\x00-\x1f\x7f]', s):
        raise UserError('方向名限 1–30 字，请去掉首尾空格、句点和文件名特殊字符')
    if re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', s, re.I):
        raise UserError('方向名是系统保留名称，请换一个名称')
    return s
