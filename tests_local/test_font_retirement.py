from pathlib import Path
from local_app.planning import ASSETS,bootstrap,make_round,compile_plans,PLACEMENTS,suite_metadata,STYLES
from tests_local.fakes import FixturePlanner
from font_library import font_references


def test_only_requested_sample_is_excluded_from_new_choices():
    all_fonts=font_references(include_disabled=True);active=font_references()
    assert {p.name for p in all_fonts}-{p.name for p in active}=={'字体参考-06.png'}
    assert next(p for p in all_fonts if p.name=='字体参考-06.png').is_file()
    assert len(bootstrap()['assets']['fonts'])==len(active)
    assert not any(x['label']=='字体参考-06' for x in bootstrap()['assets']['fonts'])


def test_new_random_selection_excludes_sample_but_frozen_plan_still_compiles(tmp_path):
    p=next(p for p in PLACEMENTS if p['image_count']==2)
    # Font retirement is independent of style sampling. A catalog style makes
    # this exercise font binding on every run, including the historical rebind.
    pr=dict(image_form='双图',pids=[p['id']],sets=3,t1='',t2='',s1='开始学习',s2='继续学习',s3='',cta='',ip='none',style=STYLES[0]['name'],feature_note='',product_facts='')
    r=make_round(pr,'retirement-test',tmp_path,2,True,defer_planning=True)
    assert all(m['font_path'] for m in r['set_metadata'].values())
    assert all(Path(m['font_path']).name!='字体参考-06.png' for m in r['set_metadata'].values())
    # Frozen historical schemes retain their original sample and reference binding.
    path=str(next(p for p in font_references(include_disabled=True) if p.name=='字体参考-06.png').resolve())
    entry=r['configs'][0]
    suite_metadata(r['set_metadata'],p['id'],entry['set'])['font_path']=path
    first=next(s for s in r['slots'] if s['set']==entry['set'] and s['idx']==1)
    ref=next(x for x in first['refs'] if x.get('role')=='标题字体参考')
    ref['path']=path
    result=FixturePlanner().plan(r,lambda x:None);compile_plans(r,result)
    assert entry['direction']['font_reference_path']==path
    assert ref['path']==path and first['plan_ready']
