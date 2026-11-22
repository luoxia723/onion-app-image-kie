"""Current learning configuration, plus already-frozen PNG/history compatibility."""
import copy,hashlib,zipfile
from pathlib import Path
import pytest
from PIL import Image
from local_app.config import UserError
from local_app.planning import PLACEMENTS,UNAVAILABLE_PLACEMENTS,make_round,compile_plans,STYLES
from local_app.quality import verify_delivery_file,verify_image_bytes
from local_app import learning_pipeline,learning_workflow
from tests_local.test_workbench import engine
from tests_local.fakes import FixturePlanner
from tests_local.learning_history import frozen_placements,install_history

LEARNING=[p for p in PLACEMENTS if p['category']=='学习机']
LEGACY_SAMPLES=list(frozen_placements(learning_workflow.RULES).values())
NO_LOGO_IDS={
 'learning-bbg-cover-216x260','learning-bbg-cover-300x360','learning-bbg-cover-400x480',
 'learning-bbg-no-logo-banner-1280x362','learning-seewo-1400x520',
 'learning-youxuepai-cover-400x480','learning-youxuepai-masked-840x404','learning-youxuepai-unmasked-840x404',
 'learning-youxuepai-logo-1400x640',
}
CTA_IDS={
 'learning-baidu-512x512','learning-baidu-1200x400','learning-zuoyebang-446x446','learning-zuoyebang-632x354',
 'learning-iflytek-1005x564','learning-iflytek-1626x684','learning-bbg-logo-banner-530x236',
 'learning-bbg-logo-banner-984x438','learning-bbg-logo-banner-988x350','learning-bbg-logo-banner-988x460',
 'learning-bbg-logo-banner-1080x528','learning-bbg-logo-banner-1280x362','learning-bbg-logo-banner-2368x670',
 'learning-bbg-no-logo-banner-1280x362',
}
PURE_IDS={'learning-bbg-cover-216x260','learning-bbg-cover-300x360','learning-bbg-cover-400x480',
          'learning-ruishi-rect-580x320','learning-ruishi-rounded-580x320'}


def params(p):
 return dict(channel='学习机',image_form=p['image_form'],pids=[p['id']],sets=1,feature_label='AI拍题精学',extra_heading='动画精讲',extra_description='查看已确认的讲解',t1='拍题精学',t2='查看学习任务',s1='',s2='',s3='',cta='立即体验',style=STYLES[0]['name'],ip='random',font='none',noLogo=False)


def test_current_catalog_has_44_fixed_placements_not_sample_gated_alternatives():
 assert len(LEARNING)==44 and not any(p['category']=='学习机' for p in UNAVAILABLE_PLACEMENTS)
 assert len({p['platform'] for p in LEARNING})==10
 assert sum(p['image_count'] for p in LEARNING)==45
 assert sum(p['logo_required'] for p in LEARNING)==35 and sum(p['cta_required'] for p in LEARNING)==14
 assert {p['id'] for p in LEARNING if not p['logo_required']}==NO_LOGO_IDS
 assert {p['id'] for p in LEARNING if p['cta_required']}==CTA_IDS
 assert {p['id'] for p in LEARNING if not p['content_modules']['main_copy']}==PURE_IDS
 assert all(not any(p['content_modules'][key] for key in ('feature_label','badge','extra_heading','extra_description')) for p in LEARNING)
 assert all(p['output_format']=='PNG' and p['source_revision']==243 for p in LEARNING)
 assert not any((p['target_width'],p['target_height'])==(96,50) for p in LEARNING)
 bbg=[p for p in LEARNING if p['platform']=='步步高' and p['target_size']=='1280x362']
 assert {p['logo_policy'] for p in bbg}=={'required','forbidden'}
 assert next(p for p in LEARNING if p['id']=='learning-youxuepai-double-840x404')['image_count']==2


def test_complete_current_plan_preserves_all_placement_mappings_and_output_indices():
 plan=learning_pipeline.preview({**params(LEARNING[0]),'pids':[p['id'] for p in LEARNING]},seed='placement-contract')
 assert plan['output_count']==45 and len(plan['outputs'])==45
 assert {o['placement_id'] for o in plan['outputs']}=={p['id'] for p in LEARNING}
 for p in LEARNING:
  outputs=[o for o in plan['outputs'] if o['placement_id']==p['id']]
  assert [o['image_index'] for o in outputs]==list(range(1,p['image_count']+1))
  assert all((o['width'],o['height'])==(p['target_width'],p['target_height']) for o in outputs)
  assert all((o['logo_required'],o['cta_required'])==(p['logo_required'],p['cta_required']) for o in outputs)
  assert all(o['depends_on']==[learning_pipeline.BASELINE_ID,learning_pipeline.BASELINE_CONFIRMATION_ID] for o in outputs)
 assert plan['execution']['enabled'] is False


@pytest.mark.history
def test_legacy_complete_round_keeps_original_modules_when_current_rules_differ(tmp_path):
 placements=frozen_placements(learning_workflow.RULES)
 pr={**params(LEGACY_SAMPLES[0]),'pids':list(placements)}
 r=make_round(pr,'legacy',tmp_path,1,True,defer_planning=True,placements_override=placements)
 compile_plans(r,FixturePlanner().plan(r,lambda _:None))
 assert len(r['slots'])==36
 configs={c['pid']:c['config'] for c in r['configs']}
 for pid,p in placements.items():
  cfg=configs[pid];modules=learning_workflow.RULES[pid]['modules']
  assert cfg['learning_modules']==modules
  assert (cfg['logo']=='不用')==(p['logo_policy']=='forbidden')
  assert cfg['cta']==('立即体验' if modules['cta'] else '')
  for field,module in [('feature_label','feature_label'),('extra_heading','extra_heading'),('extra_description','extra_description')]:
   assert cfg['learning_copy'][field]==(pr[field] if modules[module] else '')
  for asset in cfg['placements'][0].get('delivery_assets',{}).values():assert tmp_path in Path(asset['path']).parents
 # Independent examples pin the old meaning instead of comparing two objects
 # derived from today's catalog: these all deliberately differ from current.
 assert configs['learning-zuoyebang-1224x408']['cta']=='立即体验'
 assert configs['learning-dsl-rounded-card-484x580']['learning_copy']['extra_heading']=='动画精讲'
 assert configs['learning-ruishi-rect-580x320']['learning_copy']['feature_label']=='AI拍题精学'
 current={p['id']:p for p in LEARNING}
 assert current['learning-zuoyebang-1224x408']['cta_required'] is False
 assert current['learning-dsl-rounded-card-484x580']['content_modules']['extra_heading'] is False
 assert current['learning-ruishi-rect-580x320']['content_modules']['feature_label'] is False


@pytest.mark.history
def test_legacy_fixture_specification_survives_current_dimension_and_delivery_edits(tmp_path,monkeypatch):
 from local_app.planning import BY_ID
 pid='learning-dsl-rounded-card-484x580'
 changed=copy.deepcopy(BY_ID[pid]);assets=copy.deepcopy(changed['delivery_assets'])
 changed.update(target_width=12,target_height=12,target_size='12x12',render_width=12,render_height=12,
                render_size='12x12',target_ratio='1:1',image_count=3,max_file_size_kb=1,
                file_size_operator='lte',corner_radius=0,output_format='JPEG',format='jpeg')
 monkeypatch.setitem(BY_ID,pid,changed)
 frozen=frozen_placements([pid])[pid]
 assert (frozen['target_width'],frozen['target_height'],frozen['target_size'])==(484,580,'484x580')
 assert (frozen['render_width'],frozen['render_height'],frozen['render_size'])==(484,580,'484x580')
 assert frozen['image_count']==1 and frozen['target_ratio']=='121:145'
 assert (frozen['max_file_size_kb'],frozen['file_size_operator'],frozen['corner_radius'])==(100,'lt',44)
 assert frozen['output_format']=='PNG' and frozen['format']=='png' and frozen['delivery_assets']==assets
 r=make_round(params(frozen),'legacy-spec',tmp_path,1,True,defer_planning=True,placements_override={pid:frozen})
 compile_plans(r,FixturePlanner().plan(r,lambda _:None))
 assert len(r['slots'])==1
 assert r['configs'][0]['config']['placements'][0]['target_size']=='484x580'
 assert changed['target_size']=='12x12'  # Constructing the fixture did not repair or mutate current settings.


@pytest.mark.history
@pytest.mark.parametrize('pid',['learning-seewo-1400x520','learning-dsl-rounded-card-484x580','learning-ruishi-rounded-580x320','learning-baidu-512x512'])
def test_historical_png_can_be_read_saved_and_restored(engine,tmp_path,pid):
 p=next(p for p in LEARNING if p['id']==pid);t=install_history(engine,params(p));tid=t['id'];r=t['rounds'][0]
 content_before={c['pid']:{key:copy.deepcopy(c['config'][key]) for key in ('learning_modules','learning_copy','cta')} for c in r['configs']}
 for s in r['slots']:
  with Image.open(s['jpeg']) as im:
   assert im.format=='PNG' and im.size==(p['target_width'],p['target_height'])
   if p.get('alpha_sha256'):assert hashlib.sha256(im.convert('RGBA').getchannel('A').tobytes()).hexdigest()==p['alpha_sha256']
  verify_delivery_file(s,p)
 engine.mutate(tid,'adopt',{'set':1,'adopted':True});pkg=engine.package(tid,0)
 with zipfile.ZipFile(pkg['path']) as z:
  files=[f for f in z.namelist() if f!='交付清单.json'];assert len(files)==p['image_count'];assert all(f.endswith('.png') for f in files)
 backup=engine.create_backup()
 from local_app.config import Settings
 from local_app.engine import Engine
 folder=tmp_path/'restored';folder.mkdir();settings=Settings(folder/'state',folder/'test.env');settings.update({'output_dir':str(folder),'simulation':True})
 other=Engine(settings,start=False,planner=FixturePlanner())
 try:
  info=other.restore_preview(backup['path']);other.restore_backup(backup['path'],info['token']);restored=other.task(tid)
  content_after={c['pid']:{key:c['config'][key] for key in ('learning_modules','learning_copy','cta')} for c in restored['rounds'][0]['configs']}
  assert content_after==content_before
  for s in restored['rounds'][0]['slots']:verify_delivery_file(s,other.placement(restored,restored['rounds'][0],s))
  assert other.valid_package(restored,pkg['fingerprint'])
 finally:other.close()


def test_png_rejects_jpeg_disguised_as_png(tmp_path):
 p=LEARNING[0];f=tmp_path/'fake.png';Image.new('RGB',(p['target_width'],p['target_height'])).save(f,'JPEG');data=f.read_bytes()
 with pytest.raises(UserError,match='PNG'):verify_image_bytes(data,p,hashlib.sha256(data).hexdigest())


@pytest.mark.history
def test_legacy_png_size_failure_preserves_raw_and_does_not_shrink(tmp_path):
 from local_app.learning_delivery import save_png
 p=copy.deepcopy(LEARNING[0]);p['max_file_size_kb']=.01;p['file_size_operator']='lt'
 source=tmp_path/'raw.png';target=tmp_path/'finished.png';Image.new('RGB',(200,200),'white').save(source);before=source.read_bytes()
 with pytest.raises(ValueError,match='PNG无法同时满足'):save_png(source,target,p)
 assert source.read_bytes()==before and not target.exists() and not target.with_suffix('.tmp.png').exists()


@pytest.mark.history
def test_historical_badge_uses_original_pixels_after_png_encoding(tmp_path):
 from local_app.learning_delivery import save_png,checked_asset
 p=next(p for p in LEARNING if p['id']=='learning-dsl-rounded-card-484x580');source=tmp_path/'raw.png';target=tmp_path/'finished.png';Image.new('RGB',(484,580),'#3157aa').save(source);save_png(source,target,p)
 with Image.open(checked_asset(p['delivery_assets']['badge'])) as im:badge=im.convert('RGBA')
 with Image.open(target) as im:actual=im.convert('RGBA')
 for xy in [(40,20),(60,30),(80,40)]:assert badge.getpixel(xy)[3]==255 and actual.getpixel(xy)==badge.getpixel(xy)


@pytest.mark.history
def test_legacy_compiler_cannot_bypass_its_frozen_sample_gate(tmp_path):
 p=copy.deepcopy(LEGACY_SAMPLES[0]);p.pop('sample_reference')
 with pytest.raises(UserError,match='样图'):make_round(params(p),'legacy-no-sample',tmp_path,1,True,defer_planning=True,placements_override={p['id']:p})


def test_incomplete_historical_job_cannot_reach_provider(tmp_path):
 from local_app.kie_client import generate
 job={'placement':{'category':'学习机'},'slot':{'output':str(tmp_path/'result.png')}}
 with pytest.raises(UserError,match='样图'):generate(job,'fake-key',[],lambda stage:None)
