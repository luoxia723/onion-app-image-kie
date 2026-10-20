"""New prompts are positive paragraphs; contracts stay in validated metadata."""
import copy
import json
from pathlib import Path
import re
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import blue_frame
import interactive_server
import logo_reference
import positive_prompt as positive
from series_chain import validate_series
import visual_directions as visual


def configuration(count=1):
    source = {'copyDraftId': 'math', 'mainTitle': '这周我想把数学补起来',
              'subtitle': '洋葱AI按目标和基础排每日任务',
              'short1': '这周我想把数学补起来', 'short2': '洋葱AI按目标和基础排每日任务',
              'short3': '打开看今天学啥学完看进度'}
    return {'request_id': 'positive', 'prompt_format': positive.FORMAT,
            'placements': [{'image_count': count, 'target_width': 1280, 'target_height': 720}],
            'copy_refs': [source], 'sets': 1, 'logo': '洋葱学园', 'ip_asset_id': '',
            'font_reference_enabled': False, 'art_direction_required': True,
            'visual_style_mode': 'coordinated', 'visual_direction': {'style_id': 'watercolor_illustration'},
            'screen_ui_mode': 'conceptual',
            'visual_concepts': [{'name': '书院纸阶', 'prompt': '古代书院里，书页化为阶梯，引向窗边的学习任务。',
                'slot_actions': ['纸页展开成为拾级而上的起点。', '任务卡沿纸阶逐一排开。', '完成标记点亮今天的台阶。'][:count],
                'art_direction': {'world': '古代幻想书院', 'scene': '窗边纸页阶梯', 'story': '目标成为每日任务',
                                  'composition': '纸阶引向标题', 'lighting_materials': '暖窗光与纸纤维'},
                'screen_text': []}]}


def jobs_for(cfg):
    d = visual.plan_directions(cfg)['directions'][0]
    jobs = []
    for slot in range(1, cfg['placements'][0]['image_count'] + 1):
        refs = [logo_reference.build_logo_reference(cfg)] if slot == 1 else [{'label': '参考图1', 'path': '/tmp/base.png'}]
        jobs.append({'job_id': f'job{slot}', 'set_id': d['set_id'], 'slot': slot,
                     'visual_direction_id': d['direction_id'], 'ui_text': d['screen_text'],
                     'copy_text': '\n'.join(t for t in positive.approved_copy(cfg['copy_refs'][0], slot, len(d['slot_prompt_rules'])) if t),
                     'prompt': positive.compose(cfg, d, slot, refs), 'references': refs,
                     'output': '/tmp/base.png' if slot == 1 else f'/tmp/branch{slot}.png',
                     'depends_on': [] if slot == 1 else ['job1'],
                     **({} if slot == 1 else {'base_job_id': 'job1'})})
    return d, jobs


def test_new_saved_config_selects_positive_format():
    cfg = interactive_server.normalize_config_result({'delivery_name': '格式', 'placement_ids': ['oppo-rich-horizontal-big-1280x720']}, interactive_server.slots_by_id())
    assert cfg['prompt_format'] == positive.FORMAT


@pytest.mark.parametrize('count', [1, 2, 3])
def test_composed_prompts_validate_copy_and_topology_without_allowlist(tmp_path, count):
    cfg = configuration(count); d, jobs = jobs_for(cfg)
    plan = visual.plan_directions(cfg); path = tmp_path / 'plan.json'; path.write_text(json.dumps(plan))
    manifest = {'jobs': jobs, 'visual_plan_path': str(path)}
    validate_series(manifest, cfg); visual.validate_visual_plan(manifest, cfg)
    logo_reference.validate_manifest_logo(manifest, cfg)
    assert len({j['prompt'] for j in jobs}) == count
    for job in jobs:
        assert '\n' not in job['prompt']
        assert not any(word in job['prompt'] for word in ['白名单', '不得', '禁止', '不能', '不需要', '不展示', '无品牌IP', 'visual-001', '1K', '1280', 'SHA', '积分'])
        assert len(job['prompt']) < 900


@pytest.mark.parametrize('corruption', ['metadata', 'missing_title', 'missing_subtitle', 'paragraph', 'allowlist'])
def test_invalid_new_single_copy_or_format_fails_preflight(corruption):
    cfg = configuration(); _, jobs = jobs_for(cfg)
    if corruption == 'metadata': jobs[0]['copy_text'] = '错误文字'
    if corruption == 'missing_title': jobs[0]['prompt'] = jobs[0]['prompt'].replace(cfg['copy_refs'][0]['mainTitle'], '')
    if corruption == 'missing_subtitle': jobs[0]['prompt'] = jobs[0]['prompt'].replace(cfg['copy_refs'][0]['subtitle'], '')
    if corruption == 'paragraph': jobs[0]['prompt'] += '\n第二段'
    if corruption == 'allowlist': jobs[0]['prompt'] += '画面文字白名单：[]'
    with pytest.raises(ValueError): validate_series({'jobs': jobs}, cfg)


def test_positive_catalog_covers_every_style_and_is_subject_neutral():
    styles = visual.load_catalog()['styles']
    assert len(styles) == 77
    for s in styles:
        assert s['visual_prompt'].strip()
        assert not re.search(r'不要|不得|禁止|避免|不能|无需|不必|不让|不改|不套|不只|而非|IP|脸型|发型|服装', s['visual_prompt'])


def test_screen_selection_stays_metadata_without_generic_screen_bans(tmp_path):
    cfg = configuration(); cfg['screen_ui_mode'] = 'none'
    d, jobs = jobs_for(cfg)
    assert '屏幕' not in jobs[0]['prompt'] and 'UI' not in jobs[0]['prompt']
    cfg['screen_ui_mode'] = 'conceptual'; cfg['visual_concepts'][0]['screen_text'] = ['今日任务', '学习进度']
    d, jobs = jobs_for(cfg)
    assert '屏幕以清晰示意界面呈现“今日任务”、“学习进度”' in jobs[0]['prompt']
    path = tmp_path / 'plan.json'; path.write_text(json.dumps(visual.plan_directions(cfg)))
    jobs[0]['ui_text'] = ['其他功能']
    with pytest.raises(ValueError, match='ui_text'):
        visual.validate_visual_plan({'jobs': jobs, 'visual_plan_path': str(path)}, cfg)


def test_ip_inherits_identity_and_concept_period_details():
    cfg = configuration(); cfg['ip_asset_id'] = 'ip.goudan.junior.standard.001'
    cfg['visual_concepts'][0]['prompt'] += '狗蛋穿原蓝黄服装，配小披肩和黄铜扣，扶起第一张任务卡。'
    d = visual.plan_directions(cfg)['directions'][0]
    assert '小披肩和黄铜扣' in d['base_prompt_rule'] and 'IP保留脸型' in d['base_prompt_rule']
    assert '\n' not in d['base_prompt_rule'] and '不得' not in d['base_prompt_rule']


def test_original_ad_copy_is_not_filtered_as_negative_instruction():
    cfg = configuration(); cfg['copy_refs'][0]['mainTitle'] = '数学不再怕'
    _, jobs = jobs_for(cfg)
    assert '数学不再怕' in jobs[0]['prompt']
    validate_series({'jobs': jobs}, cfg)


def test_both_new_and_frozen_asset_rules_are_accepted():
    for position in ['左上角', '上方居中']:
        old = logo_reference.LEGACY_LOGO_PROMPT_TEMPLATE.replace('左上角', position).format(label='参考图1')
        assert logo_reference.has_logo_rule(old, '参考图1', position)
        assert logo_reference.has_logo_rule(logo_reference.logo_prompt_rule(position=position), '参考图1', position)
    for rule in [blue_frame.prompt_rule, blue_frame.legacy_prompt_rule]:
        assert blue_frame.has_prompt_rule(rule('参考图3'), '参考图3')
        assert not blue_frame.has_prompt_rule(rule('参考图3'), '参考图1')


def test_format_is_fingerprinted_without_changing_historical_config():
    cfg = configuration(); old = copy.deepcopy(cfg); old.pop('prompt_format')
    assert visual.config_fingerprint(cfg) != visual.config_fingerprint(old)
    assert not positive.enabled(old)
    with pytest.raises(ValueError): positive.enabled({'prompt_format': 'unknown'})
