"""Build frozen inputs with the repository's original planner and compiler."""
from __future__ import annotations
import json
import copy
from collections import Counter
from pathlib import Path
import random
import re
import shutil
import sys
import uuid
from .config import ROOT, UserError, safe_direction
from .state import suite_key
sys.path.insert(0, str(ROOT / 'scripts'))
import positive_prompt
import visual_directions
import logo_reference
from kie_model import geometry_report, normalize_model, MODEL
from font_library import font_references, disabled_names
from . import learning_workflow, learning_source

PLACEMENTS = json.loads((ROOT / 'config/channel-placement-rules.json').read_text())['placements']
learning_workflow.attach_rules(PLACEMENTS)
UNAVAILABLE_PLACEMENTS = [p for p in PLACEMENTS if not p.get('enabled',True)]
PLACEMENTS = [p for p in PLACEMENTS if p.get('enabled', True)]
BY_ID = {p['id']: p for p in PLACEMENTS}
ASSETS = json.loads((ROOT / 'assets/asset-manifest.json').read_text())['assets']
for fp in font_references(include_disabled=True):
    ASSETS.append({'asset_id':'font.'+fp.stem,'kind':'font','display_name':fp.stem,'path':str(fp.relative_to(ROOT)),'enabled':fp.name not in disabled_names()})
_catalog = visual_directions.load_catalog()
_workbench_styles = _catalog['workbench_styles']
_ad_finish = '以一个清楚的人物动作作为视觉焦点，次要物件适度概括。文案区域使用平整、对比清楚的色面，缩小后仍能辨认主体与文字。'
STYLES = [
    {**style, 'visual_prompt': _workbench_styles[style['id']] + _ad_finish}
    for style in _catalog['styles'] if style['id'] in _workbench_styles
]
BUILTIN_STYLE_REFERENCES=json.loads((ROOT/'config/builtin-style-references.json').read_text(encoding='utf-8'))['references']
REFERENCE_PURPOSES={'style':'画风参考','composition':'构图参考','ui':'真实 UI 截图','legacy':'画风/构图参考'}


def reference_note(ref):
    note=ref.get('note','')
    if not ref.get('points'): return note
    return '；'.join(part for part in ('、'.join(ref['points']),note) if part.strip())


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
    from .brand_logo import assets as brand_assets
    assets['logos']=brand_assets()
    return dict(placements=PLACEMENTS, unavailable_placements=UNAVAILABLE_PLACEMENTS, assets=assets)


def has_non_ip_reference(pr, placement, model):
    return bool(placement.get('learning_rule') or pr.get('font')!='none' or pr.get('references'))


def validate(pr, output, *, existing_references=()):
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
    from . import ximalaya
    ximalaya.validate(pr)
    learning_source.validate(pr,ps)
    from .learning_delivery import require_confirmed_sample
    for placement in ps:require_confirmed_sample(placement)
    if pr.get('noLogo') and any(p.get('logo_policy')=='required' and p['id'] not in ximalaya.placements(pr) for p in ps):
        raise UserError('所选版位要求使用 Logo，请选择 Logo 或移除该版位')
    from .brand_logo import normalize_id
    normalize_id(pr.get('logo_asset_id'))
    if 'channel' in pr and any(p['category']!=pr['channel'] for p in ps):
        raise UserError('所选版位不属于当前渠道，请重新选择')
    forms={p['image_form'] for p in ps}
    if len(forms)!=1:
        raise UserError('同一份文案只能选择同一种图片形式的渠道版位')
    form=next(iter(forms))
    if pr.get('image_form',form)!=form:
        raise UserError('文案形式与所选版位不一致，请重新选择版位')
    fields={'单图':[('t1','主标题'),('t2','副标题')],
            '双图':[('s1','短句 1'),('s2','短句 2')],
            '三图':[('s1','短句 1'),('s2','短句 2'),('s3','短句 3')]}[form]
    learning_fields=learning_workflow.copy_fields(ps)
    if all(p.get('learning_rule') for p in ps):fields=learning_fields
    else:fields+= [(key,label) for key,label in learning_fields if key not in {k for k,_ in fields}]
    for field in list(dict.fromkeys([k for k,_ in fields]+['cta','feature_note','feature_label','extra_heading','extra_description'])):
        if not isinstance(pr.get(field,''),str): raise UserError('文案请填写纯文本')
    for key,label in fields:
        if not pr.get(key,'').strip(): raise UserError('请填写'+label)
    if len(pr.get('cta', '')) > 12: raise UserError('按钮文字最多 12 字')
    if type(pr.get('cta_enabled',True)) is not bool: raise UserError('请选择是否添加统一按钮')
    overrides=pr.get('cta_overrides',{})
    if not isinstance(overrides,dict) or any(pid not in ids for pid in overrides): raise UserError('按钮设置只能用于所选版位')
    for pid,override in overrides.items():
        if not isinstance(override,dict) or override.get('mode') not in ('inherit','custom','none'): raise UserError('请选择有效的按钮模式')
        if override['mode']=='custom' and BY_ID[pid].get('cta_policy')!='forbidden':
            if not isinstance(override.get('text'),str) or not override['text'].strip(): raise UserError('请填写版位按钮文字')
            if len(override['text'])>12: raise UserError('按钮文字最多 12 字')
    for placement in ps:
        if placement.get('cta_policy')=='required':
            override=overrides.get(placement['id'],{'mode':'inherit'})
            text=override.get('text','') if override['mode']=='custom' else '' if override['mode']=='none' or not pr.get('cta_enabled',True) else pr.get('cta','')
            if not text.strip():raise UserError(placement['platform']+' '+placement['name']+' 要求按钮文字，请填写统一按钮或自定义文字')
    if len(pr.get('feature_note', '')) > 200: raise UserError('补充要求最多 200 字')
    if any(len(pr.get(k, '')) > 1000 for k in [k for k,_ in fields]+['feature_label','extra_heading','extra_description']): raise UserError('单条文案最多 1000 字')
    if pr.get('ip', 'random') not in ['random','none','full_random'] + [a['asset_id'] for a in ASSETS if a['kind']=='ip']:
        raise UserError('指定 IP 无效，请重新选择')
    if pr.get('font','random') not in ['random','none']+[a['asset_id'] for a in ASSETS if a['kind']=='font' and a.get('enabled',True)]:raise UserError('字体参考无效或已停用，请重新选择')
    if 'facts_version' in pr and (type(pr['facts_version']) is not int or pr['facts_version']<0):raise UserError('产品资料版本不正确，请重新引用资料')
    refs = pr.get('references', [])
    if not isinstance(refs, list) or len(refs) > 3: raise UserError('参考图最多 3 张')
    for ref in refs:
        if isinstance(ref,dict) and (not isinstance(ref.get('purpose','legacy'),str) or ref.get('purpose','legacy') not in REFERENCE_PURPOSES):raise UserError('请选择参考图用途：画风、构图或真实 UI 截图')
        if not isinstance(ref,dict) or not isinstance(ref.get('note',''),str) or len(ref.get('note',''))>200:
            raise UserError('参考图说明最多 200 字')
        points=ref.get('points',[])
        if not isinstance(points,list) or len(points)>6 or any(not isinstance(point,str) or not point.strip() or len(point)>16 for point in points):
            raise UserError('参考图要点最多 6 条，每条 1–16 字')
        if ref.get('purpose','legacy')=='legacy' and not any(old.get('id')==ref.get('id') and old.get('purpose','legacy')=='legacy' for old in existing_references):
            raise UserError('请选择参考图用途：画风、构图或真实 UI 截图')
    purposes=[ref.get('purpose','legacy') for ref in refs if ref.get('purpose','legacy')!='legacy']
    if 'style' not in purposes and pr.get('style','random') not in ['random',*(s['name'] for s in STYLES)]:
        raise UserError('指定画风已不在广告画风库，请重新选择')
    if len(purposes)!=len(set(purposes)): raise UserError('每种用途最多上传 1 张参考图')
    if len({ref.get('id') for ref in refs})!=len(refs): raise UserError('参考图重复，请移除重复图片')
    # If no visual material is selected, make_round binds an explicitly labelled
    # blank ratio canvas. It contributes neither a character nor art direction.
    direction = safe_direction(pr['direction']) if pr.get('direction') else safe_filename((pr.get('s1','') if form!='单图' else pr.get('t1') or pr.get('feature_label') or '学习机图片')[:16])
    if len(str(output / '工作区/产物/2026-10-29/APP图片' / ('APP_'+direction+'_APP图片_235959') / 'v001' / '喜马拉雅' / ('APP_'+direction+'_APP图片_方案020_图03_v001.jpg'))) > 259:
        raise UserError('完整保存路径超过 260 字符，请缩短方向名或保存位置')
    return direction


def normalize_form(pr):
    """Freeze one copy form for a batch; each placement remains an independent job."""
    value=copy.deepcopy(pr)
    form=BY_ID[value['pids'][0]]['image_form']
    active={'单图':{'t1','t2'},'双图':{'s1','s2'},'三图':{'s1','s2','s3'}}[form]
    value['image_form']=form
    from . import ximalaya
    selected=ximalaya.placements(value)
    if selected:
        value['pids']=[pid for pid in value['pids'] if pid not in selected]+list(selected)
    for key in ('t1','t2','s1','s2','s3'):
        value[key]=value.get(key,'') if key in active else ''
    return value


def safe_filename(value):
    value=re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]','_',str(value)).strip(' .')[:30] or '未命名'
    try: return safe_direction(value)
    except UserError: return 'APP_'+value[:26]


def copy_signature(pr):
    import hashlib
    keys=['channel','image_form','t1','t2','s1','s2','s3','cta','feature_label','extra_heading','extra_description','feature_note','ip','style','font','noLogo','logo_asset_id','facts_version','product_facts','image_model','canvas_protocol']
    value={k:pr.get(k) or '' for k in keys}
    if pr.get('ximalaya_suite'):
        from . import ximalaya
        value['ximalaya_suite']=True
        selected=ximalaya.placements(pr)
        if selected!=ximalaya.PLACEMENTS:value['ximalaya_placements']=selected
    value['learning_mode']=pr.get('learning_mode','generate')
    if learning_source.uploaded(pr):
        source=pr.get('learning_source') or {}
        value['learning_source']={k:source.get(k) for k in ('id','layout_id','layout_confirmed','copy_snapshot','original_logo_asset_id')}
    value['image_model']=pr.get('image_model',MODEL)
    value['ip']=pr.get('ip') or 'random';value['style']=pr.get('style') or 'random';value['noLogo']=bool(pr.get('noLogo'))
    value['font']=pr.get('font') or 'random'
    value['cta_enabled']=pr.get('cta_enabled',True)
    value['cta_overrides']=pr.get('cta_overrides',{})
    value['references']=[{'id':x.get('id'),'note':x.get('note'),'purpose':x.get('purpose','legacy'),**({'points':x['points']} if x.get('points') else {})} for x in pr.get('references',[])]
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def requested_pairs(pr):
    counts=pr.get('variants_by_placement',{})
    return [(pid,n) for pid in pr['pids'] for n in range(1,counts.get(pid,pr['sets'])+1)]


def suite_metadata(metadata, pid, number):
    key=suite_key(pid, number)
    if key in metadata:
        return metadata[key]
    return metadata[str(number)]  # Historical rounds shared an assignment by suite number.


def ip_role(asset_id):
    return asset_id.split('.')[1] if asset_id else ''


def make_round(pr,task_id,cache,concurrency,simulation,*,defer_planning=False,assignments=None,pairs=None,round_id=None,placements_override=None,brand_logo_templates=None):
    from . import ximalaya
    pr=learning_source.freeze(pr,cache)
    ximalaya_pids=ximalaya.placements(pr)
    ximalaya_root=ximalaya_pids[0] if ximalaya_pids else None
    from_upload=learning_source.uploaded(pr)
    image_model=normalize_model(pr.get('image_model',MODEL))
    plans=pr.get('visual_concepts')
    if not defer_planning and not plans and not from_upload:
        raise UserError('请先按原 Skill 完成画面方案与画面规划')
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    rid=round_id or uuid.uuid4().hex
    pairs=pairs or requested_pairs(pr)
    if ximalaya_pids:
        pairs=[pair for pair in pairs if pair[0] not in ximalaya_pids]+sorted(
            (pair for pair in pairs if pair[0] in ximalaya_pids),key=lambda pair:(pair[1],ximalaya_pids.index(pair[0])))
    metadata=copy.deepcopy(assignments or {})
    reference=next((x for x in pr.get('references',[]) if x.get('purpose')=='style'),None)
    style_choice=pr.get('style','random')
    ip_choice=pr.get('ip','random')
    if from_upload:ip_choice='none'
    style_source='random' if style_choice=='random' else 'specified'
    styles=[s for s in STYLES if ip_choice=='none' or s.get('supports_ip')]
    if from_upload:
        styles=[{'id':'reference','name':'上传母图','prompt':'严格沿用上传母图的原有人物、动作、场景、画风、配色、字形、材质与光影，仅调整尺寸和目标模块。'}]
        style_source='reference'
    elif reference is not None:
        note=reference_note(reference).strip()
        styles=[{'id':'reference','name':'参考风格图','prompt':'沿用参考风格图的配色、笔触、材质和光影'+('；'+note if note else '')}]
        style_source='reference'
    elif style_choice!='random':
        styles=[s for s in styles if s['name']==style_choice]
    elif style_choice=='random':
        styles += [{'id':ref['id'],'name':ref['name'],'prompt':'沿用参考风格图的配色、笔触、材质和光影；'+'、'.join(ref['points'])+'。'+_ad_finish,
                    'supports_ip':True,'builtin_reference':ref} for ref in BUILTIN_STYLE_REFERENCES]
    style_usage=Counter(meta.get('style_choice_id',meta['style_id']) for meta in metadata.values())
    style_rng=random.Random(rid+':placement-styles')
    ip_assets={a['asset_id']:a for a in ASSETS if a['kind']=='ip'}
    ip_pool={}
    for asset_id,asset in ip_assets.items():
        if asset.get('enabled',True):
            ip_pool.setdefault(ip_role(asset_id),[]).append(asset)
    ip_usage=Counter(ip_role(meta.get('ip_id')) for meta in metadata.values())
    ip_rng=random.Random(rid+':placement-ips')
    fonts=[a for a in ASSETS if a['kind']=='font' and a.get('enabled',True)]
    for pid,n in pairs:
        key=suite_key(pid,n)
        if key in metadata or str(n) in metadata: continue
        if pid in ximalaya_pids and pid!=ximalaya_root:
            metadata[key]=copy.deepcopy(metadata[suite_key(ximalaya_root,n)])
            continue
        if (placements_override or BY_ID)[pid].get('learning_rule'):
            shared=next((m for k,m in metadata.items() if k.endswith('::'+str(n)) and k.split('::')[0] in learning_workflow.RULES),None)
            if shared is not None:
                metadata[key]=copy.deepcopy(shared);continue
        if not styles: raise UserError('当前画风已不在广告画风库，请修改配置后生成')
        least_used=min(style_usage[s['id']] for s in styles)
        style=style_rng.choice([s for s in styles if style_usage[s['id']]==least_used])
        style_usage[style['id']]+=1
        builtin=style.get('builtin_reference')
        rng=random.Random(rid+':'+str(n))
        ip=ip_assets.get(ip_choice)
        if ip_choice in ('random','full_random'):
            roles=list(ip_pool)
            if ip_choice=='full_random':
                roles.append('')
            if not roles: raise UserError('没有可用的 IP 素材，请检查配置')
            least_used_ip=min(ip_usage[role] for role in roles)
            role=ip_rng.choice([role for role in roles if ip_usage[role]==least_used_ip])
            ip_usage[role]+=1
            ip=ip_rng.choice(ip_pool[role]) if role else None
        if builtin:
            builtin=copy.deepcopy(builtin)
            source=ROOT/builtin['path']
            if not source.is_file(): raise UserError('内置风格参考图缺失，请恢复项目素材')
            target=cache/'style-references'/(builtin['id']+source.suffix)
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():shutil.copy2(source,target)
            builtin['path']=str(target)
        font=None if from_upload or builtin or pr.get('font')=='none' else (rng.choice(fonts) if pr.get('font','random')=='random' else next(a for a in ASSETS if a['kind']=='font' and a['asset_id']==pr['font']))
        effective_style_id=style['id']
        metadata[key]={'ip_id':ip['asset_id'] if ip else '', 'ip_name':(ip.get('asset_name_zh') or ip['display_name']) if ip else '',
            'style_id':effective_style_id,'style':{'id':effective_style_id,'name':style['name'],'description':style.get('visual_prompt',style['prompt'])},
            'font_path':str((ROOT/font['path']).resolve()) if font else '',
            'style_source':'builtin_reference' if builtin else style_source,
            **({'style_choice_id':style['id'],'style_reference':copy.deepcopy(builtin)} if builtin else {})}
    slots=[];configs=[]
    for pid,n in pairs:
        p=copy.deepcopy((placements_override or BY_ID)[pid]);meta=suite_metadata(metadata,pid,n)
        if brand_logo_templates and pid in brand_logo_templates['templates']:
            p['brand_logo_template']=copy.deepcopy(brand_logo_templates['templates'][pid])
        from .learning_delivery import require_confirmed_sample
        sample_path=require_confirmed_sample(p)
        if sample_path:
            sample_target=cache/'samples'/(p['id']+'.png');sample_target.parent.mkdir(parents=True,exist_ok=True)
            if sample_target.resolve()!=sample_path.resolve():shutil.copy2(sample_path,sample_target)
            p['sample_reference']['path']=str(sample_target)

        if p.get('delivery_assets'):
            from .learning_delivery import checked_asset
            import hashlib
            for record in p['delivery_assets'].values():
                original=checked_asset(record);target=cache/'delivery-assets'/(record['sha256']+original.suffix)
                target.parent.mkdir(parents=True,exist_ok=True)
                if not target.exists():shutil.copy2(original,target)
                record['path']=str(target)

        cta=pr.get('cta','') if pr.get('cta_enabled',True) else ''
        override=pr.get('cta_overrides',{}).get(pid,{'mode':'inherit'})
        if override['mode']!='inherit':cta=override['text'] if override['mode']=='custom' else ''
        if p.get('cta_policy')=='forbidden':cta=''
        if p.get('cta_policy')=='required' and not cta.strip():raise UserError(p['platform']+' '+p['name']+' 要求按钮文字')
        from .brand_logo import freeze as freeze_logo
        brand_layer=None
        canvas=None
        if not p.get('learning_rule'):
            from .natural_canvas import plan as canvas_plan,PROTOCOL
            canvas=canvas_plan(p,image_model)
            forced_logo=pid in ximalaya_pids and p.get('logo_policy')=='required'
            if forced_logo and (template:=p.get('brand_logo_template')):
                from .brand_logo import default_template
                template.update(x=(1-template['width'])/2,y=min(template['y'],default_template(p)['y']))
            brand_layer=freeze_logo(p,None if pid in ximalaya_pids else pr.get('logo_asset_id'),cache,
                                   enabled=forced_logo or not pr.get('noLogo') and p.get('logo_policy')!='forbidden',
                                   generation_crop=canvas['group']['targets'][0]['crop_box'])
        logo_asset=next(a for a in ASSETS if a['asset_id']==(pr.get('logo_asset_id') or 'logo.onion.standard.001') and a['kind']=='logo') if brand_layer is None else None
        logo='不用' if brand_layer is not None or pr.get('noLogo') or p.get('logo_policy')=='forbidden' else logo_asset['display_name']
        cfg=dict(request_id=task_id+'-'+pid+'-'+str(n),placements=[p],sets=1,
            image_model=image_model,prompt_format=positive_prompt.FORMAT,prompt_layout="poster_sections_v1",visual_contract_version=positive_prompt.VISUAL_CONTRACT_VERSION,
            copy_refs=[dict(copyDraftId='approved',mainTitle=pr.get('t1',''),subtitle=pr.get('t2',''),**{'short'+str(i):pr.get('s'+str(i),'') for i in range(1,4)})],
            cta=cta,cta_render_mode='button',logo=logo,logo_asset_id=logo_asset['asset_id'] if logo!='不用' else '',
            ip_asset_id=meta['ip_id'],font_reference_enabled=bool(meta['font_path']),screen_ui_mode='reference' if any(x.get('purpose')=='ui' for x in pr.get('references',[])) else 'conceptual',
            visual_style_mode='coordinated',visual_direction={'style_id':meta['style_id']},
            art_direction_required=True,learner_story_required=True,visual_concepts=[])
        if brand_layer is not None:cfg['brand_logo_layer']=copy.deepcopy(brand_layer)
        if pid in ximalaya_pids and pid!=ximalaya_root:
            cfg.update(ximalaya_variant=True,font_reference_enabled=False)
        if canvas:
            cfg['natural_canvas_plan']=canvas
            pr['canvas_protocol']=PROTOCOL
        learning_workflow.configure_copy(cfg,pr,p)
        if meta['style_source'] in ('reference','builtin_reference'):
            cfg['visual_direction']['style_prompt']=meta['style']['description']
            cfg['visual_direction']['style_name']=meta['style']['name']
        else:
            cfg['visual_direction']['style_description']=meta['style']['description']
        if p['image_count'] > 1:
            cfg['prompt_context_version']='per_image_v1'
        ci=len(configs);configs.append({'pid':pid,'set':n,'config':cfg})
        head=uuid.uuid4().hex
        for idx in range(1,p['image_count']+1):
            sid=head if idx==1 else uuid.uuid4().hex
            if idx==1:
                refs=[]
                if cfg['logo']!='不用': refs.append(logo_reference.build_logo_reference(cfg))
                if meta['ip_id']: refs.append({'asset_id':meta['ip_id'],'path':next(a['path'] for a in ASSETS if a['asset_id']==meta['ip_id']),'role':'角色 IP'})
                if cfg['font_reference_enabled']:refs.append({'path':meta['font_path'],'role':'标题字体参考'})
                if meta.get('style_reference'):
                    ref=meta['style_reference']
                    refs.append({'path':str(ROOT/ref['path']),'purpose':'style','builtin_style':True,
                                 'role':'内置画风参考：'+'、'.join(ref['points'])+'；仅参考画风、色彩、材质与光线，不复制图中人物、品牌标识、界面、文字、字形和排版'})
                if not from_upload:refs.extend({'path':x['path'],'purpose':x.get('purpose','legacy'),'role':REFERENCE_PURPOSES[x.get('purpose','legacy')]+('：'+reference_note(x) if reference_note(x).strip() else '')} for x in pr.get('references',[]))
                if p.get('learning_rule'):
                    refs.append({'path':p['sample_reference']['path'],'purpose':'layout_sample','role':'已确认版位样图：仅参考人物与文字区域的相对位置、留白、主体占比和模块排布。样图旧文案由本张确认文字替换；人物、场景、配色和画风沿用本套首模板，不照搬样图的旧创意。'})
                for j,ref in enumerate(refs,1): ref['label']='参考图'+str(j)
                if not refs:
                    from .brand_logo import neutral_canvas
                    refs.append(neutral_canvas(cache,sid,p,image_model))
            else: refs=[{'label':'参考图1','path':str(cache/(head+'-v1.png')),'role':'图 1 完整广告成图'}]
            slots.append(dict(id=sid,pid=pid,set=n,idx=idx,state='queued',att=1,prompt='',orig='',refs=refs,up={},output=str(cache/(sid+'-v1.png')),
                first_id=head,config_idx=ci,versions=[],reason_code=None,plan_ready=False))
            if brand_layer is not None:slots[-1]['brand_logo_layer']=copy.deepcopy(brand_layer)
            if cfg.get('natural_canvas_plan'):slots[-1]['natural_canvas_plan']=copy.deepcopy(cfg['natural_canvas_plan'])
    r=dict(id=rid,created_at=__import__("time").time(),paused=False,image_model=image_model,image_resolution="1K",params=copy.deepcopy(pr),slots=slots,configs=configs,sel={},adopted_versions={},stopped=False,
        concurrency=concurrency,simulation=simulation,set_metadata=metadata,planning_source='codex_skill',planning_status='queued',
        planning_targets=[pid+'::'+str(n) for pid,n in pairs],stop_marker=str(cache/'STOP'),copy_signature=copy_signature(pr))
    learning_workflow.bind(r)
    ximalaya.bind(r)
    if brand_logo_templates is not None:r['brand_logo_templates']=copy.deepcopy(brand_logo_templates)
    if any(s.get('natural_canvas_plan') for s in slots):r['natural_canvas_version']=1
    from .scene_planner import rules_text
    rules_path=cache/'skill-rules.txt'
    if not rules_path.exists(): rules_path.write_text(rules_text(),encoding='utf-8')
    r['skill_rules_path']=str(rules_path)
    if from_upload:
        compile_plans(r,{'plans':[],'_provenance':{'provider':'uploaded_master','source_sha256':pr['learning_source']['id']}})
    elif not defer_planning:
        if isinstance(plans,list): plans={'plans':[{'placement_id':pid,'set_number':n,'concept':plans[n-1]} for pid,n in pairs if pid+'::'+str(n) in r['planning_targets']]}
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
        concept=learning_workflow.concept_for(r,entry,indexed)
        if concept is None:
            if key in targets:raise UserError('画面方案格式不正确')
            continue
        concept=copy.deepcopy(concept);meta=suite_metadata(r['set_metadata'],entry['pid'],entry['set'])
        if not isinstance(concept,dict) or concept.get('style_id')!=meta['style_id']: raise UserError('画面方案改变了已分配画风')
        concept['ip_asset_id']=meta['ip_id'];concept['font_reference_path']=meta['font_path']
        cfg=copy.deepcopy(entry['config']);cfg['visual_concepts']=[concept]
        try: direction=visual_directions.plan_directions(cfg)['directions'][0]
        except (ValueError,KeyError,TypeError): raise UserError('画面方案缺少人物故事、艺术定调或逐张动作')
        group=[s for s in r['slots'] if s['pid']==entry['pid'] and s['set']==entry['set']]
        prompts=[]
        extra=r['params'].get('feature_note','')
        first=next(s for s in group if s['idx']==1)
        notes=[ref['label']+'用于'+REFERENCE_PURPOSES.get(x.get('purpose','legacy'),'画风参考')+('，'+reference_note(x) if reference_note(x).strip() else '') for ref,x in zip([a for a in first['refs'] if not a.get('builtin_style') and (a.get('purpose') in REFERENCE_PURPOSES or a.get('role','').startswith('风格/构图'))],r['params'].get('references',[]))]
        scoped=cfg.get('prompt_context_version')=='per_image_v1'
        direction['base_prompt_rule']=positive_prompt.paragraph(direction['base_prompt_rule'],'' if scoped else extra,*notes)
        direction['branch_prompt_rule']=positive_prompt.paragraph(direction['branch_prompt_rule'],'' if scoped else extra)
        for s in group:
            prompt_direction=direction
            prompt=('本机适配：从已确认母版缩放，按目标版位应用圆角和交付规格；不调用图片模型。' if s.get('production_mode')=='local_resize' else positive_prompt.compose(cfg,prompt_direction,s['idx'],s['refs']))
            prompts.append((s,prompt))
        pending.append((entry,cfg,direction,concept,prompts))
    if apply:
        for entry,cfg,direction,concept,prompts in pending:
            entry.update(config=cfg,direction=direction,concept=concept)
            for s,prompt in prompts: s.update(prompt=prompt,orig=prompt,plan_ready=True,prompt_origin='local' if s.get('production_mode')=='local_resize' else 'system')
        r.update(planning_status='done',planning_error='',planning_provenance=result.get('_provenance',{}))
    return result
