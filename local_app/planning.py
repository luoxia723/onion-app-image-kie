"""Build frozen inputs with the repository's original planner and compiler."""
from __future__ import annotations
import json
import copy
from pathlib import Path
import random
import re
import sys
import uuid
from .config import ROOT, UserError, safe_direction
sys.path.insert(0, str(ROOT / 'scripts'))
import positive_prompt
import visual_directions
import logo_reference
import blue_frame
from kie_model import geometry_report, normalize_model, MODEL
from font_library import font_references, disabled_names

PLACEMENTS = json.loads((ROOT / 'config/channel-placement-rules.json').read_text())['placements']
PLACEMENTS = [p for p in PLACEMENTS if p.get('enabled', True)]
BY_ID = {p['id']: p for p in PLACEMENTS}
ASSETS = json.loads((ROOT / 'assets/asset-manifest.json').read_text())['assets']
for fp in font_references(include_disabled=True):
    ASSETS.append({'asset_id':'font.'+fp.stem,'kind':'font','display_name':fp.stem,'path':str(fp.relative_to(ROOT)),'enabled':fp.name not in disabled_names()})
STYLES = visual_directions.load_catalog()['styles']
REFERENCE_PURPOSES={'style':'画风参考','composition':'构图参考','ui':'真实 UI 截图','legacy':'画风/构图参考'}


def bootstrap():
    assets = {'ips': [], 'logos': [], 'fonts': [], 'styles': STYLES}
    for a in ASSETS:
        if not a.get('enabled',True): continue
        group = {'ip': 'ips', 'logo': 'logos', 'font': 'fonts'}.get(a['kind'])
        if group:
            item=dict(id=a['asset_id'], label=a.get('asset_name_zh') or a['display_name'],
                thumb='/api/assets/' + a['asset_id'])
            if group=='ips': item.update(stage=a.get('stage'),variant=a.get('variant'))
            assets[group].append(item)
    return dict(placements=PLACEMENTS, assets=assets)


def validate(pr, output):
    if not isinstance(pr, dict): raise UserError('请填写任务参数')
    if not isinstance(pr.get('product_facts',''),str) or len(pr.get('product_facts',''))>20000: raise UserError('产品资料限 20000 字，请填写已确认的信息')
    ids = pr.get('pids', [])
    if not isinstance(ids, list) or not ids or any(pid not in BY_ID for pid in ids): raise UserError('请选择有效的渠道版位')
    if len(ids) != len(set(ids)): raise UserError('渠道版位重复，请重新选择')
    try: normalize_model(pr.get('image_model',MODEL))
    except ValueError: raise UserError('请选择支持的图片模型')
    n = pr.get('sets')
    if type(n) is not int or not 1 <= n <= 20: raise UserError('套数请填写 1–20 的整数')
    counts=pr.get('variants_by_placement',{})
    if not isinstance(counts,dict) or any(pid not in ids or type(n) is not int or not 1<=n<=20 for pid,n in counts.items()):
        raise UserError('各版位套数请填写 1–20 的整数')
    ps = [BY_ID[i] for i in ids]
    forms={p['image_form'] for p in ps}
    if len(forms)!=1:
        raise UserError('同一份文案只能选择同一种图片形式的渠道版位')
    form=next(iter(forms))
    if pr.get('image_form',form)!=form:
        raise UserError('文案形式与所选版位不一致，请重新选择版位')
    fields={'单图':[('t1','主标题'),('t2','副标题')],
            '双图':[('s1','短句 1'),('s2','短句 2')],
            '三图':[('s1','短句 1'),('s2','短句 2'),('s3','短句 3')]}[form]
    for field in [k for k,_ in fields]+['cta','feature_note']:
        if not isinstance(pr.get(field,''),str): raise UserError('文案请填写纯文本')
    for key,label in fields:
        if not pr.get(key,'').strip(): raise UserError('请填写'+label)
    if len(pr.get('cta', '')) > 12: raise UserError('按钮文字最多 12 字')
    if len(pr.get('feature_note', '')) > 200: raise UserError('补充要求最多 200 字')
    if any(len(pr.get(k, '')) > 1000 for k,_ in fields): raise UserError('单条文案最多 1000 字')
    if pr.get('noLogo') and any(p.get('logo_policy') == 'required' or (p['platform']=='喜马拉雅' and p['target_width']==720 and p['target_height'] in (1280,1559)) for p in ps):
        raise UserError('所选喜马拉雅版位必须带 Logo，请取消「不用 Logo」')
    if pr.get('ip', 'random') not in ['random','none','full_random'] + [a['asset_id'] for a in ASSETS if a['kind']=='ip']:
        raise UserError('指定 IP 无效，请重新选择')
    if pr.get('style', 'random') not in ['random'] + [s['name'] for s in STYLES]: raise UserError('指定画风无效，请重新选择')
    if pr.get('font','random') not in ['random','none']+[a['asset_id'] for a in ASSETS if a['kind']=='font' and a.get('enabled',True)]:raise UserError('字体参考无效或已停用，请重新选择')
    if 'facts_version' in pr and (type(pr['facts_version']) is not int or pr['facts_version']<0):raise UserError('产品资料版本不正确，请重新引用资料')
    refs = pr.get('references', [])
    if not isinstance(refs, list) or len(refs) > 3: raise UserError('参考图最多 3 张')
    for ref in refs:
        if isinstance(ref,dict) and (not isinstance(ref.get('purpose','legacy'),str) or ref.get('purpose','legacy') not in REFERENCE_PURPOSES):raise UserError('请选择参考图用途：画风、构图或真实 UI 截图')
        if not isinstance(ref,dict) or not isinstance(ref.get('note'),str) or not 1<=len(ref['note'].strip())<=200:
            raise UserError('请填写参考图的风格或构图用途，限 1–200 字')
        if re.fullmatch(r'(参考图|图片|截图)[A-Za-z0-9一二三 ]*',ref['note'].strip()):
            raise UserError('请说明参考图的具体风格或构图用途')
    if len({ref.get('id') for ref in refs})!=len(refs): raise UserError('参考图重复，请移除重复图片')
    if pr.get('font')=='none' and pr.get('ip') in ('none','full_random') and pr.get('noLogo') and not refs:
        model=normalize_model(pr.get('image_model',MODEL))
        if any(not geometry_report(p['target_width'],p['target_height'],model=model)['needs_safe_area'] for p in ps):
            raise UserError('当前模型需要参考图，请至少保留 Logo、IP、字体参考中的一项，或上传参考图')
    direction = safe_direction(pr['direction']) if pr.get('direction') else safe_filename((pr.get('s1') if form!='单图' else pr.get('t1'))[:16])
    if len(str(output / '工作区/产物/2026-10-29/APP图片' / ('APP_'+direction+'_APP图片_235959') / 'v001' / '喜马拉雅' / ('APP_'+direction+'_APP图片_方案020_图03_v001.jpg'))) > 259:
        raise UserError('完整保存路径超过 260 字符，请缩短方向名或保存位置')
    return direction


def normalize_form(pr):
    """Freeze one copy form for a batch; each placement remains an independent job."""
    value=copy.deepcopy(pr)
    form=BY_ID[value['pids'][0]]['image_form']
    active={'单图':{'t1','t2'},'双图':{'s1','s2'},'三图':{'s1','s2','s3'}}[form]
    value['image_form']=form
    for key in ('t1','t2','s1','s2','s3'):
        value[key]=value.get(key,'') if key in active else ''
    return value


def safe_filename(value):
    value=re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]','_',str(value)).strip(' .')[:30] or '未命名'
    try: return safe_direction(value)
    except UserError: return 'APP_'+value[:26]


def copy_signature(pr):
    import hashlib
    keys=['image_form','t1','t2','s1','s2','s3','cta','feature_note','ip','style','font','noLogo','facts_version','product_facts','image_model']
    value={k:pr.get(k) or '' for k in keys}
    value['image_model']=pr.get('image_model',MODEL)
    value['ip']=pr.get('ip') or 'random';value['style']=pr.get('style') or 'random';value['noLogo']=bool(pr.get('noLogo'))
    value['font']=pr.get('font') or 'random'
    value['references']=[{'id':x.get('id'),'note':x.get('note'),'purpose':x.get('purpose','legacy')} for x in pr.get('references',[])]
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def requested_pairs(pr):
    counts=pr.get('variants_by_placement',{})
    return [(pid,n) for pid in pr['pids'] for n in range(1,counts.get(pid,pr['sets'])+1)]


def make_round(pr,task_id,cache,concurrency,simulation,*,defer_planning=False,assignments=None,pairs=None,round_id=None,placements_override=None):
    image_model=normalize_model(pr.get('image_model',MODEL))
    plans=pr.get('visual_concepts')
    if not defer_planning and not plans:
        raise UserError('请先按原 Skill 完成画面方案与画面规划')
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    rid=round_id or uuid.uuid4().hex
    pairs=pairs or requested_pairs(pr)
    metadata=copy.deepcopy(assignments or {})
    count=max(n for _,n in pairs)
    style_cfg={'request_id':rid,'sets':count,'copy_refs':[{}],'prompt_format':positive_prompt.FORMAT,
               'ip_random':pr.get('ip','random')=='random','ip_asset_id':pr.get('ip') if pr.get('ip') not in ('random','none','full_random') else ''}
    if pr.get('style','random')!='random':
        style_cfg['visual_direction']={'style_id':next(s['id'] for s in STYLES if s['name']==pr['style'])}
    styles=visual_directions.assign_styles(style_cfg)['directions']
    ips=[a for a in ASSETS if a['kind']=='ip' and '.standard.' in a['asset_id']]
    fonts=[a for a in ASSETS if a['kind']=='font' and a.get('enabled',True)]
    for n in range(1,count+1):
        if str(n) in metadata: continue
        rng=random.Random(rid+':'+str(n))
        ip=rng.choice(ips) if pr.get('ip','random')=='random' else next((a for a in ASSETS if a['asset_id']==pr.get('ip')),None)
        style=next(s for s in STYLES if s['id']==styles[n-1]['style_id'])
        font=None if pr.get('font')=='none' else (rng.choice(fonts) if pr.get('font','random')=='random' else next(a for a in ASSETS if a['kind']=='font' and a['asset_id']==pr['font']))
        metadata[str(n)]={'ip_id':ip['asset_id'] if ip else '', 'ip_name':(ip.get('asset_name_zh') or ip['display_name']) if ip else '',
            'style_id':style['id'],'style':{'id':style['id'],'name':style['name'],'description':style.get('visual_prompt',style['prompt'])},
            'font_path':str((ROOT/font['path']).resolve()) if font else '',
            'style_source':'random' if pr.get('style','random')=='random' else 'specified'}
    slots=[];configs=[]
    for pid,n in pairs:
        p=copy.deepcopy((placements_override or BY_ID)[pid]);meta=metadata[str(n)]
        cfg=dict(request_id=task_id+'-'+pid+'-'+str(n),placements=[p],sets=1,
            image_model=image_model,prompt_format=positive_prompt.FORMAT,prompt_layout="poster_sections_v1",visual_contract_version=positive_prompt.VISUAL_CONTRACT_VERSION,
            copy_refs=[dict(copyDraftId='approved',mainTitle=pr.get('t1',''),subtitle=pr.get('t2',''),**{'short'+str(i):pr.get('s'+str(i),'') for i in range(1,4)})],
            cta=pr.get('cta',''),cta_render_mode='button',logo='不用' if pr.get('noLogo') else '洋葱学园',
            ip_asset_id=meta['ip_id'],font_reference_enabled=bool(meta['font_path']),screen_ui_mode='reference' if any(x.get('purpose')=='ui' for x in pr.get('references',[])) else 'conceptual',
            visual_style_mode='coordinated',visual_direction={'style_id':meta['style_id']},
            art_direction_required=True,learner_story_required=True,visual_concepts=[])
        if p['image_count'] > 1:
            cfg['prompt_context_version']='per_image_v1'
        ci=len(configs);configs.append({'pid':pid,'set':n,'config':cfg})
        head=uuid.uuid4().hex
        frame=None
        for idx in range(1,p['image_count']+1):
            sid=head if idx==1 else uuid.uuid4().hex
            if idx==1:
                refs=[]
                if not pr.get('noLogo'): refs.append(logo_reference.build_logo_reference(cfg))
                if meta['ip_id']: refs.append({'asset_id':meta['ip_id'],'path':next(a['path'] for a in ASSETS if a['asset_id']==meta['ip_id']),'role':'角色 IP'})
                if meta['font_path']:refs.append({'path':meta['font_path'],'role':'标题字体参考'})
                refs.extend({'path':x['path'],'purpose':x.get('purpose','legacy'),'role':REFERENCE_PURPOSES[x.get('purpose','legacy')]+'：'+x['note']} for x in pr.get('references',[]))
                for j,ref in enumerate(refs,1): ref['label']='参考图'+str(j)
                if geometry_report(p['target_width'],p['target_height'],model=image_model)['needs_safe_area']:
                    frame=blue_frame.prepare_layout(p['target_width'],p['target_height'],cache/(sid+'-frame'),label='参考图'+str(len(refs)+1),model=image_model)
                    refs.append(frame['reference'])
            else: refs=[{'label':'参考图1','path':str(cache/(head+'-v1.png')),'role':'图 1 完整广告成图'}]
            slots.append(dict(id=sid,pid=pid,set=n,idx=idx,state='queued',att=1,prompt='',orig='',refs=refs,up={},output=str(cache/(sid+'-v1.png')),
                first_id=head,config_idx=ci,frame=frame,versions=[],reason_code=None,plan_ready=False))
    r=dict(id=rid,created_at=__import__("time").time(),paused=False,image_model=image_model,image_resolution="1K",params=copy.deepcopy(pr),slots=slots,configs=configs,sel={},adopted_versions={},stopped=False,
        concurrency=concurrency,simulation=simulation,set_metadata=metadata,planning_source='codex_skill',planning_status='queued',
        planning_targets=[pid+'::'+str(n) for pid,n in pairs],stop_marker=str(cache/'STOP'),copy_signature=copy_signature(pr))
    from .scene_planner import rules_text
    rules_path=cache/'skill-rules.txt'
    if not rules_path.exists(): rules_path.write_text(rules_text(),encoding='utf-8')
    r['skill_rules_path']=str(rules_path)
    if not defer_planning:
        if isinstance(plans,list): plans={'plans':[{'placement_id':pid,'set_number':n,'concept':plans[n-1]} for pid,n in pairs]}
        compile_plans(r,plans)
    return r


def compile_plans(r,result,*,apply=True):
    values=result.get('plans')
    if not isinstance(values,list): raise UserError('画面方案格式不正确')
    indexed={}
    for row in values:
        key=str(row.get('placement_id'))+'::'+str(row.get('set_number'))
        if key in indexed: raise UserError('画面方案包含重复套图')
        indexed[key]=row.get('concept')
    targets=set(r['planning_targets'])
    if set(indexed)!=targets: raise UserError('画面方案与本次版位、套号不匹配')
    pending=[]
    for entry in r['configs']:
        key=entry['pid']+'::'+str(entry['set'])
        if key not in targets: continue
        concept=copy.deepcopy(indexed[key]);meta=r['set_metadata'][str(entry['set'])]
        if not isinstance(concept,dict) or concept.get('style_id')!=meta['style_id']: raise UserError('画面方案改变了已分配画风')
        concept['ip_asset_id']=meta['ip_id'];concept['font_reference_path']=meta['font_path']
        cfg=copy.deepcopy(entry['config']);cfg['visual_concepts']=[concept]
        try: direction=visual_directions.plan_directions(cfg)['directions'][0]
        except (ValueError,KeyError,TypeError): raise UserError('画面方案缺少人物故事、艺术定调或逐张动作')
        group=[s for s in r['slots'] if s['pid']==entry['pid'] and s['set']==entry['set']]
        prompts=[]
        extra=r['params'].get('feature_note','')
        first=next(s for s in group if s['idx']==1)
        notes=[ref['label']+'用于'+REFERENCE_PURPOSES.get(x.get('purpose','legacy'),'画风参考')+'，'+x['note'] for ref,x in zip([a for a in first['refs'] if a.get('purpose') in REFERENCE_PURPOSES or a.get('role','').startswith('风格/构图')],r['params'].get('references',[]))]
        scoped=cfg.get('prompt_context_version')=='per_image_v1'
        direction['base_prompt_rule']=positive_prompt.paragraph(direction['base_prompt_rule'],'' if scoped else extra,*notes)
        direction['branch_prompt_rule']=positive_prompt.paragraph(direction['branch_prompt_rule'],'' if scoped else extra)
        for s in group:
            prompt_direction=direction
            label=(s['refs'][-1]['label'] if s['idx']==1 else '参考图1') if s.get('frame') else None
            prompt=positive_prompt.compose(cfg,prompt_direction,s['idx'],s['refs'],label)
            prompts.append((s,prompt))
        pending.append((entry,cfg,direction,concept,prompts))
    if apply:
        for entry,cfg,direction,concept,prompts in pending:
            entry.update(config=cfg,direction=direction,concept=concept)
            for s,prompt in prompts: s.update(prompt=prompt,orig=prompt,plan_ready=True,prompt_origin='system')
        r.update(planning_status='done',planning_error='',planning_provenance=result.get('_provenance',{}))
    return result
