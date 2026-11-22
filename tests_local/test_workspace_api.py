"""HTTP contract for the production shell and the read-only workspace facade."""
import json
import re
import time

from tests_local.test_learning_setup_api import api,production_learning_api
from tests_local.test_brand_logo import ready


def test_production_index_assets_and_unconfirmed_run_are_readable_without_models(production_learning_api):
    engine,request=production_learning_api
    status,index=request('/');assert status==200
    scripts=re.findall(rb'<script src="([^"]+)"',index)
    assert b'/js/workspace.js' in scripts and b'/js/production.js' in scripts
    for path in scripts:assert request(path.decode())[0]==200
    status,run=request('/api/learning-machine/runs','POST',{'params':{'channel':'学习机','t1':'只核对界面','ip':'none','font':'none'},'idempotency_key':'workspace-http-create'})
    assert status==200 and run['approval'] is None
    rid=run['id'];assert request('/api/learning-machine/runs/'+rid+'/baseline','POST',{'idempotency_key':'workspace-http-baseline'})[0]==200
    for _ in range(100):
        _,run=request('/api/learning-machine/runs/'+rid)
        if not run['busy']:break
        time.sleep(.02)
    assert run['baseline']['status']=='done' and run['approval'] is None
    status,rows=request('/api/workbench/items?kind=learning&state=ready');assert status==200 and len(rows['items'])==1
    assert rows['items'][0]['id']==rid and rows['items'][0]['status_label']=='待确认基准图'
    assert request('/api/workbench/items?limit=200')[0]==400
    assert request('/api/workbench/items?kind=unknown')[0]==400
    assert request('/api/workbench/items?cursor=bad')[0]==400
    assert not engine.tasks


def test_saved_zip_manifest_and_image_routes_use_registered_package(api):
    engine,request=api;task,_=ready(engine);pkg=engine.package(task['id'],0)
    status,rows=request('/api/workbench/packages');assert status==200 and rows['items'][0]['source_id']==task['id']
    base='/api/workbench/packages/task/'+task['id']+'/'+pkg['id']
    status,detail=request(base);assert status==200 and len(detail['images'])==1
    status,image=request(detail['images'][0]['image_url']);assert status==200 and image.startswith(b'\xff\xd8')
    assert request(base+'/images/9')[0]==404
    assert request('/api/workbench/packages/task/'+task['id']+'/'+'0'*32)[0]==404


def test_ordinary_logo_templates_save_and_freeze_into_new_rounds_without_models(api):
    engine,request=api
    status,config=request('/api/logo-templates')
    assert status==200
    assert {p['category'] for p in config['placements']}=={'应用商店','信息流'}
    assert len(config['placements'])==19
    pid='weibo-current-single-1280x720'
    template={'placement_id':pid,'asset_id':'learning.logo.white-app','x':.05,'y':.04,'width':.25}
    status,saved=request('/api/logo-templates','PUT',{'revision':config['revision'],'templates':[template]})
    assert status==200 and saved['revision']==config['revision']+1
    status,conflict=request('/api/logo-templates','PUT',{'revision':config['revision'],'templates':[template]})
    assert status==409
    task,round=ready(engine,pid)
    layer=round['slots'][0]['brand_logo_layer']
    assert layer['template']['x']==.05 and layer['template']['width']==.25
    assert layer['selected_asset_id']=='learning.logo.white-app'
    original=json.dumps(layer,sort_keys=True)
    template['x']=.1
    assert request('/api/logo-templates','PUT',{'revision':saved['revision'],'templates':[template]})[0]==200
    assert json.dumps(round['slots'][0]['brand_logo_layer'],sort_keys=True)==original
    assert not engine.document('learning_machine_logo_templates')


def test_ordinary_logo_invalid_batch_is_atomic_and_survives_index_restore(api,tmp_path):
    engine,request=api
    status,config=request('/api/logo-templates');assert status==200
    good={'placement_id':'weibo-current-single-1280x720','asset_id':'learning.logo.black','x':.04,'y':.03,'width':.2}
    bad={**good,'placement_id':'learning-baidu-512x512'}
    assert request('/api/logo-templates','PUT',{'revision':0,'templates':[good,bad]})[0]==400
    assert request('/api/logo-templates')[1]['revision']==0
    for patch in ({'x':True},{'width':float('inf')},{'y':.99},{'asset_id':'/tmp/logo.png'}):
        assert request('/api/logo-templates','PUT',{'revision':0,'templates':[{**good,**patch}]})[0]==400
    assert request('/api/logo-templates','PUT',{'revision':0,'templates':[good]})[0]==200
    from local_app.logo_templates import public_config
    from local_app.engine import Engine
    from local_app.config import Settings
    from tests_local.fakes import FixturePlanner
    import sqlite3
    settings=Settings(tmp_path/'restored-state',tmp_path/'restored.env')
    settings.state_dir.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(settings.state_dir/'index.sqlite3') as restored:engine.db.backup(restored)
    recovered=Engine(settings,start=False,planner=FixturePlanner())
    try:
        row=next(p for p in public_config(recovered)['placements'] if p['id']==good['placement_id'])
        assert row['logo_template']['x']==.04
    finally:recovered.close()


def test_removed_processing_routes_are_not_registered(api):
    engine,request=api;task,_=ready(engine)
    for action in ('reprocess-frame','fit-image'):
        assert request('/api/tasks/'+task['id']+'/'+action,'POST',{})[0]==404
