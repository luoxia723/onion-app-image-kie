from pathlib import Path
import pytest
from local_app.config import Settings,UserError
from local_app.engine import Engine
from local_app.planning import ASSETS,BY_ID,PLACEMENTS,make_round,compile_plans
from local_app.scene_planner import plan_input
from tests_local.fakes import FixturePlanner

@pytest.fixture
def app(tmp_path):
    settings=Settings(tmp_path/'state',tmp_path/'.env')
    settings.update({'simulation':True,'output_dir':str(tmp_path)})
    e=Engine(settings,start=False,planner=FixturePlanner())
    yield e
    e.close()

def params(form='单图'):
    p=next(p for p in PLACEMENTS if p['image_form']==form)
    return dict(image_form=form,pids=[p['id']],sets=1,t1='每天进步一点',t2='打开今天的学习任务',s1='开始学习',s2='继续学习',s3='查看进度',cta='',ip='none',style='random',noLogo=False)

def test_settings_failure_never_partially_updates_product(app):
    old=app.save_product('原资料');before=app.settings.env_file.read_bytes()
    with pytest.raises(UserError):app.save_settings({'planning_model':'','product_text':'新资料','product_revision':old['revision']})
    assert app.product()==old and app.settings.env_file.read_bytes()==before

def test_settings_rejects_stale_product_editor_before_any_write(app):
    first=app.save_product('第一版');app.save_product('另一窗口的第二版')
    before=app.settings.env_file.read_bytes()
    with pytest.raises(UserError,match='另一窗口|版本'):app.save_settings({'concurrency':8,'product_text':'旧窗口修改','product_revision':first['revision']})
    assert app.product()['text']=='另一窗口的第二版' and app.settings.env_file.read_bytes()==before

def test_settings_database_failure_rolls_back_env_and_product(app):
    old=app.save_product('原资料');before=app.settings.env_file.read_bytes();db=app.db
    class BrokenCommit:
        def __getattr__(self,k):return getattr(db,k)
        def commit(self):raise OSError('test disk failure')
    app.db=BrokenCommit()
    try:
        with pytest.raises(OSError):app.save_settings({'concurrency':8,'product_text':'新资料','product_revision':old['revision']})
    finally:app.db=db
    assert app.product()==old and app.settings.concurrency==4 and app.settings.env_file.read_bytes()==before

def test_draft_product_is_frozen_and_all_drafts_remain_discoverable(app):
    first=app.save_product('已确认的第一版资料')
    for i in range(51):
        saved=app.save_draft(f'{i:032x}',{'draft':params(),'revision':0,'sequence':1,'editor_id':'audit'})
    app.save_product('之后修改的第二版')
    draft=app.get_draft('0'*32)['draft']
    assert draft['product_facts']==first['text'] and draft['facts_version']==first['revision']
    assert len(app.list_drafts())==51
    summaries=app.draft_summaries('打开今天')
    assert len(summaries)==51 and all('product_facts' not in x['draft'] for x in summaries)
    task=app.create(draft,'frozen-product-submit')
    assert task['rounds'][0]['params']['facts_version']==first['revision']

def test_retired_placement_uses_frozen_specs_in_all_read_paths(app,monkeypatch):
    task=app.create(params(),'retired-placement');tid=task['id'];pid=params()['pids'][0]
    monkeypatch.delitem(BY_ID,pid)
    assert app.public(app.task(tid))['rounds'][0]['pending_placements'][0]['placement_id']==pid
    assert app.view_task(tid)['rounds'][0]['placement_rules'][pid]['target_width']>0
    assert app.list_summaries()['tasks'][0]['id']==tid

@pytest.mark.parametrize('form',['单图','双图','三图'])
@pytest.mark.parametrize('font',['none','specified'])
def test_font_choice_controls_actual_refs_and_branch_contract(tmp_path,form,font):
    selected=next(a for a in ASSETS if a['kind']=='font' and a.get('enabled',True))
    pr=params(form);pr['font']=selected['asset_id'] if font=='specified' else 'none'
    r=make_round(pr,'font-choice',tmp_path,1,True,defer_planning=True)
    compile_plans(r,FixturePlanner().plan(r,lambda x:None))
    cfg=r['configs'][0]['config'];refs=r['slots'][0]['refs']
    assert cfg['font_reference_enabled']==(font=='specified')
    fonts=[x for x in refs if x.get('role')=='标题字体参考']
    assert len(fonts)==(1 if font=='specified' else 0)
    if fonts:assert Path(fonts[0]['path']).name==Path(selected['path']).name
    for s in r['slots'][1:]:assert len(s['refs'])==1 and s['first_id']==r['slots'][0]['id']

@pytest.mark.parametrize('purpose,mode',[('style','conceptual'),('composition','conceptual'),('ui','reference')])
@pytest.mark.parametrize('form',['单图','双图','三图'])
def test_reference_purpose_reaches_planner_and_final_prompt(tmp_path,purpose,mode,form):
    pr=params(form);pr['references']=[dict(id='ref',name='截图',path=str(tmp_path/'ui.png'),note='保留上传图片的指定内容',purpose=purpose)]
    r=make_round(pr,'typed-reference',tmp_path/'cache',1,True,defer_planning=True)
    compile_plans(r,FixturePlanner().plan(r,lambda x:None))
    assert r['configs'][0]['config']['screen_ui_mode']==mode
    assert plan_input(r)['jobs'][0]['references'][0]['purpose']==purpose
    if purpose=='ui':assert '真实界面' in r['slots'][0]['prompt'] and any(x.get('purpose')=='ui' and '截图' in x['role'] for x in r['slots'][0]['refs'])
    for s in r['slots'][1:]:assert len(s['refs'])==1 and s['first_id']==r['slots'][0]['id']

def test_legacy_reference_keeps_combined_purpose_and_empty_refs_fail_before_planning(tmp_path):
    from local_app.planning import validate
    pr=params();pr['references']=[dict(id='old',name='旧参考',path=str(tmp_path/'old.png'),note='沿用画风和构图')]
    r=make_round(pr,'legacy-reference',tmp_path/'cache',1,True,defer_planning=True)
    assert plan_input(r)['jobs'][0]['references'][0]['purpose']=='legacy'
    assert next(x for x in r['slots'][0]['refs'] if x.get('purpose'))['role'].startswith('画风/构图')
    pr.update(font='none',noLogo=True,references=[])
    with pytest.raises(UserError,match='需要参考图'):validate(pr,tmp_path)
