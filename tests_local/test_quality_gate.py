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
from tests_local.test_frame_preview import fixture_slot


def fitted_image(tmp_path):
    e,t,r,s=fixture_slot(tmp_path)
    out=Path(s['output']);Image.new('RGB',(941,1672),'white').save(out)
    s.update(e.materialize_image(s,{'source':str(out),'frame_status':'failed'},out))
    e.mutate(t['id'],'adopt',{'set':1,'adopted':True})
    e.mutate(t['id'],'fit-image',{'image_id':s['id']})
    return e,t,r,s


def test_visual_notes_do_not_block_technically_valid_export(tmp_path):
    e,t,r,s=fitted_image(tmp_path)
    try:
        assert s['reason_code']=='frame_review' and e.public(t)['delivery']['can_export']
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


def test_failed_frame_cannot_be_approved_by_legacy_visual_metadata(tmp_path):
    e,t,r,s=fitted_image(tmp_path)
    try:
        s['delivery_eligible']=False;s['frame_status']='failed'
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
