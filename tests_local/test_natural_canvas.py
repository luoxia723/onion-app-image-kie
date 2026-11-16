"""Current ad requests use unmarked natural canvases and fixed learning crops."""
import copy
import hashlib
from pathlib import Path

import pytest
from PIL import Image,ImageDraw

from local_app import natural_canvas
from local_app.config import UserError
from local_app.planning import BY_ID,STYLES,compile_plans
from kie_model import MODELS
from tests_local.fakes import FixturePlanner
from tests_local.test_brand_logo import engine


def params(p,model):
    return dict(channel=p['category'],image_form=p['image_form'],pids=[p['id']],sets=1,
        t1='不会的题拍一下',t2='分步讲解',s1='第一句',s2='第二句',s3='第三句',cta='点击下载',
        ip='none',font='none',style=STYLES[0]['name'],image_model=model)


@pytest.mark.parametrize('model',list(MODELS))
def test_all_ordinary_placements_compile_without_blue_guides_or_cv(engine,monkeypatch,model):
    placements=[p for p in BY_ID.values() if p['category']!='学习机']
    assert len(placements)==19
    for i,p in enumerate(placements):
        task=engine.task(engine.create(params(p,model),'natural-create-'+str(i)+model)['id']);round=task['rounds'][0]
        compile_plans(round,FixturePlanner().plan(round,lambda _:None))
        assert round['natural_canvas_version']==1
        assert round['params']['canvas_protocol']==natural_canvas.PROTOCOL
        for slot in round['slots']:
            assert 'frame' not in slot and slot['natural_canvas_plan']['placement_id']==p['id']
            assert '生成完整自然画布' in slot['prompt'] and '蓝框' not in slot['prompt']
            assert all('蓝框' not in ref.get('role','') for ref in slot['refs'])
            natural_canvas.validate_prompt(slot['prompt'],slot['natural_canvas_plan'])
            assert len(slot['refs'])==1
            layer=slot['brand_logo_layer'];box=layer['generation_box'];crop=slot['natural_canvas_plan']['group']['targets'][0]['crop_box']
            assert (box[0]-crop[0])/(crop[2]-crop[0])==pytest.approx(layer['template']['x'])
            assert (box[1]-crop[1])/(crop[3]-crop[1])==pytest.approx(layer['template']['y'])


@pytest.mark.parametrize('model',list(MODELS))
@pytest.mark.parametrize('pid',['oppo-app-slot-slot-474x768','ximalaya-current-single-1200x480','ximalaya-current-single-720x1559','cpa-current-single-690x360'])
def test_previously_framed_sizes_use_fixed_crop_and_preserve_safe_content(tmp_path,model,pid):
    p=BY_ID[pid];plan=natural_canvas.plan(p,model);group=plan['group'];w,h=group['guide_size']
    source=tmp_path/'native.png';target=tmp_path/'exact.png';image=Image.new('RGB',(w,h),'#cccccc');draw=ImageDraw.Draw(image)
    x1,y1,x2,y2=group['content_safe_box']
    for x,y,color in [(x1,y1,'red'),(x2,y1,'green'),(x1,y2,'blue'),(x2,y2,'yellow')]:
        x=round(x*w);y=round(y*h);draw.rectangle((x-10,y-10,x+10,y+10),fill=color)
    image.save(source);before=source.read_bytes();result=natural_canvas.crop(source,target,plan,p)
    assert source.read_bytes()==before and result['exact_size_verified']
    assert result['unmarked_canvas'] is True and result['stretch_applied'] is False
    with Image.open(target) as im:
        assert im.size==(p['target_width'],p['target_height'])
        colors=set(im.convert('RGB').get_flattened_data());assert {(255,0,0),(0,128,0),(0,0,255),(255,255,0)}<=colors


def test_unexpected_provider_shape_is_refused_without_overwriting_delivery(tmp_path):
    p=BY_ID['ximalaya-current-single-720x1559'];plan=natural_canvas.plan(p,next(iter(MODELS)))
    source=tmp_path/'wrong.png';Image.new('RGB',(400,400),'red').save(source);target=tmp_path/'saved.png';target.write_bytes(b'old delivery')
    with pytest.raises(UserError,match='比例'):natural_canvas.crop(source,target,plan,p)
    assert target.read_bytes()==b'old delivery'


def test_framing_reaches_scene_planner_and_keeps_existing_request_text_frozen(engine):
    from local_app.scene_planner import plan_input
    p=BY_ID['ximalaya-current-single-1200x480']
    task=engine.task(engine.create(params(p,next(iter(MODELS))),'natural-framing-planning')['id'])
    round=task['rounds'][0];plan=round['slots'][0]['natural_canvas_plan']
    rule=natural_canvas.prompt_rule(plan)
    assert plan_input(round)['jobs'][0]['framing_rule']==rule
    assert '不要用人物大特写' in rule
    previous=copy.deepcopy(plan);previous.pop('framing_rule_version')
    old_rule=natural_canvas.prompt_rule(previous)
    assert '不要用人物大特写' not in old_rule
    natural_canvas.validate_prompt(old_rule,previous)
    with pytest.raises(ValueError,match='安全区'):natural_canvas.validate_prompt(old_rule,plan)


def test_exact_rehearsal_pixels_are_not_cropped_twice_and_logo_is_post_layer(engine):
    p=BY_ID['ximalaya-current-single-1200x480'];task=engine.task(engine.create(params(p,next(iter(MODELS))),'natural-materialize-test')['id']);round=task['rounds'][0]
    compile_plans(round,FixturePlanner().plan(round,lambda _:None));slot=round['slots'][0]
    path=Path(slot['output']);Image.new('RGB',(1200,480),'#667788').save(path);before=path.read_bytes()
    slot.update(engine.materialize_image(slot,{'source':str(path)},path,p));engine.persist(task)
    assert path.read_bytes()==before and slot['delivery_eligible']
    assert slot['natural_processing']['method']=='natural_canvas_exact_crop' and 'frame_status' not in slot
    assert slot['logo_base']['without_logo']
    details=engine.image_details(task['id'],slot['id']);assert details['canvas_fixed_rule']==natural_canvas.prompt_rule(slot['natural_canvas_plan'])
    assert 'natural_canvas_plan' not in details
    with pytest.raises(UserError,match='自然画布'):
        engine.mutate(task['id'],'regenerate',{'image_id':slot['id'],'expected_att':1,'prompt':details['logo_fixed_rule']+'\n只保留自由文案'})
    engine.mutate(task['id'],'regenerate',{'image_id':slot['id'],'expected_att':1,'prompt':slot['prompt']})
    assert slot['versions'][0]['natural_canvas_plan']==slot['natural_canvas_plan']
    assert slot['versions'][0]['natural_processing']['exact_size_verified']


def test_retired_request_metadata_cannot_be_resumed_or_regenerated(engine):
    p=BY_ID['ximalaya-current-single-1200x480'];task=engine.task(engine.create(params(p,next(iter(MODELS))),'retired-protocol-refusal')['id'])
    round=task['rounds'][0];slot=round['slots'][0]
    slot['frame']={'enabled':True};slot['state']='done'
    for action in ('regenerate','resume','add-variant','retry-planning','continue'):
        with pytest.raises(UserError,match='停用'):engine.mutate(task['id'],action,{'image_id':slot['id'],'placement_id':slot['pid']})
    slot.update(state='queued',plan_ready=True);engine.dispatch_tick()
    assert not engine.running and not engine.planning_running


def test_retired_record_loads_read_only_and_new_configuration_starts_clean_round(engine,tmp_path):
    import sqlite3
    from local_app.config import Settings
    from local_app.engine import Engine
    p=BY_ID['ximalaya-current-single-1200x480'];task=engine.task(engine.create(params(p,next(iter(MODELS))),'retired-load-refusal')['id'])
    task['rounds'][0]['slots'][0].update(frame={'enabled':True},state='queued',plan_ready=True);engine.persist(task)
    settings=Settings(tmp_path/'retired-state',tmp_path/'retired.env');settings.update({'simulation':True,'output_dir':str(engine.settings.output)})
    settings.state_dir.mkdir(exist_ok=True)
    with sqlite3.connect(settings.state_dir/'index.sqlite3') as target:engine.db.backup(target)
    restored=Engine(settings,start=False,planner=FixturePlanner())
    try:
        saved=restored.task(task['id']);old=saved['rounds'][0]
        assert old['generation_disabled'] and old['slots'][0]['state']=='stopped'
        restored.dispatch_tick();assert not restored.running and not restored.planning_running
        restored.create(copy.deepcopy(old['params']),'retired-start-clean-round',tid=saved['id'])
        assert len(saved['rounds'])==2 and saved['rounds'][1]['natural_canvas_version']==1
        assert all('frame' not in s for s in saved['rounds'][1]['slots'])
    finally:restored.close()
