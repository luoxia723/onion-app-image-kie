#!/usr/bin/env python3
"""Build source ZIP/tar bundles without credentials, local environments or user data."""
import argparse
import json
from pathlib import Path
import subprocess
import tarfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'.git','.venv','venv','__pycache__','.pytest_cache','.cache','.onion-local','工作区','.runtime'}


def source_files(root=ROOT):
    raw=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=root)
    result=[]
    for name in sorted(set(raw.decode('utf-8').split('\0'))):
        path=Path(name)
        if not name or not (root/path).is_file():continue
        if any(part in EXCLUDED or part.startswith('.venv-backup-') for part in path.parts):continue
        if path.name.startswith('.env') and path.name!='.env.example':continue
        if path.suffix.lower() in ('.pem','.key','.pyc'):continue
        if name.startswith('assets/logos/review/'):continue
        result.append(path)
    return result


def build(destination, root=ROOT):
    destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=True)
    files=source_files(root)
    secrets=[]
    env_file=root/'.env'
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            name,_,value=line.partition('=')
            if name.strip() in ('KIE_API_KEY','ONION_PLANNING_API_KEY'):
                try:value=json.loads(value)
                except ValueError:value=value.strip().strip('"\'')
                if isinstance(value,str) and len(value)>=12:secrets.append(value.encode())
    for path in files:
        if any(secret in (root/path).read_bytes() for secret in secrets):
            raise ValueError('源码内发现本机 Key，请先移除再打包：'+str(path))
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
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    paths=build(args.output_dir)
    print('已生成无 Key 源码包，共 '+str(paths[2])+' 个文件。')
    for path in paths[:2]:print(path)
