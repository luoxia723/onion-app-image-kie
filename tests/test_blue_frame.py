import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import blue_frame
from kie_model import geometry_report
from prepare_accepted_deliveries import prepare_accepted_deliveries


@pytest.mark.parametrize('width,height,enabled', [(720,1559,True),(1200,480,True),(690,360,True),(1280,720,False),(474,768,False)])
def test_routing_and_general_frame_detection(tmp_path,width,height,enabled):
    result=blue_frame.prepare_layout(width,height,tmp_path)
    assert result['enabled']==enabled
    if not enabled:
        assert not list(tmp_path.iterdir())
        return
    spec=json.loads(Path(result['frame_layout_path']).read_text())
    source=cv2.imread(result['reference']['path'])
    output,record=blue_frame.detect_and_resize(source,spec)
    assert output.shape[:2]==(height,width)
    assert np.all(output==255)  # No blue frame survives a correctly placed guide.
    assert record['crop_xyxy'][0]>spec['frame_outer_xyxy_inclusive'][0]


def test_six_percent_boundary():
    assert geometry_report(940,1000,'1:1')['adaptation_mode']=='blue_frame'
    assert geometry_report(941,1000,'1:1')['adaptation_mode']=='cover'


def test_moved_frame_is_detected_and_blue_content_is_preserved(tmp_path):
    result=blue_frame.prepare_layout(720,1559,tmp_path)
    spec=json.loads(Path(result['frame_layout_path']).read_text())
    width,height=spec['guide_canvas']
    image=np.full((height,width,3),255,np.uint8)
    x1,y1,x2,y2=spec['frame_outer_xyxy_inclusive']
    cv2.rectangle(image,(x1+5,y1+3),(x2-3,y2-2),(214,99,22),6)
    cv2.rectangle(image,(200,200),(600,500),(214,99,22),-1)
    output,record=blue_frame.detect_and_resize(image,spec)
    assert record['detected_frame_edges']['left']['start']>=x1+2
    assert output.shape==(1559,720,3)
    assert np.count_nonzero(blue_frame.blue_mask(output))>10000
    assert np.count_nonzero(blue_frame.blue_mask(output)[:5])==0


def test_missing_frame_is_reviewable_and_does_not_fake_success(tmp_path):
    result=blue_frame.prepare_layout(720,1559,tmp_path/'layout')
    source=tmp_path/'03_候选/候选图片/raw.png';source.parent.mkdir(parents=True)
    Image.new('RGB',(900,1600),'white').save(source)
    metadata={'actual_crop_percent':17.9,'review_findings':[]}
    blue_frame.attach_result(metadata,source,result['frame_layout_path'])
    assert metadata['frame_status']=='needs_review'
    assert metadata['candidate_filepath']==str(source)
    assert source.is_file()
    assert not (tmp_path/'03_候选/框内预览').exists()


def test_layout_hash_and_reference_binding_are_checked(tmp_path):
    result=blue_frame.prepare_layout(720,1559,tmp_path)
    ref=result['reference'];guide=Path(ref['path'])
    blue_frame.validate_layout(result['frame_layout_path'],'720x1559',[ref],[guide],result['prompt_rule'])
    with pytest.raises(ValueError,match='编号'):
        blue_frame.validate_layout(result['frame_layout_path'],'720x1559',[{**ref,'label':'参考图9'}],[guide],result['prompt_rule'])
    guide.write_bytes(b'changed')
    with pytest.raises(ValueError,match='哈希'):
        blue_frame.validate_layout(result['frame_layout_path'],'720x1559',[ref],[guide],result['prompt_rule'])


@pytest.mark.parametrize('has_frame',[True,False])
def test_accepted_delivery_uses_frame_result_and_never_delivers_failed_crop(tmp_path,has_frame):
    root=tmp_path/'task';version=root/'v001'
    for phase in ['02_过程','03_候选','04_交付','05_质检']:
        (version/phase).mkdir(parents=True)
    (root/'任务索引.json').write_text(json.dumps({'task_id':'test','file_stem':'frame-test'}))
    layout=blue_frame.prepare_layout(720,1559,version/'02_过程')
    source=version/'03_候选/raw.png'
    guide=Image.open(layout['reference']['path']).convert('RGB')
    if not has_frame:guide=Image.new('RGB',guide.size,'white')
    guide.save(source)
    job={'job_id':'one','set_id':'one','slot':1,'output':str(source),'frame_layout_path':layout['frame_layout_path'],'target_width':720,'target_height':1559,'target_kb':150}
    (version/'02_过程/image-render-manifest.json').write_text(json.dumps({'jobs':[job]}))
    (version/'02_过程/image-config-result.json').write_text(json.dumps({'placements':[{'target_width':720,'target_height':1559,'max_file_size_kb':150}]}))
    selection=version/'03_候选/image-selection-result.json'
    selection.write_text(json.dumps({'accepted_schemes':[{'set_id':'one','thumb':['raw.png']}]}))
    if not has_frame:
        with pytest.raises(ValueError):prepare_accepted_deliveries(selection)
        assert not list((version/'04_交付').iterdir())
    else:
        result=prepare_accepted_deliveries(selection)
        delivered=Image.open(result['files'][0]['delivery'])
        assert delivered.size==(720,1559)
        assert all(min(pixel)>240 for pixel in delivered.get_flattened_data())
        assert result['files'][0]['frame_processing']['output_size']==[720,1559]
        resumed=prepare_accepted_deliveries(selection)
        assert resumed['files'][0]['reused_existing']
