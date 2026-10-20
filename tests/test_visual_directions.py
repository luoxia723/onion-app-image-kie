"""Diversity planning must change composition, preserve IP, and enter prompts."""
from pathlib import Path
import copy
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from visual_directions import SKILL_DIR, plan_directions, validate_visual_plan


def config(sets=8):
    return {'request_id': 'visual-test', 'sets': sets, 'visual_diversity_enabled': True,
            'logo': '洋葱学园', 'ip': '雷婷', 'ip_asset_id': 'ip.leiting.junior.standard.001',
            'font_reference_enabled': True,
            'copy_refs': [{'copyDraftId': 'math', 'short1': '这周我想把数学补起来',
                           'short2': '洋葱AI按目标和基础排每日任务', 'short3': '打开看今天学啥学完看进度'}],
            'placements': [{'id': 'oppo', 'image_count': 3, 'target_width': 320, 'target_height': 210}]}


def test_batch_varies_rendering_and_composition_without_replacing_selected_ip():
    cfg = config()
    plan = plan_directions(cfg, seed='stable')
    directions = plan['directions']
    assert plan == plan_directions(cfg, seed='stable')
    assert len(directions) == 8
    assert len({d['style_id'] for d in directions}) == 8
    assert len({d['layout_id'] for d in directions}) >= 6
    assert len({d['ip_asset_id'] for d in directions}) == 1
    assert directions[0]['ip_asset_id'] == cfg['ip_asset_id']
    for left, right in zip(directions, directions[1:]):
        assert left['style_id'] != right['style_id']
        assert left['layout_id'] != right['layout_id']
    for direction in directions:
        assert Path(direction['font_reference_path']).is_file()
        assert direction['small_canvas']


def test_fixed_direction_is_an_explicit_exception():
    cfg = config(3)
    cfg['visual_direction'] = {'style_id': 'soft_3d', 'layout_id': 'title_top_scene_bottom'}
    plan = plan_directions(cfg)
    assert all(d['style_id'] == 'soft_3d' and d['layout_id'] == 'title_top_scene_bottom' for d in plan['directions'])
    assert plan['mode'] == 'fixed'


def test_no_ip_never_inserts_a_brand_mascot():
    cfg = config(2)
    cfg.update(ip='不用', ip_asset_id='', ip_random=False)
    plan = plan_directions(cfg)
    assert all(not d['ip_asset_id'] for d in plan['directions'])
    assert all(d['subject_mode'] == 'approved_action_without_ip' for d in plan['directions'])


def test_plan_must_be_bound_to_every_base_and_branch(tmp_path):
    cfg = config(2)
    plan = plan_directions(cfg)
    path = tmp_path / 'visual-plan.json'
    path.write_text(json.dumps(plan))
    jobs = []
    for direction in plan['directions']:
        for slot in (1, 2, 3):
            rule = direction['base_prompt_rule'] if slot == 1 else direction['branch_prompt_rule']
            jobs.append({'job_id': f'{direction["set_id"]}-{slot}', 'set_id': direction['set_id'],
                         'slot': slot, 'visual_direction_id': direction['direction_id'], 'prompt': rule,
                         'references': ([{'asset_id': direction['ip_asset_id'], 'path': str(SKILL_DIR / direction['ip_reference_path'])},
                                         {'path': direction['font_reference_path']}] if slot == 1 else [])})
    manifest = {'request_id': cfg['request_id'], 'visual_plan_path': str(path), 'jobs': jobs}
    validate_visual_plan(manifest, cfg)
    for corruption in ('unused_rule', 'switched_branch', 'stale_config', 'missing_plan', 'wrong_ip', 'wrong_font'):
        bad = copy.deepcopy(manifest)
        saved = copy.deepcopy(cfg)
        if corruption == 'unused_rule': bad['jobs'][0]['prompt'] = '普通动漫，蓝色背景'
        if corruption == 'switched_branch': bad['jobs'][1]['visual_direction_id'] = plan['directions'][1]['direction_id']
        if corruption == 'stale_config': saved['placements'][0]['target_height'] = 211
        if corruption == 'missing_plan': bad.pop('visual_plan_path')
        if corruption == 'wrong_ip': bad['jobs'][0]['references'][0]['asset_id'] = 'ip.someone.else'
        if corruption == 'wrong_font': bad['jobs'][0]['references'].pop()
        with pytest.raises(ValueError):
            validate_visual_plan(bad, saved)


def test_historical_config_can_resume_without_new_planning_fields():
    validate_visual_plan({'jobs': []}, {'placements': [{}]})


def test_combinations_do_not_repeat_until_style_layout_pool_is_used():
    directions = plan_directions(config(48))['directions']
    assert len({(d['style_id'], d['layout_id']) for d in directions}) == 48


def test_paid_batch_rejects_missing_visual_plan_before_render(tmp_path, monkeypatch):
    import argparse
    import direct_batch
    from logo_reference import build_logo_reference, logo_prompt_rule
    cfg = config(1)
    monkeypatch.setenv('ONION_IMAGE_WORKSPACE', str(tmp_path))
    config_path, manifest_path = tmp_path / 'config.json', tmp_path / 'manifest.json'
    config_path.write_text(json.dumps(cfg))
    manifest_path.write_text(json.dumps({'request_id': cfg['request_id'], 'jobs': [{
        'job_id': 'base', 'set_id': 'set1', 'prompt': logo_prompt_rule(),
        'references': [build_logo_reference(cfg)], 'output': str(tmp_path / '工作区/产物/base.png')
    }]}))
    monkeypatch.setattr(direct_batch, 'invoke', lambda *a, **k: pytest.fail('render reached'))
    with pytest.raises(ValueError, match='visual_plan_path'):
        direct_batch.execute(argparse.Namespace(manifest=manifest_path, config=config_path,
            validate_only=False, approved_in_current_task=True, approved_count=None))


def task_styles():
    descriptions = [
        ('pastel_story', '粉彩叙事', '用柔和粉彩色层、可辨识的人物轮廓与少量纸面颗粒表现动作。'),
        ('colored_pencil', '彩铅插画', '以有方向的彩铅笔触塑造人物与道具，关键面部特征清楚。'),
        ('gouache_blocks', '水粉色块', '用概括水粉色块与受控边缘构建人物和空间。'),
        ('matte_clay', '哑光黏土', '人物与场景采用统一的哑光黏土体积与柔和投影。'),
        ('felt_scene', '毛毡场景', '以柔和毛毡材质构建角色和道具，保留角色识别轮廓。'),
        ('ceramic_scene', '陶瓷质感', '用克制陶瓷釉面与清楚立体造型表现同一角色。'),
        ('line_and_wash', '线描淡彩', '清楚细线勾勒人物身份，少量淡彩承托动作和道具。'),
        ('risograph', '孔版印刷', '概括轮廓和轻微孔版印刷质感，普通场景有限色块。'),
        ('woodcut_scene', '版画插画', '以受控木刻式线面组织人物与道具，不改变面部识别。'),
        ('low_poly', '低多边形', '使用统一低多边形场景语言，面部和服装识别保持清楚。'),
        ('ink_comic', '墨线叙事', '用节制墨线与大面积留白表现一个完整的学习动作。'),
        ('pastel_volume', '柔粉体积', '用柔粉材质和克制立体光影统一人物与空间。'),
    ]
    return [{'id': i, 'name': name, 'prompt': text, 'supports_ip': True,
             'components': {'medium': name, 'lighting': '明亮柔光'}} for i, name, text in descriptions]


def test_task_authored_directions_are_not_limited_to_builtin_eight():
    cfg = config(12)
    cfg['visual_diversity_mode'] = 'open'
    cfg['visual_candidates'] = {'styles': task_styles()}
    plan = plan_directions(cfg, seed='open')
    assert len({d['style_id'] for d in plan['directions']}) == 12
    assert {d['style_id'] for d in plan['directions']} == {s['id'] for s in task_styles()}
    assert all(d['style_origin'] == 'task_authored' for d in plan['directions'])
    assert all(d['ip_asset_id'] == cfg['ip_asset_id'] for d in plan['directions'])
    for d in plan['directions']:
        assert '明亮柔光' in d['base_prompt_rule']


def test_task_can_define_layouts_outside_the_builtin_pool():
    cfg = config(2)
    cfg['visual_candidates'] = {'styles': task_styles()[:2], 'layouts': [
        {'id': 'foreground_action', 'name': '前景动作留白', 'prompt': '主要动作放在前景，文字占独立清楚留白。'},
        {'id': 'arc_balance', 'name': '弧线平衡', 'prompt': '用道具和人物视线形成自然弧线，文字在弧线外完整呈现。'}]}
    plan = plan_directions(cfg)
    assert {d['layout_id'] for d in plan['directions']} == {'foreground_action', 'arc_balance'}
    assert all(d['layout_origin'] == 'task_authored' for d in plan['directions'])
    assert all(d['framing_id'] == 'layout_defined' for d in plan['directions'])


@pytest.mark.parametrize('problem', ['duplicate_id', 'same_description', 'unsupported_ip', 'unknown_framing'])
def test_invalid_open_candidates_are_rejected(problem):
    cfg = config(2)
    candidates = {'styles': task_styles()[:2]}
    if problem == 'duplicate_id': candidates['styles'][1]['id'] = candidates['styles'][0]['id']
    if problem == 'same_description': candidates['styles'][1]['prompt'] = candidates['styles'][0]['prompt']
    if problem == 'unsupported_ip':
        for style in candidates['styles']: style['supports_ip'] = False
    if problem == 'unknown_framing':
        candidates['layouts'] = [{'id': 'new_layout', 'name': '新布局', 'prompt': '大字清楚，完整动作。', 'framing_ids': ['missing_framing']}]
    cfg['visual_candidates'] = candidates
    with pytest.raises(ValueError):
        plan_directions(cfg)


def test_open_mode_requires_authored_styles_but_respects_user_fixed_style():
    cfg = config(2)
    cfg['visual_diversity_mode'] = 'open'
    with pytest.raises(ValueError, match='task-authored'):
        plan_directions(cfg)
    cfg['visual_direction'] = {'style_prompt': '按用户要求使用彩铅表现，保留角色身份与关键服装特征。'}
    plan = plan_directions(cfg)
    assert all(d['style_origin'] == 'user_fixed' for d in plan['directions'])


def test_open_candidates_are_part_of_the_frozen_plan_identity(tmp_path):
    cfg = config(1)
    cfg['visual_candidates'] = {'styles': task_styles()[:1]}
    plan = plan_directions(cfg)
    path = tmp_path / 'visual-plan.json'
    path.write_text(json.dumps(plan))
    changed = copy.deepcopy(cfg)
    changed['visual_candidates']['styles'][0]['prompt'] = '改成另一种实际画法。'
    with pytest.raises(ValueError, match='stale'):
        validate_visual_plan({'visual_plan_path': str(path), 'jobs': []}, changed)
