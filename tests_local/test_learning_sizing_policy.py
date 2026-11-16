"""Opt-in complete-source adaptation is distinct from frozen historical crops."""
import hashlib

import pytest
from PIL import Image,ImageDraw

from local_app.config import Settings,UserError
from local_app import learning_logo,learning_mask
from local_app.learning_sizing import export_exact
from local_app.learning_output import export_output


@pytest.mark.parametrize('target_size,content_box',[
    ((400,100),(100,0,300,100)),((200,200),(0,50,200,150)),
])
def test_full_source_policy_keeps_all_edge_content_without_stretch_or_crop(tmp_path,target_size,content_box):
    source=tmp_path/'source.png';target=tmp_path/'delivery.png'
    image=Image.new('RGBA',(200,100),'white');draw=ImageDraw.Draw(image)
    draw.rectangle((0,0,199,99),outline='red',width=4)
    for box,color in (((0,0,8,8),'blue'),((190,0,199,8),'green'),((0,90,8,99),'yellow'),((190,90,199,99),'purple')):
        draw.rectangle(box,fill=color)
    image.save(source);before=source.read_bytes()
    result=export_exact(source,target,*target_size,crop_box=[0,.25,1,.75],
                        protected_regions=[[0,0,1,1]],sizing_policy='preserve_source')
    with Image.open(target) as exported:
        assert exported.size==target_size and exported.format=='PNG'
        assert exported.convert('RGBA').crop(content_box).tobytes()==image.tobytes()
    assert source.read_bytes()==before
    assert result['source_box']==result['crop_box']==[0,0,1,1]
    assert result['crop_percent']==0 and result['padding_percent']==50
    assert result['content_detection']=='not_performed' and result['full_source_preserved'] is True
    assert result['seam_review_required'] is True and result['ai_repair_performed'] is False


@pytest.mark.history
def test_legacy_run_without_policy_still_uses_its_frozen_crop(tmp_path):
    source=tmp_path/'source.png';old=tmp_path/'old.png';new=tmp_path/'new.png'
    image=Image.new('RGB',(200,100),'green');draw=ImageDraw.Draw(image)
    draw.rectangle((0,0,199,9),fill='red');draw.rectangle((0,90,199,99),fill='blue');image.save(source)
    box=[0,.25,1,.75]
    original=export_exact(source,old,400,100,crop_box=box)
    preserved=export_exact(source,new,400,100,crop_box=box,sizing_policy='preserve_source')
    with Image.open(old) as legacy:
        assert legacy.convert('RGB').getpixel((200,0))==(0,128,0)
        assert legacy.convert('RGB').getpixel((200,99))==(0,128,0)
    with Image.open(new) as safe:
        assert safe.convert('RGB').getpixel((200,0))==(255,0,0)
        assert safe.convert('RGB').getpixel((200,99))==(0,0,255)
    assert original['sizing_policy']=='fixed_crop' and original['crop_percent']==50
    assert preserved['sizing_policy']=='preserve_source' and preserved['crop_percent']==0


def test_output_records_preserved_source_geometry_with_exact_channel_dimensions(tmp_path):
    pid='learning-bbg-no-logo-banner-1280x362'
    settings=Settings(tmp_path/'state',tmp_path/'test.env')
    logo=learning_logo.freeze_templates(settings,[pid]);mask={pid:learning_mask.preset_for(pid)}
    source=tmp_path/'source.png';target=tmp_path/'finished.png';Image.new('RGB',(1536,512),'#7799bb').save(source)
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    result=export_output(source,target,pid,logo,mask_snapshot=mask,crop_box=[0,.07578125,1,.92421875],sizing_policy='preserve_source')
    with Image.open(target) as image:assert image.size==(1280,362) and image.format=='PNG'
    sizing=result['sizing']
    assert sizing['crop_percent']==0 and sizing['padding_percent']==pytest.approx(15.15625)
    assert sizing['method']=='contain_full_source_color_gradient' and 'path' not in sizing
    assert result['processing_order'][0]=='exact_contain_and_resize'
    assert not result['logo']['logo_applied'] and not result['mask']['mask_applied']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before


def test_preserve_source_rejects_overwriting_input_or_unknown_policy(tmp_path):
    source=tmp_path/'source.png';Image.new('RGB',(200,100),'white').save(source);before=source.read_bytes()
    with pytest.raises(UserError,match='覆盖'):export_exact(source,source,400,100,sizing_policy='preserve_source')
    with pytest.raises(UserError,match='策略'):export_exact(source,tmp_path/'bad.png',400,100,sizing_policy='imaginary_ai_repair')
    assert source.read_bytes()==before and not (tmp_path/'bad.png').exists()
