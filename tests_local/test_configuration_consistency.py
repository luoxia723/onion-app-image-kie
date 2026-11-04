import copy
from pathlib import Path
from unittest.mock import Mock
import pytest
from local_app.config import Settings,UserError
from local_app.engine import Engine
from local_app.planning import ASSETS,BY_ID,PLACEMENTS,STYLES,REFERENCE_PURPOSES,make_round,compile_plans
from local_app.scene_planner import PLAN_SCHEMA,SCOPED_PLAN_SCHEMA,plan_input,validate_schema
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
    with pytest.raises(UserError,match='另一窗口|版本'):app.save_settings({'planning_model':'new-model','product_text':'旧窗口修改','product_revision':first['revision']})
    assert app.product()['text']=='另一窗口的第二版' and app.settings.env_file.read_bytes()==before

def test_settings_database_failure_rolls_back_env_and_product(app):
    old=app.save_product('原资料');before=app.settings.env_file.read_bytes();model=app.settings.planning_model;db=app.db
    class BrokenCommit:
        def __getattr__(self,k):return getattr(db,k)
        def commit(self):raise OSError('test disk failure')
    app.db=BrokenCommit()
    try:
        with pytest.raises(OSError):app.save_settings({'planning_model':'new-model','product_text':'新资料','product_revision':old['revision']})
    finally:app.db=db
    assert app.product()==old and app.settings.planning_model==model and app.settings.env_file.read_bytes()==before

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

@pytest.mark.parametrize('form',['单图','双图','三图'])
@pytest.mark.parametrize('style',['random',STYLES[0]['name']])
@pytest.mark.parametrize('note',['','保留水彩笔触与暖色光影'])
def test_style_reference_unifies_all_sets_without_assigning_styles(tmp_path,monkeypatch,form,style,note):
    import visual_directions
    assign=Mock(side_effect=AssertionError('参考风格图不应调用画风分配'))
    monkeypatch.setattr(visual_directions,'assign_styles',assign)
    pr=params(form);pr.update(sets=3,style=style,ip='random')
    pr['pids']=[p['id'] for p in PLACEMENTS if p['image_form']==form][:2]
    pr['references']=[dict(id='style-ref',path=str(tmp_path/'style.png'),purpose='style',note=note)]
    r=make_round(pr,'reference-style',tmp_path/'cache',1,True,defer_planning=True)
    styles=[meta['style'] for meta in r['set_metadata'].values()]
    assert len(styles)==3 and all(style==styles[0] for style in styles)
    assert all(meta['style_id']=='reference' and meta['style_source']=='reference' for meta in r['set_metadata'].values())
    assert styles[0]['id']=='reference' and styles[0]['name']=='参考风格图'
    assert '配色、笔触、材质和光影' in styles[0]['description']
    if note:assert note in styles[0]['description']
    assert all(job['style']==styles[0] for job in plan_input(r)['jobs'])
    result=FixturePlanner().plan(r,lambda x:None)
    validate_schema(result['plans'],(PLAN_SCHEMA if form=='单图' else SCOPED_PLAN_SCHEMA)['properties']['plans'])
    compile_plans(r,result)
    assert all(entry['direction']['style_id']=='reference' for entry in r['configs'])
    assert all(styles[0]['description'] in slot['prompt'] for slot in r['slots'] if slot['idx']==1)
    assert all('参考风格图' in slot['prompt'] for slot in r['slots'])
    changed=copy.deepcopy(result);changed['plans'][0]['concept']['style_id']=STYLES[0]['id']
    with pytest.raises(UserError,match='改变了已分配画风'):compile_plans(r,changed)
    assign.assert_not_called()

@pytest.mark.parametrize('purpose',[None,'composition','ui','legacy'])
@pytest.mark.parametrize('style',['random',STYLES[0]['name']])
def test_without_style_reference_keeps_catalog_assignments(tmp_path,monkeypatch,purpose,style):
    import visual_directions
    assign=Mock(wraps=visual_directions.assign_styles)
    monkeypatch.setattr(visual_directions,'assign_styles',assign)
    pr=params();pr.update(sets=3,style=style)
    if purpose:pr['references']=[dict(id='ref',path=str(tmp_path/'ref.png'),purpose=purpose,note='')]
    r=make_round(pr,'catalog-style',tmp_path/'cache',1,True,defer_planning=True)
    assign.assert_called_once()
    expected=assign(*assign.call_args.args,**assign.call_args.kwargs)['directions']
    for number,meta in r['set_metadata'].items():
        assert meta['style_id']==expected[int(number)-1]['style_id']
        assert meta['style_source']==('random' if style=='random' else 'specified')
        catalog_style=next(item for item in STYLES if item['id']==meta['style_id'])
        assert meta['style']==dict(id=catalog_style['id'],name=catalog_style['name'],description=catalog_style.get('visual_prompt',catalog_style['prompt']))
    compile_plans(r,FixturePlanner().plan(r,lambda x:None))

@pytest.mark.parametrize('purpose',['style','composition','ui','legacy'])
@pytest.mark.parametrize('note',[None,'','   ','保留指定配色'])
def test_optional_reference_notes_do_not_leave_empty_punctuation(tmp_path,purpose,note):
    pr=params();reference=dict(id='ref',path=str(tmp_path/'ref.png'),purpose=purpose)
    if note is not None:reference['note']=note
    pr['references']=[reference]
    r=make_round(pr,'reference-note',tmp_path/'cache',1,True,defer_planning=True)
    compile_plans(r,FixturePlanner().plan(r,lambda x:None))
    role=next(ref['role'] for ref in r['slots'][0]['refs'] if ref.get('purpose')==purpose)
    expected=REFERENCE_PURPOSES[purpose]+('：'+note if note and note.strip() else '')
    assert role==expected and expected in r['slots'][0]['prompt']
    if not note or not note.strip():
        assert REFERENCE_PURPOSES[purpose]+'：' not in r['slots'][0]['prompt']
        assert REFERENCE_PURPOSES[purpose]+'，' not in r['slots'][0]['prompt']

@pytest.mark.parametrize('style',['random',STYLES[0]['name']])
def test_frozen_catalog_styles_survive_style_reference_when_filling_round(tmp_path,style):
    pr=params();pr.update(sets=3,style=style)
    original=make_round(pr,'frozen-style',tmp_path/'original',1,True,defer_planning=True)
    metadata=copy.deepcopy(original['set_metadata'])
    pr['references']=[dict(id='old-ref',path=str(tmp_path/'old.png'),purpose='style',note='旧任务已有参考风格图')]
    filled=make_round(pr,'frozen-style',tmp_path/'filled',1,True,defer_planning=True,
                      assignments=metadata,round_id=original['id'])
    assert filled['set_metadata']==original['set_metadata']==metadata
    compile_plans(filled,FixturePlanner().plan(filled,lambda x:None))
    for entry in filled['configs']:
        meta=metadata[str(entry['set'])]
        assert entry['direction']['style_id']==meta['style_id']
        assert 'style_prompt' not in entry['config']['visual_direction']
        assert meta['style']['description'] in next(slot['prompt'] for slot in filled['slots'] if slot['set']==entry['set'])

def test_legacy_reference_keeps_combined_purpose_and_empty_refs_fail_before_planning(tmp_path):
    from local_app.planning import validate
    pr=params();pr['references']=[dict(id='old',name='旧参考',path=str(tmp_path/'old.png'),note='沿用画风和构图')]
    r=make_round(pr,'legacy-reference',tmp_path/'cache',1,True,defer_planning=True)
    assert plan_input(r)['jobs'][0]['references'][0]['purpose']=='legacy'
    assert next(x for x in r['slots'][0]['refs'] if x.get('purpose'))['role'].startswith('画风/构图')
    pr.update(font='none',noLogo=True,references=[])
    with pytest.raises(UserError,match='需要参考图'):validate(pr,tmp_path)


def test_new_form_fields_survive_drafts_defaults_and_frozen_rounds(app):
    import copy
    pr=params();pid=pr['pids'][0]
    pr.update(channel=BY_ID[pid]['category'],cta_enabled=False,cta_overrides={pid:{'mode':'custom','text':'去学习'}})
    saved=app.save_draft('b'*32,{'draft':pr,'form_drafts':{'单图':pr}})
    for draft in (saved['draft'],saved['form_drafts']['单图'],app.get_draft('b'*32)['draft']):
        assert all(draft[key]==pr[key] for key in ('channel','cta_enabled','cta_overrides'))
    task=app.create(saved['draft'],'new-form-fields',draft_id='b'*32)
    frozen=copy.deepcopy(app.task(task['id'])['rounds'][0]['params'])
    defaults=app.document('form_defaults')['单图']
    assert all(defaults[key]==frozen[key]==pr[key] for key in ('channel','cta_enabled','cta_overrides'))
    pr['cta_overrides'][pid]['text']='之后修改'
    assert app.task(task['id'])['rounds'][0]['params']['cta_overrides'][pid]['text']=='去学习'


@pytest.mark.parametrize('changes',[
    {'cta_enabled':False},{'cta_overrides':{'mode':'custom','text':'去学习'}},
    {'cta_overrides':{'mode':'none'}},{'cta_overrides':{'mode':'inherit'}},
])
def test_button_setting_changes_create_a_new_round(app,changes):
    import copy
    pr=params();pr['cta']='统一按钮';pid=pr['pids'][0]
    task=app.create(pr,'button-first-round');tid=task['id']
    unchanged=app.create({**pr,'cta_enabled':True,'cta_overrides':{}},'button-same-round',tid)
    assert unchanged['added_image_count']==0 and len(app.task(tid)['rounds'])==1
    if 'cta_overrides' in changes:changes={'cta_overrides':{pid:changes['cta_overrides']}}
    changed={**copy.deepcopy(app.task(tid)['rounds'][0]['params']),**changes}
    app.create(changed,'button-new-round',tid)
    rounds=app.task(tid)['rounds']
    assert len(rounds)==2 and rounds[0]['copy_signature']!=rounds[1]['copy_signature']
    assert all(rounds[1]['params'][key]==value for key,value in changes.items())
    assert all(app.document('form_defaults')['单图'][key]==value for key,value in changes.items())
    if 'cta_overrides' in changes and changes['cta_overrides'][pid]['mode']=='custom':
        changed['cta_overrides'][pid]['text']='再去学习'
        app.create(changed,'button-updated-custom',tid)
        assert len(rounds)==3 and rounds[-1]['configs'][0]['config']['cta']=='再去学习'


def test_existing_legacy_references_can_be_reused_but_new_ones_are_rejected(app):
    import copy
    from PIL import Image
    upload=app.settings.state_dir/'uploads'/'legacy.png';upload.parent.mkdir(exist_ok=True)
    Image.new('RGB',(32,32),'white').save(upload)
    pr=params();pr['references']=[dict(id='old',purpose='style',path=str(upload))]
    task=app.create(pr,'before-legacy-migration');tid=task['id']
    original=app.task(tid)['rounds'][0];original['params']['references'][0].pop('purpose')
    changed=copy.deepcopy(original['params']);changed['t1']='旧任务的新标题'
    app.create(changed,'reuse-legacy-reference',tid)
    current=app.task(tid)['rounds'][-1]
    assert plan_input(current)['jobs'][0]['references'][0]['purpose']=='legacy'
    assert next(ref for ref in current['slots'][0]['refs'] if ref.get('purpose')=='legacy')['role'].startswith('画风/构图')
    changed['references'][0].update(id='new',purpose='legacy')
    with pytest.raises(UserError,match='请选择参考图用途'):app.create(changed,'reject-new-legacy',tid)
    with pytest.raises(UserError,match='请选择参考图用途'):app.create(original['params'],'reject-new-task-legacy')


@pytest.mark.parametrize('note',[None,'','参考图A','字'*200])
@pytest.mark.parametrize('purpose',['style','composition','ui'])
def test_upload_accepts_optional_reference_note_without_binding_a_port(app,note,purpose):
    import base64
    from io import BytesIO
    from types import SimpleNamespace
    from PIL import Image
    from local_app.server import Handler
    image=BytesIO();Image.new('RGB',(32,32),'white').save(image,format='PNG')
    body=dict(data=base64.b64encode(image.getvalue()).decode(),purpose=purpose)
    if note is not None:body['note']=note
    handler=Handler.__new__(Handler)
    handler.server=SimpleNamespace(engine=app,server_port=8000)
    handler.headers={'Host':'127.0.0.1:8000'};handler.path='/api/uploads';handler.command='POST'
    handler.body=lambda:body;handler.json=lambda result:result
    result=handler.handle_api()
    assert result['note']==(note or '') and result['purpose']==purpose
    assert Path(result['path']).is_file()


@pytest.mark.parametrize('body',[
    {'purpose':'style','note':'字'*201},{'purpose':'legacy'},{'purpose':'unknown'},{},
])
def test_upload_rejects_long_notes_and_legacy_purposes(app,body):
    from types import SimpleNamespace
    from local_app.server import Handler
    handler=Handler.__new__(Handler)
    handler.server=SimpleNamespace(engine=app,server_port=8000)
    handler.headers={'Host':'127.0.0.1:8000'};handler.path='/api/uploads';handler.command='POST'
    handler.body=lambda:body
    with pytest.raises(UserError,match='参考图'):handler.handle_api()
