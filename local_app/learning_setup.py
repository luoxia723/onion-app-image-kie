"""Local learning-machine setup; previewing never invokes planning or image APIs."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import time
import uuid

from PIL import Image

from .config import ROOT, UserError

CONFIGURATION_DOCUMENT = 'learning_machine_configuration'
LOGO_BACKUP_DOCUMENT = 'learning_machine_logo_templates'


def is_learning_request(params):
    if not isinstance(params, dict):
        return False
    ids = params.get('pids', [])
    return (params.get('channel') == '学习机'
            or params.get('learning_pipeline') == 'baseline_then_suite'
            or isinstance(ids, list) and any(isinstance(pid, str) and pid.startswith('learning-') for pid in ids))


def generation_unavailable():
    raise UserError('学习机需要先生成并查看基准图，人工确认后才能扩展整套；请使用学习机独立制作入口，旧任务与上传母图入口不能直接生成整套', 409)


def public_config(engine):
    from . import learning_logo, learning_pipeline, learning_mask
    with engine.lock:
        # Existing database backups already preserve documents. Recover the
        # standalone template file only when absent, never overwrite live edits.
        if not (Path(engine.settings.state_dir)/learning_logo.STATE_NAME).exists():
            recovered=engine.document(LOGO_BACKUP_DOCUMENT)
            if recovered:
                placements=recovered.get('placements',{})
                if not isinstance(placements,dict):raise UserError('学习机Logo配置快照不完整')
                templates=[{'placement_id':pid,**row['logo_template']} for pid,row in placements.items()
                           if row.get('logo_required') and pid not in learning_logo.RETIRED_LOGO_PLACEMENTS]
                learning_logo.save_templates(engine.settings,{'revision':0,'templates':templates})
        base = learning_pipeline.public_contract()
        logos = learning_logo.config(engine.settings)
        by_id = {row['id']: row for row in logos['placements']}
        placements = []
        for row in base['placements']:
            logo = by_id[row['id']]
            # The content contract fixes presence; the template only supplies
            # the registered asset and bounds for placements which require it.
            merged={**copy.deepcopy(row),'logo_template':copy.deepcopy(logo['logo_template'])}
            merged['mask_template']=learning_mask.preset_for(row['id'])
            for key in ('sample_url','sample_size','sample_reference_only','sample_note'):
                if key in logo:merged[key]=copy.deepcopy(logo[key])
            placements.append(merged)
        groups=json.loads((ROOT/'config/learning-machine-master-groups.json').read_text(encoding='utf-8'))
        return {**base, 'revision': logos['revision'], 'logo_assets': logos['logo_assets'],
                'master_groups':copy.deepcopy(groups['groups']),
                'prompt_templates_version':groups['version'],
                'template_text_defaults':copy.deepcopy(groups['text_defaults']),
                'offline_prompt_preview_ready':True,
                'runtime_available':True,'runtime_modes':['real'],'default_runtime_mode':'real',
                **learning_mask.config(),
                'placements': placements,
                'saved_configuration': copy.deepcopy(engine.document(CONFIGURATION_DOCUMENT))}


def _registered_references(settings, references):
    if not isinstance(references, list) or len(references) > 3:
        raise UserError('参考图最多3张')
    result, purposes, ids = [], set(), set()
    root = (Path(settings.state_dir) / 'uploads').resolve()
    for supplied in references:
        if not isinstance(supplied, dict):
            raise UserError('参考图记录不正确')
        rid, purpose = supplied.get('id'), supplied.get('purpose')
        if not isinstance(rid, str) or not re.fullmatch('[a-f0-9]{64}', rid):
            raise UserError('请重新上传参考图片')
        if purpose not in ('style', 'composition', 'ui') or purpose in purposes or rid in ids:
            raise UserError('画风、构图和真实UI参考各最多一张，不能重复')
        path = next((root / (rid + suffix) for suffix in ('.png', '.jpg', '.webp')
                     if (root / (rid + suffix)).is_file()), None)
        if path is None or path.resolve().parent != root:
            raise UserError('参考图片未在本机登记，请重新上传')
        try:
            if hashlib.sha256(path.read_bytes()).hexdigest() != rid:
                raise ValueError()
            with Image.open(path) as image:
                if image.format not in ('PNG', 'JPEG', 'WEBP') or image.width*image.height > 40000000:
                    raise ValueError()
                image.verify()
        except (OSError, ValueError):
            raise UserError('参考图片校验失败，请重新上传') from None
        note = supplied.get('note', '')
        points = supplied.get('points', [])
        if not isinstance(note, str) or len(note) > 200:
            raise UserError('参考图说明最多200字')
        if (not isinstance(points, list) or len(points) > 6
                or any(not isinstance(p, str) or not p.strip() or len(p) > 16 for p in points)):
            raise UserError('参考图要点最多6条，每条1–16字')
        result.append(dict(id=rid, sha256=rid,path=str(path),thumbnail_url='/api/uploads/'+rid,name=Path(str(supplied.get('name', '参考图片'))).name[:120],
                           purpose=purpose, note=note, points=copy.deepcopy(points)))
        purposes.add(purpose); ids.add(rid)
    return result


def save_and_preview(engine, params):
    from . import learning_logo, learning_pipeline, learning_mask
    if not isinstance(params, dict) or len(json.dumps(params, ensure_ascii=False)) > 100000:
        raise UserError('学习机配置不正确或过长')
    with engine.lock:
        if engine.maintenance_active:
            raise UserError('正在进行本机数据维护，请稍后保存配置')
        params = copy.deepcopy(params)
        params.setdefault('image_model',engine.settings.image_model)
        if params.get('concept') is not None:
            from .learning_concept import params_for_concept
            params_for_concept(engine.settings,params)
        params['references'] = _registered_references(engine.settings, params.get('references', []))
        seed = params.get('learning_seed')
        if seed is not None and (not isinstance(seed, str) or not seed or len(seed) > 128):
            raise UserError('学习机视觉配置标识不正确')
        seed = seed or uuid.uuid4().hex
        configuration = public_config(engine)
        plan = learning_pipeline.preview(params, configuration['placements'], seed=seed)
        normalized = plan['normalized_params']
        normalized['learning_logo_snapshot'] = learning_logo.freeze_templates(engine.settings, normalized['pids'])
        normalized['learning_mask_snapshot'] = {pid:learning_mask.preset_for(pid) for pid in normalized['pids']}
        from . import learning_prompts
        prompt_plan=learning_prompts.build(plan,params['image_model'])
        if normalized.get('concept'):
            from .learning_concept import LABELS, configure_plan
            configure_plan(plan,prompt_plan)
        plan['prompt_plan']=prompt_plan
        plan['master_count']=prompt_plan['counts']['master_count']
        plan['planned_image_calls']=prompt_plan['counts']['planned_image_calls']
        plan['suite'].update(master_count=plan['master_count'],
                             planned_image_calls_after_confirmation=prompt_plan['counts']['image_model_master_calls']+prompt_plan['counts']['background_image_calls'])
        by_output={o['output_id']:o for o in prompt_plan['outputs']}
        by_master={m['id']:m for m in prompt_plan['masters']}
        from .learning_sizing import plan as size_plan
        for output in plan['outputs']:
            reuse=by_output[output['id']]
            output['master_id']=reuse['master_id']
            output['main_visual_framing']=copy.deepcopy(by_master[reuse['master_id']]['main_visual_framing'])
            output['processing_kind']=reuse['processing_kind']
            output['requires_image_model_call']=reuse['requires_image_model_call']
            output['depends_on'].append(reuse['master_id'])
            output['dependency_ids']=list(output['depends_on'])
            output['size_plan']=size_plan(output['width'],output['height'],params['image_model'],aspect_ratio=reuse['aspect_ratio'])
            method=output['size_plan']['source_ratio']+'目标安全区构图 → '+('AI自然扩展背景 → ' if reuse['background_image_required'] else '轻量裁切 → ')+'精确尺寸'
            if reuse.get('concept_route'):
                output['concept_route']=reuse['concept_route']
                method=LABELS[reuse['concept_route']]+(' → GPT 补齐版位背景' if reuse['background_image_required'] else '')+' → 精确尺寸'
            if output['logo_required']:method+=' → 固定Logo图层'
            output['size_plan']['method_label']=method
            output['method']=method
        saved = {'id': uuid.uuid4().hex, 'saved_at': time.time(),
                 'params': copy.deepcopy(normalized), 'logo_revision': configuration['revision'],
                 'pipeline': learning_pipeline.PIPELINE}
        engine.put_document(CONFIGURATION_DOCUMENT, saved)
        plan.update(saved=True, configuration_id=saved['id'], params=copy.deepcopy(normalized),
                    saved_configuration=saved, logo_revision=configuration['revision'])
        return plan


def save_logo_templates(engine, data):
    from . import learning_logo
    with engine.lock:
        if engine.maintenance_active:
            raise UserError('正在进行本机数据维护，请稍后保存配置')
        learning_logo.save_templates(engine.settings, data)
        all_ids=[p['id'] for p in learning_logo.config(engine.settings)['placements']]
        engine.put_document(LOGO_BACKUP_DOCUMENT,learning_logo.freeze_templates(engine.settings,all_ids))
        return public_config(engine)
