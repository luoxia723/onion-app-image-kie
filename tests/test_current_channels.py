import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import interactive_server
from kie_model import geometry_report
from logo_reference import logo_position


def test_only_current_table_combinations_are_available():
    expected = {
        ('华为','单图',984,422):200,
        ('vivo','三图',320,211):80,
        ('OPPO','单图',1280,720):500,
        ('OPPO','双图',474,768):500,
        ('OPPO','三图',320,210):500,
        ('小米','单图',960,540):500,
        ('小米','双图',960,540):500,
        ('小米','三图',320,320):300,
        ('小米','单图',480,320):500,
        ('荣耀','单图',1280,720):500,
        ('荣耀','三图',1080,1920):500,
        ('微博粉丝通','单图',1280,720):5120,
        ('喜马拉雅','单图',1280,720):150,
        ('喜马拉雅','单图',720,1280):150,
        ('喜马拉雅','单图',1200,480):150,
        ('喜马拉雅','单图',1000,1000):150,
        ('喜马拉雅','单图',720,1559):150,
        ('CPA','单图',690,360):500,
        ('CPA','单图',1080,1920):800,
    }
    slots = interactive_server.load_platform_slots()
    actual = {(s['platform'],s['image_form'],s['target_width'],s['target_height']):s['max_file_size_kb'] for s in slots if s['enabled']}
    assert actual == expected
    assert len(slots) == len(expected)
    assert sum(s['geometry']['needs_safe_area'] for s in slots) == 3
    for slot in slots:
        assert slot['source_revision'] == 105
        if slot['platform']=='喜马拉雅' and slot['target_size'] in ['720x1280','720x1559']:
            assert slot['logo_policy']=='required'
            assert logo_position({'placements':[slot]})=='上方居中'


def test_missing_or_empty_config_never_reenables_old_fallback(tmp_path):
    assert interactive_server.load_platform_slots(tmp_path/'missing.json') == []
    path=tmp_path/'empty.json';path.write_text(json.dumps({'placements':[]}))
    assert interactive_server.load_platform_slots(path) == []
    archived=json.loads((ROOT/'config/history/channel-placement-rules-legacy-102.json').read_text())
    assert len(archived['placements'])==102
    assert not any(p['enabled'] for p in archived['placements'])
    slots={slot['id']:slot for slot in interactive_server.load_platform_slots()}
    with pytest.raises(ValueError,match='unknown placement'):
        interactive_server.normalize_config_result({'delivery_name':'旧双图','placement_ids':['huawei-app-slot-slot-480x422']},slots)


def test_form_filters_match_current_table_only():
    expected={'单图':13,'双图':2,'三图':4}
    for form,count in expected.items():
        payload=interactive_server.build_config_payload('current-table',{'image_form':form})
        slots=[s for s in payload['slots'] if s['enabled'] and s['image_form']==form]
        assert len(slots)==count
        assert not any(s['category'] in ['学习机','百度'] for s in slots)
    slots=interactive_server.load_platform_slots()
    double={s['platform'] for s in slots if s['image_form']=='双图'}
    triple={s['platform'] for s in slots if s['image_form']=='三图'}
    assert double=={'OPPO','小米'}
    assert triple=={'vivo','OPPO','小米','荣耀'}
