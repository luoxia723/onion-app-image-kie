"""Collected descriptors must be traceable and reach the actual base prompt."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import visual_directions as visual


def style_config():
    return {'request_id':'sourced-style-check','sets':1,'logo':'洋葱学园',
            'ip':'雷婷','ip_asset_id':'ip.leiting.junior.standard.001','font_reference_enabled':True,
            'visual_diversity_mode':'open',
            'visual_direction':{'style_id':'art-deco'},
            'copy_refs':[{'copyDraftId':'math','short1':'这周我想把数学补起来','short2':'洋葱AI按目标和基础排每日任务','short3':'打开看今天学啥学完看进度'}],
            'placements':[{'id':'oppo','image_count':3,'target_width':320,'target_height':210}]}


def test_sourced_style_alias_and_ip_adaptation_reach_base_prompt():
    plan=visual.plan_directions(style_config())
    direction=plan['directions'][0]
    catalog=visual.load_catalog()
    style=next(s for s in catalog['styles'] if s['id']==direction['style_id'])
    assert direction['style_id']=='art-deco-geometric'
    assert style['prompt'] in direction['base_prompt_rule']
    assert style['ip_adaptation'] in direction['base_prompt_rule']
    assert direction['style_source_ids']==style['source_ids']
    assert direction['style_image_validated'] is False


def test_library_definitions_are_original_descriptions_not_raw_sd_templates():
    catalog=visual.load_catalog()
    sources=json.loads((visual.SKILL_DIR/'config/visual-style-sources.json').read_text())['sources']
    ids={s['id'] for s in sources}
    assert len(catalog['styles'])>20
    for s in catalog['styles']:
        assert s['source_ids'] and set(s['source_ids'])<=ids
        assert len(s['prompt'])>=25 and s['ip_adaptation']
        assert s['verification_status']=='text_reviewed' and s['image_validated'] is False
        assert 'negative_prompt' not in s
        assert all(token not in s['prompt'].lower() for token in ('{prompt}','<lora:','--ar','(worst quality'))


def test_unknown_provenance_is_rejected(tmp_path, monkeypatch):
    catalog=json.loads(visual.CATALOG.read_text())
    sources=json.loads((visual.SKILL_DIR/'config/visual-style-sources.json').read_text())
    (tmp_path/'sources.json').write_text(json.dumps(sources))
    catalog['style_sources_path']='sources.json'
    catalog['styles'][0]['source_ids']=['unverified-source']
    path=tmp_path/'catalog.json';path.write_text(json.dumps(catalog))
    monkeypatch.setattr(visual,'CATALOG',path)
    with pytest.raises(ValueError,match='source'):
        visual.load_catalog()


def test_search_exposes_real_prompt_and_separates_validation_status():
    result=subprocess.run([sys.executable,str(visual.SKILL_DIR/'scripts/visual_directions.py'),
                           '--list-styles','--query','浮世绘','--detail'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    rows=json.loads(result.stdout)['styles']
    assert rows and any('浮世绘' in row['name'] for row in rows)
    assert all(row['prompt'] and row['source_ids'] and row['image_validated'] is False for row in rows)


def test_open_candidate_can_reference_a_collected_style_without_losing_provenance():
    cfg=style_config()
    cfg.pop('visual_direction')
    cfg['visual_candidates']={'styles':[{'id':'art-deco'}]}
    direction=visual.plan_directions(cfg)['directions'][0]
    assert direction['style_id']=='art-deco-geometric'
    assert direction['style_source_ids']
    assert direction['style_description_origin']=='original_synthesis'
    assert '本主风格的IP适配' in direction['base_prompt_rule']


def test_unrecognized_style_reference_cannot_create_an_empty_direction():
    cfg=style_config()
    cfg.pop('visual_direction')
    cfg['visual_candidates']={'styles':[{'id':'uncollected-unknown-style'}]}
    with pytest.raises(ValueError,match='concrete prompt'):
        visual.plan_directions(cfg)
