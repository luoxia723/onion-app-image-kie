from pathlib import Path
import pytest
from local_app.config import UserError
from local_app.planning import PLACEMENTS, validate

def params(form):
    p=next(p for p in PLACEMENTS if p['image_form']==form)
    return dict(image_form=form,pids=[p['id']],sets=1,t1='主标题',t2='副标题',s1='第一句',s2='第二句',s3='第三句',cta='立即体验',ip='none',style='random')

@pytest.mark.parametrize('forms',[['单图','双图'],['双图','三图']])
def test_batch_rejects_incompatible_copy_forms(forms,tmp_path):
    pr=params(forms[0]);a=pr['pids'][0]
    pr['pids'].append(next(p['id'] for p in PLACEMENTS if p['image_form']==forms[1] and p['id']!=a))
    with pytest.raises(UserError,match='形式|同一种|同一'):validate(pr,tmp_path)

def test_form_cannot_disagree_with_placement(tmp_path):
    pr=params('双图');pr['image_form']='三图'
    with pytest.raises(UserError,match='形式'):validate(pr,tmp_path)

@pytest.mark.parametrize('form,fields',[('单图',['t1','t2']),('双图',['s1','s2']),('三图',['s1','s2','s3'])])
def test_only_active_form_fields_are_required(form,fields,tmp_path):
    pr=params(form)
    for k in ['t1','t2','s1','s2','s3']:
        if k not in fields:pr[k]=''
    validate(pr,tmp_path)
    pr[fields[-1]]=''
    with pytest.raises(UserError):validate(pr,tmp_path)

@pytest.mark.parametrize('form',['单图','双图','三图'])
def test_same_copy_supports_multiple_compatible_placements(form,tmp_path):
    pr=params(form);pr['pids']=[p['id'] for p in PLACEMENTS if p['image_form']==form][:2]
    validate(pr,tmp_path)


def test_freezing_copy_discards_fields_from_other_forms():
    from local_app.planning import normalize_form
    original=params('双图')
    normalized=normalize_form(original)
    assert normalized['t1']==normalized['t2']==normalized['s3']==''
    assert normalized['s1']=='第一句' and normalized['s2']=='第二句'
    assert original['t1']=='主标题'


def test_real_generation_does_not_use_simulation_scene_templates(tmp_path):
    from local_app.planning import make_round
    with pytest.raises(UserError,match='画面方案|画面规划'):
        make_round(params('单图'),'real-plan-required',tmp_path,20,False)


@pytest.mark.parametrize('ip_choice',['none','random','specified'])
@pytest.mark.parametrize('no_logo',[True,False])
def test_user_material_choices_reach_planner_and_actual_first_image_refs(tmp_path,ip_choice,no_logo):
    from local_app.planning import ASSETS,STYLES,make_round,compile_plans
    from local_app.scene_planner import plan_input
    from tests_local.fakes import FixturePlanner
    ip=next(a for a in ASSETS if a['kind']=='ip' and '.standard.' in a['asset_id'])
    pr=params('单图')
    pr.update(ip=ip['asset_id'] if ip_choice=='specified' else ip_choice,
              style=STYLES[0]['name'],noLogo=no_logo,feature_note='标题与人物不要互相遮挡',
              references=[dict(id='user-ref',path=str(tmp_path/'reference.png'),note='参考空间构图',name='reference.png',purpose='composition')])
    validate(pr,tmp_path)
    r=make_round(pr,'material-choices',tmp_path,2,True,defer_planning=True)
    data=plan_input(r)['jobs'][0];meta=r['set_metadata']['1']
    assert data['style']['name']==pr['style']
    assert data['feature_note']==pr['feature_note'] and data['reference_notes']==['参考空间构图']
    if ip_choice=='none':assert meta['ip_id']=='' and data['ip']=='普通原创初中生'
    elif ip_choice=='specified':assert meta['ip_id']==ip['asset_id']
    else:assert meta['ip_id']
    compile_plans(r,FixturePlanner().plan(r,lambda x:None))
    refs=r['slots'][0]['refs']
    assert any(x.get('role')=='角色 IP' for x in refs)==(ip_choice!='none')
    assert any('Logo' in x.get('role','') for x in refs)==(not no_logo)
    assert any(x['path']==pr['references'][0]['path'] for x in refs)
    assert r['configs'][0]['config']['ip_asset_id']==meta['ip_id']
    assert pr['feature_note'] in r['slots'][0]['prompt']


def test_all_available_ip_variants_can_be_selected_without_losing_identity(tmp_path):
    from local_app.planning import ASSETS,bootstrap,make_round,compile_plans
    from local_app.scene_planner import plan_input
    from tests_local.fakes import FixturePlanner
    catalog={a['id']:a for a in bootstrap()['assets']['ips']}
    source=[a for a in ASSETS if a['kind']=='ip' and a.get('enabled',True)]
    assert set(catalog)=={a['asset_id'] for a in source}
    for ip in source:
        pr=params('单图');pr['ip']=ip['asset_id']
        validate(pr,tmp_path)
        r=make_round(pr,'variant-'+ip['asset_id'],tmp_path/ip['asset_id'],2,True,defer_planning=True)
        label=ip.get('asset_name_zh') or ip['display_name']
        assert plan_input(r)['jobs'][0]['ip']==label
        assert catalog[ip['asset_id']]['stage']==ip['stage']
        compile_plans(r,FixturePlanner().plan(r,lambda x:None))
        refs=[ref for ref in r['slots'][0]['refs'] if ref.get('role')=='角色 IP']
        assert len(refs)==1 and refs[0]['asset_id']==ip['asset_id']
        assert refs[0]['path']==ip['path']
        assert r['configs'][0]['config']['ip_asset_id']==ip['asset_id']


@pytest.mark.parametrize('channel',sorted({p['category'] for p in PLACEMENTS}))
def test_channel_accepts_only_its_placements(channel,tmp_path):
    pr=params('单图');pr.update(channel=channel,pids=[p['id'] for p in PLACEMENTS if p['category']==channel and p['image_form']=='单图'])
    validate(pr,tmp_path)
    pr['pids'].append(next(p['id'] for p in PLACEMENTS if p['category']!=channel and p['image_form']=='单图'))
    with pytest.raises(UserError,match='^所选版位不属于当前渠道，请重新选择$'):validate(pr,tmp_path)


def test_channel_uses_catalog_categories_and_remains_optional(tmp_path,monkeypatch):
    from local_app.planning import BY_ID
    pr=params('单图');pr['pids']=[p['id'] for p in PLACEMENTS if p['image_form']=='单图']
    validate(pr,tmp_path)
    pr['channel']='未配置渠道'
    with pytest.raises(UserError,match='所选版位不属于当前渠道'):validate(pr,tmp_path)
    placement=BY_ID[pr['pids'][0]];monkeypatch.setitem(placement,'category','学习机')
    pr.update(channel='学习机',pids=[placement['id']])
    validate(pr,tmp_path)


@pytest.mark.parametrize('enabled',[None,0,1,'false'])
def test_cta_enabled_must_be_boolean(enabled,tmp_path):
    with pytest.raises(UserError,match='统一按钮'):validate({**params('单图'),'cta_enabled':enabled},tmp_path)


@pytest.mark.parametrize('override',[
    None,[],{'unselected':{'mode':'none'}},
    {'selected':None},{'selected':{}},{'selected':{'mode':'invalid'}},
    {'selected':{'mode':'custom'}},{'selected':{'mode':'custom','text':''}},
    {'selected':{'mode':'custom','text':'  '}},{'selected':{'mode':'custom','text':123}},
    {'selected':{'mode':'custom','text':'字'*13}},
])
def test_invalid_cta_overrides_are_rejected(override,tmp_path):
    pr=params('单图')
    if isinstance(override,dict):override={pr['pids'][0] if key=='selected' else key:value for key,value in override.items()}
    pr['cta_overrides']=override
    with pytest.raises(UserError,match='按钮'):validate(pr,tmp_path)


@pytest.mark.parametrize('form',['单图','双图','三图'])
@pytest.mark.parametrize('enabled,unified',[(True,'统一按钮'),(False,'统一按钮'),(True,'')])
@pytest.mark.parametrize('mode',['inherit','custom','none','default'])
def test_effective_cta_is_resolved_per_placement_and_uses_existing_prompt_path(tmp_path,form,enabled,unified,mode):
    from local_app.planning import make_round,compile_plans
    from tests_local.fakes import FixturePlanner
    pr=params(form);pr['pids']=[p['id'] for p in PLACEMENTS if p['image_form']==form][:2]
    first,second=pr['pids']
    overrides={second:{'mode':'custom','text':'字'*12}}
    if mode!='default':overrides[first]={'mode':mode,'text':'单独按钮'}
    pr.update(cta=unified,cta_enabled=enabled,cta_overrides=overrides)
    validate(pr,tmp_path)
    r=make_round(pr,'per-placement-cta',tmp_path,1,True,defer_planning=True)
    compile_plans(r,FixturePlanner().plan(r,lambda result:None))
    expected={first:'单独按钮' if mode=='custom' else (unified if enabled and mode!='none' else ''),second:'字'*12}
    assert {entry['pid']:entry['config']['cta'] for entry in r['configs']}==expected
    for slot in r['slots']:
        text=expected[slot['pid']]
        assert ('CTA按钮' in slot['prompt'])==bool(text)
        if text:assert '按钮文字逐字为“'+text+'”' in slot['prompt']


def test_legacy_cta_defaults_and_new_fields_are_fingerprinted(tmp_path):
    from local_app.planning import copy_signature,make_round
    pr=params('单图');signature=copy_signature(pr)
    assert copy_signature({**pr,'cta_enabled':True,'cta_overrides':{}})==signature
    assert copy_signature({**pr,'cta_enabled':False})!=signature
    assert copy_signature({**pr,'cta_overrides':{pr['pids'][0]:{'mode':'custom','text':'试试学习'}}})!=signature
    r=make_round(pr,'legacy-cta',tmp_path,1,True,defer_planning=True)
    assert r['configs'][0]['config']['cta']==pr['cta']


@pytest.mark.parametrize('note',[None,'','参考图A','字'*200])
def test_reference_notes_are_optional_and_reach_compilation(note,tmp_path):
    from local_app.planning import make_round,compile_plans
    from local_app.scene_planner import plan_input
    from tests_local.fakes import FixturePlanner
    pr=params('单图');ref=dict(id='ref',purpose='style',path=str(tmp_path/'ref.png'))
    if note is not None:ref['note']=note
    pr['references']=[ref]
    validate(pr,tmp_path)
    r=make_round(pr,'optional-note',tmp_path,1,True,defer_planning=True)
    assert plan_input(r)['jobs'][0]['reference_notes']==[note or '']
    compile_plans(r,FixturePlanner().plan(r,lambda result:None))


@pytest.mark.parametrize('purpose',['style','composition','ui'])
def test_reference_purposes_have_one_slot_each(purpose,tmp_path):
    pr=params('单图');pr['references']=[{'id':name,'purpose':name,'note':''} for name in ('style','composition','ui')]
    validate(pr,tmp_path)
    pr['references']=[{'id':'first','purpose':purpose},{'id':'second','purpose':purpose}]
    with pytest.raises(UserError,match='每种用途最多上传 1 张'):validate(pr,tmp_path)


@pytest.mark.parametrize('reference',[
    {'purpose':'style','note':'字'*201},{'purpose':'style','note':None},
    {'purpose':'legacy'},{},{'purpose':'unknown'},
])
def test_new_references_reject_invalid_notes_and_legacy_purposes(reference,tmp_path):
    pr=params('单图');pr['references']=[{'id':'ref',**reference}]
    with pytest.raises(UserError,match='参考图'):validate(pr,tmp_path)
