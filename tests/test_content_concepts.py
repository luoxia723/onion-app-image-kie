"""New tasks freeze authored scenes instead of mixing unrelated visual pools."""
import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import interactive_server
import visual_directions as visual


def content_config():
    return {
        'request_id': 'content-first-math', 'sets': 2, 'visual_diversity_enabled': True,
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
        for slot in (1, 2, 3):
            rule = direction['base_prompt_rule'] if slot == 1 else direction['branch_prompt_rule']
            refs = ([{'asset_id': direction['ip_asset_id'], 'path': str(visual.SKILL_DIR / direction['ip_reference_path'])},
                     {'path': direction['font_reference_path']}] if slot == 1 else [])
            jobs.append({'set_id': direction['set_id'], 'slot': slot,
                         'visual_direction_id': direction['direction_id'],
                         'prompt': rule + '\n' + direction['slot_prompt_rules'][str(slot)], 'references': refs})
    return {'request_id': cfg['request_id'], 'visual_plan_path': str(path), 'jobs': jobs}


def test_new_saved_config_defaults_to_content_first():
    saved = interactive_server.normalize_config_result(
        {'delivery_name': '数学三图', 'placement_ids': ['oppo-app-slot-slot-320x210']},
        interactive_server.slots_by_id())
    assert saved['visual_diversity_mode'] == 'content_first'


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


def test_content_first_triptych_passes_batch_preflight_and_rejects_wrong_action(tmp_path,monkeypatch):
    import argparse
    import direct_batch
    import render
    from logo_reference import build_logo_reference, logo_prompt_rule
    from series_chain import text_rule

    cfg=content_config(); cfg['visual_diversity_mode']='content_first'
    plan=visual.plan_directions(cfg)
    manifest=bound_manifest(cfg,plan,tmp_path)
    directions={d['set_id']:d for d in plan['directions']}
    monkeypatch.setenv('ONION_IMAGE_WORKSPACE',str(tmp_path))
    monkeypatch.setattr(render,'request_json',lambda *a,**k:pytest.fail('paid API during preflight'))
    for job in manifest['jobs']:
        direction=directions[job['set_id']];slot=job['slot']
        base_id=job['set_id']+'-slot-01'
        base_path=tmp_path/'工作区/产物/03_候选'/f'{base_id}.png'
        job.update(job_id=job['set_id']+f'-slot-{slot:02d}',copy_text=cfg['copy_refs'][0][f'short{slot}'],
                   resolution='1K',size='320x210',
                   output=str(tmp_path/'工作区/产物/03_候选'/f'{job["set_id"]}-slot-{slot:02d}.png'),
                   depends_on=[] if slot==1 else [base_id])
        if slot==1:
            job['references']=[build_logo_reference(cfg),
                {'label':'参考图2','asset_id':direction['ip_asset_id'],'path':direction['ip_reference_path']},
                {'label':'参考图3','path':direction['font_reference_path']}]
            job['prompt']+='\n参考图1为Logo，参考图2为IP，参考图3为字体。'+logo_prompt_rule()
        else:
            job['base_job_id']=base_id
            job['references']=[{'label':'参考图1','path':str(base_path)}]
            job['prompt']+='\n参考图1为本套首张。'
        job['prompt']+='\n'+text_rule(job['copy_text'],cfg['logo'])
    cfg_path=tmp_path/'config.json'; manifest_path=tmp_path/'manifest.json'
    cfg_path.write_text(json.dumps(cfg,ensure_ascii=False));manifest_path.write_text(json.dumps(manifest,ensure_ascii=False))
    args=argparse.Namespace(manifest=manifest_path,config=cfg_path,validate_only=True,approved_in_current_task=False,approved_count=None)
    assert direct_batch.execute(args)==0
    first=plan['directions'][0]
    manifest['jobs'][1]['prompt']=manifest['jobs'][1]['prompt'].replace(first['slot_prompt_rules']['2'],first['slot_prompt_rules']['1'])
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False))
    monkeypatch.setattr(direct_batch,'invoke',lambda *a,**k:pytest.fail('render called before validating all scene actions'))
    with pytest.raises(ValueError,match='planned scene action'):direct_batch.execute(args)
