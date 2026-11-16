from pathlib import Path
import pytest
from PIL import Image
from local_app.config import UserError
from local_app.planning import BY_ID,make_round,compile_plans
from local_app import learning_workflow,learning_pipeline
from tests_local.fakes import FixturePlanner
from tests_local.test_workbench import engine
from tests_local.learning_history import frozen_placements,install_history

ROOT='learning-bbg-logo-banner-984x438'
SMALL='learning-bbg-logo-banner-530x236'
WIDE='learning-bbg-logo-banner-2368x670'
WIDE_SMALL='learning-bbg-logo-banner-1280x362'


def params(*pids):
    return dict(channel='学习机',image_form='单图',pids=list(pids),sets=1,
                feature_label='AI拍题精学',t1='疑问只需',t2='简单一拍！',
                extra_heading='动画精讲',extra_description='查看已确认的讲解',
                cta='点击下载',ip='random',style='random',font='none',noLogo=False)


def planned(tmp_path,*pids):
    """Construct a legacy frozen round directly, never through the new entry."""
    r=make_round(params(*pids),'legacy-test',tmp_path,2,True,defer_planning=True,
                 placements_override=frozen_placements(pids))
    compile_plans(r,FixturePlanner().plan(r,lambda _:None))
    return r


@pytest.mark.history
@pytest.mark.parametrize('pid,fields',[('learning-bbg-cover-400x480',[]),('learning-ruishi-rect-580x320',['feature_label'])])
def test_legacy_prompt_reconstruction_keeps_only_visible_copy(tmp_path,pid,fields):
    pr=params(pid);pr.update(t1='',t2='',cta='',feature_label='AI拍题精学' if fields else '')
    # Historical records retain their own old module contract, independently
    # from the current user rule which removes every function label.
    r=make_round(pr,'legacy-copy',tmp_path,1,True,defer_planning=True,placements_override=frozen_placements([pid]))
    compile_plans(r,FixturePlanner().plan(r,lambda _:None));prompt=r['slots'][0]['prompt']
    assert '主标题：' not in prompt and '副标题：' not in prompt
    assert ('功能名：' in prompt)==bool(fields)
    assert '点击下载' not in prompt


@pytest.mark.history
def test_legacy_main_copy_stays_same_hierarchy_and_hidden_cta_ignored(tmp_path):
    prompt=planned(tmp_path,'learning-seewo-1400x520')['slots'][0]['prompt']
    assert '疑问只需' in prompt and '简单一拍！' in prompt
    assert '同一层级' in prompt and '副标题：' not in prompt and '点击下载' not in prompt


def test_new_pipeline_does_not_use_a_delivery_placement_as_the_baseline():
    p=learning_pipeline.preview(params(SMALL,ROOT,WIDE_SMALL,WIDE),seed='unique-baseline')
    assert p['baseline']['id']==learning_pipeline.BASELINE_ID and p['baseline']['is_delivery'] is False
    assert len(p['outputs'])==4
    assert all(o['depends_on']==[learning_pipeline.BASELINE_ID,learning_pipeline.BASELINE_CONFIRMATION_ID] for o in p['outputs'])
    assert p['execution']['enabled'] is False


@pytest.mark.parametrize('mode',['generate','upload','baseline_then_suite'])
def test_new_learning_requests_cannot_enter_legacy_generation_engine(engine,mode):
    pr={**params(ROOT),'learning_mode':mode}
    with pytest.raises(UserError):engine.create(pr,'retired-learning-'+mode)
    assert not engine.tasks


@pytest.mark.history
def test_legacy_completed_round_keeps_source_version_checks(engine):
    t=install_history(engine,params(ROOT,SMALL));r=t['rounds'][0]
    by={s['pid']:s for s in r['slots']};learning_workflow.freeze_sources(r,by[SMALL])
    version=by[SMALL]['source_versions'][by[ROOT]['id']]
    assert version['att']==1 and version['sha256']==by[ROOT]['sha256']
    assert Path(version['path']).is_file()
    Path(by[ROOT]['jpeg']).write_bytes(b'changed')
    with pytest.raises(UserError,match='校验失败'):learning_workflow.freeze_sources(r,by[SMALL])


@pytest.mark.history
def test_legacy_descendants_are_scoped_to_recorded_sources(tmp_path):
    r=planned(tmp_path,ROOT,SMALL,WIDE,WIDE_SMALL);by={s['pid']:s for s in r['slots']}
    assert {s['pid'] for s in learning_workflow.descendants(r,by[WIDE])}=={WIDE,WIDE_SMALL}
    assert {s['pid'] for s in learning_workflow.descendants(r,by[ROOT])}=={ROOT,SMALL,WIDE,WIDE_SMALL}


@pytest.mark.history
def test_legacy_local_resize_and_round_corner_require_no_provider(tmp_path):
    p=BY_ID['learning-xiaoyuan-1372x480'];source=tmp_path/'mother.png';target=tmp_path/'scaled.png'
    Image.new('RGB',(2880,1020),'#557799').save(source)
    s={'output':str(target),'parent_id':'parent','source_versions':{'parent':{'path':str(source)}}}
    learning_workflow.resize_local({},s,p)
    with Image.open(target) as image:
        assert image.size==(1372,480) and image.getextrema()==((85,85),(119,119),(153,153))
    from local_app.learning_delivery import save_png
    rounded=BY_ID['learning-ruishi-rounded-580x320'];save_png(source,tmp_path/'rounded.png',rounded)
    with Image.open(tmp_path/'rounded.png') as image:assert image.convert('RGBA').getpixel((0,0))[3]==0


def test_direct_model_adapter_rejects_local_tasks():
    from local_app.kie_client import _generate
    with pytest.raises(UserError,match='不能提交图片模型'):_generate({'slot':{'production_mode':'local_resize'}},'unused',[],lambda _:None)
