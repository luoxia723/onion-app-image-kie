"""Ordinary ad geometry using the learning-machine natural-canvas crop contract.

Each ordinary picture keeps its own story and model call. Only deterministic
geometry is shared; no blue-frame reference, detector or stretching is involved.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from PIL import Image

from .config import UserError
from . import master_canvas

VERSION=1
PROTOCOL='natural_canvas_v1'


def plan(placement,model):
    geometry=master_canvas.plan([dict(id=placement['id'],target_width=placement['target_width'],
        target_height=placement['target_height'],image_form=placement.get('image_form','单图'))],model)
    return dict(version=VERSION,kind='ordinary_natural_canvas',placement_id=placement['id'],
                framing_rule_version=2,group=geometry['groups'][0])


def _checked(value):
    if not isinstance(value,dict) or value.get('version')!=VERSION or value.get('kind')!='ordinary_natural_canvas':
        raise UserError('自然画布冻结配置不完整，请保留旧记录并新建任务',409)
    group=master_canvas._checked(value.get('group'))
    if value.get('framing_rule_version',1) not in (1,2):
        raise UserError('自然画布构图规则版本不受支持，请保留旧记录并新建任务',409)
    if len(group['targets'])!=1 or group['targets'][0]['id']!=value.get('placement_id'):
        raise UserError('自然画布与冻结版位不一致',409)
    return group


def aspect_ratio(value):return _checked(value)['aspect_ratio']


def prompt_rule(value):
    group=_checked(value);x1,y1,x2,y2=group['content_safe_box']
    rule=('生成完整自然画布，场景连续画满四边，不添加外框、定位线或白色辅助边带。'
        f'人物主视觉、完整广告文字与按钮放在画面横向{x1*100:.1f}%至{x2*100:.1f}%、纵向{y1*100:.1f}%至{y2*100:.1f}%范围内；'
        '外围只延续自然场景背景，后续会按固定窗口取景。'
        '镜头适当退远，将人物、动作和关键道具成组缩小重排；保留发梢、脸手与本张动作需要呈现的身体部位，勿贴边或截断。'
        '主标题、副标题、按钮外框及投影完整留在上述范围内，不靠扩大主体或文字填满边缘。')
    if value.get('framing_rule_version',1)==2:
        rule+=('采用中景或中远景，人物头顶发梢、左右轮廓、双手与关键道具四周均有可见背景间距；'
               '不要用人物大特写撑满画面，也不要让发梢伸入外围背景区。'
               '空间不足时缩小整个人物与动作道具组，再安排文字和按钮，不通过截去头发、手臂或道具腾出空间。')
    return rule


def validate_prompt(prompt,value):
    if prompt_rule(value) not in prompt:raise ValueError('prompt缺少本轮完整自然画布与主视觉安全区约束')


def crop(source,target,value,placement):
    group=_checked(value);spec=group['targets'][0]
    if (placement['id']!=value['placement_id'] or placement['target_width']!=spec['target_width']
            or placement['target_height']!=spec['target_height']):raise UserError('自然画布目标尺寸与冻结版位不符',409)
    source,target=Path(source),Path(target)
    if source.resolve()==target.resolve():raise UserError('自然画布适配不能覆盖模型原图')
    with Image.open(source) as image:actual=Fraction(image.width,image.height)
    native=Fraction(group['aspect_ratio'].replace(':','/'));desired=Fraction(spec['target_width'],spec['target_height'])
    if abs(float(actual/native)-1)*100<=.5:
        result=master_canvas.crop_ai_result(source,target,group,spec['id'])
    elif abs(float(actual/desired)-1)*100<=.5:
        # Local rehearsal and providers may already return the precise target
        # ratio. Accept it without cropping the native window a second time.
        from image_compress import resize_cover
        with Image.open(source) as image:
            resized=resize_cover(image.convert('RGB'),spec['target_width'],spec['target_height']);target.parent.mkdir(parents=True,exist_ok=True);resized.save(target,'PNG')
        result=dict(path=str(target),source=str(target),actual_source_crop_box=master_canvas._box(actual,desired),
                    width=spec['target_width'],height=spec['target_height'],exact_size_verified=True)
    else:raise UserError('模型原图比例与自然画布请求不符，已保留原图；请重试本图',409)
    return {**result,'method':'natural_canvas_exact_crop','aspect_ratio':group['aspect_ratio'],
            'content_safe_box':list(group['content_safe_box']),'planned_crop_percent':spec['crop_percent'],
            'crop_percent':100*(1-master_canvas._area(result['actual_source_crop_box'])),
            'unmarked_canvas':True,'stretch_applied':False,'cv_detection_performed':False,'visual_review_required':True}
