from pathlib import Path
import json
import sys
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import render


def test_request_matches_provider_contract():
    request=render.build_create_request(render.DEFAULT_API_BASE,'fake','prompt','9:16','1K',['https://example.invalid/ref.png'])
    payload=json.loads(request.data)
    assert request.full_url == 'https://api.kie.ai/api/v1/jobs/createTask'
    assert payload['model']=='gpt-image-2-5-sunburst-image-to-image'
    assert payload['input']['input_urls']==['https://example.invalid/ref.png']
    assert payload['input']['resolution']=='1K'
    assert payload['input']['background']=='opaque'


@pytest.mark.parametrize('ratio',['2:1','1:2','auto'])
def test_request_rejects_unsupported_or_uncontrolled_ratios(ratio):
    with pytest.raises(ValueError,match='aspect_ratio'):
        render.build_create_request(render.DEFAULT_API_BASE,'fake','prompt',ratio,'1K',['https://example.invalid/ref.png'])


def test_geometry_flags_tall_ximalaya_and_uses_1k_only_ratios():
    from kie_model import geometry_report
    tall=geometry_report(720,1559)
    assert tall['aspect_ratio']=='9:16'
    assert tall['crop_percent']==pytest.approx(17.9,abs=.01)
    assert tall['crop_axis']=='左右'
    assert tall['needs_safe_area']
    assert geometry_report(474,768)['aspect_ratio']=='16:27'
    assert geometry_report(984,422)['aspect_ratio']=='21:9'
    assert geometry_report(1280,720)['crop_percent']==0
    assert geometry_report(1200,480)['needs_safe_area']
    assert geometry_report(690,360)['needs_safe_area']
    assert not geometry_report(474,768)['needs_safe_area']
