import copy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import socket
import zipfile

from PIL import Image, ImageDraw
import pytest

from local_app import brand_logo
from local_app.config import Settings,UserError
from local_app.engine import Engine
from local_app.planning import BY_ID,STYLES,bootstrap,compile_plans
from local_app.quality import verify_saved_package
from tests_local.fakes import FixturePlanner
from tests_local.test_learning_setup_api import api


@pytest.fixture
def engine(tmp_path,monkeypatch):
    monkeypatch.setenv('ONION_SIM_SECONDS','0')
    settings=Settings(tmp_path/'state',tmp_path/'fake.env')
    settings.update({'output_dir':str(tmp_path),'simulation':True})
    engine=Engine(settings,start=False,planner=FixturePlanner())
    yield engine
    engine.close()


def ready(engine,pid='appstore-ios-single',**changes):
    if pid not in BY_ID:
        pid=next(p['id'] for p in BY_ID.values() if p['category']!='学习机' and p['image_count']==1)
    p=BY_ID[pid]
    params={**dict(pids=[pid],sets=1,t1='每天进步一点',t2='看看今天的学习内容',cta='点击体验',
                ip='none',font='none',style=STYLES[0]['name'],noLogo=False),**changes}
    value=engine.create(params,'brand-test-'+str(len(engine.tasks)))
    task=engine.task(value['id']);round=task['rounds'][0]
    compile_plans(round,FixturePlanner().plan(round,lambda value:None))
    for slot in round['slots']:
        path=Path(slot['output'])
        Image.new('RGB',(p['target_width'],p['target_height']),'#7c91bb').save(path,'PNG')
        slot.update(engine.materialize_image(slot,{'source':str(path)},path,p))
    engine.persist(task)
    engine.mutate(task['id'],'adopt',{'set':1,'adopted':True})
    return task,round


def test_registered_variants_aliases_transparency_and_selection_validation():
    assert [a['id'] for a in bootstrap()['assets']['logos']]==['learning.logo.black','learning.logo.white-app']
    assert brand_logo.normalize_id('logo.onion.standard.001')=='learning.logo.black'
    assert brand_logo.normalize_id('logo.onion.app.002')=='learning.logo.white-app'
    assert brand_logo.normalize_id('logo.onion.app.001')=='learning.logo.white-app'
    for row in brand_logo.assets():
        with Image.open(brand_logo.asset_path(row['id'])) as image:
            assert image.mode=='RGBA' and image.getchannel('A').getextrema()[0]==0
    for bad in ['/etc/passwd',{},'logo.unknown']:
        with pytest.raises(UserError):brand_logo.normalize_id(bad)


def test_new_ordinary_prompt_has_no_logo_reference_and_neutral_canvas_is_honest(engine,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('no network')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    task,round=ready(engine)
    assert all(c['config']['logo']=='不用' and c['config']['brand_logo_layer']['model_draws_logo'] is False for c in round['configs'])
    slot=round['slots'][0]
    assert not any(r.get('asset_id','').startswith('logo.') or r.get('asset_id','').startswith('learning.logo.') for r in slot['refs'])
    if not slot.get('frame'):
        assert slot['refs'][0]['kind']=='neutral_canvas'
        assert '只定比例，不提供人物、内容或画风' in slot['prompt']
        with Image.open(slot['refs'][0]['path']) as blank:assert blank.getextrema()==((255,255),)*3
    assert '绘制无Logo底图' in slot['prompt'] and '预留自然连续' in slot['prompt']
    assert brand_logo.switchable(slot)
    assert slot['logo_base']['without_logo'] and slot['delivery_logo_asset_id']=='learning.logo.black'


def test_materialization_keeps_exact_unbranded_base_and_independent_logo(engine):
    task,round=ready(engine);slot=round['slots'][0];p=BY_ID[slot['pid']]
    with Image.open(slot['logo_base']['path']) as base:
        assert base.size==(p['target_width'],p['target_height'])
        assert base.convert('RGB').getextrema()==((124,124),(145,145),(187,187))
    with Image.open(slot['jpeg']) as output:
        assert output.size==(p['target_width'],p['target_height'])
        assert len(output.getcolors(output.width*output.height))>1
    public=engine.public(task)['rounds'][0]
    assert public['logo_export_switchable'] and public['logo_export_capability']['editable']
    assert public['slots'][0]['logo_switchable'] and 'logo_base' not in public['slots'][0]
    details=engine.image_details(task['id'],slot['id'])
    assert details['logo_switchable'] and 'brand_logo_layer' not in details and 'logo_base' not in details


def test_ordinary_automatic_logo_uses_the_wordmark_area_not_the_whole_image(tmp_path):
    placement=dict(id='contrast-test',target_width=480,target_height=240,output_format='PNG')
    layer=brand_logo.freeze(placement,None,tmp_path)
    source=tmp_path/'source.png';target=tmp_path/'result.png'
    image=Image.new('RGB',(480,240),'#ddd4ac')
    x=round(layer['template']['x']*480);y=round(layer['template']['y']*240)
    w=round(layer['template']['width']*480)
    ImageDraw.Draw(image).rectangle((x+w//4,y,x+w,y+w//4),fill='#20274e')
    image.save(source)
    result=brand_logo.render_delivery(source,target,placement,layer)
    assert result['asset_id']=='learning.logo.white-app'
    assert result['pixel_box'][:2]==[x,y]
    with Image.open(target) as rendered:
        assert rendered.size==(480,240)
        assert rendered.getpixel((400,180))[:3]==image.getpixel((400,180))


def test_export_variant_changes_actual_bytes_and_choice_but_keeps_old_zip_and_artwork(engine):
    task,round=ready(engine);tid=task['id'];slot=round['slots'][0]
    old_slot=copy.deepcopy(slot);black=engine.package(tid,0)
    old_bytes=Path(black['path']).read_bytes()
    preview=engine.package_preview(tid,0,logo_asset_id='learning.logo.white-app')
    assert preview['next_version']=='v002'
    white=engine.package(tid,0,logo_asset_id='learning.logo.white-app')
    assert white['id']!=black['id'] and white['fingerprint']!=black['fingerprint']
    assert white['fingerprint_schema']==black['fingerprint_schema']==3
    assert Path(black['path']).read_bytes()==old_bytes and slot==old_slot
    assert engine.delivery_state(task,round)['has_changes'] is False and task['downloaded'] is True
    assert white['source_fingerprint']==black['source_fingerprint']
    assert engine.package(tid,0,logo_asset_id='logo.onion.app.002')['id']==white['id']
    assert engine.package(tid,0)['id']==black['id']
    with zipfile.ZipFile(white['path']) as archive:
        manifest=json.loads(archive.read('交付清单.json'))
        assert manifest['fingerprint_schema']==3
        assert manifest['images'][0]['logo_asset_id']=='learning.logo.white-app'
        assert manifest['images'][0]['logo_layer']['asset_sha256']==slot['brand_logo_layer']['assets']['learning.logo.white-app']['sha256']
        actual=archive.read(manifest['images'][0]['path'])
        assert hashlib.sha256(actual).hexdigest()==manifest['images'][0]['sha256']
        assert actual!=Path(slot['jpeg']).read_bytes()
    verify_saved_package(white['path'],white['fingerprint'],engine.placement_rules(task,round))

def test_review_logo_uses_the_same_bytes_in_preview_and_a_new_zip(api):
    engine,request=api
    task,round=ready(engine);slot=round['slots'][0];tid=task['id'];sid=slot['id']
    base='/api/tasks/'+tid
    original=Path(slot['jpeg']).read_bytes()
    old=engine.package(tid,0)
    old_archive=Path(old['path']).read_bytes()
    body={'image_id':sid,'expected_att':slot['att'],'expected_sha256':slot['sha256'],'asset_id':'learning.logo.white-app'}
    status,updated=request(base+'/review-logo','POST',body)
    assert status==200,updated
    image=updated['rounds'][0]['slots'][0]
    status,preview=request(image['image_url'])
    assert status==200 and preview!=original and image['att']==slot['att']
    assert Path(slot['jpeg']).read_bytes()==original and image['delivery_logo_asset_id']==body['asset_id']
    assert request(base+'/review-logo','POST',body)[0]==409
    status,pkg=request(base+'/packages','POST',{'round':0})
    assert status==200 and pkg['package_id']!=old['id']
    status,archive_bytes=request(pkg['download_url'])
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        item=json.loads(archive.read('交付清单.json'))['images'][0]
        assert status==200 and item['logo_asset_id']==body['asset_id'] and archive.read(item['path'])==preview
    assert Path(old['path']).read_bytes()==old_archive
    assert request(updated['pkgs'][0]['images'][0]['thumbnail_url'])[1]==original
    status,reverted=request(base+'/review-logo','POST',{**body,'asset_id':slot['delivery_logo_asset_id'],'expected_sha256':image['sha256']})
    assert status==200 and request(reverted['rounds'][0]['slots'][0]['image_url'])[1]==original
    no_logo_task,no_logo_round=ready(engine,noLogo=True)
    excluded=no_logo_round['slots'][0]
    assert not engine.public(no_logo_task)['rounds'][0]['slots'][0]['logo_review_switchable']
    assert request('/api/tasks/'+no_logo_task['id']+'/review-logo','POST',
                   {**body,'image_id':excluded['id'],'expected_att':excluded['att'],'expected_sha256':excluded['sha256']})[0]==409


@pytest.mark.history
def test_legacy_baked_images_export_unchanged_and_cannot_claim_logo_replacement(engine):
    task,round=ready(engine);slot=round['slots'][0]
    for key in ('brand_logo_layer','logo_base','delivery_logo_asset_id'):slot.pop(key,None)
    raw=Path(slot['jpeg']).read_bytes();engine.persist(task)
    assert not engine.public(task)['rounds'][0]['logo_export_switchable']
    ordinary=engine.package(task['id'],0)
    assert ordinary['fingerprint_schema']==2
    with zipfile.ZipFile(ordinary['path']) as archive:
        manifest=json.loads(archive.read('交付清单.json'))
        assert archive.read(manifest['images'][0]['path'])==raw
    for action in (engine.package,engine.package_preview):
        with pytest.raises(UserError,match='没有无Logo底图'):
            action(task['id'],0,logo_asset_id='learning.logo.white-app')
    assert Path(slot['jpeg']).read_bytes()==raw


def test_corrupted_frozen_logo_or_base_cannot_be_exported_as_success(engine):
    task,round=ready(engine);slot=round['slots'][0]
    base=Path(slot['logo_base']['path']);original=base.read_bytes();base.write_bytes(b'broken')
    with pytest.raises(UserError,match='底图校验失败'):engine.package(task['id'],0,logo_asset_id='learning.logo.white-app')
    base.write_bytes(original)
    logo=Path(slot['brand_logo_layer']['assets']['learning.logo.white-app']['path']);logo.write_bytes(b'broken')
    with pytest.raises(UserError,match='冻结Logo素材校验失败'):engine.package(task['id'],0,logo_asset_id='learning.logo.white-app')


def test_centered_portrait_and_corner_templates_fit_both_logo_variants(tmp_path):
    for platform,w,h in [('喜马拉雅',720,1280),('应用商店',1242,2688),('信息流',1280,720),('信息流',400,100)]:
        p=dict(id=platform+str(w),platform=platform,target_width=w,target_height=h)
        layer=brand_logo.freeze(p,'learning.logo.black',tmp_path/platform)
        assert layer['template']['position']==('上方居中' if platform=='喜马拉雅' else '左上角')
        source=tmp_path/(platform+str(w)+'-base.png');Image.new('RGB',(w,h),'#334455').save(source)
        for row in brand_logo.assets():
            target=source.with_name(source.stem+row['id']+'.png')
            metadata=brand_logo.composite(source,target,layer,row['id'])
            assert metadata['logo_applied'] and metadata['asset_id']==row['id']
            with Image.open(target) as result:assert result.size==(w,h)
    with pytest.raises(UserError,match='不能覆盖来源'):brand_logo.composite(source,source,layer)


def test_restart_preserves_schema3_and_reuses_variant_zip(engine):
    task,round=ready(engine)
    saved=engine.package(task['id'],0,logo_asset_id='learning.logo.white-app')
    before=Path(saved['path']).read_bytes();settings=engine.settings
    engine.close()
    reloaded=Engine(settings,start=False,planner=FixturePlanner())
    try:
        stored=reloaded.task(task['id'])['pkgs'][0]
        assert stored['fingerprint_schema']==3 and stored['fingerprint']==saved['fingerprint']
        assert reloaded.package(task['id'],0,logo_asset_id='learning.logo.white-app')['id']==saved['id']
        assert Path(saved['path']).read_bytes()==before
    finally:reloaded.close()
    # The fixture closes only the replacement, avoiding a second DB close.
    engine.close=lambda:None


def test_history_freezes_logo_base_and_backup_restore_preserves_both_variants(engine,tmp_path):
    task,round=ready(engine);slot=round['slots'][0];sid=slot['id'];p=engine.placement(task,round,slot)
    old_base=slot['logo_base']['sha256']
    white=brand_logo.export_variant(slot,p,'learning.logo.white-app')['sha256']
    saved=engine.package(task['id'],0)
    engine.mutate(task['id'],'regenerate',{'image_id':sid})
    previous=slot['versions'][0]
    assert previous['logo_base']['sha256']==old_base
    assert previous['brand_logo_layer']['selected_asset_id']=='learning.logo.black'
    assert previous['delivery_logo_asset_id']=='learning.logo.black'
    assert engine.image_details(task['id'],sid,1)['logo_switchable'] is True
    assert engine.image_details(task['id'],sid,2)['logo_switchable'] is False
    plan=engine.prune_plan()
    assert not any(v['image_id']==sid and v['att']==1 for v in plan['versions'])
    backup=engine.create_backup()
    assert backup['missing']==0
    manifest=engine.inspect_backup(backup['path'])
    paths={f['path'] for f in manifest['files']}
    assert previous['logo_base']['path'] in paths
    assert all(a['path'] in paths for a in previous['brand_logo_layer']['assets'].values())
    (tmp_path/'restored-output').mkdir()
    settings=Settings(tmp_path/'restored-state',tmp_path/'restored.env')
    settings.update({'output_dir':str(tmp_path/'restored-output'),'simulation':True})
    restored=Engine(settings,start=False,planner=FixturePlanner())
    try:
        preview=restored.restore_preview(backup['path'])
        restored.restore_backup(backup['path'],preview['token'])
        reloaded=restored.task(task['id'])['rounds'][0]['slots'][0]
        historical=reloaded['versions'][0]
        assert brand_logo.switchable(historical)
        assert historical['logo_base']['path']!=previous['logo_base']['path']
        assert historical['logo_base']['sha256']==old_base
        assert brand_logo.export_variant(historical,p,'learning.logo.white-app')['sha256']==white
        assert restored.image_details(task['id'],sid,1)['logo_switchable'] is True
    finally:restored.close()


def test_prune_unprotected_history_removes_its_base_but_protects_current_assets(engine):
    task,round=ready(engine);slot=round['slots'][0]
    engine.mutate(task['id'],'regenerate',{'image_id':slot['id']})
    old=slot['versions'][0];p=engine.placement(task,round,slot)
    path=Path(slot['output']);Image.new('RGB',(p['target_width'],p['target_height']),'#818181').save(path)
    slot.update(engine.materialize_image(slot,{'source':str(path)},path,p));engine.persist(task)
    plan=engine.prune_plan()
    candidate=next(v for v in plan['versions'] if v['image_id']==slot['id'] and v['att']==1)
    assert str(Path(old['logo_base']['path']).resolve()) in candidate['files']
    current_base=Path(slot['logo_base']['path']);assets=[Path(a['path']) for a in slot['brand_logo_layer']['assets'].values()]
    assert all(str(path.resolve()) not in candidate['files'] for path in [current_base,*assets])
    engine.prune_versions(plan['token'])
    assert not Path(old['logo_base']['path']).exists()
    assert current_base.is_file() and all(path.is_file() for path in assets)


def test_optional_no_logo_is_never_added_by_variant_export(engine):
    task,round=ready(engine,noLogo=True);slot=round['slots'][0]
    assert not slot['brand_logo_layer']['enabled']
    assert not engine.public(task)['rounds'][0]['logo_export_switchable']
    black=engine.package(task['id'],0)
    white=engine.package(task['id'],0,logo_asset_id='learning.logo.white-app')
    assert white['id']==black['id']
    assert slot['delivery_logo_asset_id']==''
    with Image.open(slot['jpeg']) as image:assert image.convert('RGB').getextrema()[0][1]-image.convert('RGB').getextrema()[0][0]==0
