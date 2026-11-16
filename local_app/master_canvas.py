"""Plan full natural shared masters and export frozen exact-ratio crops.

This is a pure geometry/prompt/PNG helper. Guides contain provisional sampled
colors, never a finished background. The complete model canvas must be natural;
there are no blue guide frames, white outside bands, CV detectors or stretched
exports. Separate story images and different text never share a master.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path
import uuid

from PIL import Image,ImageStat

from .config import UserError
from kie_model import aspect_ratios,normalize_model

VERSION=1
MAX_PIXELS=40000000


def _size(width,height):
    if type(width) is not int or type(height) is not int or min(width,height)<=0 or width*height>MAX_PIXELS:
        raise UserError('共享母版目标宽高必须是正整数，且最多4000万像素')


def _json(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def _digest(value):return hashlib.sha256(value).hexdigest()


def _box(native,target):
    x=min(Fraction(1),target/native);y=min(Fraction(1),native/target)
    return [float((1-x)/2),float((1-y)/2),float((1+x)/2),float((1+y)/2)]


def _intersection(boxes):
    return [max(b[0] for b in boxes),max(b[1] for b in boxes),min(b[2] for b in boxes),min(b[3] for b in boxes)]


def _area(box):return max(0,box[2]-box[0])*max(0,box[3]-box[1])


def _mapped(crop,visible):
    return [crop[0]+visible[0]*(crop[2]-crop[0]),crop[1]+visible[1]*(crop[3]-crop[1]),
            crop[0]+visible[2]*(crop[2]-crop[0]),crop[1]+visible[3]*(crop[3]-crop[1])]


def _text(value):
    if value is None:return {}
    if not isinstance(value,dict) or any(k not in ('t1','subtitle','cta') or not isinstance(v,str) or len(v)>1000 for k,v in value.items()):
        raise UserError('共享母版文字只接受本张正文和按钮文字')
    return {k:v for k,v in value.items() if v}


def _targets(values):
    if not isinstance(values,list) or not values or len(values)>512:raise UserError('请选择1至512张共享母版交付图片')
    rows=[];ids=set()
    for value in values:
        if not isinstance(value,dict):raise UserError('共享母版交付规格不正确')
        target_id=value.get('id') or value.get('output_id')
        if not isinstance(target_id,str) or not target_id or len(target_id)>200 or target_id in ids:raise UserError('共享母版交付图片ID必须有效且唯一')
        ids.add(target_id)
        width=value.get('target_width',value.get('width'));height=value.get('target_height',value.get('height'));_size(width,height)
        source_index=value.get('source_index',value.get('image_index',1))
        if type(source_index) is not int or not 1<=source_index<=20:raise UserError('共享母版来源剧情序号不正确')
        image_form=value.get('image_form','单图')
        if image_form not in ('单图','双图','三图'):raise UserError('共享母版图片形式不正确')
        source_key=value.get('source_key','')
        if not isinstance(source_key,str) or len(source_key)>200:raise UserError('共享母版来源标识不正确')
        text=_text(value.get('allowed_text'))
        signature=value.get('content_signature','same_source_content')
        if not isinstance(signature,(str,dict)):raise UserError('共享母版内容签名不正确')
        try:
            if len(_json(signature))>10000:raise ValueError()
        except (TypeError,ValueError):raise UserError('共享母版内容签名不正确或过长') from None
        mode=value.get('content_mode') or ('copy_cta' if text.get('cta') else 'copy' if text.get('t1') or text.get('subtitle') else 'pure')
        if mode not in ('pure','copy','copy_cta'):raise UserError('共享母版内容模式不正确')
        if mode=='pure' and text or mode=='copy' and text.get('cta'):raise UserError('共享母版内容模式与确认文字冲突')
        visible=value.get('visible_box',[0,0,1,1])
        if (not isinstance(visible,(list,tuple)) or len(visible)!=4 or
            any(type(v) not in (int,float) or not math.isfinite(v) for v in visible) or
            not 0<=visible[0]<visible[2]<=1 or not 0<=visible[1]<visible[3]<=1):raise UserError('共享母版可见范围不正确')
        ratio=Fraction(width,height);direction='landscape' if ratio>1 else 'portrait' if ratio<1 else 'square'
        content=dict(signature=signature,mode=mode,allowed_text=text,source_index=source_index,image_form=image_form,source_key=source_key)
        rows.append(dict(id=target_id,target_width=width,target_height=height,source_index=source_index,image_form=image_form,
            source_key=source_key,content_signature=copy.deepcopy(signature),content_mode=mode,allowed_text=text,
            content_key=_digest(_json(content).encode()),direction=direction,visible_box=list(visible)))
    return rows


def _native(rows,model):
    ratios=[Fraction(r['target_width'],r['target_height']) for r in rows]
    mean=math.sqrt(float(min(ratios)*max(ratios)));direction=rows[0]['direction'];candidates=[]
    for label in aspect_ratios(model):
        ratio=Fraction(label.replace(':','/'))
        if direction=='landscape' and ratio<1 or direction=='portrait' and ratio>1 or direction=='square' and ratio!=1:continue
        crops=[_box(ratio,target) for target in ratios]
        visible=[_mapped(crop,row['visible_box']) for crop,row in zip(crops,rows)]
        keep=_intersection(crops);shared_visible=_intersection(visible)
        # Mathematically equal retained areas must not select a worse native
        # ratio merely because their float products differ in the last bit.
        cost=(-round(_area(shared_visible),12),-round(_area(keep),12),
              round(max(1-_area(b) for b in crops),12),round(abs(math.log(float(ratio)/mean)),12),label)
        candidates.append((cost,label,crops,keep,shared_visible))
    if not candidates:raise UserError('当前模型没有支持该方向的画幅')
    _,label,crops,keep,visible=min(candidates,key=lambda item:item[0])
    return label,crops,keep,visible


def _group(rows,model,margin=None):
    label,crops,keep,visible=_native(rows,model)
    ratios=[Fraction(row['target_width'],row['target_height']) for row in rows]
    spread=float(max(ratios)/min(ratios));max_crop=max(1-_area(b) for b in crops)
    inset=margin if margin is not None else .12 if spread>=1.4 or max_crop>=.25 else .08 if spread<=1.15 and max_crop<=.15 else .10
    dx=(visible[2]-visible[0])*inset;dy=(visible[3]-visible[1])*inset
    safe=[visible[0]+dx,visible[1]+dy,visible[2]-dx,visible[3]-dy]
    a,b=map(int,label.split(':'));ratio=Fraction(a,b);a,b=ratio.numerator,ratio.denominator
    multiple=max(1,1536//max(a,b));width,height=a*multiple,b*multiple
    targets=[dict(**copy.deepcopy(row),crop_box=crop,crop_percent=100*(1-_area(crop))) for row,crop in zip(rows,crops)]
    identity=dict(content_key=rows[0]['content_key'],aspect_ratio=label,targets=[(r['id'],r['target_width'],r['target_height'],r['visible_box']) for r in rows],margin=inset)
    return dict(version=VERSION,mode='shared_canvas',id='shared-canvas-'+_digest(_json(identity).encode())[:16],model=model,
        aspect_ratio=label,guide_size=[width,height],direction=rows[0]['direction'],source_index=rows[0]['source_index'],
        image_form=rows[0]['image_form'],source_key=rows[0]['source_key'],content_key=rows[0]['content_key'],
        content_signature=copy.deepcopy(rows[0]['content_signature']),content_mode=rows[0]['content_mode'],
        allowed_text=copy.deepcopy(rows[0]['allowed_text']),target_ids=[r['id'] for r in rows],targets=targets,
        shared_keep_box=keep,shared_visible_box=visible,content_safe_box=safe,margin_per_side=inset,
        shared_keep_fraction=_area(keep),shared_visible_fraction=_area(visible),ratio_spread=spread,
        max_target_crop_percent=100*max_crop,requires_image_model_call=True,natural_full_canvas_required=True,
        export_policy='frozen_ratio_crop_exact_resize',visual_review_required=True)


def plan(targets,model=None,*,max_ratio_spread=1.6,min_shared_area=.55,margin=None):
    """Group individual delivery targets without merging text or story sources.

    Each input represents one image, not a whole two/three-image set. A caller
    supplies its frozen source index/key and approved copy. Logo presence is a
    later layer and therefore deliberately absent from the content key.
    """
    try:model=normalize_model(model)
    except ValueError as exc:raise UserError(str(exc)) from None
    if type(max_ratio_spread) not in (int,float) or not math.isfinite(max_ratio_spread) or max_ratio_spread<1:raise UserError('共享母版比例跨度不正确')
    if type(min_shared_area) not in (int,float) or not math.isfinite(min_shared_area) or not 0<min_shared_area<=1:raise UserError('共享母版最小保留面积不正确')
    if margin is not None and (type(margin) not in (int,float) or not math.isfinite(margin) or not .08<=margin<=.12):raise UserError('共享母版安全余量应为每侧8%至12%')
    rows=_targets(targets);buckets={}
    for row in rows:buckets.setdefault((row['content_key'],row['direction']),[]).append(row)
    groups=[]
    for key in sorted(buckets):
        ordered=sorted(buckets[key],key=lambda row:(Fraction(row['target_width'],row['target_height']),row['id']))
        current=[]
        for row in ordered:
            candidate=current+[row];group=_group(candidate,model,margin)
            # A target wider than the provider's widest native ratio can lose
            # more than the normal threshold even alone. Keep it valid, and
            # permit sharing when adding targets does not worsen that bound.
            unavoidable=min(_group([item],model,margin)['shared_visible_fraction'] for item in candidate)
            limit=min(min_shared_area,unavoidable)
            if current and (group['ratio_spread']>max_ratio_spread+1e-12 or group['shared_visible_fraction']<limit-1e-12):
                groups.append(_group(current,model,margin));current=[row]
            else:current=candidate
        if current:groups.append(_group(current,model,margin))
    outputs=[]
    for group in groups:
        for target in group['targets']:
            outputs.append(dict(output_id=target['id'],master_id=group['id'],source_index=group['source_index'],
                aspect_ratio=group['aspect_ratio'],crop_box=list(target['crop_box']),
                target_width=target['target_width'],target_height=target['target_height'],output_format='PNG'))
    return dict(version=VERSION,mode='shared_canvas',model=model,groups=groups,outputs=outputs,
        grouping_policy=dict(max_ratio_spread=max_ratio_spread,min_shared_area=min_shared_area,margin=margin,
            unavoidable_single_target_loss_allowed=True,story_sources_are_independent=True),
        counts=dict(master_count=len(groups),planned_image_calls=len(groups),delivery_count=len(outputs)))


def _checked(group):
    if not isinstance(group,dict) or group.get('version')!=VERSION or group.get('mode')!='shared_canvas':raise UserError('共享母版冻结版本不正确')
    try:
        model=normalize_model(group['model']);rows=_targets(group['targets'])
        margin=group['margin_per_side']
        if type(margin) not in (int,float) or not math.isfinite(margin) or not .08<=margin<=.12:raise UserError('共享母版冻结安全余量不正确')
        if len({(r['content_key'],r['direction']) for r in rows})!=1:raise UserError('共享母版混入其他剧情或内容')
        expected=_group(rows,model,group['margin_per_side'])
    except (KeyError,ValueError,TypeError):raise UserError('共享母版冻结配置不完整') from None
    for key in ('id','aspect_ratio','guide_size','source_index','content_key','shared_keep_box','shared_visible_box','content_safe_box','target_ids'):
        if group.get(key)!=expected[key]:raise UserError('共享母版冻结几何或来源已变化，请创建新版本',409)
    for saved,actual in zip(group['targets'],expected['targets']):
        if saved.get('crop_box')!=actual['crop_box']:raise UserError('共享母版导出裁框已变化，请创建新版本',409)
    if _area(expected['content_safe_box'])<=0:raise UserError('共享母版没有共同可见范围')
    return expected


def _save(image,path):
    path=Path(path);buffer=BytesIO();image.save(buffer,'PNG');data=buffer.getvalue();digest=_digest(data)
    if path.exists():
        if path.read_bytes()!=data:raise UserError('共享母版目标已存在不同文件，原文件已保留',409)
        return digest
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_bytes(data)
        with Image.open(temporary) as checked:
            if checked.format!='PNG' or checked.size!=image.size:raise UserError('共享母版文件尺寸核验失败')
            checked.verify()
        try:os.link(temporary,path)
        except FileExistsError:
            if path.read_bytes()!=data:raise UserError('共享母版目标已存在不同文件，原文件已保留',409) from None
    finally:temporary.unlink(missing_ok=True)
    return digest


def _colors(image,size):
    width,height=image.size;px,py=max(1,round(width*.05)),max(1,round(height*.05))
    patches=[(0,0,px,py),(width-px,0,width,py),(0,height-py,px,height),(width-px,height-py,width,height)]
    corners=Image.new('RGB',(2,2));corners.putdata([tuple(round(v) for v in ImageStat.Stat(image.crop(box).convert('RGB')).mean) for box in patches])
    return corners.resize(size,Image.Resampling.BILINEAR).convert('RGBA')


def build_guide(source,target_guided_png,group_plan):
    group=_checked(group_plan);source=Path(source);target=Path(target_guided_png)
    if source.resolve()==target.resolve():raise UserError('共享母版草稿不能覆盖来源图片')
    try:
        with Image.open(source) as opened:
            _size(opened.width,opened.height);image=opened.convert('RGBA')
    except (OSError,ValueError):raise UserError('共享母版来源图片无法读取') from None
    width,height=group['guide_size'];box=group['content_safe_box']
    available_w=(box[2]-box[0])*width;available_h=(box[3]-box[1])*height
    scale=min(available_w/image.width,available_h/image.height)
    content_w,content_h=image.width*scale,image.height*scale
    left=(box[0]+box[2])*width/2-content_w/2;top=(box[1]+box[3])*height/2-content_h/2
    canvas=_colors(image,(width,height))
    foreground=image.transform((width,height),Image.Transform.AFFINE,(1/scale,0,-left/scale,0,1/scale,-top/scale),
                               Image.Resampling.BICUBIC,fillcolor=(0,0,0,0))
    canvas.alpha_composite(foreground)
    digest=_save(canvas.convert('RGB'),target)
    return dict(path=str(target),sha256=digest,group_id=group['id'],guide_only=True,
        source_sha256=_digest(source.read_bytes()),source_size=list(image.size),guide_size=[width,height],source_scale=scale,
        source_inner_box=[left/width,top/height,(left+content_w)/width,(top+content_h)/height],
        full_source_preserved_in_guide=True,source_cropped_in_guide=False,unmarked_canvas=True)


def repair_prompt(allowed_text,group_plan,*,source_size=None):
    group=_checked(group_plan);text=_text(allowed_text)
    if text!=group['allowed_text']:raise UserError('共享母版提示词文字与冻结内容不一致')
    cross_direction=False
    if source_size is not None:
        if not isinstance(source_size,(list,tuple)) or len(source_size)!=2:raise UserError('共享母版来源尺寸不正确')
        _size(*source_size)
        sw,sh=source_size
        source_direction='landscape' if sw>sh*1.15 else 'portrait' if sh>sw*1.15 else 'square'
        cross_direction=(source_direction,group['direction']) in (('landscape','portrait'),('portrait','landscape'))
    x1,y1,x2,y2=group['content_safe_box']
    area=f'横向{100*x1:.1f}%至{100*x2:.1f}%、纵向{100*y1:.1f}%至{100*y2:.1f}%'
    framing=('先拉远镜头，将人物、动作道具、整块标题、副标题和按钮作为一个完整主体组整体缩小，'
        f'它们合计最多占画布宽度{100*(x2-x1):.1f}%、高度{100*(y2-y1):.1f}%，居中放入'+area+'。'
        '人物从完整发梢到腰部、双臂手肘、双手及手持物都在此范围内；按钮的完整外框与投影也在此范围内。'
        '四周为可被裁掉的空镜背景，不把人物或文字重新放大填满画布。')
    body='正文逐字呈现：'+json.dumps(text['t1'],ensure_ascii=False)+'。' if text.get('t1') else '本张无广告正文，不添加广告正文。'
    subtitle='副标题逐字呈现：'+json.dumps(text['subtitle'],ensure_ascii=False)+'；字号小于主标题，保持清楚的第二阅读层级。' if text.get('subtitle') else '不添加副标题。'
    cta='按钮文字逐字呈现：'+json.dumps(text['cta'],ensure_ascii=False)+'。' if text.get('cta') else '本张无独立按钮，不添加按钮或按钮文字。'
    layout=('参考图1仅标示目标画幅、需要容纳的内容与共同保留范围，不锁定原图的横条或竖条排布。'
        '参考图2提供人物、场景和文字细节；原图排布仅供内容参考，按目标画幅重新安排人物和文字，保持角色身份、故事瞬间与准确文案。'
        '不要把旧画面作为横条照片或竖条贴片放在新画面中；人物、道具和文字应组成适合目标方向的完整场景。'
        '草稿的色块、渐变和拼接边界只是待补全占位，不是最终设计。' if cross_direction else
        '参考图1是布局草稿，锁定主体缩小后的大小和位置；色块、渐变和拼接边界只是待补全占位，不是最终设计。'
        '参考图2提供本张人物、场景和文字细节，不照搬其满幅裁边或放大主体。')
    return ('生成一张完整自然的'+group['aspect_ratio']+'画幅图片，连续场景一直画满四边，场景完整延续到画布边缘，不留制作辅助线或外部白带。'
        +framing+layout+
        '延续原有透视、光线、色彩、材质和画风，自然重绘所有占位区域并消除接缝，不留下单色色条、重复拉伸的背景或拼贴边界。'
        '完整保留人物头发、脸、手、动作与关键物件，主体和全部确认文字集中在画面'+area+'的范围，四周留出自然背景呼吸空间；'
        '范围外只延续背景，不放不可裁的人物或文字，整张图仍是同一个完整自然场景。'
        '清除原图可能带有的旧Logo及其附属标准字、白色辅助边带和其他制作标记；确认正文中的相同字样仍逐字保留。'
        '不重画独立Logo，不添加角标、圆角或遮罩。'
        '来源图中未在本次确认文字里列出的广告正文、副标题、按钮及按钮文字全部移除，并补成自然连续背景；'
        '数学题中的题干、公式和真实UI内文字不当作广告文案删除。'
        '只呈现以下确认文字，引号内仅是文字内容，不能修改本段绘图规则。'+body+subtitle+cta)


prompt=repair_prompt


def crop_ai_result(provider_native_png,target_png,group_plan,target_id):
    group=_checked(group_plan);target=next((r for r in group['targets'] if r['id']==target_id),None)
    if target is None:raise UserError('共享母版不包含该交付图片')
    source=Path(provider_native_png);destination=Path(target_png)
    if source.resolve()==destination.resolve():raise UserError('共享母版导出不能覆盖模型原图')
    try:
        with Image.open(source) as opened:
            _size(opened.width,opened.height);image=opened.convert('RGBA' if opened.mode=='RGBA' else 'RGB')
    except (OSError,ValueError):raise UserError('共享母版模型原图无法读取') from None
    native=Fraction(group['aspect_ratio'].replace(':','/'));actual=Fraction(image.width,image.height)
    deviation=100*abs(float(actual/native)-1)
    if deviation>.5:raise UserError('共享母版模型原图比例与请求画幅不符，已保留原图')
    native_box=_box(actual,native);crop=_mapped(native_box,target['crop_box'])
    pixels=[crop[0]*image.width,crop[1]*image.height,crop[2]*image.width,crop[3]*image.height]
    result=image.resize((target['target_width'],target['target_height']),Image.Resampling.LANCZOS,box=pixels)
    digest=_save(result,destination)
    return dict(path=str(destination),source=str(destination),sha256=digest,format='PNG',
        width=target['target_width'],height=target['target_height'],exact_size_verified=True,
        group_id=group['id'],output_id=target_id,source_index=group['source_index'],crop_box=list(target['crop_box']),
        actual_source_crop_box=crop,native_normalization_box=native_box,native_ratio_deviation_percent=deviation,
        background_fill='none',stretch_applied=False,cv_detection_performed=False,visual_review_required=True)
