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
              references=[dict(id='user-ref',path=str(tmp_path/'reference.png'),note='参考空间构图',name='reference.png')])
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
