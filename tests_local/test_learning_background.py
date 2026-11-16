import copy
from fractions import Fraction
import hashlib
from pathlib import Path
import socket

from PIL import Image,ImageDraw
import pytest

from local_app import learning_background as background
from local_app.config import UserError
from kie_model import GPT_IMAGE_26_FLARE,MODEL,aspect_ratios


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def picture(path,size=(1536,512),color='#667788'):
    image=Image.new('RGB',size,color);draw=ImageDraw.Draw(image);w,h=size
    for box,color in [((0,0,35,35),'red'),((w-36,0,w-1,35),'green'),((0,h-36,35,h-1),'blue'),((w-36,h-36,w-1,h-1),'yellow')]:draw.rectangle(box,fill=color)
    image.save(path,'PNG');return path


def test_ultrawide_uses_native_three_to_one_and_preserves_all_original_content_in_inner_band():
    p=background.plan(1536,512,1400,340,GPT_IMAGE_26_FLARE)
    assert p['aspect_ratio']=='3:1' and p['guide_size']==[1536,512]
    assert p['version']==3
    assert p['final_crop_box']==pytest.approx([0,.1357142857142857,1,.8642857142857143])
    assert p['source_inner_size']==pytest.approx([1119.0857142857142*.84,373.0285714285714*.84])
    assert p['source_scale']==pytest.approx(.7285714285714285*.84)
    assert p['source_safety_margin_per_side']==.08
    assert p['padding_percent']==pytest.approx(27.14285714285714)
    assert p['background_needed'] and p['requires_ai_repair'] and p['guide_only']
    assert p['full_source_preserved_in_guide'] and not p['source_cropped_in_guide']


def test_portrait_uses_square_native_canvas_with_top_and_bottom_expansion_regions():
    p=background.plan(1536,1536,1536,1708,GPT_IMAGE_26_FLARE)
    assert p['aspect_ratio']=='1:1' and p['guide_size']==[1536,1536]
    assert p['final_crop_box'][0]>0 and p['final_crop_box'][1]==0
    assert p['source_inner_box'][1]>0 and p['source_inner_box'][3]<1
    assert p['source_inner_box'][0]>p['final_crop_box'][0]
    assert p['padding_percent']==pytest.approx(100*(1-1536/1708))
    assert p['background_needed']


@pytest.mark.parametrize('model',[MODEL,GPT_IMAGE_26_FLARE])
def test_native_ratio_is_nearest_among_the_selected_models_supported_ratios(model):
    from local_app.learning_pipeline import CONTENT_BY_ID
    for row in CONTENT_BY_ID.values():
        w,h=row['target_width'],row['target_height'];p=background.plan(1536,864,w,h,model)
        assert p['aspect_ratio'] in aspect_ratios(model)
        target=Fraction(w,h)
        costs={key:1-min(target/Fraction(key.replace(':','/')),Fraction(key.replace(':','/'))/target) for key in aspect_ratios(model)}
        assert costs[p['aspect_ratio']]==min(costs.values())
        a,b=p['guide_size'];ratio=Fraction(p['aspect_ratio'].replace(':','/'))
        assert Fraction(a,b)==ratio and max(a,b)<=2048
        x1,y1,x2,y2=p['final_crop_box']
        assert (x2-x1)*a/((y2-y1)*b)==pytest.approx(w/h)
        sx1,sy1,sx2,sy2=p['source_inner_box']
        assert sx1>=x1+(x2-x1)*.08-1e-12 and sy1>=y1+(y2-y1)*.08-1e-12
        assert sx2<=x2-(x2-x1)*.08+1e-12 and sy2<=y2-(y2-y1)*.08+1e-12
        assert (sx2-sx1)*a/((sy2-sy1)*b)==pytest.approx(1536/864)


def test_guide_keeps_original_four_corners_and_is_not_mistaken_for_a_finished_image(tmp_path):
    source=picture(tmp_path/'source.png');original=source.read_bytes()
    p=background.plan(1536,512,1400,340,GPT_IMAGE_26_FLARE)
    path=tmp_path/'guide.png';result=background.build_guided_canvas(source,path,p)
    assert result['guide_only'] is True and sha(path)==result['sha256']
    with Image.open(path) as guide:
        assert guide.size==(1536,512)
        x1,y1,x2,y2=p['source_inner_box'];w,h=guide.size
        points=[(round(x1*w)+8,round(y1*h)+8),(round(x2*w)-9,round(y1*h)+8),
                (round(x1*w)+8,round(y2*h)-9),(round(x2*w)-9,round(y2*h)-9)]
        assert [guide.getpixel(point) for point in points]==[(255,0,0),(0,128,0),(0,0,255),(255,255,0)]
        assert guide.getpixel((0,0))!=(255,255,255)
        assert p['unmarked_canvas']
        assert (22,99,214) not in set(guide.get_flattened_data())
    assert source.read_bytes()==original
    assert background.build_guided_canvas(source,path,p)==result
    path.write_bytes(b'keep existing inconsistent guide')
    with pytest.raises(UserError,match='原文件已保留'):background.build_guided_canvas(source,path,p)
    assert path.read_bytes()==b'keep existing inconsistent guide'


def test_ai_result_is_cropped_to_exact_target_without_new_padding_or_overwriting_raw(tmp_path):
    p=background.plan(1536,512,1400,340,GPT_IMAGE_26_FLARE)
    raw=tmp_path/'provider-original.png';image=Image.new('RGB',(1536,512),'white')
    ImageDraw.Draw(image).rectangle((0,60,1535,450),fill='#de5b86');image.save(raw)
    original=raw.read_bytes();target=tmp_path/'natural.png'
    result=background.crop_ai_result(raw,target,p)
    assert result['exact_size_verified'] and result['background_fill']=='none'
    assert result['actual_source_crop_box']==pytest.approx(p['final_crop_box'])
    assert result['content_detection']=='not_performed'
    with Image.open(target) as finished:
        assert finished.format=='PNG' and finished.size==(1400,340)
        assert finished.getextrema()==((222,222),(91,91),(134,134))
    assert raw.read_bytes()==original and sha(target)==result['sha256']
    assert background.crop_ai_result(raw,target,p)['sha256']==result['sha256']
    Image.new('RGB',(1536,512),'blue').save(raw)
    with pytest.raises(UserError,match='原文件已保留'):background.crop_ai_result(raw,target,p)
    assert sha(target)==result['sha256']


def test_one_pixel_provider_quantization_is_normalized_without_stretching_or_fill(tmp_path):
    p=background.plan(1536,512,1400,340,GPT_IMAGE_26_FLARE)
    raw=tmp_path/'rounded.png';Image.new('RGB',(1537,512),'#123456').save(raw)
    result=background.crop_ai_result(raw,tmp_path/'out.png',p)
    assert result['native_ratio_deviation_percent']<.5
    x1,y1,x2,y2=result['actual_source_crop_box']
    assert (x2-x1)*1537/((y2-y1)*512)==pytest.approx(1400/340)
    assert result['native_normalization_box']!=[0,0,1,1]
    with Image.open(result['path']) as finished:assert finished.getextrema()==((18,18),(52,52),(86,86))


def test_one_repaired_native_can_export_multiple_pixel_sizes_at_same_frozen_target_ratio(tmp_path):
    p=background.plan(1536,512,1400,340,GPT_IMAGE_26_FLARE)
    raw=picture(tmp_path/'provider-native.png');original=raw.read_bytes()
    small=background.crop_ai_result(raw,tmp_path/'small.png',p)
    large=background.crop_ai_result(raw,tmp_path/'large.png',p,2800,680)
    assert [large['width'],large['height']]==[2800,680]
    assert large['final_crop_box']==small['final_crop_box']==p['final_crop_box']
    assert large['actual_source_crop_box']==small['actual_source_crop_box']
    assert large['background_plan']['target_size']==[1400,340]
    with Image.open(large['path']) as checked:assert checked.format=='PNG' and checked.size==(2800,680)
    assert raw.read_bytes()==original
    for width,height in [(2800,681),(2800,None),(False,680),(2800,0)]:
        with pytest.raises(UserError):background.crop_ai_result(raw,tmp_path/'bad.png',p,width,height)


def test_incorrect_model_canvas_or_forged_geometry_fails_without_creating_a_finished_image(tmp_path):
    p=background.plan(1536,512,1400,340,GPT_IMAGE_26_FLARE)
    raw=picture(tmp_path/'wrong.png',(1536,1024));before=raw.read_bytes();target=tmp_path/'no-result.png'
    with pytest.raises(UserError,match='请求比例不符'):background.crop_ai_result(raw,target,p)
    assert raw.read_bytes()==before and not target.exists()
    bad=copy.deepcopy(p);bad['final_crop_box']=[0,0,1,1]
    with pytest.raises(UserError,match='几何配置已变化'):background.crop_ai_result(raw,target,bad)
    with pytest.raises(UserError,match='目标尺寸与冻结'):background.crop_ai_result(raw,target,p,1401,340)
    with pytest.raises(UserError,match='不能覆盖模型原图'):background.crop_ai_result(raw,raw,p)


@pytest.mark.parametrize('mode',['real','simulation'])
def test_prepare_job_is_offline_and_guide_first_with_real_source_hashes(tmp_path,monkeypatch,mode):
    def forbidden(*a,**k):raise AssertionError('helper cannot call providers')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    source=picture(tmp_path/'original.png');raw=tmp_path/'provider-raw.png'
    run=dict(mode=mode,params={'image_model':GPT_IMAGE_26_FLARE},stop_marker=str(tmp_path/'STOP'))
    job=background.prepare_job(run,source,raw,1400,340,{'t1':'遇到不会的题','cta':'立即体验'})
    assert job['kind']=='background_expansion' and job['simulation']==(mode=='simulation')
    assert job['output']==str(raw) and not raw.exists()
    refs=job['reference_bindings']
    assert [r['slot'] for r in refs]==[1,2]
    assert [r['kind'] for r in refs]==['adaptation_canvas','source_picture']
    assert refs[0]['path']==str(raw.with_suffix('.guide.png')) and refs[1]['path']==str(source)
    assert all(sha(r['path'])==r['sha256'] for r in refs)
    assert job['source_sha256']==sha(source)
    assert '参考图1锁定最终构图' in job['prompt'] and '参考图2提供原始人物' in job['prompt']
    assert '不能保留为背景条带' in job['prompt'] and '不重新放大人物' in job['prompt']
    assert '四周额外的自然背景间距' in job['prompt'] and '均不贴边' in job['prompt']
    assert '蓝框' not in job['prompt'] and '白色辅助边带' in job['prompt']
    assert job['background_plan']['version']==3 and job['background_plan']['unmarked_canvas']
    assert '正文逐字保留："遇到不会的题"' in job['prompt'] and '按钮文字逐字保留："立即体验"' in job['prompt']
    assert '"t1"' not in job['prompt'] and '"cta"' not in job['prompt']
    assert '遇到不会的题' in job['prompt'] and str(tmp_path) not in job['prompt']
    assert background.prepare_job(run,source,raw,1400,340,job['allowed_text'])==job


def test_same_source_and_exact_target_ratio_can_share_model_repair_across_pixel_sizes(tmp_path):
    source=picture(tmp_path/'source.png');run=dict(mode='simulation',params={'image_model':GPT_IMAGE_26_FLARE})
    first=background.prepare_job(run,source,tmp_path/'one.png',1400,340,{'t1':'原文'})
    second=background.prepare_job(run,source,tmp_path/'two.png',2800,680,{'t1':'原文'})
    assert first['reuse_key']==second['reuse_key']
    assert first['guide_sha256']==second['guide_sha256'] and first['prompt']==second['prompt']
    other_ratio=background.prepare_job(run,source,tmp_path/'three.png',1200,350,{'t1':'原文'})
    other_text=background.prepare_job(run,source,tmp_path/'four.png',1400,340,{'t1':'新文'})
    assert other_ratio['reuse_key']!=first['reuse_key'] and other_text['reuse_key']!=first['reuse_key']


def test_no_padding_and_threshold_checks_are_geometry_only_and_do_not_claim_content_detection():
    exact=background.plan(1536,512,1200,400,GPT_IMAGE_26_FLARE)
    assert exact['padding_percent']==0 and exact['crop_percent']==0
    assert not exact['background_needed'] and not exact['requires_ai_repair']
    assert exact['unmarked_canvas']
    threshold=background.plan(100,100,100,108,GPT_IMAGE_26_FLARE,threshold_percent=8)
    assert threshold['padding_percent']<8 and not threshold['background_needed']
    assert threshold['requires_ai_repair']
    prompt=background.repair_prompt({},exact)
    assert '本张无广告正文' in prompt and '本张无独立按钮' in prompt


@pytest.mark.parametrize('sizes',[(0,512,1400,340),(1536,-1,1400,340),(1536,512,False,340),(1536,512,100000,100000)])
def test_invalid_dimensions_fail_as_user_errors(sizes):
    with pytest.raises(UserError):background.plan(*sizes,GPT_IMAGE_26_FLARE)


@pytest.mark.parametrize('text',[{'logo':'Logo'}, {'t1':[]},{'feature_label':'不应出现'},['一句文案'],{'cta':'x'*1001}])
def test_repair_text_is_only_confirmed_body_and_cta(text):
    p=background.plan(1536,512,1400,340,GPT_IMAGE_26_FLARE)
    with pytest.raises(UserError):background.repair_prompt(text,p)


@pytest.mark.parametrize('version',[1,2])
def test_retired_geometry_versions_are_not_accepted(version):
    with pytest.raises(UserError,match='停用'):
        background.plan(1536,512,1400,340,GPT_IMAGE_26_FLARE,version=version)
