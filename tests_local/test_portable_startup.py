"""Offline startup contracts. Fresh dependency installation is also exercised in CI."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
import pytest
from local_app.config import Settings
from local_app.engine import Engine
from local_app.server import Handler
from tests_local.fakes import FixturePlanner

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('workbench_bootstrap',ROOT/'bootstrap.py')
launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)


def test_platform_interpreter_paths():
    base=Path('project')/'.venv'
    assert launcher.environment_python(base,True)==base/'Scripts/python.exe'
    assert launcher.environment_python(base,False)==base/'bin/python'


def test_complete_bundle_has_no_external_asset_dependency():
    launcher.check_bundle(ROOT)


def test_run_help_needs_only_runtime_dependencies(tmp_path):
    # The developer environment can still have retired image libraries. Block
    # them explicitly so it cannot hide a broken clean-install entry point.
    script='''
import importlib.abc,sys,runpy
class RuntimeOnly(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in ('cv2','numpy'):
            raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0,RuntimeOnly())
sys.path.insert(0,sys.argv[1])
sys.argv=[sys.argv[1]+'/run.py','--help']
runpy.run_path(sys.argv[0],run_name='__main__')
'''
    result=subprocess.run([sys.executable,'-c',script,str(ROOT)],cwd=tmp_path,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert '--state-dir' in result.stdout and '--env-file' in result.stdout


def test_missing_bundle_fails_before_installing(tmp_path):
    with pytest.raises(launcher.SetupError,match='不完整'):launcher.ensure_environment(tmp_path)
    assert not (tmp_path/'.venv').exists()


def test_clean_env_does_not_inherit_another_projects_import_paths(monkeypatch):
    for key in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV'):monkeypatch.setenv(key,'another-project')
    env=launcher.child_environment()
    assert all(key not in env for key in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV'))
    assert env['PYTHONUTF8']=='1'


def test_first_setup_creates_venv_installs_only_requirements_and_is_idempotent(tmp_path,monkeypatch):
    root=tmp_path/'中文 Shared Project';root.mkdir()
    (root/'requirements.txt').write_text('Pillow==12.3.0\n')
    monkeypatch.setattr(launcher,'check_bundle',lambda p:None)
    monkeypatch.setattr(launcher,'interpreter_ready',lambda p:False)
    calls=[];ready=[False,True,True]
    monkeypatch.setattr(launcher,'dependencies_ready',lambda *a:ready.pop(0))
    class Builder:
        def __init__(self,with_pip):assert with_pip
        def create(self,path):calls.append(('create',path))
    monkeypatch.setattr(launcher.venv,'EnvBuilder',Builder)
    monkeypatch.setattr(launcher.subprocess,'run',lambda command,**kw:calls.append(('install',command,kw)))
    one=launcher.ensure_environment(root);two=launcher.ensure_environment(root)
    assert one==two and len(calls)==2
    command=calls[1][1]
    assert command[:3]==[str(one),'-m','pip'] and '--only-binary=:all:' in command
    assert command[-1]==str(root/'requirements.txt')
    assert not (root/'.env').exists()


def test_no_keys_fresh_workspace_serves_ui_and_can_be_configured(tmp_path):
    root=tmp_path/'中文 Shared Project';root.mkdir()
    settings=Settings(root/'state',root/'.env');settings.update({'output_dir':str(root)})
    engine=Engine(settings,start=False,planner=FixturePlanner())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.engine=engine
    threading.Thread(target=server.serve_forever,daemon=True).start()
    base='http://127.0.0.1:'+str(server.server_port)
    try:
        assert urllib.request.urlopen(base).status==200
        public=json.load(urllib.request.urlopen(base+'/api/settings'))
        assert not public['key_configured'] and not public['planning_key_configured']
        assert public['planning_base_url']=='https://ops-ai-gateway.yc345.tv/v1'
        assert public['planning_model']=='gpt-6.1-terra'
        assert public['image_model']=='gpt-image-2-6/flare-image-to-image'
        data={'planning_api_key':'test-only-planning','kie_api_key':'test-only-kie'}
        req=urllib.request.Request(base+'/api/settings',data=json.dumps(data).encode(),method='PUT',
            headers={'Content-Type':'application/json','X-Onion-Request':'1'})
        updated=json.load(urllib.request.urlopen(req))
        assert updated['key_configured'] and updated['planning_key_configured'] and not updated['simulation']
        assert 'test-only-' not in json.dumps(updated)
        assert updated['planning_base_url']==public['planning_base_url']
    finally:server.shutdown();server.server_close();engine.close()
