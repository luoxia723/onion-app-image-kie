import copy
import socket
import pytest

from local_app.config import UserError
from local_app import learning_pipeline as pipeline


def params(**changes):
    return {**dict(channel='学习机',t1='拍下不会的题',ip='random',style='random',font='none'),**changes}


def test_all_44_placements_have_fixed_content_rules_and_45_deliverables():
    records=pipeline.placement_contracts()
    assert len(records)==44
    assert sum(p['image_count'] for p in records)==45
    assert sum(p['logo_required'] for p in records)==36
    assert sum(p['cta_required'] for p in records)==14
    assert all(p['category']=='学习机' and p['enabled'] for p in records)
    assert all(p['target_width']>0 and p['target_height']>0 and p['output_format']=='PNG' for p in records)
    wide=next(p for p in records if p['id']=='learning-zuoyebang-1224x408')
    assert wide['cta_policy']=='forbidden'
    assert next(p for p in records if p['id']=='learning-dsl-resource-484x580')['logo_required']


def test_baseline_is_internal_and_not_a_selected_advertising_placement():
    plan=pipeline.preview(params(),seed='task-a')
    baseline=plan['baseline']
    assert baseline['id']==pipeline.BASELINE_ID and baseline['type']=='visual_baseline'
    assert baseline['is_delivery'] is False and baseline['aspect_ratio']=='16:9'
    assert not baseline['advertising_copy'] and not baseline['logo'] and not baseline['cta']
    assert len(plan['outputs'])==45 and plan['output_count']==45 and plan['total_image_count']==46
    assert all(o['depends_on']==[baseline['id'],pipeline.BASELINE_CONFIRMATION_ID] for o in plan['outputs'])
    assert baseline['id'] not in {o['placement_id'] for o in plan['outputs']}
    double=[o for o in plan['outputs'] if o['placement_id']=='learning-youxuepai-double-840x404']
    assert [o['image_index'] for o in double]==[1,2]


def test_normalize_selects_one_suite_and_disallows_upload_path():
    n=pipeline.normalize(params(sets=9,variants_by_placement={'learning-baidu-512x512':8}),seed='one-suite')
    assert n['sets']==1 and set(n['variants_by_placement'].values())=={1}
    assert n['learning_mode']==n['learning_pipeline']=='baseline_then_suite'
    with pytest.raises(UserError,match='先生成基准图'):
        pipeline.normalize(params(learning_mode='upload',learning_source={'path':'irrelevant'}))
    with pytest.raises(UserError,match='请选择学习机'):
        pipeline.normalize(params(pids=[]))


def test_cta_presence_cannot_be_overridden_but_text_is_shared_and_customizable():
    ids=['learning-bbg-no-logo-banner-1280x362','learning-seewo-1400x520']
    plan=pipeline.preview(params(pids=ids,cta='立即点击下载',cta_enabled=False,
                                 cta_overrides={ids[0]:{'mode':'none'}},noLogo=True),seed='fixed')
    yes,no=plan['outputs']
    assert yes['cta_required'] and yes['cta_text']=='立即点击下载' and yes['logo_required'] is False
    assert not no['cta_required'] and no['cta_text']==''
    assert plan['normalized_params']['cta_overrides']=={} and plan['normalized_params']['cta_enabled'] is True
    default=pipeline.preview(params(pids=ids,cta='   '),seed='fixed')
    assert default['outputs'][0]['cta_text']=='点击下载'


def test_random_visual_is_frozen_once_and_reference_style_takes_priority():
    first=pipeline.normalize(params(ip='full_random'),seed='freeze-me')
    second=pipeline.normalize(first)
    assert first['learning_visual_config']==second['learning_visual_config']
    refs=[dict(id='test-owned-reference',purpose='style',note='暖色水彩')]
    p=pipeline.preview({**params(),'references':refs,'style':'not-in-pool'},seed='style-ref')
    assert p['visual_config']['style_source']=='reference' and p['visual_config']['style_id']=='reference'
    assert p['visual_config']['randomized_once'] is True


def test_configuration_preview_and_simulation_never_call_a_provider(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('No network permitted')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    result=pipeline.simulate(params(pids=['learning-baidu-512x512']),seed='offline')
    assert result['execution']['enabled'] is False
    assert result['execution']['prompt_generation_ready'] is False
    assert result['network_requests']==0 and result['artifacts_generated'] is False
    assert result['events'][0]['stage']=='baseline' and result['events'][0]['state']=='configuration_checked'
    assert result['events'][1]['stage']=='baseline_confirmation' and result['events'][1]['confirmed'] is False
    assert not any(e['stage']=='suite' for e in result['events'])
    assert result['blocked_at']=='baseline_confirmation'
    assert result['baseline']['artifact_ready'] is False
    assert result['baseline']['state']=='not_generated' and result['baseline']['has_image'] is False
    assert result['confirmation']['can_confirm'] is result['confirmation']['confirmed'] is False
    assert result['suite']['can_expand'] is False
    assert all(o['artifact_ready'] is False and o['started'] is False and o['can_expand'] is False for o in result['outputs'])


def test_normalization_is_non_mutating_and_choices_are_not_reused_after_setting_change():
    original=params();before=copy.deepcopy(original)
    normalized=pipeline.normalize(original,seed='original')
    assert original==before
    changed={**normalized,'ip':'none'}
    again=pipeline.normalize(changed)
    assert again['learning_visual_config']['ip_id']==''
    assert again['learning_visual_config']['selection_fingerprint']!=normalized['learning_visual_config']['selection_fingerprint']


def test_client_cannot_spoof_frozen_visual_configuration():
    valid=pipeline.normalize(params(),seed='server-resolve')
    forged=copy.deepcopy(valid)
    forged['learning_visual_config'].update(ip_id='ip.not-owned',style_id='made-up',font_id='/arbitrary/file')
    fixed=pipeline.normalize(forged)
    assert fixed['learning_visual_config']==valid['learning_visual_config']


def test_reference_preview_only_freezes_metadata_and_never_uses_a_network_provider(monkeypatch):
    from local_app.scene_planner import ApiScenePlanner
    def forbidden(*args,**kwargs):raise AssertionError('Configuration previews cannot call scene planning')
    monkeypatch.setattr(ApiScenePlanner,'_request',forbidden)
    p=pipeline.preview(params(references=[dict(id='owned-reference',purpose='style',note='参考配色')]),seed='reference')
    assert p['visual_config']['style_source']=='reference'
    assert p['execution']['enabled'] is False


def test_baseline_user_confirmation_is_a_required_nonautomatic_stage():
    plan=pipeline.preview(params(),seed='human-approval')
    assert plan['version']==2
    assert [s['id'] for s in plan['stages']]==['baseline','baseline_confirmation','main_visual_framing','suite','background_adaptation','export']
    confirm=plan['stages'][1]
    assert confirm['kind']=='user_action' and confirm['required'] is True and confirm['automatic'] is False
    framing,suite,background,export=plan['stages'][2:]
    assert framing['depends_on']==['baseline_confirmation'] and framing['kind']=='code'
    assert framing['additional_image_calls']==0
    assert suite['depends_on']==['main_visual_framing']
    assert suite['can_start'] is False and suite['automatic'] is False
    assert background['depends_on']==['suite'] and background['kind']=='conditional' and background['threshold_percent']==8
    assert export['depends_on']==['background_adaptation'] and export['inspection']=='user_visual_review'
    assert plan['baseline']['needs_user_confirmation'] is True
    assert plan['baseline']['approval']=={'required':True,'status':'waiting_for_image','confirmed':False,'can_confirm':False}
    assert plan['confirmation']['status']=='waiting_for_image'
    assert all(o['state']=='waiting_for_baseline_confirmation' and o['requires_baseline_confirmation'] is True for o in plan['outputs'])
    contract=pipeline.public_contract()
    assert contract['confirmation']['requires_real_baseline_image'] is True
    assert contract['suite']['automatic_after_baseline'] is False


def test_configuration_payload_cannot_create_a_baseline_or_user_confirmation():
    forged=params(baseline={'has_image':True,'artifact_ready':True,'id':'made-up'},
                  confirmation={'confirmed':True,'can_expand':True},suite={'can_expand':True},
                  confirmed=True,baseline_confirmed=True,baseline_approval={'status':'confirmed'},
                  learning_baseline_confirmation={'confirmed':True},has_image=True,artifact_ready=True,
                  auto_expand=True,can_confirm=True,can_expand=True,execution={'enabled':True},
                  learning_auto_expand=True,learning_requires_baseline_confirmation=False)
    plan=pipeline.preview(forged,seed='no-confirmation-in-config')
    clean=plan['normalized_params']
    for key in ['baseline','confirmation','suite','confirmed','baseline_confirmed','baseline_approval',
                'learning_baseline_confirmation','has_image','artifact_ready','auto_expand','can_confirm','can_expand','execution']:
        assert key not in clean
    assert clean['learning_auto_expand'] is False and clean['learning_requires_baseline_confirmation'] is True
    assert plan['baseline']['has_image'] is False and plan['confirmation']['confirmed'] is False
    assert plan['suite']['can_expand'] is False
    assert plan['execution']['enabled'] is False
