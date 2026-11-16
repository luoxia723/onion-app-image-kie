import copy
import hashlib

import pytest
from PIL import Image

from local_app.config import Settings,UserError
from local_app import learning_logo,learning_mask
from local_app.learning_output import export_output


def frozen(tmp_path,pid):
    settings=Settings(tmp_path/'state',tmp_path/'test.env')
    return learning_logo.freeze_templates(settings,[pid]),{pid:learning_mask.preset_for(pid)}


def test_export_uses_gray_mask_at_exact_dimensions_and_preserves_source(tmp_path):
    pid='learning-youxuepai-masked-840x404';logo,mask=frozen(tmp_path,pid)
    source=tmp_path/'source.png';target=tmp_path/'output.png';Image.new('RGB',(2000,1000),'white').save(source)
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    result=export_output(source,target,pid,logo,mask_snapshot=mask,protected_regions=[(.2,.2,.6,.6)])
    with Image.open(target) as image:
        assert image.format=='PNG' and image.size==(840,404)
        assert image.convert('RGBA').getpixel((400,50))==(255,255,255,255)
        assert 140<=image.getpixel((400,403))[0]<=155
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    assert result['exact_size_verified'] and not result['badge_applied']
    assert result['processing_order']==['exact_crop_and_resize','bottom_gray_mask','placement_logo','rounded_corners']


def test_deferred_featured_card_keeps_only_logo_and_rounded_alpha(tmp_path):
    pid='learning-dsl-rounded-card-484x580';logo,mask=frozen(tmp_path,pid)
    source=tmp_path/'source.png';target=tmp_path/'output.png';Image.new('RGB',(1000,1250),'#ccddee').save(source)
    result=export_output(source,target,pid,logo,mask_snapshot=mask)
    with Image.open(target) as image:
        assert image.size==(484,580)
        assert image.getpixel((0,0))[3]==0
        assert image.getpixel((40,70))==(204,221,238,255)
    assert result['logo']['logo_applied'] and result['corner_radius']==44
    assert not result['badge_applied'] and not result['feature_label_drawn']


def test_export_refuses_unsafe_crop_without_replacing_existing_output(tmp_path):
    pid='learning-baidu-1200x400';logo,mask=frozen(tmp_path,pid)
    source=tmp_path/'source.png';target=tmp_path/'output.png';Image.new('RGB',(1000,1000),'white').save(source)
    target.write_bytes(b'previous version')
    with pytest.raises(UserError,match='重要内容'):
        export_output(source,target,pid,logo,mask_snapshot=mask,protected_regions=[(0,0,1,1)])
    assert target.read_bytes()==b'previous version'
    assert not list(tmp_path.glob('.learning-export-*'))


def test_current_png_size_limit_does_not_shrink_pixels_or_replace_previous_output(tmp_path):
    import random
    pid='learning-dsl-resource-484x580';logo,mask=frozen(tmp_path,pid)
    source=tmp_path/'source.png';target=tmp_path/'output.png'
    # An actual high-entropy PNG exceeds this placement's 100KB limit, without
    # weakening the configured limit or replacing the compressor with a mock.
    Image.frombytes('RGB',(484,580),random.Random(7).randbytes(484*580*3)).save(source)
    before=source.read_bytes();target.write_bytes(b'previous exported version')
    with pytest.raises(UserError,match='超过.*PNG大小限制'):
        export_output(source,target,pid,logo,mask_snapshot=mask)
    assert source.read_bytes()==before
    assert target.read_bytes()==b'previous exported version'
    assert not list(tmp_path.glob('.learning-export-*'))


def test_export_uses_frozen_mask_instead_of_later_preset_edits(tmp_path,monkeypatch):
    pid='learning-youxuepai-masked-840x404';logo,mask=frozen(tmp_path,pid)
    source=tmp_path/'source.png';Image.new('RGB',(840,404),'white').save(source)
    first=tmp_path/'first.png';second=tmp_path/'second.png'
    export_output(source,first,pid,logo,mask_snapshot=mask)
    changed=copy.deepcopy(mask[pid]);changed['max_opacity']=.9
    monkeypatch.setattr(learning_mask,'preset_for',lambda _:changed)
    export_output(source,second,pid,logo,mask_snapshot=mask)
    assert first.read_bytes()==second.read_bytes()


def test_all_compiled_fixed_ratio_crops_export_to_exact_delivery_pixels(tmp_path):
    from local_app.learning_pipeline import preview
    from local_app.learning_prompts import build
    from local_app.learning_sizing import export_exact
    from kie_model import GPT_IMAGE_26_FLARE
    plan=build(preview({'t1':'不会的题拍一下','ip':'none','font':'none'},seed='all-fixed-crops'),GPT_IMAGE_26_FLARE)
    sources={}
    for output in plan['outputs']:
        ratio=output['aspect_ratio']
        if ratio not in sources:
            a,b=map(int,ratio.split(':'));sources[ratio]=tmp_path/(ratio.replace(':','-')+'.png')
            Image.new('RGB',(a*32,b*32),'white').save(sources[ratio])
        target=tmp_path/(output['output_id'].replace('::','-')+'.png')
        result=export_exact(sources[ratio],target,output['target_width'],output['target_height'],crop_box=output['crop_box'])
        with Image.open(target) as image:assert image.size==(output['target_width'],output['target_height'])
        assert result['exact_size_verified']
    assert len(plan['outputs'])==45


def test_indexed_byte_limit_keeps_size_and_prioritizes_logo_colors(tmp_path):
    import numpy as np
    pid='learning-dsl-banner-830x250';logo,mask=frozen(tmp_path,pid)
    source=tmp_path/'colorful.png';target=tmp_path/'delivery.png'
    # Coarse textured regions represent compressible artwork. Full-resolution
    # entropy remains a separate rejection case, not a promise of arbitrary
    # noise fitting the channel budget without quality loss.
    Image.fromarray(np.random.default_rng(7).integers(0,256,(250,415,3),dtype=np.uint8)).resize((830,250),Image.Resampling.NEAREST).save(source)
    assert source.stat().st_size>200*1024
    result=export_output(source,target,pid,logo,mask_snapshot=mask)
    assert result['palette_colors'] is not None and target.stat().st_size<200*1024
    with Image.open(target) as image:
        assert image.size==(830,250)
        aid=result['logo']['logo_asset_id'];x,y,w,h=result['logo']['pixel_box']
        with Image.open(logo['assets'][aid]['path']) as mark:
            mark=mark.convert('RGBA').resize((w,h),Image.Resampling.LANCZOS)
            px,py=next((px,py) for py in range(h) for px in range(w) if mark.getpixel((px,py))[3]==255)
            actual=image.convert('RGBA').getpixel((x+px,y+py));expected=mark.getpixel((px,py))
            # Indexed PNG is a color reduction, not lossless RGB storage. Keep
            # the brand's color close instead of allowing a noisy picture to
            # consume the whole palette and turn the blue mark into purple.
            assert actual[3]==expected[3]==255
            assert max(abs(a-b) for a,b in zip(actual[:3],expected[:3]))<=12


def test_transparent_textured_png_can_use_palette_without_shrinking_or_losing_rounding(tmp_path):
    import random
    pid='learning-dsl-rounded-card-484x580';logo,mask=frozen(tmp_path,pid)
    source=tmp_path/'textured.png';target=tmp_path/'rounded.png'
    Image.frombytes('RGB',(242,290),random.Random(29).randbytes(242*290*3)).resize((484,580),Image.Resampling.NEAREST).save(source)
    before=source.read_bytes()
    result=export_output(source,target,pid,logo,mask_snapshot=mask)
    assert result['encoding_method']=='indexed' and result['bytes']<100*1024
    assert source.read_bytes()==before
    with Image.open(target) as image:
        assert image.format=='PNG' and image.size==(484,580)
        rgba=image.convert('RGBA');assert rgba.getpixel((0,0))[3]==0
        assert rgba.getpixel((242,290))[3]==255
