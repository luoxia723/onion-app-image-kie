import pytest
from local_app.planning import PLACEMENTS,validate,make_round,compile_plans
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
    slots = PLACEMENTS
    actual = {(s['platform'],s['image_form'],s['target_width'],s['target_height']):s['max_file_size_kb'] for s in slots if s['enabled']}
    assert actual == expected
    assert len(slots) == len(expected)
    assert sum(geometry_report(s['target_width'],s['target_height'])['needs_safe_area'] for s in slots) == 3
    for slot in slots:
        assert slot['source_revision'] == 105
        if slot['platform']=='喜马拉雅' and slot['target_size'] in ['720x1280','720x1559']:
            assert slot['logo_policy']=='required'
            assert logo_position({'placements':[slot]})=='上方居中'


@pytest.mark.parametrize('no_logo',[True,False])
def test_required_logo_is_locked_per_placement(tmp_path,no_logo):
    from tests_local.fakes import FixturePlanner
    required=[p for p in PLACEMENTS if p['logo_policy']=='required']
    optional=next(p for p in PLACEMENTS if p['category']==required[0]['category'] and p['image_form']=='单图' and p['logo_policy']!='required')
    placements=required+[optional]
    pr=dict(pids=[p['id'] for p in placements],sets=1,t1='主标题',t2='副标题',ip='none',noLogo=no_logo)
    validate(pr,tmp_path)
    r=make_round(pr,'locked-logo',tmp_path,1,True,defer_planning=True)
    compile_plans(r,FixturePlanner().plan(r,lambda result:None))
    for config_idx,entry in enumerate(r['configs']):
        cfg=entry['config'];expected=not no_logo or cfg['placements'][0]['logo_policy']=='required'
        assert cfg['logo']==('洋葱学园' if expected else '不用')
        slot=next(slot for slot in r['slots'] if slot['config_idx']==config_idx)
        assert any(ref.get('asset_id','').startswith('logo.') for ref in slot['refs'])==expected


def test_required_logo_satisfies_reference_requirement(tmp_path):
    required=next(p for p in PLACEMENTS if p['logo_policy']=='required')
    pr=dict(pids=[required['id']],sets=1,t1='主标题',t2='副标题',ip='none',font='none',noLogo=True)
    validate(pr,tmp_path)
    r=make_round(pr,'required-logo-only',tmp_path,1,True,defer_planning=True)
    assert any(ref.get('asset_id','').startswith('logo.') for ref in r['slots'][0]['refs'])
