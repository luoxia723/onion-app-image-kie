#!/usr/bin/env python3
"""Build source ZIP/tar bundles without credentials, local environments or user data."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tarfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'.git','.venv','venv','__pycache__','.pytest_cache','.cache','.onion-local','工作区','.runtime',
          'uploads','backups','.restored','dist'}


def distributable(path):
    if any(part in EXCLUDED or part.startswith('.venv-backup-') for part in path.parts):return False
    if path.name.startswith('.env') and path.name!='.env.example':return False
    if path.suffix.lower() in ('.pem','.key','.pyc','.sqlite','.sqlite3','.db','.zip','.tar','.gz','.log'):return False
    if re.search(r'\.(sqlite3?|db)-(wal|shm|journal)$',path.name,re.I):return False
    return not path.as_posix().startswith('assets/logos/review/')


def source_files(root=ROOT):
    raw=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=root)
    result=[]
    for name in sorted(set(raw.decode('utf-8').split('\0'))):
        path=Path(name)
        if not name or not (root/path).is_file():continue
        if not distributable(path):continue
        result.append(path)
    return result


def check_sources(root=ROOT,files=None):
    """Check the Git distribution set without printing credential values."""
    root=Path(root).resolve();files=source_files(root) if files is None else files
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode('utf-8').split('\0')
    forbidden=[name for name in tracked if name and not distributable(Path(name))]
    if forbidden:raise ValueError('Git索引包含本地数据或敏感文件：'+', '.join(forbidden[:5]))
    secrets=[]
    env_file=root/'.env'
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            name,_,value=line.partition('=')
            if name.strip() in ('KIE_API_KEY','ONION_PLANNING_API_KEY'):
                try:value=json.loads(value)
                except ValueError:value=value.strip().strip('"\'')
                if isinstance(value,str) and len(value)>=12:secrets.append(value.encode())
    token=re.compile(rb'\b(?:ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{60,}|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,})\b')
    for path in files:
        if (root/path).is_symlink():raise ValueError('源码包不能引用符号链接：'+str(path))
        content=(root/path).read_bytes()
        if any(secret in content for secret in secrets):
            raise ValueError('源码内发现本机 Key，请先移除再打包：'+str(path))
        if token.search(content) or re.search(rb'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----',content):
            raise ValueError('源码内发现疑似凭据，请检查：'+str(path))
        if re.search(rb'disposable_login_token=[A-Za-z0-9_-]{20,}',content):
            raise ValueError('源码内发现一次性登录链接，请移除：'+str(path))
        if path.name=='.env.example':
            for line in content.decode('utf-8').splitlines():
                name,separator,value=line.partition('=')
                if separator and not name.lstrip().startswith('#') and re.search(r'(KEY|TOKEN|SECRET|PASSWORD)$',name.strip()):
                    if value.strip().strip('"\''):raise ValueError('.env.example中的凭据必须留空')
    return files


def build(destination, root=ROOT):
    files=check_sources(root)
    destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=True)
    zip_path=destination/'洋葱广告图工作台-本机版.zip'
    tar_path=destination/'洋葱广告图工作台-本机版.tar.gz'
    for target,kind in ((zip_path,'zip'),(tar_path,'tar')):
        temp=target.with_suffix(target.suffix+'.tmp')
        if kind=='zip':
            with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as archive:
                for path in files:archive.write(root/path,arcname='onion-app-image-kie/'+path.as_posix())
        else:
            with tarfile.open(temp,'w:gz') as archive:
                for path in files:archive.add(root/path,arcname='onion-app-image-kie/'+path.as_posix(),recursive=False)
        temp.replace(target)
    return zip_path,tar_path,len(files)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output-dir',type=Path)
    group.add_argument('--check',action='store_true',help='仅检查Git源码范围、凭据及本地数据排除规则')
    args=parser.parse_args()
    if args.check:
        print('源码发布检查通过，共 '+str(len(check_sources()))+' 个文件。')
        raise SystemExit(0)
    paths=build(args.output_dir)
    print('已生成无 Key 源码包，共 '+str(paths[2])+' 个文件。')
    for path in paths[:2]:print(path)
