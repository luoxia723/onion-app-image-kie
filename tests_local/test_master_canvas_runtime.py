"""Application-level one-to-many canvases, encoding, history and grouped retries."""
import copy
import json
import zipfile
from io import BytesIO

import pytest
from PIL import Image

from local_app.config import UserError
from local_app.learning_runtime import LearningRuntime
from tests_local.test_brand_logo import engine,ready
from tests_local.test_learning_runtime import CountingExecutor,settled

TARGETS=['weibo-current-single-1280x720','ximalaya-current-single-1200x480','cpa-current-single-690x360']


def make_shared(engine):
    task,round=ready(engine);executor=CountingExecutor(engine.settings);runtime=LearningRuntime(engine,executor)
    body=dict(source=dict(kind='ordinary',task_id=task['id'],image_ids=[round['slots'][0]['id']],
                         atts={round['slots'][0]['id']:1}),target_kind='ordinary',pids=TARGETS)
    run=runtime.create_shared_canvas(body,'shared-create-runtime-test')
    return runtime,executor,run,task,body


def test_one_application_canvas_creates_three_exact_jpegs_and_switchable_logos(engine):
    runtime,executor,run,task,body=make_shared(engine);rid=run['id'];old=copy.deepcopy(task)
    try:
        assert run['kind']=='shared_canvas_adaptation' and run['counts']['expected_new_calls']==1
        assert run['counts']['output_count']==3 and run['source_images'][0]['image_url']
        assert runtime.create_shared_canvas(body,'shared-create-runtime-test')['id']==rid
        with pytest.raises(UserError):runtime.create_shared_canvas({**body,'pids':TARGETS[:1]},'shared-create-runtime-test')
        runtime.expand_suite(rid,'shared-expand-runtime-test');done=settled(runtime,rid)
        assert done['status']=='completed',done.get('error')
        assert len(executor.jobs)==1 and executor.jobs[0]['kind']=='shared_canvas_master'
        assert [ref['kind'] for ref in executor.jobs[0]['reference_bindings']]==['canvas_guide','source_picture']
        for output in done['outputs']:
            with Image.open(runtime.image(rid,'output',output['id'],output['version'])) as im:
                assert im.format=='JPEG' and im.size==(output['width'],output['height'])
            assert output['processing']['method']=='shared_canvas_crop'
            assert output['processing']['format']=='JPEG'
        black=runtime.package(rid,logo_asset_id='learning.logo.black')
        white=runtime.package(rid,logo_asset_id='learning.logo.white-app')
        with zipfile.ZipFile(runtime.package_file(rid,black['id'])) as bz,zipfile.ZipFile(runtime.package_file(rid,white['id'])) as wz:
            records=json.loads(wz.read('交付清单.json'))['images'];assert len(records)==3
            for item in records:
                assert item['path'].endswith('.jpg') and bz.read(item['path'])!=wz.read(item['path'])
                with Image.open(BytesIO(wz.read(item['path']))) as im:assert im.size==(item['width'],item['height'])
        assert task==old and len(executor.jobs)==1
        row=next(output for output in done['outputs'] if output.get('logo_review_switchable'))
        first=row['logo_template']['asset_id']
        choice='learning.logo.black' if first=='learning.logo.white-app' else 'learning.logo.white-app'
        changed=runtime.review_output_logo(rid,row['id'],{'expected_version':row['version'],'expected_sha256':row['sha256'],'asset_id':choice})
        active=next(item for item in changed['outputs'] if item['id']==row['id'])
        assert active['version']==row['version'] and active['logo_template']['asset_id']==choice
        with Image.open(runtime.image(rid,'output',row['id'],row['version'],active['sha256'])) as reviewed:
            assert reviewed.format=='JPEG' and reviewed.size==(row['width'],row['height'])
        assert len(executor.jobs)==1
        with pytest.raises(UserError):runtime.generate_baseline(rid,'cannot-regenerate-source')
    finally:runtime.close()


def test_group_retry_costs_one_image_and_updates_all_children_without_overwriting_history(engine):
    runtime,executor,run,_,_=make_shared(engine);rid=run['id']
    try:
        runtime.expand_suite(rid,'shared-initial-for-retry');first=settled(runtime,rid)
        files={o['id']:runtime.image(rid,'output',o['id'],1).read_bytes() for o in first['outputs']}
        mid=first['masters'][0]['id']
        executor.fail_one='shared_canvas_master'
        runtime.regenerate_canvas_master(rid,mid,'shared-group-retry-key',1);failed=settled(runtime,rid)
        assert failed['masters'][0]['query_required'] and failed['masters'][0]['version']==2
        runtime.regenerate_canvas_master(rid,mid,'shared-group-retry-key',2);done=settled(runtime,rid)
        assert done['status']=='completed' and done['masters'][0]['version']==2
        assert len(executor.jobs)==3 and executor.jobs[-1]==executor.jobs[-2]
        for row in done['outputs']:
            assert row['version']==2 and row['versions'][0]['version']==1
            assert runtime.image(rid,'output',row['id'],1).read_bytes()==files[row['id']]
        runtime.regenerate_canvas_master(rid,mid,'shared-group-retry-key',1)
        assert len(executor.jobs)==3
    finally:runtime.close()
