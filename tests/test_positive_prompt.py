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
        refs = ([logo_reference.build_logo_reference(cfg)] +
                ([{'label': '参考图2', 'role': '标题字体参考', 'path': d['font_reference_path']}] if d['font_reference_path'] else [])) if slot == 1 else [{'label': '参考图1', 'path': '/tmp/base.png'}]
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
    assert cfg['learner_story_required']
    assert cfg['visual_contract_version'] == positive.VISUAL_CONTRACT_VERSION


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


@pytest.mark.parametrize('count', [2, 3])
def test_asset_roles_and_complete_ad_reference_are_explicit(count):
    cfg = configuration(count); cfg['font_reference_enabled'] = True
    d = visual.plan_directions(cfg)['directions'][0]
    refs = [logo_reference.build_logo_reference(cfg),
            {'label': '参考图2', 'role': '标题字体参考', 'path': d['font_reference_path']}]
    base = positive.compose(cfg, d, references=refs)
    assert '原样呈现参考图1的完整Logo' in base and '参考图2仅用于标题字形和排版参考' in base
    assert '完整广告成图' not in base
    for slot in range(2, count + 1):
        branch = positive.compose(cfg, d, slot, [{'label': '参考图1', 'path': '/tmp/base.png'}])
        assert '本套采用透明水彩画风' in branch
        assert '参考图1为本套已生成的第1张完整广告成图' in branch
        assert '标题字形参考' not in branch


def test_random_style_is_bound_before_writing_even_a_single_image_prompt():
    cfg = configuration(); cfg.update(visual_style_mode='random', visual_direction={})
    assignment = visual.assign_styles(cfg)['directions'][0]
    cfg['visual_concepts'][0]['style_id'] = assignment['style_id']
    d = visual.plan_directions(cfg)['directions'][0]
    assert d['style_id'] == assignment['style_id']
    assert assignment['style_prompt'] in d['base_prompt_rule']
    other = next(s['id'] for s in visual.load_catalog()['styles'] if s['id'] != assignment['style_id'])
    cfg['visual_concepts'][0]['style_id'] = other
    with pytest.raises(ValueError, match='assign-styles'): visual.plan_directions(cfg)


def test_new_learner_story_keeps_a_student_in_no_ip_prompts_and_records_the_pain():
    cfg = configuration(); cfg['learner_story_required'] = True
    story = {'protagonist': '一位扎马尾、穿米白上衣的原创初中女生',
             'pain_point': '想补数学，却不知道该先补哪个章节',
             'product_action': '洋葱AI按目标和基础安排每日任务',
             'visible_change': '学生看清今天先学什么，开始动笔'}
    cfg['visual_concepts'][0]['learner_story'] = story
    d = visual.plan_directions(cfg)['directions'][0]
    assert d['subject_mode'] == 'original_student' and not d['ip_asset_id']
    assert story['protagonist'] in d['base_prompt_rule']
    assert d['learner_story'] == story
    assert story['pain_point'] in d['base_prompt_rule']
    del cfg['visual_concepts'][0]['learner_story']['pain_point']
    with pytest.raises(ValueError, match='learner_story'): visual.plan_directions(cfg)


def test_missing_new_story_fails_without_changing_frozen_legacy_configs():
    cfg = configuration(); cfg['learner_story_required'] = True
    with pytest.raises(ValueError, match='learner_story'): visual.plan_directions(cfg)
    cfg.pop('learner_story_required')
    assert visual.plan_directions(cfg)['directions'][0]['subject_mode'] == 'approved_action_without_ip'


def test_logo_prompt_keeps_the_complete_mark_wordmark_and_original_geometry():
    rule = logo_reference.logo_prompt_rule()
    for key in ['参考图1', '品牌图形', '洋葱学园', '全部标准字', '同一完整组合', '原版颜色', '图文比例', '轮廓', '眼睛', '角标', '整体等比缩放']:
        assert key in rule
    assert not re.search(r'不得|不要|禁止|不能', rule)
    previous = logo_reference.PREVIOUS_POSITIVE_LOGO_TEMPLATE.format(label='参考图1')
    assert logo_reference.has_logo_rule(previous, '参考图1', '左上角')


@pytest.mark.parametrize('count', [1, 2, 3])
def test_restored_rules_reach_every_model_prompt_as_positive_single_paragraphs(tmp_path, count):
    import render
    cfg = configuration(count)
    cfg.update(visual_contract_version=positive.VISUAL_CONTRACT_VERSION, font_reference_enabled=True)
    d, jobs = jobs_for(cfg)
    for job in jobs:
        prompt = job['prompt']
        request = render.build_create_request('https://example.invalid', 'test-key', prompt, '16:9', '1K', ['https://example.invalid/ref.png'])
        sent = json.loads(request.data)['input']['prompt']
        assert '横版' in sent and '独立广告图' in sent and '一个连续完整的场景' in sent
        assert '广告正文仅使用本张确认文案' in sent and '具体数字' in sent
        assert '背景明度、自然留白和布局调整解决' in sent
        assert '\n' not in sent and not re.search(r'不得|不要|禁止|不能|白名单', sent)
        if job['slot'] == 1:
            assert '示例字句在本图由确认文案完整替换' in sent
            assert '字面宽窄与排版密度' in sent and '插画画风用于人物与场景' in sent
            assert '独立可见边界仅由原版标识自身构成' in sent
            assert '描边与附属元素逐项沿用原图' in sent
        else:
            assert '首张文案所在区域在本图完整替换' in sent
            assert '文案区仅保留本张确认内容' in sent
            assert '首张已确定的字体体系' in sent
    validate_series({'jobs': jobs}, cfg)
    logo_reference.validate_manifest_logo({'jobs': jobs}, cfg)


@pytest.mark.parametrize('missing', ['task', 'font', 'contrast', 'content', 'logo_background', 'branch_copy', 'branch_font'])
def test_missing_restored_rule_is_rejected_before_submission(missing):
    cfg = configuration(2)
    cfg.update(visual_contract_version=positive.VISUAL_CONTRACT_VERSION, font_reference_enabled=True)
    d, jobs = jobs_for(cfg)
    job = jobs[1] if missing.startswith('branch') else jobs[0]
    rules = {'task': positive.task_rule(cfg), 'font': positive.font_rule('参考图2'),
             'contrast': positive.readability_rule(), 'content': positive.CONTENT_RULE,
             'logo_background': logo_reference.logo_prompt_rule(),
             'branch_copy': positive.branch_title_rule(job['copy_text']),
             'branch_font': positive.inherited_font_rule()}
    job['prompt'] = job['prompt'].replace(rules[missing], '')
    with pytest.raises(ValueError):
        logo_reference.validate_manifest_logo({'jobs': jobs}, cfg)
        validate_series({'jobs': jobs}, cfg)


def test_contract_version_is_optional_for_frozen_prompts_and_part_of_new_fingerprints():
    cfg = configuration()
    before = visual.config_fingerprint(cfg)
    positive.validate_visual_contract(cfg, '旧任务原提示词', [])
    cfg['visual_contract_version'] = positive.VISUAL_CONTRACT_VERSION
    assert visual.config_fingerprint(cfg) != before
    with pytest.raises(ValueError): positive.validate_visual_contract(cfg, '旧任务原提示词', [])
    cfg['visual_contract_version'] = 'unknown'
    with pytest.raises(ValueError, match='unsupported'): positive.validate_visual_contract(cfg, '旧任务原提示词', [])


def test_source_logo_background_rule_remains_resumable_for_the_previous_version():
    cfg = configuration(); cfg['learner_story_required'] = True
    previous = logo_reference.PREVIOUS_COMPLETE_LOGO_TEMPLATE.format(label='参考图1')
    job = {'slot': 1, 'prompt': previous, 'references': [logo_reference.build_logo_reference(cfg)]}
    logo_reference.validate_manifest_logo({'jobs': [job]}, cfg)
    cfg['visual_contract_version'] = positive.VISUAL_CONTRACT_VERSION
    with pytest.raises(ValueError, match='Logo'): logo_reference.validate_manifest_logo({'jobs': [job]}, cfg)


@pytest.mark.parametrize('width,height,category,expected', [(474,768,'应用商店','竖版应用商店'), (320,320,'信息流','方版信息流'), (1280,720,'学习机','横版学习机')])
def test_prompt_task_keeps_channel_context_without_technical_dimensions(width,height,category,expected):
    cfg = configuration(); cfg['placements'][0].update(target_width=width,target_height=height,category=category)
    rule = positive.task_rule(cfg)
    assert expected in rule and not re.search(r'\d|KB|1K', rule)


def test_confirmed_product_help_reaches_each_prompt_and_is_not_only_plan_metadata(tmp_path):
    cfg = configuration(3);cfg['visual_contract_version']=positive.VISUAL_CONTRACT_VERSION
    cfg['visual_concepts'][0]['learner_story']={
        'protagonist':'一位原创初中女生','pain_point':'她拿不准先补哪部分数学。',
        'product_action':'根据学习目标与现有基础形成每日学习安排',
        'visible_change':'对照当天任务开始练习'}
    plan=visual.plan_directions(cfg);d,jobs=jobs_for(cfg)
    path=tmp_path/'plan.json';path.write_text(json.dumps(plan))
    manifest={'visual_plan_path':str(path),'jobs':jobs}
    visual.validate_visual_plan(manifest,cfg)
    fact=cfg['visual_concepts'][0]['learner_story']['product_action']
    assert all(fact in job['prompt'] for job in jobs)
    jobs[1]['prompt']=jobs[1]['prompt'].replace(fact,'')
    with pytest.raises(ValueError,match='product action'):visual.validate_visual_plan(manifest,cfg)
