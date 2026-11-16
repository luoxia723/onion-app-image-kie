"""Unified lists retain provenance, real pagination and immutable ZIP records."""
import copy
import json
import hashlib
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import uuid
import zipfile

from PIL import Image
import pytest

from local_app import workspace
from local_app.config import UserError
from tests_local.test_brand_logo import engine,ready


def test_cross_source_search_sort_paging_and_counts_do_not_rewrite_data(engine):
    task,round=ready(engine);old=copy.deepcopy(task)
    for n in range(23):
        engine.save_draft(uuid.uuid4().hex,{'draft':{'t1':f'同名检索{n:02d}','channel':'学习机' if n%2 else '应用商店'},'sequence':1})
    run=dict(id='f'*32,name='同名检索运行',params={'t1':'最后一条正文'},outputs=[],baseline={'version':0,'status':'not_generated'},suite={'status':'not_started'},mode='simulation',busy=False,status='configured',updated_at=1)
    runtime=SimpleNamespace(runs={run['id']:run})
    page=workspace.items(engine,runtime,q='同名检索',limit=5)
    assert page['total']==24 and page['counts']['draft']==23 and page['counts']['ready']==1
    keys=[]
    while True:
        keys.extend(row['key'] for row in page['items'])
        if not page['next_cursor']:break
        page=workspace.items(engine,runtime,q='同名检索',limit=5,cursor=page['next_cursor'])
    assert len(keys)==len(set(keys))==24 and keys[-1]=='run:'+run['id']
    only=workspace.items(engine,runtime,q='同名检索',kind='learning',state='draft',limit=100)
    assert len(only['items'])==11 and all(r['source_type']=='draft' for r in only['items'])
    with pytest.raises(UserError):workspace.items(engine,runtime,q='changed',cursor=workspace.items(engine,runtime,q='同名检索',limit=1)['next_cursor'])
    assert task==old and run['status']=='configured'


def test_run_pending_confirmation_unknown_and_completed_are_distinct(engine):
    base=dict(id='a'*32,name='来源',params={},outputs=[dict(id='one',version=1,status='waiting_for_baseline_confirmation')],baseline={'status':'done','version':1},suite={'status':'not_started'},mode='simulation',busy=False,status='waiting_for_confirmation',approval=None)
    runtime=SimpleNamespace(runs={base['id']:base})
    assert workspace.items(engine,runtime)['items'][0]['status_label']=='待确认基准图'
    base['masters']=[{'query_required':True}]
    assert workspace.items(engine,runtime)['items'][0]['status']=='attention'
    base['masters']=[];base['outputs'][0]['status']='done';base['status']='completed'
    assert workspace.items(engine,runtime)['items'][0]['status']=='completed'
    base['kind']='shared_canvas_adaptation';base['outputs'][0]['status']='waiting';base['status']='baseline_confirmed'
    assert workspace.items(engine,runtime)['items'][0]['status_label']=='待生成共用母版'


def test_delivery_details_and_preview_read_saved_zip_bytes_not_current_candidate(engine,monkeypatch):
    task,round=ready(engine);pkg=engine.package(task['id'],0);runtime=SimpleNamespace(runs={})
    record=workspace.packages(engine,runtime)['items'][0]
    assert record['source_type']=='task' and record['image_count']==1 and record['format']=='JPEG'
    checks=[];verify=workspace.verify_saved_package
    monkeypatch.setattr(workspace,'verify_saved_package',lambda *a,**k:(checks.append(True),verify(*a,**k))[1])
    details=workspace.package_details(engine,runtime,'task',task['id'],pkg['id']);row=details['images'][0]
    first,mime=workspace.package_image(engine,runtime,'task',task['id'],pkg['id'],0)
    assert len(checks)==1
    assert mime=='image/jpeg' and hashlib.sha256(first).hexdigest()==row['sha256']
    Path(round['slots'][0]['jpeg']).write_bytes(b'new candidate bytes')
    assert workspace.package_image(engine,runtime,'task',task['id'],pkg['id'],0)[0]==first
    with pytest.raises(UserError):workspace.package_image(engine,runtime,'task',task['id'],pkg['id'],-1)
    Path(pkg['path']).write_bytes(b'corrupt ZIP')
    with pytest.raises(UserError):workspace.package_details(engine,runtime,'task',task['id'],pkg['id'])


@pytest.mark.parametrize('field,value',[('limit',True),('limit',0),('kind','invalid'),('state','invalid'),('cursor','bad-base64'),('q','a'*201)])
def test_workspace_input_boundaries(engine,field,value):
    with pytest.raises(UserError):workspace.items(engine,SimpleNamespace(runs={}),**{field:value})


def test_current_delivery_facade_keeps_saved_legacy_learning_png_type(engine):
    from tests_local.learning_history import install_history
    from tests_local.test_learning_workflow import params,ROOT
    task=install_history(engine,params(ROOT));pid=task['rounds'][0]['params']['pids'][0]
    engine.mutate(task['id'],'adopt',{'placement_id':pid,'set':1,'adopted':True})
    package=engine.package(task['id'],0)
    row=workspace.packages(engine,SimpleNamespace(runs={}),kind='learning')['items'][0]
    assert row['id']==package['id'] and row['format']=='PNG' and row['type']=='learning'
    raw,mime=workspace.package_image(engine,SimpleNamespace(runs={}), 'task',task['id'],package['id'],0)
    assert mime=='image/png' and raw.startswith(b'\x89PNG')
