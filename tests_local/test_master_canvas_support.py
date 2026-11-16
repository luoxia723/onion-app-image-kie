"""Trusted source selection freezes pixels, narrative identity and current rules."""
import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from local_app.config import UserError
from local_app.master_canvas_support import freeze_adaptation,freeze_sources
from local_app.planning import BY_ID
from tests_local.test_brand_logo import engine,ready


def ordinary(task,round,**extra):
    return dict(source=dict(kind='ordinary',task_id=task['id'],image_ids=[s['id'] for s in round['slots']],
                            atts={s['id']:s['att'] for s in round['slots']}),
                target_kind='ordinary',pids=[round['slots'][0]['pid']],**extra)


def test_ordinary_clean_source_frozen_without_replanning_or_mutating_task(engine,tmp_path):
    task,round=ready(engine);before=copy.deepcopy(task);params=ordinary(task,round)
    from local_app.logo_templates import save_templates
    pid=params['pids'][0]
    save_templates(engine,{'revision':0,'templates':[{'placement_id':pid,'asset_id':'learning.logo.white-app','x':.05,'y':.04,'width':.2}]})
    frozen=freeze_adaptation(engine,params,tmp_path/'adaptation')
    assert task==before
    source=frozen['sources'][0];slot=round['slots'][0]
    assert Path(source['path']).read_bytes()==Path(slot['logo_base']['path']).read_bytes()
    assert not source['contains_logo']
    assert source['sha256']==slot['logo_base']['sha256']
    assert frozen['mode']=='simulation' and frozen['kind']=='shared_canvas_adaptation'
    assert frozen['params']['t1']=='每天进步一点' and frozen['params']['bodysource']=='frozen_source'
    assert frozen['compiled']['counts']['baseline_image_calls']==0
    assert frozen['compiled']['counts']['background_image_calls']==0
    master=frozen['compiled']['masters'][0]
    assert master['allowed_text']=={'t1':'每天进步一点','subtitle':'看看今天的学习内容','cta':'点击体验'}
    assert master['source_id']==source['id'] and master['canvas_plan']['id']==master['id']
    pid=params['pids'][0]
    assert frozen['placement_snapshots'][pid]['output_format']=='JPEG'
    assert frozen['logo_snapshot']['placements'][pid]['logo_required']
    assert frozen['logo_snapshot']['placements'][pid]['logo_template']['x']==.05
    assert frozen['logo_snapshot']['placements'][pid]['logo_template']['asset_id']=='learning.logo.white-app'
    save_templates(engine,{'revision':1,'templates':[{'placement_id':pid,'asset_id':'learning.logo.black','x':.1,'y':.04,'width':.2}]})
    assert frozen['logo_snapshot']['placements'][pid]['logo_template']['x']==.05
    assert Path(next(iter(frozen['logo_snapshot']['assets'].values()))['path']).parent.name=='learning-logo-assets'
    assert frozen['source_approval']['source']=='explicit_source_selection'
    assert frozen['source_summary']['copy_basis']=='frozen_task_copy'
    from local_app import learning_logo
    exported=tmp_path/'logo-preview.png'
    assert learning_logo.composite(source['path'],exported,pid,frozen['logo_snapshot'])['logo_applied']
    with Image.open(exported) as image:assert image.size==(BY_ID[pid]['target_width'],BY_ID[pid]['target_height'])


def test_application_freeze_passes_source_direction_to_relayout_prompt(engine,tmp_path):
    task,round=ready(engine)
    params=ordinary(task,round)
    params['pids']=['cpa-current-single-1080x1920']
    frozen=freeze_adaptation(engine,params,tmp_path/'portrait')
    master=frozen['compiled']['masters'][0]
    assert master['direction']=='portrait'
    assert '按目标画幅重新安排人物和文字' in master['prompt']
    assert master['single_regeneration_prompt']==master['prompt']


def test_historical_version_uses_its_own_clean_bytes_and_corruption_refused(engine,tmp_path):
    task,round=ready(engine);slot=round['slots'][0];old=copy.deepcopy(slot);old.pop('versions')
    slot['versions']=[old];slot['att']=2
    slot['logo_base']={'path':str(tmp_path/'other.png'),'sha256':'0'*64,'without_logo':True}
    params=ordinary(task,round);params['source']['atts'][slot['id']]=1
    frozen=freeze_sources(engine,params,tmp_path/'history')
    assert frozen['sources'][0]['sha256']==old['logo_base']['sha256']
    Path(old['logo_base']['path']).write_bytes(b'changed')
    with pytest.raises(UserError,match='校验失败'):freeze_sources(engine,params,tmp_path/'corrupt')


def test_baked_legacy_jpeg_and_failed_frame_are_truthful_sources(engine,tmp_path):
    task,round=ready(engine);slot=round['slots'][0];slot.pop('logo_base');slot.pop('brand_logo_layer')
    frozen=freeze_sources(engine,ordinary(task,round),tmp_path/'legacy')
    assert frozen['sources'][0]['contains_logo'] is True
    assert Path(frozen['sources'][0]['path']).read_bytes()==Path(slot['jpeg']).read_bytes()
    slot['delivery_eligible']=False
    with pytest.raises(UserError,match='规格'):freeze_sources(engine,ordinary(task,round),tmp_path/'unqualified')


def test_explicit_raw_selects_verified_original_instead_of_clean_or_jpeg(engine,tmp_path):
    task,round=ready(engine);slot=round['slots'][0]
    # The native model canvas is explicitly selected instead of its JPEG delivery.
    Image.new('RGB',(180,240),'blue').save(slot['output'],'PNG')
    slot['raw_sha256']=hashlib.sha256(Path(slot['output']).read_bytes()).hexdigest()
    params=ordinary(task,round);params['source']['use_raw']=True
    frozen=freeze_sources(engine,params,tmp_path/'explicit-raw');source=frozen['sources'][0]
    assert source['sha256']==slot['raw_sha256']
    assert source['sha256'] not in (slot['sha256'],slot['logo_base']['sha256'])
    assert source['contains_logo'] is False
    assert source['raw_selected'] is True
    slot.pop('brand_logo_layer')
    assert freeze_sources(engine,params,tmp_path/'legacy-raw')['sources'][0]['contains_logo'] is True
    for invalid in ('true',1,None):
        params['source']['use_raw']=invalid
        with pytest.raises(UserError,match='来源方式'):freeze_sources(engine,params,tmp_path/str(invalid))


def test_three_story_sources_never_group_together_and_incomplete_suite_refused(engine,tmp_path):
    pid=next(p['id'] for p in BY_ID.values() if p['category']!='学习机' and p['image_count']==3)
    task,round=ready(engine,pid,s1='第一张难题',s2='第二张分析',s3='第三张懂了')
    params=ordinary(task,round)
    with pytest.raises(UserError,match='全部来源'):
        freeze_sources(engine,{**params,'source':{**params['source'],'image_ids':[round['slots'][0]['id']],
                           'atts':{round['slots'][0]['id']:1}}},tmp_path/'incomplete')
    frozen=freeze_adaptation(engine,params,tmp_path/'complete')
    masters=frozen['compiled']['masters'];assert len(masters)==3
    assert {m['source_index'] for m in masters}=={1,2,3}
    assert {m['allowed_text']['t1'] for m in masters}=={'第一张难题','第二张分析','第三张懂了'}
    single=next(p['id'] for p in BY_ID.values() if p['category']!='学习机' and p['image_count']==1)
    with pytest.raises(UserError,match='张数一致'):freeze_adaptation(engine,{**params,'pids':[single]},tmp_path/'wrong-count')


def test_source_path_escape_and_target_kind_are_rejected(engine,tmp_path):
    task,round=ready(engine);slot=round['slots'][0]
    outside=tmp_path.parent/(tmp_path.name+'-outside.png');Image.new('RGB',(20,20)).save(outside)
    slot['logo_base'].update(path=str(outside),sha256=hashlib.sha256(outside.read_bytes()).hexdigest())
    try:
        with pytest.raises(UserError,match='登记工作区'):freeze_sources(engine,ordinary(task,round),tmp_path/'escaped')
    finally:outside.unlink()


def test_optional_cta_override_none_does_not_invent_button(engine,tmp_path):
    pid=next(p['id'] for p in BY_ID.values() if p['category']!='学习机' and p['image_count']==1 and p.get('cta_policy')=='optional')
    task,round=ready(engine,pid,cta_overrides={pid:{'mode':'none'}})
    frozen=freeze_adaptation(engine,ordinary(task,round),tmp_path/'no-cta')
    assert all('cta' not in m['allowed_text'] for m in frozen['compiled']['masters'])


def test_custom_cta_survives_global_button_disabled(engine,tmp_path):
    pid=next(p['id'] for p in BY_ID.values() if p['category']!='学习机' and p['image_count']==1 and p.get('cta_policy')=='optional')
    task,round=ready(engine,pid,cta_enabled=False,cta='',cta_overrides={pid:{'mode':'custom','text':'立即看看'}})
    frozen=freeze_adaptation(engine,ordinary(task,round),tmp_path/'custom-cta')
    assert frozen['placement_snapshots'][pid]['modules']['cta'] is True
    assert all(m['allowed_text']['cta']=='立即看看' for m in frozen['compiled']['masters'])


def test_learning_confirmation_hash_and_runtime_injection(engine,tmp_path):
    directory=tmp_path/'learning';directory.mkdir();path=directory/'base.png';Image.new('RGB',(160,90),'green').save(path)
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    source=dict(id='source-run',directory=str(directory),mode='simulation',busy=False,
        params={'t1':'问题拍一下','cta':'点击下载','ip':'none','style':'frozen','font':'none'},
        baseline=dict(id='baseline',status='done',version=3,sha256=sha,raw_path=str(path),prompt='old exact prompt'),
        approval=dict(confirmed=False,baseline_version=3,sha256=sha,mode='simulation'),outputs=[])
    runtime=SimpleNamespace(runs={'source-run':source});params=dict(source={'kind':'learning','run_id':'source-run','baseline':True},
        target_kind='learning',pids=['learning-baidu-512x512'])
    with pytest.raises(UserError,match='确认'):freeze_sources(engine,params,tmp_path/'unconfirmed',source_runtime=runtime)
    source['approval']['confirmed']=True;before=copy.deepcopy(source)
    frozen=freeze_adaptation(engine,params,tmp_path/'approved',source_runtime=runtime)
    assert source==before and frozen['sources'][0]['sha256']==sha
    assert frozen['inherited_baseline']['prompt']=='old exact prompt'
    assert frozen['placement_snapshots']['learning-baidu-512x512']['output_format']=='PNG'
    masked=freeze_adaptation(engine,{**params,'pids':['learning-youxuepai-masked-840x404']},tmp_path/'masked',source_runtime=runtime)
    group=masked['compiled']['masters'][0]
    assert group['targets'][0]['visible_box']==[0,0,1,.72]
    assert group['content_safe_box'][3]<group['shared_keep_box'][3]
    with pytest.raises(UserError,match='版本已更新'):
        freeze_sources(engine,{**params,'source':{**params['source'],'baseline_version':2}},tmp_path/'old-selection',source_runtime=runtime)
    source['outputs']=[dict(id='output::1',status='done',version=2,raw_path=str(path),raw_sha256=sha)]
    output_params={**params,'source':dict(kind='learning',run_id='source-run',output_ids=['output::1'],versions={'output::1':1})}
    with pytest.raises(UserError,match='版本已更新'):freeze_sources(engine,output_params,tmp_path/'old-output',source_runtime=runtime)
    output_params['source']['versions']['output::1']=2
    output=freeze_sources(engine,output_params,tmp_path/'current-output',source_runtime=runtime)
    assert output['sources'][0]['sha256']==sha and output['sources'][0]['source_kind']=='learning_output'
    source['approval']['sha256']='0'*64
    with pytest.raises(UserError,match='确认'):freeze_sources(engine,params,tmp_path/'stale',source_runtime=runtime)
