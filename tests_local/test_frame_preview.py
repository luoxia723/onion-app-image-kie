"""Postprocessing is local; failed guides never become cover-cropped finished previews."""
import json
import cv2
import numpy as np
import pytest
from pathlib import Path
from PIL import Image
from local_app.config import Settings,UserError
from local_app.engine import Engine,digest
from local_app.planning import PLACEMENTS
from tests_local.fakes import FixturePlanner


def fixture_slot(tmp_path):
    st=Settings(tmp_path/'state',tmp_path/'.env');st.update({'output_dir':str(tmp_path)})
    e=Engine(st,start=False,planner=FixturePlanner())
    p=next(p for p in PLACEMENTS if p['target_size']=='720x1559')
    params=dict(image_form='单图',pids=[p['id']],sets=1,t1='完整标题',t2='完整副标题',cta='立即体验',ip='none',style='random')
    tid=e.create(params,'crop-local-fixture')['id'];t=e.task(tid);r=t['rounds'][0];r['planning_status']='done'
    s=r['slots'][0];s['state']='done';s['plan_ready']=True
    return e,t,r,s


def test_failed_frame_preview_preserves_raw_aspect_and_blocks_delivery(tmp_path):
    e,t,r,s=fixture_slot(tmp_path)
    try:
        out=Path(s['output']);Image.new('RGB',(941,1672),'white').save(out)
        original=digest(out)
        update=e.materialize_image(s,{'source':str(out),'frame_status':'failed','frame_review':True},out)
        s.update(update);e.persist(t)
        assert digest(out)==original and Image.open(s['jpeg']).size==(941,1672)
        public=e.public(t)['rounds'][0]['slots'][0]
        assert public['preview_kind']=='raw' and public['image_url'].endswith('&raw=1')
        assert public['reason_code']=='frame_failed' and '原图' in public['msg']
        e.mutate(t['id'],'adopt',{'set':1,'adopted':True})
        assert not e.public(t)['delivery']['can_export']
    finally:e.close()


def test_local_recrop_keeps_previous_version_raw_and_package_selection(tmp_path):
    e,t,r,s=fixture_slot(tmp_path)
    try:
        spec=json.loads(Path(s['frame']['frame_layout_path']).read_text())
        image=cv2.imread(spec['guide_path'])
        cv2.rectangle(image,(150,150),(600,600),(80,180,210),-1)
        out=Path(s['output']);cv2.imwrite(str(out),image)
        s.update(e.materialize_image(s,{'source':str(out),'frame_status':'failed','frame_review':True},out))
        old_raw=digest(out);old_jpeg=s['jpeg'];old_jpeg_hash=digest(old_jpeg)
        e.mutate(t['id'],'adopt',{'set':1,'adopted':True})
        e.mutate(t['id'],'repair-set',{'placement_id':s['pid'],'set':1})
        assert s['att']==2 and s['state']=='done' and s['delivery_eligible']
        assert digest(out)==old_raw==digest(s['output'])
        assert digest(old_jpeg)==old_jpeg_hash
        assert s['versions'][0]['jpeg']==old_jpeg and s['versions'][0]['att']==1
        assert Image.open(s['jpeg']).size==(720,1559)
        assert not r['sel'].get(s['pid']+'::1') and not e.running
        assert s['version_reason']=='local_frame_processing'
    finally:e.close()


def test_unreliable_recrop_never_queues_paid_regeneration(tmp_path):
    e,t,r,s=fixture_slot(tmp_path)
    try:
        out=Path(s['output']);Image.new('RGB',(900,1600),'white').save(out)
        s.update(e.materialize_image(s,{'source':str(out),'frame_status':'failed'},out))
        with pytest.raises(UserError,match='完整蓝框'):e.mutate(t['id'],'repair-set',{'placement_id':s['pid'],'set':1})
        assert s['att']==1 and s['state']=='done' and not s['delivery_eligible']
        assert not e.running
    finally:e.close()


@pytest.mark.parametrize('action',['reprocess-frame','fit-image'])
def test_crop_endpoint_serves_processed_preview_and_original_separately(tmp_path,action):
    import threading,urllib.request
    from http.server import ThreadingHTTPServer
    from local_app.server import Handler
    e,t,r,s=fixture_slot(tmp_path)
    spec=json.loads(Path(s['frame']['frame_layout_path']).read_text())
    out=Path(s['output']);Image.open(spec['guide_path']).save(out)
    s.update(e.materialize_image(s,{'source':str(out),'frame_status':'failed'},out));e.persist(t)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.engine=e
    threading.Thread(target=server.serve_forever,daemon=True).start()
    base='http://127.0.0.1:'+str(server.server_port)
    try:
        req=urllib.request.Request(base+'/api/tasks/'+t['id']+'/'+action,
            data=json.dumps({'round':0,'image_id':s['id']}).encode(),headers={'Content-Type':'application/json','X-Onion-Request':'1'})
        value=json.load(urllib.request.urlopen(req))['rounds'][0]['slots'][0]
        assert value['att']==2 and value['preview_kind']=='processed'
        from io import BytesIO
        preview=Image.open(BytesIO(urllib.request.urlopen(base+value['image_url']).read()))
        raw=Image.open(BytesIO(urllib.request.urlopen(base+value['original_image_url']).read()))
        assert preview.size==(720,1559) and raw.size==(900,1600)
        old=base+'/api/tasks/'+t['id']+'/images/'+s['id']+'?v=1&raw=1'
        assert Image.open(BytesIO(urllib.request.urlopen(old).read())).size==(900,1600)
    finally:server.shutdown();server.server_close();e.close()


def test_full_image_fit_is_an_explicit_local_operation_and_keeps_user_selection(tmp_path):
    e,t,r,s=fixture_slot(tmp_path)
    try:
        out=Path(s['output']);image=np.full((1672,941,3),255,np.uint8)
        image[:30,:30]=(10,10,230);image[-30:,-30:]=(10,200,10);cv2.imwrite(str(out),image)
        s.update(e.materialize_image(s,{'source':str(out),'frame_status':'failed'},out));before=digest(out)
        e.mutate(t['id'],'adopt',{'set':1,'adopted':True})
        e.mutate(t['id'],'fit-image',{'image_id':s['id']})
        assert s['state']=='done' and s['delivery_eligible'] and s['frame_status']=='full_image_fit'
        assert Image.open(s['jpeg']).size==(720,1559) and digest(out)==before==digest(s['output'])
        key=s['pid']+'::1'
        assert r['sel'][key] and r['adopted_versions'][key][s['id']]==2
        assert e.public(t)['delivery']['can_export'] and not e.running
        result=np.array(Image.open(s['jpeg']))
        assert result[:12,:12,0].mean()>180 and result[-12:,-12:,1].mean()>140
        assert s['frame_processing']['crop_xyxy']==[0,0,941,1672]
    finally:e.close()
