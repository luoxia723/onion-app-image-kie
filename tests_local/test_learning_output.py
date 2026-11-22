import copy
import hashlib

import pytest
from PIL import Image

from local_app.config import Settings,UserError
from local_app import learning_logo,learning_mask
from local_app.learning_output import export_output


def frozen(tmp_path,pid):
    settings=Settings(tmp_path/'state',tmp_path/'test.env')
    return learning_logo.freeze_templates(settings,[pid]),{pid:learning_mask.preset_for(pid)}


def test_export_uses_gray_mask_at_exact_dimensions_and_preserves_source(tmp_path):
    pid='learning-youxuepai-masked-840x404';logo,mask=frozen(tmp_path,pid)
    source=tmp_path/'source.png';target=tmp_path/'output.png';Image.new('RGB',(2000,1000),'white').save(source)
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    result=export_output(source,target,pid,logo,mask_snapshot=mask,protected_regions=[(.2,.2,.6,.6)])
    with Image.open(target) as image:
        assert image.format=='PNG' and image.size==(840,404)
        assert image.convert('RGBA').getpixel((400,50))==(255,255,255,255)
        assert 140<=image.getpixel((400,403))[0]<=155
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    assert result['exact_size_verified'] and not result['badge_applied']
    assert result['processing_order']==['exact_crop_and_resize','bottom_gray_mask','placement_logo','rounded_corners']


def test_deferred_featured_card_keeps_only_logo_and_rounded_alpha(tmp_path):
    pid='learning-dsl-rounded-card-484x580';logo,mask=frozen(tmp_path,pid)
    source=tmp_path/'source.png';target=tmp_path/'output.png';Image.new('RGB',(1000,1250),'#ccddee').save(source)
    result=export_output(source,target,pid,logo,mask_snapshot=mask)
    with Image.open(target) as image:
        assert image.size==(484,580)
        assert image.getpixel((0,0))[3]==0
        assert image.getpixel((40,70))==(204,221,238,255)
    assert result['logo']['logo_applied'] and result['corner_radius']==44
    assert not result['badge_applied'] and not result['feature_label_drawn']


def test_rounded_card_has_one_clean_alpha_transition(tmp_path):
    pid = 'learning-dsl-rounded-card-484x580'
    logo, mask = frozen(tmp_path, pid)
    source, target = tmp_path / 'source.png', tmp_path / 'card.png'
    Image.new('RGB', (484, 580), '#efb973').save(source)

    export_output(source, target, pid, logo, mask_snapshot=mask)

    with Image.open(target) as card:
        alpha = card.convert('RGBA').getchannel('A')
    # From outside the arc toward the opaque area, coverage can only increase.
    for y in range(45):
        row = [alpha.getpixel((x, y)) for x in range(46)]
        assert row == sorted(row)
    assert alpha.crop((0, 0, 44, 44)).tobytes() == alpha.crop((440, 0, 484, 44)).transpose(
        Image.Transpose.FLIP_LEFT_RIGHT).tobytes()
    assert alpha.getpixel((44, 0)) == alpha.getpixel((0, 44)) == 255
    for x, y in ((15, 10), (17, 8), (16, 9), (20, 6)):
        # Independently measure the approved 44 px circle at subpixel scale.
        covered = sum((44 - x - (i + 0.5) / 64) ** 2 + (44 - y - (j + 0.5) / 64) ** 2 <= 44 ** 2
                      for i in range(64) for j in range(64))
        assert abs(alpha.getpixel((x, y)) - 255 * covered / 4096) <= 5
    assert target.stat().st_size < 100 * 1024


def test_same_coverage_can_retain_different_rounded_edge_colors():
    from local_app.learning_output import _AlphaPalette

    red, blue = (232, 72, 48, 191), (45, 104, 207, 191)
    image = Image.new('RGBA', (6, 1))
    image.putdata([red, red, blue, blue, (100, 120, 140, 255), (0, 0, 0, 0)])
    indexed = Image.new('P', image.size)
    indexed.putpalette([100, 120, 140])

    result = _AlphaPalette(image, local_edge_colors=True).apply(indexed).convert('RGBA')

    assert result.tobytes() == image.tobytes()


def test_export_refuses_unsafe_crop_without_replacing_existing_output(tmp_path):
    pid='learning-baidu-1200x400';logo,mask=frozen(tmp_path,pid)
    source=tmp_path/'source.png';target=tmp_path/'output.png';Image.new('RGB',(1000,1000),'white').save(source)
    target.write_bytes(b'previous version')
    with pytest.raises(UserError,match='重要内容'):
        export_output(source,target,pid,logo,mask_snapshot=mask,protected_regions=[(0,0,1,1)])
    assert target.read_bytes()==b'previous version'
    assert not list(tmp_path.glob('.learning-export-*'))


def test_impossible_png_size_limit_does_not_shrink_pixels_or_replace_previous_output(tmp_path):
    import random
    from local_app.learning_pipeline import CONTENT_BY_ID

    pid='learning-dsl-resource-484x580';logo,mask=frozen(tmp_path,pid)
    source=tmp_path/'source.png';target=tmp_path/'output.png'
    # Keep the failure case stable as additional encoders improve compression.
    spec = {**CONTENT_BY_ID[pid], 'max_file_size_kb': 1}
    Image.frombytes('RGB',(484,580),random.Random(7).randbytes(484*580*3)).save(source)
    before=source.read_bytes();target.write_bytes(b'previous exported version')
    with pytest.raises(UserError,match='超过.*PNG大小限制'):
        export_output(source,target,pid,logo,mask_snapshot=mask,placement_snapshot=spec)
    assert source.read_bytes()==before
    assert target.read_bytes()==b'previous exported version'
    assert not list(tmp_path.glob('.learning-export-*'))


def test_export_uses_frozen_mask_instead_of_later_preset_edits(tmp_path,monkeypatch):
    pid='learning-youxuepai-masked-840x404';logo,mask=frozen(tmp_path,pid)
    source=tmp_path/'source.png';Image.new('RGB',(840,404),'white').save(source)
    first=tmp_path/'first.png';second=tmp_path/'second.png'
    export_output(source,first,pid,logo,mask_snapshot=mask)
    changed=copy.deepcopy(mask[pid]);changed['max_opacity']=.9
    monkeypatch.setattr(learning_mask,'preset_for',lambda _:changed)
    export_output(source,second,pid,logo,mask_snapshot=mask)
    assert first.read_bytes()==second.read_bytes()


def test_all_compiled_fixed_ratio_crops_export_to_exact_delivery_pixels(tmp_path):
    from local_app.learning_pipeline import CONTENT_BY_ID, preview
    from local_app.learning_prompts import build
    from local_app.learning_sizing import export_exact
    from kie_model import GPT_IMAGE_26_FLARE
    plan=build(preview({'t1':'不会的题拍一下','ip':'none','font':'none'},seed='all-fixed-crops'),GPT_IMAGE_26_FLARE)
    sources={}
    for output in plan['outputs']:
        ratio=output['aspect_ratio']
        if ratio not in sources:
            a,b=map(int,ratio.split(':'));sources[ratio]=tmp_path/(ratio.replace(':','-')+'.png')
            Image.new('RGB',(a*32,b*32),'white').save(sources[ratio])
        target=tmp_path/(output['output_id'].replace('::','-')+'.png')
        spec=CONTENT_BY_ID[output['placement_id']]
        width,height=output['target_width'],output['target_height']
        result=export_exact(sources[ratio],target,spec.get('artwork_width',width),height,crop_box=output['crop_box'])
        with Image.open(target) as image:assert image.size==(spec.get('artwork_width',width),height)
        assert result['exact_size_verified']
    assert len(plan['outputs'])==45


def test_unmasked_banner_has_exact_solid_right_panel_and_preserves_left_artwork(tmp_path):
    from PIL import ImageDraw
    pid='learning-youxuepai-unmasked-840x404';logo,mask=frozen(tmp_path,pid)
    source=tmp_path/'art.png';target=tmp_path/'banner.png'
    art=Image.new('RGB',(644,404),'#89cbd4')
    ImageDraw.Draw(art).rectangle((60,60,590,320),fill='#fff5cf')
    art.save(source)
    result=export_output(source,target,pid,logo,mask_snapshot=mask)
    with Image.open(target) as image:
        assert image.size==(840,404)
        assert image.crop((0,0,644,404)).convert('RGB').tobytes()==art.tobytes()
        right=image.crop((644,0,840,404))
        assert right.getcolors()==[(196*404,tuple(result['sizing']['right_panel']['fill_rgb']))]
    assert not result['logo']['logo_applied'] and not result['mask']['mask_applied']


def test_limited_png_uses_exact_palette_before_color_reduction(tmp_path):
    import random
    from local_app.learning_pipeline import CONTENT_BY_ID
    pid='learning-bbg-cover-216x260';logo,mask=frozen(tmp_path,pid)
    palette=[(16,68,220),(197,54,21),(9,212,87),(221,212,211)]
    image=Image.new('RGB',(216,260))
    image.putdata(random.Random(19).choices(palette,k=image.width*image.height))
    source=tmp_path/'source.png';target=tmp_path/'export.png'
    image.save(source,optimize=True)
    assert source.stat().st_size>18*1024
    spec={**CONTENT_BY_ID[pid],'max_file_size_kb':18,'file_size_operator':'lt'}
    result=export_output(source,target,pid,logo,mask_snapshot=mask,placement_snapshot=spec)
    with Image.open(target) as output:
        assert output.convert('RGB').tobytes()==image.tobytes()
    assert result['palette_colors']==4 and result['pixel_lossless'] and result['bytes']<18*1024


def test_indexed_byte_limit_keeps_size_and_prioritizes_logo_colors(tmp_path):
    import numpy as np
    pid='learning-dsl-banner-830x250';logo,mask=frozen(tmp_path,pid)
    source=tmp_path/'colorful.png';target=tmp_path/'delivery.png'
    # Coarse textured regions represent compressible artwork. Full-resolution
    # entropy remains a separate rejection case, not a promise of arbitrary
    # noise fitting the channel budget without quality loss.
    Image.fromarray(np.random.default_rng(7).integers(0,256,(250,415,3),dtype=np.uint8)).resize((830,250),Image.Resampling.NEAREST).save(source)
    assert source.stat().st_size>200*1024
    result=export_output(source,target,pid,logo,mask_snapshot=mask)
    assert result['palette_colors'] is not None and target.stat().st_size<200*1024
    with Image.open(target) as image:
        assert image.size==(830,250)
        aid=result['logo']['logo_asset_id'];x,y,w,h=result['logo']['pixel_box']
        with Image.open(logo['assets'][aid]['path']) as mark:
            mark=mark.convert('RGBA').resize((w,h),Image.Resampling.LANCZOS)
            px,py=next((px,py) for py in range(h) for px in range(w) if mark.getpixel((px,py))[3]==255)
            actual=image.convert('RGBA').getpixel((x+px,y+py));expected=mark.getpixel((px,py))
            # Indexed PNG is a color reduction, not lossless RGB storage. Keep
            # the brand's color close instead of allowing a noisy picture to
            # consume the whole palette and turn the blue mark into purple.
            assert actual[3]==expected[3]==255
            assert max(abs(a-b) for a,b in zip(actual[:3],expected[:3]))<=12


def test_transparent_textured_png_can_use_palette_without_shrinking_or_losing_rounding(tmp_path):
    import random
    pid='learning-dsl-rounded-card-484x580';logo,mask=frozen(tmp_path,pid)
    source=tmp_path/'textured.png';target=tmp_path/'rounded.png'
    Image.frombytes('RGB',(242,290),random.Random(29).randbytes(242*290*3)).resize((484,580),Image.Resampling.NEAREST).save(source)
    before=source.read_bytes()
    result=export_output(source,target,pid,logo,mask_snapshot=mask)
    assert result['encoding_method']=='indexed' and result['bytes']<100*1024
    assert source.read_bytes()==before
    with Image.open(target) as image:
        assert image.format=='PNG' and image.size==(484,580)
        rgba=image.convert('RGBA');assert rgba.getpixel((0,0))[3]==0
        assert rgba.getpixel((242,290))[3]==255


def test_pngquant_candidates_keep_original_alpha_after_rgb_quantization(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from local_app import learning_output
    image = Image.new('RGBA', (32, 16), '#4b83de')
    alpha = Image.new('L', image.size)
    alpha.putdata([value for y in range(image.height) for value in [0, 64, 192]+[255]*29])
    image.putalpha(alpha)
    monkeypatch.setattr(learning_output.shutil, 'which', lambda _: 'pngquant')
    dithers = []

    def encode(argv, **options):
        dithers.append(next(arg for arg in argv if arg.startswith('--floyd=')))
        with Image.open(argv[-1]) as source:
            assert source.mode == 'RGB'
            indexed = source.quantize(colors=4)
            indexed.save(argv[argv.index('--output')+1], 'PNG')
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(learning_output.subprocess, 'run', encode)
    candidates = list(learning_output._pngquant_candidates(
        image.convert('RGB'), learning_output._AlphaPalette(image), None, 2048, tmp_path))
    assert set(dithers) == {'--floyd=0', '--floyd=0.35', '--floyd=1'}
    assert len(candidates) == 3
    from io import BytesIO
    for _, data, _, _, _ in candidates:
        with Image.open(BytesIO(data)) as output:
            assert output.size == image.size and output.format == 'PNG'
            assert output.convert('RGBA').getchannel('A').tobytes() == alpha.tobytes()


def test_joint_png_compacts_palette_and_preserves_transparency(tmp_path, monkeypatch):
    from io import BytesIO
    from types import SimpleNamespace

    from local_app import learning_output

    image = Image.new('RGBA', (32, 16), '#2077c8')
    alpha = Image.new('L', image.size, 255)
    alpha.putpixel((0, 0), 0)
    alpha.putpixel((1, 0), 80)
    image.putalpha(alpha)
    monkeypatch.setattr(learning_output.shutil, 'which',
                        lambda program: program if program == 'onion-learning-png' else None)
    attempts = []

    def encode(argv, **options):
        from pathlib import Path

        assert Path(argv[1]).read_bytes() == image.convert('RGB').tobytes()
        assert argv[2:4] == ['32', '16'] and argv[-1] in ('min', 'joint')
        attempts.append(argv[0])
        return SimpleNamespace(stdout=b'\x00\x01' + bytes([32, 119, 200]) * 256 + b'\xff' * 512)

    monkeypatch.setattr(learning_output.subprocess, 'run', encode)
    candidates = list(learning_output._joint_png_candidates(
        image.convert('RGB'), learning_output._AlphaPalette(image), None, 2048, tmp_path))

    assert attempts and candidates
    for _, data, colors, compressor, _ in candidates:
        with Image.open(BytesIO(data)) as output:
            assert output.size == image.size and output.format == 'PNG' and len(data) <= 2048
            assert output.convert('RGBA').tobytes() == image.tobytes()
        assert colors == 1 and compressor == 'zenquant'
