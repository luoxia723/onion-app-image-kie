"""New tasks freeze authored scenes instead of mixing unrelated visual pools."""
import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import visual_directions as visual


def content_config():
    return {
        'request_id': 'content-first-math', 'sets': 2, 'visual_diversity_enabled': True,
        'visual_style_mode': 'coordinated',  # Explicit shared-style design remains available.
        'logo': '洋葱学园', 'ip_asset_id': 'ip.leiting.junior.standard.001',
        'font_reference_enabled': True,
        'copy_refs': [{'copyDraftId': 'math', 'short1': '这周我想把数学补起来',
                       'short2': '洋葱AI按目标和基础排每日任务', 'short3': '打开看今天学啥学完看进度'}],
        'placements': [{'image_count': 3, 'target_width': 320, 'target_height': 210}],
        'visual_concepts': [
            {'name': '清蓝目标路线',
             'prompt': '用商业动漫表现开始数学学习的书桌场景。角色右侧前倾，视线引向练习本；蓝白环境与暖黄笔尖呼应，标题在左侧自然留白，前景纸张与后景形成层次。',
             'slot_actions': ['握笔看向练习本，认真准备开始。', '身体前倾，双手将纸卡排成有序路线。', '指向今日纸卡和完成勾选，神情轻松。']},
            {'name': '暖黄学习手账',
             'prompt': '同样采用商业动漫，暖黄阅读角里角色侧身整理手账，光线从书架后方落在纸面，标题沿视线方向布局，人物、纸张和铅笔构成连贯的暖色场景。',
             'slot_actions': ['抬笔停在手账上，思考本周数学目标。', '翻开折叠纸卡，沿桌面展开学习安排。', '轻松抬头，将完成的卡片归到手账一侧。']},
        ],
    }


def bound_manifest(cfg, plan, tmp_path):
    path = tmp_path / 'visual-plan.json'
    path.write_text(json.dumps(plan, ensure_ascii=False))
    jobs = []
    for direction in plan['directions']:
        for slot in range(1, int(cfg['placements'][0]['image_count']) + 1):
            rule = direction['base_prompt_rule'] if slot == 1 else direction['branch_prompt_rule']
            refs = ([{'asset_id': direction['ip_asset_id'], 'path': str(visual.SKILL_DIR / direction['ip_reference_path'])},
                     {'path': direction['font_reference_path']}] if slot == 1 else [])
            jobs.append({'set_id': direction['set_id'], 'slot': slot,
                         'visual_direction_id': direction['direction_id'],
                         'prompt': rule + '\n' + direction['slot_prompt_rules'][str(slot)], 'references': refs})
    return {'request_id': cfg['request_id'], 'visual_plan_path': str(path), 'jobs': jobs}


def test_complete_concepts_are_preserved_without_any_visual_pool_sampling(monkeypatch):
    def unwanted(*a, **k):
        pytest.fail('new task sampled a visual pool')
    for name in ('load_catalog', 'balanced', 'prioritized_styles', 'varied_layouts'):
        monkeypatch.setattr(visual, name, unwanted)
    cfg = content_config()
    plan = visual.plan_directions(cfg)
    assert plan['mode'] == 'content_first'
    assert plan == visual.plan_directions(cfg)
    for concept, direction in zip(cfg['visual_concepts'], plan['directions']):
        assert direction['concept_prompt'] == concept['prompt']
        assert concept['prompt'] in direction['base_prompt_rule']
        assert direction['ip_asset_id'] == cfg['ip_asset_id']
        assert Path(direction['font_reference_path']).is_file()
        for slot, action in enumerate(concept['slot_actions'], 1):
            assert action in direction['slot_prompt_rules'][str(slot)]


def test_each_branch_must_contain_its_own_planned_action(tmp_path):
    cfg = content_config(); plan = visual.plan_directions(cfg)
    manifest = bound_manifest(cfg, plan, tmp_path)
    visual.validate_visual_plan(manifest, cfg)
    for wrong_slot in (1, 3):
        broken = copy.deepcopy(manifest)
        direction = plan['directions'][0]
        broken['jobs'][1]['prompt'] = direction['branch_prompt_rule'] + direction['slot_prompt_rules'][str(wrong_slot)]
        with pytest.raises(ValueError, match='planned scene action'):
            visual.validate_visual_plan(broken, cfg)


def test_editing_scene_or_action_invalidates_the_frozen_plan(tmp_path):
    cfg = content_config(); plan = visual.plan_directions(cfg)
    manifest = bound_manifest(cfg, plan, tmp_path)
    for field in ('prompt', 'slot_actions'):
        changed = copy.deepcopy(cfg)
        if field == 'prompt': changed['visual_concepts'][0][field] += '改用另一个场景。'
        else: changed['visual_concepts'][0][field][1] = '另一个动作。'
        with pytest.raises(ValueError, match='stale'):
            visual.validate_visual_plan(manifest, changed)


@pytest.mark.parametrize('problem', ['missing_concepts', 'wrong_count', 'empty_scene', 'missing_action', 'replace_fixed_ip', 'replace_font'])
def test_incomplete_or_conflicting_concepts_are_rejected(problem):
    cfg = content_config()
    if problem == 'missing_concepts': cfg.pop('visual_concepts')
    if problem == 'wrong_count': cfg['visual_concepts'].pop()
    if problem == 'empty_scene': cfg['visual_concepts'][0]['prompt'] = ''
    if problem == 'missing_action': cfg['visual_concepts'][0]['slot_actions'].pop()
    if problem == 'replace_fixed_ip': cfg['visual_concepts'][0]['ip_asset_id'] = 'ip.doubao.junior.standard.001'
    if problem == 'replace_font': cfg['visual_concepts'][0]['font_reference_path'] = str(visual.SKILL_DIR / 'assets/logos/onion-logo-standard-001.png')
    with pytest.raises(ValueError): visual.plan_directions(cfg)


def test_random_ip_can_be_chosen_to_fit_each_authored_concept():
    cfg = content_config(); cfg.update(ip_random=True, ip_asset_id='__random_ip__')
    choices = ['ip.goudan.junior.standard.001', 'ip.doubao.junior.standard.001']
    for concept, asset in zip(cfg['visual_concepts'], choices): concept['ip_asset_id'] = asset
    assert [d['ip_asset_id'] for d in visual.plan_directions(cfg)['directions']] == choices


def test_no_ip_and_font_disabled_remain_respected():
    cfg = content_config(); cfg.update(ip='不用', ip_asset_id='', font_reference_enabled=False)
    assert all(not d['ip_asset_id'] and not d['font_reference_path'] for d in visual.plan_directions(cfg)['directions'])
    cfg['visual_concepts'][0]['ip_asset_id'] = 'ip.doubao.junior.standard.001'
    with pytest.raises(ValueError, match='saved IP'): visual.plan_directions(cfg)


def test_user_fixed_visual_requirements_are_kept_with_the_scene():
    cfg = content_config()
    cfg['visual_direction'] = {'style_prompt': '角色用原版二维动漫画法。', 'layout_id': 'title_top_scene_bottom'}
    layout = next(item for item in visual.load_catalog()['layouts'] if item['id'] == 'title_top_scene_bottom')
    for direction in visual.plan_directions(cfg)['directions']:
        assert cfg['visual_direction']['style_prompt'] in direction['base_prompt_rule']
        assert layout['prompt'] in direction['base_prompt_rule']


def random_style_config(sets=6):
    cfg=content_config();cfg.pop('visual_style_mode');cfg['sets']=sets
    assigned=visual.assign_styles(cfg)['directions']
    cfg['visual_concepts']=[{
        'name':f'学习场景{i+1}', 'style_id':style['style_id'],
        'prompt':'在家庭学习角整理数学任务，人物与纸张的动作关系清楚。'+style['style_prompt'],
        'slot_actions':['握笔准备开始。','展开纸卡安排任务。','查看完成纸卡。'],
    } for i,style in enumerate(assigned)]
    return cfg,assigned


def test_batch_default_assigns_random_main_styles_without_repeating_the_pool():
    cfg,assigned=random_style_config()
    assert assigned==visual.assign_styles(cfg)['directions']
    assert len({s['style_id'] for s in assigned})==6
    other=copy.deepcopy(cfg);other['request_id']='another-random-style-task'
    assert [s['style_id'] for s in assigned]!=[s['style_id'] for s in visual.assign_styles(other)['directions']]
    plan=visual.plan_directions(cfg)
    assert plan['style_mode']=='random'
    for direction,style in zip(plan['directions'],assigned):
        assert direction['style_id']==style['style_id']
        assert style['style_prompt'] in direction['base_prompt_rule']
        assert direction['style_source_ids']==style['style_source_ids']


def test_scene_must_acknowledge_its_randomly_assigned_style():
    cfg,_=random_style_config(2)
    cfg['visual_concepts'][0]['style_id']='unassigned-style'
    with pytest.raises(ValueError,match='assign-styles'):visual.plan_directions(cfg)


def test_user_fixed_style_overrides_batch_randomization():
    cfg,_=random_style_config(6)
    cfg['visual_direction']={'style_id':'commercial_anime'}
    for concept in cfg['visual_concepts']:
        concept['style_id']='commercial_anime'
        concept['prompt']='在完整的学习场景中使用商业动漫画法，人物动作、光线与构图统一。'
    plan=visual.plan_directions(cfg)
    assert {d['style_id'] for d in plan['directions']}=={'commercial_anime'}


def test_double_image_batches_randomize_by_set_and_keep_each_branch_bound(tmp_path):
    cfg,_=random_style_config(2)
    cfg['placements'][0]['image_count']=2
    for concept in cfg['visual_concepts']:concept['slot_actions']=concept['slot_actions'][:2]
    plan=visual.plan_directions(cfg)
    manifest=bound_manifest(cfg,plan,tmp_path)
    assert len({d['style_id'] for d in plan['directions']})==2
    assert len(manifest['jobs'])==4
    visual.validate_visual_plan(manifest,cfg)
    manifest['jobs'][1]['prompt']=manifest['jobs'][0]['prompt']
    with pytest.raises(ValueError,match='distinct complete prompt'):visual.validate_visual_plan(manifest,cfg)
