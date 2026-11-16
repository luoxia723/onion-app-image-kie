import copy
from fractions import Fraction
import hashlib
from pathlib import Path
import socket

from PIL import Image,ImageDraw
import pytest

from local_app import master_canvas as canvas
from local_app.config import UserError
from kie_model import GPT_IMAGE_26_FLARE,MODEL,aspect_ratios


def target(id,w,h,**changes):
    return {**dict(id=id,target_width=w,target_height=h,source_index=1,image_form='单图',
        content_signature='same-scene',allowed_text={'t1':'看清思路','cta':'点击体验'}),**changes}


def source(path,size=(1536,864)):
    image=Image.new('RGB',size,(33,88,99));draw=ImageDraw.Draw(image)
    draw.rectangle((size[0]*.25,size[1]*.25,size[0]*.75,size[1]*.75),fill=(210,60,80))
    image.save(path,'PNG');return path


def test_eight_similar_learning_banners_share_one_full_native_and_independent_frozen_crops():
    sizes=[(1400,520),(1372,480),(2880,1020),(1224,408),(830,250),(1200,350),(1280,348),(1400,340)]
    result=canvas.plan([target(str(i),w,h) for i,(w,h) in enumerate(sizes)],GPT_IMAGE_26_FLARE)
    assert result['counts']==dict(master_count=1,planned_image_calls=1,delivery_count=8)
    group=result['groups'][0]
    assert group['aspect_ratio']=='3:1' and group['guide_size']==[1536,512]
    assert group['shared_keep_box']==pytest.approx([2/39,19/140,37/39,121/140])
    assert group['shared_keep_fraction']==pytest.approx(17/26)
    assert group['margin_per_side']==.12
    x1,y1,x2,y2=group['shared_keep_box'];safe=group['content_safe_box']
    assert safe==pytest.approx([x1+(x2-x1)*.12,y1+(y2-y1)*.12,x2-(x2-x1)*.12,y2-(y2-y1)*.12])
    assert len({tuple(o['crop_box']) for o in result['outputs']})>1
    for output in result['outputs']:
        assert output['master_id']==group['id'] and output['source_index']==1
        bx1,by1,bx2,by2=output['crop_box']
        assert (bx2-bx1)*3/(by2-by1)==pytest.approx(output['target_width']/output['target_height'])
        assert safe[0]>bx1 and safe[1]>by1 and safe[2]<bx2 and safe[3]<by2


def test_content_cta_subtitle_visual_signature_and_story_slot_are_not_cross_shared():
    rows=[target('one',1280,720),target('same',1005,564),
          target('new-copy',1280,720,allowed_text={'t1':'另一句话','cta':'点击体验'}),
          target('no-cta',1280,720,allowed_text={'t1':'看清思路'}),
          target('subtitle',1280,720,allowed_text={'t1':'看清思路','subtitle':'只属于此图','cta':'点击体验'}),
          target('new-look',1280,720,content_signature={'style':'other-frozen-style'}),
          target('story-two',1280,720,source_index=2,image_form='双图'),
          target('story-one',1280,720,source_index=1,image_form='双图'),
          target('different-source',1280,720,source_key='other-source-sha')]
    result=canvas.plan(rows,GPT_IMAGE_26_FLARE)
    assert len(result['groups'])==8
    together=next(g for g in result['groups'] if 'one' in g['target_ids'])
    assert set(together['target_ids'])=={'one','same'}
    for group in result['groups']:
        assert len({(r['content_key'],r['source_index'],r['image_form']) for r in group['targets']})==1


def test_complete_three_image_story_keeps_three_distinct_sources_for_every_delivery_size():
    rows=[]
    for index in (1,2,3):
        for size in [(1280,720),(1005,564)]:
            rows.append(target(str(index)+'-'+str(size),*size,source_index=index,image_form='三图',allowed_text={'t1':'相同字句也不能合并剧情'}))
    result=canvas.plan(rows,GPT_IMAGE_26_FLARE)
    assert result['counts']['master_count']==3 and result['counts']['delivery_count']==6
    assert {g['source_index'] for g in result['groups']}=={1,2,3}
    assert all(len(g['targets'])==2 for g in result['groups'])


def test_logo_presence_does_not_split_same_content_master():
    rows=[target('logo',1280,720,logo_required=True),target('no-logo',1280,720,logo_required=False)]
    group=canvas.plan(rows,GPT_IMAGE_26_FLARE)['groups'][0]
    assert set(group['target_ids'])=={'logo','no-logo'}


def test_direction_and_excessive_ratio_spread_split_but_unavoidable_single_crop_stays_valid():
    rows=[target('portrait',400,480),target('square',512,512),target('landscape',1200,400)]
    result=canvas.plan(rows,GPT_IMAGE_26_FLARE)
    assert len(result['groups'])==3
    assert {g['direction'] for g in result['groups']}=={'portrait','square','landscape'}
    spread=canvas.plan([target('narrow',1250,1000),target('middle',1500,1000),target('wide',3000,1000)],GPT_IMAGE_26_FLARE)
    assert len(spread['groups'])==2
    unavoidable=canvas.plan([target('ultrawide',1400,340),target('similar',1200,350)],GPT_IMAGE_26_FLARE,min_shared_area=.9)
    assert len(unavoidable['groups'])==1
    assert unavoidable['groups'][0]['max_target_crop_percent']==pytest.approx(100*19/70)
    assert unavoidable['groups'][0]['shared_keep_fraction']<.9


def test_visible_mask_region_influences_shared_content_safety_not_outer_crop():
    group=canvas.plan([target('masked',840,404,visible_box=[0,0,1,.72]),target('plain',840,404)],GPT_IMAGE_26_FLARE)['groups'][0]
    crop=group['targets'][0]['crop_box'];visible=group['shared_visible_box']
    assert visible[3]==pytest.approx(crop[1]+.72*(crop[3]-crop[1]))
    assert group['content_safe_box'][3]<visible[3]
    split=canvas.plan([target('left',1000,1000,visible_box=[0,0,.4,1]),target('right',1000,1000,visible_box=[.6,0,1,1])],GPT_IMAGE_26_FLARE)
    assert len(split['groups'])==2


def test_native_choice_maximizes_common_retained_area_and_balances_individual_crop():
    group=canvas.plan([target('two',1000,500),target('three',1200,400)],GPT_IMAGE_26_FLARE)['groups'][0]
    assert group['aspect_ratio']=='21:9'
    assert group['shared_keep_fraction']==pytest.approx(2/3)
    assert group['max_target_crop_percent']==pytest.approx(100*2/9)
    for model in [MODEL,GPT_IMAGE_26_FLARE]:
        result=canvas.plan([target('one',1400,340),target('two',1536,1708)],model)
        assert all(g['aspect_ratio'] in aspect_ratios(model) for g in result['groups'])


def test_guide_is_full_colored_unmarked_natural_canvas(tmp_path,monkeypatch):
    def forbidden(*a,**k):raise AssertionError('pure helper cannot call network')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    group=canvas.plan([target('wide',1400,340),target('near',1200,350)],GPT_IMAGE_26_FLARE)['groups'][0]
    original=source(tmp_path/'original.png');original_bytes=original.read_bytes()
    path=tmp_path/'guide.png';guide=canvas.build_guide(original,path,group)
    assert guide['guide_only'] and guide['unmarked_canvas']
    assert guide['full_source_preserved_in_guide'] and not guide['source_cropped_in_guide']
    with Image.open(path) as image:
        assert image.size==tuple(group['guide_size'])
        assert {image.getpixel(p) for p in [(0,0),(image.width-1,0),(0,image.height-1),(image.width-1,image.height-1)]}=={(33,88,99)}
    box=guide['source_inner_box'];safe=group['content_safe_box']
    assert box[0]>=safe[0]-1e-12 and box[1]>=safe[1]-1e-12 and box[2]<=safe[2]+1e-12 and box[3]<=safe[3]+1e-12
    assert original.read_bytes()==original_bytes
    assert canvas.build_guide(original,path,group)==guide
    path.write_bytes(b'existing different guide')
    with pytest.raises(UserError,match='原文件已保留'):canvas.build_guide(original,path,group)
    assert path.read_bytes()==b'existing different guide'


def test_prompt_requires_entire_native_natural_and_preserves_actual_copy_subtitle_and_cta():
    text={'t1':'洋葱学园帮助看清思路','subtitle':'逐步理解','cta':'立即体验'}
    group=canvas.plan([target('wide',1400,340,allowed_text=text)],GPT_IMAGE_26_FLARE)['groups'][0]
    prompt=canvas.repair_prompt(text,group)
    assert '连续场景一直画满四边' in prompt and '不留制作辅助线或外部白带' in prompt
    assert '参考图1是布局草稿' in prompt and '参考图2提供本张人物' in prompt
    assert '旧Logo及其附属标准字' in prompt and '确认正文中的相同字样仍逐字保留' in prompt
    assert '正文逐字呈现："洋葱学园帮助看清思路"' in prompt
    assert '合计最多占画布宽度' in prompt and '按钮的完整外框与投影' in prompt
    assert '副标题逐字呈现："逐步理解"' in prompt and '按钮文字逐字呈现："立即体验"' in prompt
    assert '"t1"' not in prompt and '"subtitle"' not in prompt and 'content_safe_box' not in prompt
    with pytest.raises(UserError,match='冻结内容不一致'):canvas.repair_prompt({'t1':'被偷换的文字'},group)
    pure=canvas.plan([target('pure',400,480,allowed_text={})],GPT_IMAGE_26_FLARE)['groups'][0]
    assert '无广告正文' in canvas.prompt({},pure) and '无独立按钮' in canvas.prompt({},pure)


def test_multiple_exact_exports_preserve_square_geometry_without_padding_or_cv_detection(tmp_path):
    group=canvas.plan([target('wide',900,300),target('near',1000,350)],GPT_IMAGE_26_FLARE)['groups'][0]
    assert group['aspect_ratio']=='3:1'
    width,height=group['guide_size'];raw=tmp_path/'provider.png';image=Image.new('RGB',(width,height),(33,88,99))
    ImageDraw.Draw(image).rectangle((width//2-50,height//2-50,width//2+49,height//2+49),fill=(255,0,0));image.save(raw)
    original=raw.read_bytes()
    for row in group['targets']:
        result=canvas.crop_ai_result(raw,tmp_path/(row['id']+'.png'),group,row['id'])
        assert result['background_fill']=='none' and not result['stretch_applied'] and not result['cv_detection_performed']
        assert result['crop_box']==row['crop_box'] and result['source_index']==1
        with Image.open(result['path']) as finished:
            assert finished.format=='PNG' and finished.size==(row['target_width'],row['target_height'])
            mask=finished.point(lambda value:255 if value>235 else 0).split()[0]
            # Teal background red=33, the red square is >235. Uniform resize
            # must retain equal horizontal and vertical extents after each crop.
            box=mask.getbbox();assert box and abs((box[2]-box[0])-(box[3]-box[1]))<=1
        actual=result['actual_source_crop_box']
        assert (actual[2]-actual[0])*width/((actual[3]-actual[1])*height)==pytest.approx(row['target_width']/row['target_height'])
    assert raw.read_bytes()==original


def test_export_accepts_provider_one_pixel_rounding_but_rejects_wrong_native_ratio(tmp_path):
    group=canvas.plan([target('wide',1400,340)],GPT_IMAGE_26_FLARE)['groups'][0]
    raw=tmp_path/'native.png';Image.new('RGB',(1537,512),'#123456').save(raw)
    result=canvas.crop_ai_result(raw,tmp_path/'output.png',group,'wide')
    assert result['native_ratio_deviation_percent']<.5
    box=result['actual_source_crop_box']
    assert (box[2]-box[0])*1537/((box[3]-box[1])*512)==pytest.approx(1400/340)
    Image.new('RGB',(1536,1024),'#123456').save(raw);data=raw.read_bytes()
    with pytest.raises(UserError,match='请求画幅不符'):canvas.crop_ai_result(raw,tmp_path/'wrong.png',group,'wide')
    assert not (tmp_path/'wrong.png').exists() and raw.read_bytes()==data


def test_grouping_is_nonmutating_stable_for_reordered_input_and_respects_explicit_margin():
    rows=[target('one',1400,520),target('two',1400,340),target('three',1280,348)]
    before=copy.deepcopy(rows)
    original=canvas.plan(rows,GPT_IMAGE_26_FLARE,margin=.10)
    reversed_plan=canvas.plan(list(reversed(rows)),GPT_IMAGE_26_FLARE,margin=.10)
    assert original==reversed_plan and rows==before
    assert original['groups'][0]['margin_per_side']==.10


def test_forged_geometry_or_wrong_target_does_not_overwrite_sources(tmp_path):
    group=canvas.plan([target('wide',1400,340)],GPT_IMAGE_26_FLARE)['groups'][0]
    raw=source(tmp_path/'source.png',(1536,512));original=raw.read_bytes()
    forged=copy.deepcopy(group);forged['targets'][0]['crop_box']=[0,0,1,1]
    with pytest.raises(UserError,match='裁框已变化'):canvas.crop_ai_result(raw,tmp_path/'bad.png',forged,'wide')
    with pytest.raises(UserError,match='不包含该交付'):canvas.crop_ai_result(raw,tmp_path/'bad.png',group,'unknown')
    with pytest.raises(UserError,match='不能覆盖模型原图'):canvas.crop_ai_result(raw,raw,group,'wide')
    with pytest.raises(UserError,match='不能覆盖来源'):canvas.build_guide(raw,raw,group)
    assert raw.read_bytes()==original and not (tmp_path/'bad.png').exists()


@pytest.mark.parametrize('change',[{'target_width':0},{'target_height':False},{'source_index':0},{'allowed_text':{'t1':[]}},
    {'content_signature':[]},{'content_mode':'pure'},{'visible_box':[.8,0,.2,1]}])
def test_invalid_target_contracts_are_user_errors(change):
    with pytest.raises(UserError):canvas.plan([target('bad',1400,340,**change)],GPT_IMAGE_26_FLARE)


@pytest.mark.parametrize('options',[{'margin':0},{'margin':.2},{'max_ratio_spread':.9},{'min_shared_area':0},{'min_shared_area':2}])
def test_invalid_grouping_policy_is_rejected(options):
    with pytest.raises(UserError):canvas.plan([target('a',1400,340)],GPT_IMAGE_26_FLARE,**options)


def test_all_current_learning_targets_have_real_exact_png_geometry_from_fewer_shared_canvases(tmp_path):
    # This is an export geometry exercise with synthetic native pictures, not
    # evidence that an AI has followed the scene/copy/Logo instructions.
    from local_app.learning_pipeline import CONTENT_BY_ID
    rows=[]
    for placement in CONTENT_BY_ID.values():
        text={}
        if placement['modules']['main_copy']:text['t1']='本轮确认文案'
        if placement['modules']['cta']:text['cta']='点击下载'
        for index in range(1,placement['image_count']+1):
            rows.append(target(placement['id']+'::'+str(index),placement['target_width'],placement['target_height'],
                content_signature='one-frozen-visual',allowed_text=text))
    result=canvas.plan(rows,GPT_IMAGE_26_FLARE)
    assert len(rows)==45 and result['counts']['delivery_count']==45
    assert result['counts']['master_count']<16
    expected={r['id']:(r['target_width'],r['target_height']) for r in rows};exported={}
    for group in result['groups']:
        raw=tmp_path/(group['id']+'-synthetic-native.png')
        Image.new('RGB',tuple(group['guide_size']),(33,88,99)).save(raw)
        before=raw.read_bytes()
        for row in group['targets']:
            path=tmp_path/('delivery-'+hashlib.sha256(row['id'].encode()).hexdigest()+'.png')
            output=canvas.crop_ai_result(raw,path,group,row['id'])
            with Image.open(path) as finished:
                assert finished.format=='PNG' and finished.size==expected[row['id']]
                assert finished.getextrema()==((33,33),(88,88),(99,99))
            exported[row['id']]=output
        assert raw.read_bytes()==before
    assert set(exported)==set(expected)


def test_source_with_existing_cta_is_explicitly_stripped_for_body_only_target(tmp_path):
    original=source(tmp_path/'existing-ad.png')
    with Image.open(original) as opened:image=opened.copy()
    draw=ImageDraw.Draw(image);draw.rounded_rectangle((600,620,1150,770),radius=30,fill='orange')
    draw.text((650,660),'OLD CTA DOWNLOAD',fill='black');image.save(original)
    body={'t1':'本次唯一确认正文'}
    group=canvas.plan([target('no-cta',1400,340,allowed_text=body)],GPT_IMAGE_26_FLARE)['groups'][0]
    guide=canvas.build_guide(original,tmp_path/'body-only-guide.png',group)
    assert guide['full_source_preserved_in_guide']
    prompt=canvas.repair_prompt(body,group)
    assert group['allowed_text']==body
    assert '正文逐字呈现："本次唯一确认正文"' in prompt
    assert '本张无独立按钮，不添加按钮或按钮文字' in prompt
    assert '广告正文、副标题、按钮及按钮文字全部移除，并补成自然连续背景' in prompt
    assert '数学题中的题干、公式和真实UI内文字不当作广告文案删除' in prompt
    assert '旧Logo及其附属标准字' in prompt and '制作标记' in prompt
    assert 'OLD CTA DOWNLOAD' not in prompt


@pytest.mark.parametrize('source_size,target_size',[((1536,864),(400,480)),((864,1536),(1280,720))])
def test_cross_direction_prompt_recomposes_scene_instead_of_locking_an_old_photo_strip(source_size,target_size):
    group=canvas.plan([target('new-direction',*target_size)],GPT_IMAGE_26_FLARE)['groups'][0]
    prompt=canvas.repair_prompt(group['allowed_text'],group,source_size=source_size)
    assert '原图排布仅供内容参考，按目标画幅重新安排人物和文字' in prompt
    assert '保持角色身份、故事瞬间与准确文案' in prompt
    assert '不要把旧画面作为横条照片或竖条贴片' in prompt
    assert '锁定主体缩小后的大小和位置' not in prompt
    assert '主体和全部确认文字集中在画面' in prompt
    assert '连续场景一直画满四边' in prompt
    assert '正文逐字呈现："看清思路"' in prompt
    assert '按钮文字逐字呈现："点击体验"' in prompt


def test_same_direction_prompt_keeps_small_complete_guide_layout_and_validates_source_size():
    group=canvas.plan([target('landscape',1400,340)],GPT_IMAGE_26_FLARE)['groups'][0]
    same=canvas.repair_prompt(group['allowed_text'],group,source_size=(1536,864))
    assert '锁定主体缩小后的大小和位置' in same
    assert '按目标画幅重新安排人物和文字' not in same
    assert canvas.prompt(group['allowed_text'],group,source_size=(1536,864))==same
    for size in [(0,500),(800,False),(1000,),{'width':1000}]:
        with pytest.raises(UserError):canvas.repair_prompt(group['allowed_text'],group,source_size=size)
