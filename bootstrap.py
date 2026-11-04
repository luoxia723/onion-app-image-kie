#!/usr/bin/env python3
"""Stdlib-only launcher: prepare an isolated environment, then start the app."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import venv

ROOT=Path(__file__).resolve().parent
MIN_PYTHON=(3,10)
MAX_PYTHON=(3,14)

class SetupError(Exception): pass


def environment_python(directory, windows=None):
    windows=os.name=='nt' if windows is None else windows
    return directory/('Scripts/python.exe' if windows else 'bin/python')


def child_environment():
    # A caller's active venv/PYTHONPATH must not change this project's imports.
    env=dict(os.environ)
    for key in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV'): env.pop(key,None)
    env['PYTHONUTF8']='1'
    # Local app traffic must not be sent through a machine's HTTP proxy.
    bypass=env.get('NO_PROXY',env.get('no_proxy',''))
    for host in ('localhost','127.0.0.1','::1'):
        if host not in bypass.split(','):bypass=','.join(filter(None,(bypass,host)))
    env['NO_PROXY']=env['no_proxy']=bypass
    return env


def check_bundle(root):
    required=['run.py','requirements.txt','local_app/server.py','frontend/index.html',
              'local_app/maintenance.py','local_app/safety.py','frontend/js/maintenance.js','local_app/scheduler.py','local_app/workbench.py','local_app/delivery.py','local_app/kie_client.py',
              'frontend/js/prompt-drafts.js','scripts/font_library.py','scripts/poster_prompt.py',
              'config/channel-placement-rules.json','assets/asset-manifest.json',
              'SKILL.md','skills/visual-scene-planner/SKILL.md','references/art-direction.md',
              'references/scene-planning-app.md']
    missing=[name for name in required if not (root/name).is_file()]
    if not missing:
        manifest=json.loads((root/'assets/asset-manifest.json').read_text(encoding='utf-8'))
        missing.extend(item['path'] for item in manifest['assets'] if not (root/item['path']).is_file())
    if missing: raise SetupError('项目文件不完整，请重新下载完整源码包：'+', '.join(missing[:4]))


PROBE=r'''
import sys,re
from pathlib import Path
from importlib.metadata import version
assert (3,10)<=sys.version_info[:2]<=(3,14)
for raw in Path(sys.argv[1]).read_text(encoding='utf-8').splitlines():
    text=raw.strip()
    if not text or text.startswith('#'):continue
    requirement,_,marker=text.partition(';')
    if marker.strip():
        if marker.strip()=='python_version < "3.12"':applies=sys.version_info[:2]<(3,12)
        elif marker.strip()=='python_version >= "3.12"':applies=sys.version_info[:2]>=(3,12)
        else:raise ValueError('Unsupported requirement marker')
        if not applies:continue
    name,expected=requirement.strip().split('==',1)
    assert version(name)==expected
import PIL,cv2,numpy as np
from PIL import Image
assert cv2.resize(np.zeros((2,2,3),dtype=np.uint8),(1,1)).shape==(1,1,3)
assert Image.new('RGB',(1,1)).mode=='RGB'
'''


def dependencies_ready(python, root):
    try:
        result=subprocess.run([str(python),'-c',PROBE,str(root/'requirements.txt')],cwd=root,
            env=child_environment(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
        return result.returncode==0
    except (OSError,subprocess.TimeoutExpired): return False


def interpreter_ready(python):
    try:
        return subprocess.run([str(python),'-c','import sys;sys.exit(not ((3,10)<=sys.version_info[:2]<=(3,14)))'],
            env=child_environment(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10).returncode==0
    except (OSError,subprocess.TimeoutExpired): return False


def ensure_environment(root=ROOT):
    root=Path(root).resolve();check_bundle(root)
    env_dir=root/'.venv';python=environment_python(env_dir)
    if dependencies_ready(python,root):
        print('运行环境已就绪。',flush=True)
        return python
    if env_dir.exists() and not (env_dir/'pyvenv.cfg').is_file():
        raise SetupError('.venv 目录不是有效的虚拟环境，请先将此目录改名，再重新启动。')
    if not interpreter_ready(python):
        if env_dir.exists():
            backup=root/('.venv-backup-'+str(time.time_ns()))
            env_dir.rename(backup)
            print('旧虚拟环境不可用，已保留并准备重建。',flush=True)
        print('首次启动：正在创建本项目的 Python 环境…',flush=True)
        venv.EnvBuilder(with_pip=True).create(env_dir)
    print('正在安装或修复依赖，首次启动需要联网，请稍候…',flush=True)
    try:
        subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check','--no-input',
                        '--only-binary=:all:','-r',str(root/'requirements.txt')],
                       cwd=root,env=child_environment(),check=True)
    except (OSError,subprocess.CalledProcessError):
        raise SetupError('依赖安装失败。请检查网络后重新双击启动；已有配置和任务不受影响。\n建议使用 Python 3.12 或 3.13（64位）。') from None
    if not dependencies_ready(python,root):
        raise SetupError('依赖已安装，但图像库未能正常加载。请确认使用64位 Python，或改用 Python 3.12/3.13 后重试。')
    print('环境准备完成。',flush=True)
    return python


def main(args=None):
    args=list(sys.argv[1:] if args is None else args)
    if not MIN_PYTHON<=sys.version_info[:2]<=MAX_PYTHON:
        print('请先安装64位 Python 3.10–3.14，建议3.12或3.13：https://www.python.org/downloads/')
        return 1
    install_only='--install-only' in args
    args=[arg for arg in args if arg!='--install-only']
    try:
        (ROOT/'.onion-local').mkdir(exist_ok=True)
        from local_app.instance import InstanceLock
        from local_app.config import UserError
        try: lock=InstanceLock(ROOT/'.onion-local/setup.lock')
        except UserError: raise SetupError('另一个启动窗口正在准备运行环境，请稍后重试。') from None
        try: python=ensure_environment()
        finally: lock.close()
        if install_only: return 0
        return subprocess.call([str(python),str(ROOT/'run.py'),*args],cwd=ROOT,env=child_environment())
    except (SetupError,OSError,ValueError) as exc:
        print('启动未完成：'+str(exc),flush=True)
        return 1
    except KeyboardInterrupt: return 130

if __name__=='__main__':sys.exit(main())
