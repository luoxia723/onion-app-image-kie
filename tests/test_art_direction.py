"""Art direction remains hierarchical while subject and screen choices open up."""
import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import interactive_server
import visual_directions as visual
from series_chain import text_rule
from validate_task import validate


def art_config():
    return {
        'request_id':'art-direction-test','sets':1,'ip':'不用','ip_asset_id':'',
        'font_reference_enabled':False,'visual_diversity_mode':'content_first',
        'visual_style_mode':'coordinated','art_direction_required':True,'screen_ui_mode':'conceptual',
        'visual_direction':{'style_id':'steampunk'},
        'copy_refs':[{'copyDraftId':'math','mainTitle':'这周我想把数学补起来','subtitle':'洋葱AI按目标和基础排每日任务'}],
        'placements':[{'image_count':1,'target_width':1280,'target_height':720}],
        'visual_concepts':[{
            'name':'中世纪启发的纸页路径','prompt':'石拱窗光下，纸页被整理成学习任务路径，清晰屏幕展示已确认的任务与进度。',
            'slot_actions':['展开纸页，让散乱目标转为有序任务。'],
            'art_direction':{'world':'中世纪幻想藏书室','scene':'石拱窗、木桌与展开纸页','story':'从只有学习目标到看清每日任务',
                             'composition':'纸页路径引向主要学习动作，标题在自然留白','lighting_materials':'窗光统一石材、木材与纸面'},
            'screen_text':['今日任务','学习进度'],
        }],
    }


def test_layers_compile_in_order_and_conceptual_screen_does_not_need_a_screenshot():
    cfg=art_config();d=visual.plan_directions(cfg)['directions'][0]
    prompt=d['base_prompt_rule']
    labels=['画风定调','场景与故事：','本张动作与情绪']
    positions=[prompt.index(label) for label in labels]
    assert positions==sorted(positions)
    assert d['art_direction']==cfg['visual_concepts'][0]['art_direction']
    assert d['screen_ui_mode']=='conceptual' and d['screen_text']==['今日任务','学习进度']
    assert not d['ip_asset_id']


def test_long_internal_art_direction_is_saved_but_not_dumped_into_prompt():
    cfg=art_config()
    for key in cfg['visual_concepts'][0]['art_direction']:
        cfg['visual_concepts'][0]['art_direction'][key]+='内部设计推敲。'*300
    d=visual.plan_directions(cfg)['directions'][0]
    assert len(json.dumps(d['art_direction'],ensure_ascii=False))>10000
    assert '内部设计推敲' not in d['base_prompt_rule']
    assert cfg['visual_concepts'][0]['prompt'] in d['base_prompt_rule']
    assert len(d['base_prompt_rule'])<1000


@pytest.mark.parametrize('missing',['world','scene','story','composition','lighting_materials'])
def test_new_tasks_require_every_art_direction_layer(missing):
    cfg=art_config();cfg['visual_concepts'][0]['art_direction'].pop(missing)
    with pytest.raises(ValueError,match='art_direction'):visual.plan_directions(cfg)


def test_new_saved_configs_allow_conceptual_ui_by_default_and_keep_real_ui_explicit():
    body={'delivery_name':'艺术定调','placement_ids':['oppo-rich-horizontal-big-1280x720']}
    slots=interactive_server.slots_by_id()
    conceptual=interactive_server.normalize_config_result(body,slots)
    assert conceptual['art_direction_required']
    assert conceptual['screen_ui_mode']=='conceptual' and not conceptual['ui_reference_required']
    assert conceptual['ui_reference_next_action']==''
    real=interactive_server.normalize_config_result({**body,'ui_reference_required':True},slots)
    assert real['screen_ui_mode']=='reference' and real['ui_reference_required']
    explicit=interactive_server.normalize_config_result({**body,'ui_reference_required':True,'screen_ui_mode':'conceptual'},slots)
    assert not explicit['ui_reference_required']


def test_ui_screenshot_validation_is_only_for_real_reference_mode():
    task={'schema_version':'onion_app_image_task_v1','task_id':'test','copy_source':'copy.md','approved_copy_ids':['one'],
          'config_status':'saved','placements':[{}],'asset_references':[],'ui_required':True,'ui_references':[],
          'candidate_count':1,'paid_generation_approved':False,'publishing_allowed':False,'screen_ui_mode':'conceptual'}
    assert validate(task)==[]
    task['screen_ui_mode']='reference'
    assert 'ui_reference_required' in validate(task)
    task['ui_references']=['real-screenshot.png']
    assert validate(task)==[]


def test_no_ip_style_assignments_do_not_inherit_identity_constraints():
    cfg=art_config();cfg.update(sets=39,visual_direction={})
    cfg['copy_refs'].append({**cfg['copy_refs'][0],'copyDraftId':'math-2'})
    directions=visual.assign_styles(cfg)['directions']
    assert len(directions)==78 and len({d['style_id'] for d in directions})==77
    for d in directions:
        assert d['ip_adaptation']==''
        assert not any(token in d['style_prompt'] for token in ['IP','脸型','发型','体型','服装','五官'])


def test_ip_can_take_small_period_details_without_changing_identity():
    cfg=art_config();cfg.update(ip='狗蛋',ip_asset_id='ip.goudan.junior.standard.001')
    cfg['visual_concepts'][0]['prompt']='狗蛋在中世纪启发藏书室展开纸页，原蓝黄服装上加入小披肩与黄铜扣，保持原脸型和标识。'
    d=visual.plan_directions(cfg)['directions'][0]
    assert d['ip_asset_id']==cfg['ip_asset_id']
    assert '小披肩与黄铜扣' in d['base_prompt_rule']
    assert d['art_direction']['world']=='中世纪幻想藏书室'
    style=visual.assign_styles(cfg)['directions'][0]
    assert '扣件' in style['ip_adaptation']


def test_screen_text_is_bound_to_the_visual_plan_and_literal_whitelist(tmp_path):
    cfg=art_config();plan=visual.plan_directions(cfg);d=plan['directions'][0]
    path=tmp_path/'visual-plan.json';path.write_text(json.dumps(plan))
    job={'set_id':d['set_id'],'slot':1,'visual_direction_id':d['direction_id'],
         'prompt':d['base_prompt_rule'],'references':[],'ui_text':d['screen_text']}
    manifest={'visual_plan_path':str(path),'jobs':[job]}
    visual.validate_visual_plan(manifest,cfg)
    assert json.loads(text_rule('主文案','洋葱学园','',job['ui_text']).split('：',1)[1])==['主文案','洋葱学园','今日任务','学习进度']
    broken=copy.deepcopy(manifest);broken['jobs'][0]['ui_text']=['未经确认的成绩']
    with pytest.raises(ValueError,match='ui_text'):visual.validate_visual_plan(broken,cfg)


def test_screen_none_does_not_accept_screen_labels():
    cfg=art_config();cfg['screen_ui_mode']='none'
    with pytest.raises(ValueError,match='screen_text'):visual.plan_directions(cfg)


def test_user_fixed_style_is_not_overridden_by_a_concept_and_not_repeated():
    cfg=art_config()
    d=visual.plan_directions(cfg)['directions'][0]
    style=next(s for s in visual.load_catalog()['styles'] if s['id']=='steampunk')
    assert d['base_prompt_rule'].count(style['no_ip_prompt'])==1
    cfg['visual_concepts'][0]['style_id']='watercolor_illustration'
    with pytest.raises(ValueError,match='assign-styles'):visual.plan_directions(cfg)


@pytest.mark.parametrize('saved',['none','reference'])
def test_concept_cannot_override_an_explicit_screen_choice(saved):
    cfg=art_config();cfg['screen_ui_mode']=saved
    cfg['visual_concepts'][0]['screen_ui_mode']='conceptual'
    with pytest.raises(ValueError,match='saved screen choice'):visual.plan_directions(cfg)
