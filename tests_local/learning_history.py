"""Build an already-completed historical learning round without Engine.create or providers."""
import copy
import hashlib
import time
import uuid
from fractions import Fraction
from pathlib import Path
from PIL import Image
from local_app.planning import BY_ID,make_round,compile_plans
from local_app.learning_workflow import RULES
from local_app.learning_delivery import save_png
from tests_local.fakes import FixturePlanner


def frozen_placements(pids):
    """Reconstruct the fields retained by the old 36-placement contract.

    The historical workflow JSON is the retained 36-placement format. In
    particular it still contains function labels, the featured footer and the
    old CTA on the 1224×408 sample. This is not a full archived task dump:
    sample/delivery-asset records come from the retained project assets, whose
    hashes and image sizes are checked by the actual legacy compiler/exporter.
    """
    result={}
    for pid in pids:
        placement=copy.deepcopy(BY_ID[pid])
        rule=copy.deepcopy(RULES[pid])
        width,height=map(int,rule['size'].split('x'))
        ratio=Fraction(width,height)
        placement.update(platform=rule['platform'],name=rule['name'],placement=rule['name'],learning_rule=rule,
                         image_form='单图',image_count=1,
                         target_width=width,target_height=height,target_size=rule['size'],
                         target_ratio=f'{ratio.numerator}:{ratio.denominator}',
                         render_width=width,render_height=height,render_size=rule['size'],
                         max_file_size_kb=rule['max_kb'],file_size_operator=rule['file_size_operator'],
                         corner_radius=rule['corner_radius'],output_format=rule['format'],format=rule['format'].lower(),
                         content_modules=copy.deepcopy(rule['modules']),
                         logo_required=rule['modules']['logo'],cta_required=rule['modules']['cta'],
                         logo_policy='required' if rule['modules']['logo'] else 'forbidden',
                         cta_policy='required' if rule['modules']['cta'] else 'forbidden')
        result[pid]=placement
    return result


def install_history(engine, params):
    tid=uuid.uuid4().hex
    cache=engine.settings.output/'.cache'/tid/uuid.uuid4().hex
    r=make_round(params,tid,cache,engine.settings.concurrency,True,defer_planning=True,
                 placements_override=frozen_placements(params['pids']))
    if r['planning_status']!='done':compile_plans(r,FixturePlanner().plan(r,lambda _:None))
    for slot in r['slots']:
        p=r['configs'][slot['config_idx']]['config']['placements'][0]
        Image.new('RGB',(p['target_width'],p['target_height']),'#557799').save(slot['output'],'PNG')
        dest=str(Path(slot['output']).with_suffix('.delivery.png'));save_png(slot['output'],dest,p)
        slot.update(state='done',jpeg=dest,sha256=hashlib.sha256(Path(dest).read_bytes()).hexdigest(),
                    raw_sha256=hashlib.sha256(Path(slot['output']).read_bytes()).hexdigest(),delivery_eligible=True)
    r.update(planning_status='done',paused=True,stopped=True)
    task=dict(id=tid,pkg='historical-learning',name='历史学习机任务',direction='历史学习机',date=time.time()*1000,
              rounds=[r],ri=0,pkgs=[],downloaded=False,output_dir=str(engine.settings.output),archived=False)
    with engine.lock:engine.persist(task,'history-fixture-'+tid)
    return task
