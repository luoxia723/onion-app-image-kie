import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from local_app import learning_logo as logos
from local_app.config import ROOT, UserError


@pytest.fixture
def settings(tmp_path):
    return SimpleNamespace(state_dir=tmp_path / 'state')


def logo_row(config):
    return next(p for p in config['placements'] if p['logo_required'])


def update(row, **changes):
    return {'placement_id': row['id'], **row['logo_template'], **changes}


def test_registry_defaults_fixed_presence_and_transparency(settings):
    config = logos.config(settings)
    assert config['revision'] == 0 and len(config['placements']) == 44
    assert sum(p['logo_required'] for p in config['placements']) == 36
    assert len(config['logo_assets']) == 2
    assert {a['id'] for a in config['logo_assets']} == logos.ASSET_IDS
    for p in config['placements']:
        assert bool(p['logo_template']) == p['logo_required']
        if p['logo_required']:
            assert p['logo_template']['asset_id'] == 'learning.logo.black'
    for asset in config['logo_assets']:
        with Image.open(logos.asset_path(asset['id'])) as image:
            assert image.format == 'PNG'
            assert image.size == (asset['width'], asset['height'])
            assert image.convert('RGBA').getchannel('A').getextrema() == (0, 255)


def test_default_logos_stay_near_upper_left_and_both_export_variants_fit(settings,tmp_path):
    cfg=logos.config(settings)
    for row in cfg['placements']:
        if not row['logo_required']:continue
        template=row['logo_template']
        assert template['x']<=.04 and template['y']<=.04
        if row['target_width']/row['target_height']>=2.7:assert template['width']>=.10
        snapshot=logos.freeze_templates(settings,[row['id']])
        for aid in logos.ASSET_IDS:
            selected=logos.variant_snapshot(snapshot,aid,tmp_path/aid)
            t=selected['placements'][row['id']]['logo_template'];a=selected['assets'][aid]
            height=t['width']*row['target_width']/row['target_height']*a['height']/a['width']
            assert t['x']+t['width']<=1 and t['y']+height<=1+1e-9


def test_black_asset_preserves_original_pixels_and_white_preserves_eyes():
    with Image.open(ROOT / 'assets/logos/onion-logo-standard-001.png') as source:
        original = source.convert('RGBA');original = original.crop(original.getbbox())
    with Image.open(logos.asset_path('learning.logo.black')) as output:
        assert original.tobytes() == output.convert('RGBA').tobytes()
    # White APP source has genuine dark pupil pixels inside the mascot. They
    # remain opaque and unchanged rather than being removed with the navy field.
    with Image.open(ROOT / 'assets/logos/onion-logo-app-001.png') as source:
        original = source.convert('RGB')
    with Image.open(logos.asset_path('learning.logo.white-app')) as output:
        rgba = output.convert('RGBA')
        checked = 0
        for y in range(480, 570):
            for x in range(160, 430):
                color = original.getpixel((x, y))
                if max(color) < 30:
                    assert rgba.getpixel((x-86, y-311)) == color + (255,)
                    checked += 1
        assert checked > 500
        assert rgba.getpixel((1250-86, 600-311))[3] == 0


def test_save_roundtrip_freeze_is_independent_and_revision_conflict(settings, tmp_path):
    initial = logos.config(settings);row = logo_row(initial)
    saved = logos.save_templates(settings, {'revision': 0, 'templates': [update(row, asset_id='learning.logo.white-app', x=.04, y=.05, width=.15)]})
    assert saved['revision'] == 1
    restored = logos.config(SimpleNamespace(state_dir=settings.state_dir))
    current = next(p for p in restored['placements'] if p['id'] == row['id'])
    assert current['logo_template'] == {'asset_id':'learning.logo.white-app','x':.04,'y':.05,'width':.15}
    frozen = logos.freeze_templates(settings, [row['id']], tmp_path/'round')
    snapshot = copy.deepcopy(frozen)
    logos.save_templates(settings, {'revision':1,'templates':[update(current, asset_id='learning.logo.black', x=.10)]})
    assert frozen == snapshot and frozen['revision'] == 1
    for asset in frozen['assets'].values():
        assert Path(asset['path']).parent == tmp_path/'round/learning-logo-assets'
        assert hashlib.sha256(Path(asset['path']).read_bytes()).hexdigest() == asset['sha256']
    with pytest.raises(UserError, match='另一窗口'):
        logos.save_templates(settings, {'revision':1,'templates':[update(current)]})


@pytest.mark.parametrize('field,value', [('x', -1), ('y', -1), ('width', 0), ('width', -1), ('width', True), ('width', '0.2'), ('width', float('nan')), ('x', float('inf')), ('y', float('-inf'))])
def test_invalid_geometry_is_rejected_without_writing(settings, field, value):
    row = logo_row(logos.config(settings))
    with pytest.raises(UserError):
        logos.save_templates(settings, {'revision':0,'templates':[update(row, **{field:value})]})
    assert not (settings.state_dir/logos.STATE_NAME).exists()


def test_atomic_validation_bounds_fixed_off_and_registered_assets(settings):
    config = logos.config(settings);row = logo_row(config)
    off = next(p for p in config['placements'] if not p['logo_required'])
    bad_cases = [
        [update(row, x=.99, width=.2)],
        [update(row, y=.99, width=.2)],
        [update(row, asset_id='/tmp/logo.png')],
        [update(row, path='/tmp/logo.png')],
        [update(row), update(row)],
        [{'placement_id':off['id'],'asset_id':'learning.logo.black','x':.02,'y':.02,'width':.2}],
        [update(row), {'placement_id':'unknown','asset_id':'learning.logo.black','x':.02,'y':.02,'width':.2}],
    ]
    for changes in bad_cases:
        with pytest.raises(UserError):logos.save_templates(settings, {'revision':0,'templates':changes})
        assert logos.config(settings)['revision'] == 0
        assert not (settings.state_dir/logos.STATE_NAME).exists()
    with pytest.raises(UserError):logos.asset_path('../../.env')
    with pytest.raises(UserError):logos.sample_path('../../.env')


def test_optional_sample_and_sampleless_template(settings):
    config = logos.config(settings)
    assert sum('sample_url' in p for p in config['placements']) == 41
    missing = next(p for p in config['placements'] if p['id']=='learning-xueersi-1125x885')
    assert missing['logo_required'] and missing['logo_template'] and 'sample_url' not in missing
    given = next(p for p in config['placements'] if p['id']=='learning-baidu-512x512')
    assert given['sample_url'].endswith(given['id']) and logos.sample_path(given['id']).is_file()


def test_all_new_content_samples_are_project_local_and_near_size_is_reference_only(settings):
    config = logos.config(settings)
    new_ids = {'learning-dsl-banner-830x250','learning-dsl-banner-1200x350',
               'learning-youxuepai-masked-840x404','learning-youxuepai-double-840x404',
               'learning-zuoyebang-1223x471'}
    content = logos._placements()
    for row in config['placements']:
        if row['id'] not in new_ids:
            continue
        path = logos.sample_path(row['id'])
        assert path.parent == (ROOT/'assets/learning-machine/samples').resolve()
        assert path.name == row['id']+'.png'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == content[row['id']]['evidence']['sha256']
        assert row['sample_reference_only'] is True and row['sample_url'].endswith(row['id'])
        with Image.open(path) as image:assert list(image.size)==row['sample_size']
    near = next(p for p in config['placements'] if p['id']=='learning-zuoyebang-1223x471')
    assert near['target_width']==1223 and near['sample_size']==[1224,471]
    assert '近尺寸' in near['sample_note'] and '不作为直接成品替代' in near['sample_note']


def test_sample_whitelist_rejects_outside_paths_symlinks_and_bad_hash(tmp_path, monkeypatch):
    folder=tmp_path/'assets/learning-machine/samples';folder.mkdir(parents=True)
    secret=tmp_path/'private.txt';secret.write_text('not a sample')
    safe=folder/'registered.png';Image.new('RGB',(10,10)).save(safe)
    alias=folder/'alias.png';alias.symlink_to(secret)
    monkeypatch.setattr(logos,'ROOT',tmp_path)
    original_read=Path.read_bytes
    def checked_read(path):
        assert path.resolve()!=secret.resolve(), 'must not read an outside file'
        return original_read(path)
    monkeypatch.setattr(Path,'read_bytes',checked_read)
    for path in [str(secret),'assets/learning-machine/samples/../../../private.txt',str(alias),None]:
        assert logos._sample_file({'path':path,'sha256':'0'*64}) is None
    with pytest.raises(UserError,match='样图校验'):
        logos._sample_file({'path':str(safe),'sha256':'0'*64})
    assert logos._sample_file({'path':str(safe),'sha256':hashlib.sha256(original_read(safe)).hexdigest()})==safe


@pytest.mark.parametrize('filename',['../../private.png',r'..\private.png','/tmp/private.png'])
def test_sample_evidence_cannot_supply_a_local_path(monkeypatch, filename):
    pid='learning-test-sample'
    monkeypatch.setattr(logos,'_placements',lambda:{pid:{'evidence':{'kind':'sample_review','sample_file':filename,'sha256':'0'*64}}})
    with pytest.raises(UserError,match='注册信息'):
        logos.sample_path(pid)


def test_composite_uses_frozen_asset_preserves_size_and_source(settings, tmp_path):
    config=logos.config(settings);row=logo_row(config)
    frozen=logos.freeze_templates(settings,[row['id']],tmp_path/'round')
    source=tmp_path/'raw.png';output=tmp_path/'with-logo.png'
    Image.new('RGB',(row['target_width'],row['target_height']),'#8aabc4').save(source)
    before=source.read_bytes();metadata=logos.composite(source,output,row['id'],frozen)
    assert source.read_bytes()==before and metadata['logo_applied']
    with Image.open(output) as im:
        assert im.format=='PNG' and im.size==(row['target_width'],row['target_height'])
        x,y,w,h=metadata['pixel_box'];assert x>=0 and y>=0 and x+w<=im.width and y+h<=im.height
        assert im.convert('RGB').getpixel((im.width-1,im.height-1))==(138,171,196)
    with pytest.raises(UserError,match='覆盖来源'):
        logos.composite(source,source,row['id'],frozen)
    Image.new('RGB',(100,100)).save(source)
    with pytest.raises(UserError,match='精确尺寸'):
        logos.composite(source,tmp_path/'wrong.png',row['id'],frozen)


def test_composite_fixed_off_does_not_add_logo(settings, tmp_path):
    row=next(p for p in logos.config(settings)['placements'] if not p['logo_required'])
    frozen=logos.freeze_templates(settings,[row['id']],tmp_path/'round')
    source=tmp_path/'source.png';output=tmp_path/'result.png'
    Image.new('RGBA',(row['target_width'],row['target_height']),(20,30,40,120)).save(source)
    metadata=logos.composite(source,output,row['id'],frozen)
    assert not metadata['logo_applied'] and not frozen['assets']
    with Image.open(source) as a, Image.open(output) as b:assert a.tobytes()==b.tobytes()


def test_frozen_logo_corruption_is_rejected(settings, tmp_path):
    row=logo_row(logos.config(settings));snapshot=logos.freeze_templates(settings,[row['id']],tmp_path/'round')
    asset=next(iter(snapshot['assets'].values()));Path(asset['path']).write_bytes(b'corrupt')
    source=tmp_path/'source.png';Image.new('RGB',(row['target_width'],row['target_height'])).save(source)
    with pytest.raises(UserError,match='冻结 Logo'):
        logos.composite(source,tmp_path/'out.png',row['id'],snapshot)
