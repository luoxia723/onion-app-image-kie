"""Freeze a learning run and bind its local assets without invoking providers."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import shutil

from .config import ROOT,UserError


def _sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _copy_checked(source,target,expected=None):
    source,target=Path(source),Path(target)
    if not source.is_file():raise UserError('本套参考素材缺失，请重新配置')
    before=_sha(source)
    if expected and before!=expected:raise UserError('本套参考素材校验失败')
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
    if _sha(target)!=before:raise UserError('冻结参考素材失败，请重试')
    return before


def _key(binding):
    if binding.get('reference_id'):return 'reference:'+binding['reference_id']
    if binding.get('asset_id'):return 'asset:'+binding['asset_id']
    raise UserError('参考素材缺少登记标识')


def _source_plan(engine,params,source):
    """Recompile current rules while keeping the approved visual selection."""
    from .learning_setup import public_config
    from .learning_pipeline import preview
    from . import learning_logo,learning_mask,learning_prompts
    config=public_config(engine)
    visual=source['plan']['visual_config']
    plan=preview(params,config['placements'],seed=visual['seed'],trusted_visual=visual)
    normalized=plan['normalized_params']
    normalized['learning_logo_snapshot']=learning_logo.freeze_templates(engine.settings,normalized['pids'])
    normalized['learning_mask_snapshot']={pid:learning_mask.preset_for(pid) for pid in normalized['pids']}
    compiled=learning_prompts.build(plan,normalized['image_model'])
    if normalized.get('concept'):
        from .learning_concept import configure_plan
        configure_plan(plan,compiled)
        plan.update(params=copy.deepcopy(normalized),prompt_plan=compiled)
        return plan
    for master in compiled['masters']:
        if master.get('reuse_baseline'):
            master.update(prompt=master['single_regeneration_prompt'],reuse_baseline=False,image_generation_required=True,
                          needs_image_model_call=True,source_kind='confirmed_baseline_image_to_image',
                          baseline_reuse_disabled_reason='recompose_source_framing')
    calls=sum(m['needs_image_model_call'] for m in compiled['masters'])
    backgrounds=compiled['counts'].get('background_image_calls',0)
    compiled['counts'].update(image_model_master_calls=calls,baseline_reused_master_count=0,
                              planned_image_calls=calls+backgrounds,baseline_image_calls=0,baseline_reused=True,expected_new_calls=calls+backgrounds)
    plan.update(params=copy.deepcopy(normalized),prompt_plan=compiled)
    return plan


def _source_path(engine,source,path):
    resolved=Path(path).resolve()
    roots=(Path(source['directory']).resolve(),(engine.settings.output/'.restored').resolve())
    if not any(resolved.is_relative_to(root) for root in roots):raise UserError('来源批次素材超出冻结目录')
    return resolved


def freeze_run(engine,params,run_dir,*,confirmed_source=None):
    """Freeze specifications, prompt text, reference pixels and layer parameters."""
    from .learning_setup import save_and_preview
    from .learning_pipeline import CONTENT_BY_ID
    from .planning import ASSETS,BUILTIN_STYLE_REFERENCES
    run_dir=Path(run_dir);run_dir.mkdir(parents=True,exist_ok=True)
    plan=copy.deepcopy(_source_plan(engine,params,confirmed_source) if confirmed_source else save_and_preview(engine,params))
    normalized=copy.deepcopy(plan['params'])
    logo=copy.deepcopy(normalized['learning_logo_snapshot'])
    for aid,record in logo['assets'].items():
        target=run_dir/'learning-logo-assets'/(aid+'.png')
        _copy_checked(record['path'],target,record['sha256']);record['path']=str(target)
    normalized['learning_logo_snapshot']=logo
    masks=copy.deepcopy(normalized['learning_mask_snapshot'])
    lookup={a['asset_id']:a for a in ASSETS}
    lookup.update({a['id']:a for a in BUILTIN_STYLE_REFERENCES})
    registered={r['id']:r for r in normalized.get('references',[])}
    source_bindings={_key(r):r for r in confirmed_source.get('asset_bindings',[])} if confirmed_source else {}
    templates=[plan['prompt_plan']['baseline'],*plan['prompt_plan']['masters']]
    bindings={}
    for template in templates:
        for ref in template['reference_bindings']:
            if ref['kind']=='confirmed_baseline':continue
            key=_key(ref)
            if key in bindings:continue
            record=source_bindings.get(key) if confirmed_source else registered.get(ref.get('reference_id')) if ref.get('reference_id') else lookup.get(ref.get('asset_id'))
            if not record:raise UserError('冻结参考素材未登记，请重新配置')
            source=Path(record['path']);source=source if source.is_absolute() else ROOT/source
            resolved=source.resolve()
            if confirmed_source:_source_path(engine,confirmed_source,resolved)
            else:
                allowed_root=(Path(engine.settings.state_dir)/'uploads').resolve() if ref.get('reference_id') else ROOT.resolve()
                if not resolved.is_relative_to(allowed_root):raise UserError('参考素材超出登记目录')
            identifier=hashlib.sha256(key.encode()).hexdigest()[:20]
            target=run_dir/'assets'/(identifier+source.suffix.lower())
            expected=record.get('sha256') or (record['id'] if ref.get('reference_id') else None)
            digest=_copy_checked(resolved,target,expected)
            bindings[key]={**copy.deepcopy(ref),'path':str(target),'sha256':digest}
    # Keep the request data coherent with its copied bytes. No saved record
    # depends on the mutable upload file surviving later cleanup.
    for ref in normalized.get('references',[]):
        copied=bindings.get('reference:'+ref['id'])
        if copied:ref['path']=copied['path'];ref['sha256']=copied['sha256']
    plan['normalized_params']=copy.deepcopy(normalized);plan['params']=copy.deepcopy(normalized)
    plan.pop('saved_configuration',None)
    placements={pid:copy.deepcopy(CONTENT_BY_ID[pid]) for pid in normalized['pids']}
    groups=json.loads((ROOT/'config/learning-machine-master-groups.json').read_text(encoding='utf-8'))
    frozen=dict(params=normalized,plan=plan,compiled=copy.deepcopy(plan['prompt_plan']),
                asset_bindings=list(bindings.values()),placements=placements,placement_snapshots=copy.deepcopy(placements),
                group_snapshot=groups,logo_snapshot=logo,mask_snapshot=masks)
    frozen['baseline_reference_bindings']=resolve_bindings(frozen,frozen['compiled']['baseline']['reference_bindings'])
    if normalized.get('concept') and not confirmed_source:
        from .learning_concept import resolve
        concept,source=resolve(engine.settings,normalized['concept'])
        target=run_dir/'baselines'/('v1'+source.suffix)
        _copy_checked(source,target,concept['id'])
        frozen['uploaded_baseline']=dict(id='baseline',version=1,status='done',raw_path=str(target),sha256=concept['id'],
                                         prompt=frozen['compiled']['baseline']['prompt'],uploaded=True)
    if confirmed_source:
        baseline=copy.deepcopy(confirmed_source['baseline'])
        path=run_dir/'baselines'/('v1'+(Path(baseline['raw_path']).suffix if normalized.get('concept') else '.png'))
        _copy_checked(_source_path(engine,confirmed_source,baseline['raw_path']),path,baseline['sha256'])
        replacements={str(record['path']):bindings[key]['path'] for key,record in source_bindings.items() if key in bindings}
        actual=[]
        for index,ref in enumerate(baseline.get('reference_bindings') or confirmed_source.get('baseline_reference_bindings',[]),1):
            item=copy.deepcopy(ref);old=str(item['path']);target=replacements.get(old)
            if target is None:
                original=_source_path(engine,confirmed_source,old)
                target=run_dir/'assets'/('baseline-reference-'+str(index)+original.suffix.lower())
                _copy_checked(original,target,item.get('sha256'));replacements[old]=str(target)
            item.update(path=str(target),sha256=_sha(target));actual.append(item)
        if baseline.get('provider_original_path'):
            original=_source_path(engine,confirmed_source,baseline['provider_original_path'])
            target=run_dir/'baselines'/'v1.provider-original.png'
            _copy_checked(original,target,baseline['provider_original_sha256']);replacements[str(original)]=str(target)
        def replace(value):
            if isinstance(value,dict):return {key:replace(item) for key,item in value.items()}
            if isinstance(value,list):return [replace(item) for item in value]
            return replacements.get(value,value) if isinstance(value,str) else value
        baseline=replace(baseline)
        baseline.update(id='baseline',version=1,status='done',raw_path=str(path),reference_bindings=actual,
                        inherited=True,query_required=False)
        baseline.pop('versions',None)
        frozen['inherited_baseline']=baseline
    return frozen


def resolve_bindings(run,bindings,baseline_path=None,baseline_sha256=None):
    assets={_key(r):r for r in run.get('asset_bindings',[])}
    result=[]
    for i,binding in enumerate(bindings,1):
        row=copy.deepcopy(binding)
        if row.get('kind')=='confirmed_baseline':
            if not baseline_path or not baseline_sha256:raise UserError('请先确认本套基准图')
            source=Path(baseline_path);expected=baseline_sha256
        else:
            frozen=assets.get(_key(row))
            if not frozen:raise UserError('本套冻结素材未找到')
            source=Path(frozen['path']);expected=frozen['sha256']
        if not source.is_file() or _sha(source)!=expected:raise UserError('本套冻结图片校验失败，已保留现有结果')
        row.update(slot=i,label='参考图'+str(i),path=str(source),sha256=expected)
        result.append(row)
    return result


def _compiled(run):
    value=run.get('compiled') or run.get('plan',{}).get('prompt_plan')
    if not isinstance(value,dict):raise UserError('学习机冻结提示词不完整')
    return value


def compile_baseline(run,scene_plan):
    from .scene_planner import validate_schema
    compiled=_compiled(run)
    validate_schema(scene_plan,compiled['scene_planning']['output_schema'],path='scene_plan')
    baseline=copy.deepcopy(compiled['baseline'])
    markers=('\n场景规划：〈生成基准图时填入场景方案〉','\n场景规划：〈待接入 scene_plan，当前模板不可执行〉')
    marker=next((value for value in markers if value in baseline['prompt']),None)
    if marker is None:raise UserError('基准图模板版本不兼容，请重新保存配置')
    if baseline.get('prompt_contract_version')==2:
        labels={'subjects':'主体','moment':'瞬间','interactions':'动作与物体关系','camera':'镜头',
                'composition':'构图','lighting_materials':'光色材质','visible_evidence':'可见细节'}
        scene='\n画面安排：\n'+'\n'.join(label+'：'+scene_plan[field] for field,label in labels.items())
    else:scene='\n场景规划（服务端已验证）数据：'+json.dumps(scene_plan,ensure_ascii=False,sort_keys=True)
    baseline['prompt']=baseline['prompt'].replace(marker,scene,1)
    baseline.update(scene_plan=copy.deepcopy(scene_plan),allowed_text={},content_safe_area=baseline.get('content_safe_area') or baseline['shared_safe_area'],
                    reference_bindings=resolve_bindings(run,baseline['reference_bindings']),missing_inputs=[])
    return baseline


def compile_single(run,output_id):
    compiled=_compiled(run)
    output=next((o for o in compiled['outputs'] if o['output_id']==output_id),None)
    if not output:raise UserError('图片不存在',404)
    master=copy.deepcopy(next(m for m in compiled['masters'] if m['id']==output['master_id']))
    master.update(prompt=master['single_regeneration_prompt'],placement_ids=[output['placement_id']],
                  output_ids=[output_id],delivery_count=1,reuse_baseline=False,image_generation_required=True,
                  needs_image_model_call=True,force_image_regeneration=True,reuse_existing_master=False,
                  updates_shared_master=False,updates_siblings=False)
    if master.get('main_visual_framing',{}).get('removed_ad_module'):
        master.pop('concept_audit_box',None)
        if not output.get('background_image_required'):
            master['concept_audit_box']=output['crop_box']
    return master


def prepare_restored_run(engine,run):
    """Rehome future writes and keep restored immutable layer assets usable."""
    rid=run.get('id')
    if not isinstance(rid,str) or not re.fullmatch('[a-f0-9]{32}',rid):raise UserError('备份中的学习机任务标识不正确')
    value=copy.deepcopy(run)
    directory=Path(engine.settings.output)/'.cache'/'learning-runs'/rid
    value['directory']=str(directory)
    replacements={}
    for aid,asset in value.get('logo_snapshot',{}).get('assets',{}).items():
        if aid not in ('learning.logo.black','learning.logo.white-app'):raise UserError('备份中的Logo素材未登记')
        source=Path(asset['path'])
        if not source.resolve().is_relative_to((engine.settings.output/'.restored').resolve()):
            raise UserError('恢复的Logo素材超出本机恢复目录')
        target=directory/'learning-logo-assets'/(aid+'.png')
        _copy_checked(source,target,asset['sha256']);replacements[str(source)]=str(target)
    def replace(item):
        if isinstance(item,dict):return {k:replace(v) for k,v in item.items()}
        if isinstance(item,list):return [replace(v) for v in item]
        if isinstance(item,str):return replacements.get(item,item)
        return item
    value=replace(value)
    # Pending backgrounds can have journals before any native PNG exists.
    from render import task_state_path
    restored=(engine.settings.output/'.restored').resolve()
    for key,operation in value.get('background_operations',{}).items():
        if operation.get('status')=='done':continue
        if not re.fullmatch('[a-f0-9]{64}',key):raise UserError('恢复的背景任务标识不正确')
        job=operation['job'];old_native=Path(job['output'])
        receipt=Path(operation.get('receipt_path') or task_state_path(old_native))
        native=directory/'backgrounds'/key/'native.png';journal=task_state_path(native)
        if receipt.is_file():
            if not receipt.resolve().is_relative_to(restored):raise UserError('恢复的背景回执超出归档目录')
            _copy_checked(receipt,journal)
            if old_native.is_file():
                if not old_native.resolve().is_relative_to(restored):raise UserError('恢复的背景图片超出归档目录')
                _copy_checked(old_native,native)
        elif operation.get('query_required'):
            operation['restore_query_blocked']=True
        job['output']=str(native);operation['receipt_path']=str(journal)
        for row in value.get('outputs',[]):
            request=row.get('background_request') or {}
            if row.get('background_repair_pending') and request.get('operation_id')==key:
                row['background_native_path']=str(native);row['raw_path']=str(native)
    if value.get('busy'):
        value.update(busy=False,status='interrupted',error='从备份恢复，已有结果保留；请明确恢复未完成操作')
        if value.get('suite',{}).get('status')=='generating':value['suite']['status']='interrupted'
        for row in [value.get('baseline',{}),*value.get('masters',[]),*value.get('outputs',[])]:
            if row.get('status') in ('queued','generating'):
                from scripts.render import task_state_path
                receipt=task_state_path(Path(row.get('raw_path') or directory/'none'))
                row.update(status='interrupted',query_required=receipt.is_file())
    return value
