"""Small local integrity and capacity guards, shared by execution and maintenance."""
import shutil
from pathlib import Path
from .config import UserError


def require_space(path,needed=0):
    path=Path(path)
    while not path.exists():path=path.parent
    reserve=64*1024*1024
    if shutil.disk_usage(path).free<needed+reserve:raise UserError('磁盘空间不足，已暂停新提交；请释放空间后继续',507)


def valid_task(value,tid):
    try:
        assert isinstance(value,dict) and value['id']==tid
        assert all(isinstance(value[k],str) for k in ('pkg','direction','output_dir'))
        assert isinstance(value['date'],(int,float))
        assert isinstance(value['rounds'],list) and value['rounds']
        assert type(value['ri']) is int and 0<=value['ri']<len(value['rounds'])
        assert isinstance(value['pkgs'],list) and isinstance(value['output_dir'],str)
        for p in value['pkgs']:
            assert isinstance(p,dict) and isinstance(p['path'],str) and isinstance(p['images'],list)
            assert isinstance(p['id'],str) and type(p['v']) is int
            assert all(isinstance(i['id'],str) and type(i['att']) is int for i in p['images'])
        for r in value['rounds']:
            assert isinstance(r['id'],str) and isinstance(r['params'].get('pids'),list)
            assert isinstance(r['params'],dict) and isinstance(r['slots'],list) and r['slots']
            assert isinstance(r['sel'],dict) and isinstance(r['adopted_versions'],dict)
            for s in r['slots']:
                assert isinstance(s['id'],str) and isinstance(s['pid'],str) and type(s['att']) is int and s['att']>0
                assert s['state'] in ('queued','generating','done','failed','blocked_first_failed','stopped')
                assert isinstance(s['first_id'],str) and type(s['set']) is int and type(s['idx']) is int
                assert isinstance(s.get('prompt'),str) and isinstance(s.get('orig'),str)
                assert isinstance(s['output'],str) and isinstance(s['refs'],list) and isinstance(s['versions'],list)
                assert all(isinstance(x,dict) and isinstance(x['path'],str) for x in s['refs'])
                for v in s['versions']:
                    assert isinstance(v,dict) and type(v['att']) is int and isinstance(v['output'],str) and isinstance(v['refs'],list)
        return True
    except (AssertionError,KeyError,TypeError,AttributeError):return False
