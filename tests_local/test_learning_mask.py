import copy
import json
from pathlib import Path

import pytest
from PIL import Image

from local_app import learning_mask as masks
from local_app.config import UserError


PID = masks.MASKED_PLACEMENT_ID


def test_fixed_mask_and_read_only_registry():
    config = masks.config();template = masks.preset_for(PID)
    assert config['mask_read_only'] is True
    assert template['enabled'] and template['height_fraction'] == .28
    assert template['max_opacity'] == .42 and template['color'] == '#000000'
    assert template['curve'] == 'linear' and template['parameter_basis'] == 'visual_initial'
    assert template['preset_id'] == config['mask_presets'][0]['id']
    assert masks.presetFor(PID) == template
    for pid in ['learning-youxuepai-unmasked-840x404','learning-baidu-512x512','not-learning']:
        assert not masks.preset_for(pid)['enabled']
    config['mask_presets'][0]['max_opacity'] = 0
    assert masks.preset_for(PID)['max_opacity'] == .42


def test_rows_are_linear_start_clear_and_bottom_matches_frontend():
    template = masks.preset_for(PID);height = 404
    rows = masks.alpha_rows(height,template)
    assert len(rows)==height and rows[-1]==107
    assert all(a==0 for a in rows[:291])
    assert rows == sorted(rows)
    for y in [291,300,350,402,403]:
        start = height*(1-template['height_fraction'])
        ratio = max(0,min(1,(y-start)/(height-1-start)))
        assert rows[y] == int(255*template['max_opacity']*ratio+.5)


def test_mask_exact_dimensions_top_unchanged_bottom_darkened_source_preserved(tmp_path):
    source=tmp_path/'source.png';target=tmp_path/'masked.png'
    Image.new('RGB',(840,404),(200,180,160)).save(source)
    before=source.read_bytes();metadata=masks.apply_mask(source,target,PID)
    assert source.read_bytes()==before and metadata['mask_applied']
    assert metadata['mask_template']==masks.preset_for(PID)
    with Image.open(target) as image:
        assert image.format=='PNG' and image.size==(840,404)
        assert image.getpixel((20,0))==(200,180,160,255)
        assert image.getpixel((400,290))==(200,180,160,255)
        assert image.getpixel((20,403))==image.getpixel((800,403))
        assert image.getpixel((20,403))[:3]==(116,104,93)
        assert image.getpixel((20,350))[0] > image.getpixel((20,403))[0]


def test_transparent_shape_is_preserved(tmp_path):
    source=tmp_path/'rgba.png';target=tmp_path/'result.png'
    image=Image.new('RGBA',(840,404),(180,150,120,130));image.putpixel((0,403),(0,0,0,0));image.save(source)
    masks.apply_mask(source,target,PID)
    with Image.open(target) as actual:
        assert actual.getchannel('A').tobytes()==image.getchannel('A').tobytes()
        assert actual.getpixel((0,403))[3]==0


def test_unmasked_png_is_byte_identical_and_cannot_be_forced_on(tmp_path):
    source=tmp_path/'source.png';target=tmp_path/'copy.png'
    Image.new('RGBA',(840,404),(51,72,91,127)).save(source)
    metadata=masks.apply_mask(source,target,'learning-youxuepai-unmasked-840x404')
    assert source.read_bytes()==target.read_bytes() and not metadata['mask_applied']
    with pytest.raises(UserError,match='固定不使用'):
        masks.apply_mask(source,tmp_path/'invalid.png','learning-youxuepai-unmasked-840x404',template=masks.preset_for(PID))


def test_size_mismatch_and_source_overwrite_are_rejected(tmp_path):
    source=tmp_path/'small.png';Image.new('RGB',(840,403)).save(source)
    with pytest.raises(UserError,match='精确尺寸'):
        masks.apply_mask(source,tmp_path/'result.png',PID)
    with pytest.raises(UserError,match='覆盖来源'):
        masks.apply_mask(source,source,PID)
    assert not list(tmp_path.glob('.learning-mask-*'))


def test_frozen_template_wins_over_changed_current_preset(tmp_path, monkeypatch):
    frozen=masks.preset_for(PID)
    config=json.loads(masks.CONFIG_PATH.read_text());config['mask_presets'][0]['max_opacity']=.9
    changed=tmp_path/'changed.json';changed.write_text(json.dumps(config));monkeypatch.setattr(masks,'CONFIG_PATH',changed)
    assert masks.preset_for(PID)['max_opacity']==.9
    source=tmp_path/'source.png';target=tmp_path/'frozen.png';Image.new('RGB',(840,404),'white').save(source)
    metadata=masks.apply_mask(source,target,PID,template=frozen)
    assert metadata['mask_template']['max_opacity']==.42
    with Image.open(target) as image:assert image.getpixel((400,403))[:3]==(148,148,148)


@pytest.mark.parametrize('changes',[
    {'enabled':1},{'enabled':'true'},{'height_fraction':True},{'height_fraction':0},
    {'height_fraction':1.1},{'height_fraction':float('nan')},{'max_opacity':True},
    {'max_opacity':-1},{'max_opacity':float('inf')},{'color':'black'},
    {'color':'#00000000'},{'color':'url(/file)'},{'curve':'ease-in'},
    {'preset_id':'../../private.png'},
])
def test_frozen_parameters_are_validated(tmp_path, changes):
    source=tmp_path/'source.png';target=tmp_path/'bad.png';Image.new('RGB',(840,404),'white').save(source)
    template={**masks.preset_for(PID),**changes};before=source.read_bytes()
    with pytest.raises(UserError):masks.apply_mask(source,target,PID,template=template)
    assert source.read_bytes()==before and not target.exists()


def test_disabled_frozen_template_is_a_copy(tmp_path):
    source=tmp_path/'source.png';target=tmp_path/'disabled.png';Image.new('RGB',(840,404),'white').save(source)
    metadata=masks.apply_mask(source,target,PID,template={'enabled':False})
    assert not metadata['mask_applied'] and source.read_bytes()==target.read_bytes()
