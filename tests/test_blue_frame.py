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


def test_routing_compares_unrounded_crop_at_six_percent():
    # Both round to 6.00%, but only the second really reaches the threshold.
    assert not geometry_report(21934,10000)['needs_safe_area']
    assert geometry_report(21933,10000)['needs_safe_area']
    assert geometry_report(329,150)['needs_safe_area']  # exactly 6%, nearest 21:9


@pytest.mark.parametrize('width,height', [(720,1559),(1200,480),(690,360)])
def test_nested_blue_frames_are_reviewed_instead_of_delivered(tmp_path,width,height):
    layout=blue_frame.prepare_layout(width,height,tmp_path/'layout')
    spec=json.loads(Path(layout['frame_layout_path']).read_text())
    image=cv2.imread(layout['reference']['path'])
    x1,y1,x2,y2=spec['frame_outer_xyxy_inclusive']
    cv2.rectangle(image,(x1+12,y1+12),(x2-12,y2-12),(214,99,22),6)
    source=tmp_path/'03_候选/raw.png';source.parent.mkdir()
    cv2.imwrite(str(source),image)
    metadata=blue_frame.attach_result({},source,layout['frame_layout_path'])
    assert metadata['frame_status']=='needs_review'
    assert metadata['candidate_filepath']==str(source)
    assert not (source.parent/'框内预览').exists()


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


def expanded_frame_fixture(tmp_path, nested=False):
    layout=blue_frame.prepare_layout(720,1559,tmp_path/'layout')
    spec=json.loads(Path(layout['frame_layout_path']).read_text())
    image=np.full((1672,941,3),255,np.uint8)
    # Provider kept the reference canvas ratio but expanded the frame almost to its edges.
    cv2.rectangle(image,(27,20),(914,1647),(214,99,22),5)
    cv2.rectangle(image,(42,40),(897,1627),(190,220,240),-1)
    cv2.rectangle(image,(48,55),(90,90),(20,40,220),-1)
    cv2.rectangle(image,(850,1560),(890,1610),(20,180,30),-1)
    cv2.line(image,(100,1608),(840,1608),(214,99,22),4) # Long blue artwork is not the outer guide.
    if nested:cv2.rectangle(image,(40,33),(901,1634),(214,99,22),4)
    return image,spec


def test_expanded_complete_frame_is_removed_before_preview(tmp_path):
    image,spec=expanded_frame_fixture(tmp_path)
    output,record=blue_frame.detect_and_resize(image,spec)
    assert output.shape==(1559,720,3)
    assert record['detection_method']=='outer_rectangle'
    assert record['crop_xyxy'][0]<40 and record['crop_xyxy'][2]>900
    assert np.count_nonzero(blue_frame.blue_mask(output)[:5])==0
    assert np.count_nonzero(blue_frame.blue_mask(output)[:,:3])==0
    assert np.count_nonzero((output[:100,:100,2]>180)&(output[:100,:100,0]<60))>100
    assert np.count_nonzero((output[-120:,-100:,1]>130)&(output[-120:,-100:,2]<60))>100


def test_expanded_nested_frames_are_never_guessed(tmp_path):
    image,spec=expanded_frame_fixture(tmp_path,nested=True)
    with pytest.raises(ValueError):blue_frame.detect_and_resize(image,spec)


def test_thin_frame_inner_outer_contours_do_not_count_as_two_frames(tmp_path):
    layout=blue_frame.prepare_layout(720,1559,tmp_path)
    spec=json.loads(Path(layout['frame_layout_path']).read_text())
    image=np.full((1600,900,3),255,np.uint8)
    cv2.rectangle(image,(60,20),(840,1580),(214,99,22),1)
    cv2.rectangle(image,(150,200),(750,1400),(120,160,80),-1)
    output,record=blue_frame.detect_and_resize(image,spec)
    assert record['detection_method']=='outer_rectangle'
    assert output.shape==(1559,720,3)
    border=np.concatenate([blue_frame.blue_mask(output)[0,:],blue_frame.blue_mask(output)[-1,:],blue_frame.blue_mask(output)[:,0],blue_frame.blue_mask(output)[:,-1]])
    assert np.count_nonzero(border)==0
    assert record['crop_xyxy'][0]<70 and record['crop_xyxy'][2]>830


def test_complete_white_exterior_frame_validates_template_aspect_drift(tmp_path):
    layout=blue_frame.prepare_layout(720,1559,tmp_path)
    spec=json.loads(Path(layout['frame_layout_path']).read_text())
    source=cv2.imread(layout['reference']['path'])
    spec['target_size']=[720,1700]
    output,record=blue_frame.detect_and_resize(source,spec)
    assert record['detection_method']=='outer_rectangle'
    assert record['aspect_change_percent']>4
    assert output.shape==(1700,720,3) and np.all(output==255)
