"""Create a reviewable new round from frozen scenes, with no new planning call."""
import copy
from pathlib import Path
import uuid
from .config import UserError
from .planning import make_round,compile_plans


def rebrief(t,source,concurrency):
    if source.get('planning_status')!='done' or any(s['state'] in ('queued','generating') for s in source['slots']):
        raise UserError('请等本轮任务结束后再改写重出')
    rid=uuid.uuid4().hex
    cache=Path(t['output_dir'])/'.cache'/t['id']/rid
    r=make_round(source['params'],t['id'],cache,concurrency,source['simulation'],defer_planning=True,
                 assignments=copy.deepcopy(source['set_metadata']),
                 pairs=[(e['pid'],e['set']) for e in source['configs']],round_id=rid,placements_override={e['pid']:e['config']['placements'][0] for e in source['configs']})
    rows=[]
    for entry in source['configs']:
        concept=copy.deepcopy(entry.get('concept'))
        if not concept: raise UserError('原轮次缺少已保存的画面方案')
        if r['params']['image_form']!='单图' and not concept.get('common_visual'):
            art=concept.get('art_direction') or {}
            concept['common_visual']='。'.join(art[k] for k in ('world','scene','lighting_materials') if art.get(k))
        rows.append({'placement_id':entry['pid'],'set_number':entry['set'],'concept':concept})
    compile_plans(r,{'plans':rows,'_provenance':{'provider':'frozen_plan_rebrief','source_round':source['id']}})
    # Keep the exact original asset list, order, and labels, including user references.
    for s in r['slots']:
        old=next(x for x in source['slots'] if (x['pid'],x['set'],x['idx'])==(s['pid'],s['set'],s['idx']))
        if s['idx']==1:
            s['refs']=copy.deepcopy(old['refs']);s['frame']=copy.deepcopy(old.get('frame'))
        else:
            s['frame']=copy.deepcopy(old.get('frame'))
        entry=r['configs'][s['config_idx']]
        from positive_prompt import compose
        label=(s['refs'][-1]['label'] if s['idx']==1 else s['refs'][0]['label']) if s.get('frame') else None
        s['prompt']=s['orig']=compose(entry['config'],entry['direction'],s['idx'],s['refs'],label)
        s['prompt_origin']='system'
    r['reformatted_from']=source['id']
    return r
