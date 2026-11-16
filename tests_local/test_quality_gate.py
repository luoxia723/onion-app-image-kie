"""Visual choice does not block export; objective delivery failures do."""
import json
import threading
import urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer
import pytest
from PIL import Image
from local_app.config import UserError
from local_app.engine import digest
from local_app.server import Handler


def fitted_image(tmp_path):
    from local_app.config import Settings
    from local_app.engine import Engine
    from local_app.planning import STYLES,BY_ID,compile_plans
    from tests_local.fakes import FixturePlanner
    settings=Settings(tmp_path/'state',tmp_path/'fake.env');settings.update({'simulation':True,'output_dir':str(tmp_path)})
    e=Engine(settings,start=False,planner=FixturePlanner())
    p=BY_ID['ximalaya-current-single-720x1559']
    pr=dict(channel='信息流',image_form='单图',pids=[p['id']],sets=1,t1='完整标题',t2='完整副标题',cta='点击下载',ip='none',font='none',style=STYLES[0]['name'])
    t=e.task(e.create(pr,'natural-quality-fixture')['id']);r=t['rounds'][0];compile_plans(r,FixturePlanner().plan(r,lambda _:None));s=r['slots'][0]
    out=Path(s['output']);Image.new('RGB',(720,1559),'white').save(out)
    s.update(e.materialize_image(s,{'source':str(out)},out,p));e.persist(t);e.mutate(t['id'],'adopt',{'set':1,'adopted':True})
    return e,t,r,s

def test_visual_notes_do_not_block_technically_valid_export(tmp_path):
    e,t,r,s=fitted_image(tmp_path)
    try:
        assert s['natural_processing']['visual_review_required'] and e.public(t)['delivery']['can_export']
        assert 'review_required' not in e.public(t)['rounds'][0]['slots'][0]
        pkg=e.package(t['id'],0);assert Path(pkg['path']).exists()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.engine=e
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            url='http://127.0.0.1:'+str(server.server_port)+'/api/tasks/'+t['id']+'/packages/'+pkg['id']
            assert urllib.request.urlopen(url).status==200
        finally:server.shutdown();server.server_close()
    finally:e.close()


@pytest.mark.parametrize('failure',['dimensions','format','hash','missing'])
def test_objective_file_failures_block_export_even_when_all_selected(tmp_path,failure):
    e,t,r,s=fitted_image(tmp_path)
    try:
        path=Path(s['jpeg'])
        if failure=='dimensions':Image.new('RGB',(300,500),'white').save(path)
        elif failure=='format':Image.new('RGB',(720,1559),'white').save(path,format='PNG');s['sha256']=digest(path)
        elif failure=='hash':Image.new('RGB',(720,1559),'black').save(path)
        else:path.unlink()
        with pytest.raises(UserError):e.package(t['id'],0)
        assert not t['pkgs']
    finally:e.close()


def test_failed_delivery_cannot_be_approved_by_visual_metadata(tmp_path):
    e,t,r,s=fitted_image(tmp_path)
    try:
        s['delivery_eligible']=False
        s['quality_review']={'image_version':s['att'],'image_sha256':s['sha256'],'checks':dict(copy=True,brand=True,completeness=True,quality=True)}
        assert not e.public(t)['delivery']['can_export']
        with pytest.raises(UserError):e.package(t['id'],0)
    finally:e.close()


def test_corrupt_saved_package_is_not_reused_and_reexport_keeps_original(tmp_path):
    e,t,r,s=fitted_image(tmp_path)
    try:
        old=e.package(t['id'],0);old_path=Path(old['path']);old_path.write_bytes(b'corrupt archive')
        assert e.package_preview(t['id'],0)['next_version']=='v002'
        new=e.package(t['id'],0)
        assert new['v']==2 and new['id']!=old['id'] and old_path.read_bytes()==b'corrupt archive'
        assert e.package(t['id'],0)['id']==new['id']
    finally:e.close()
