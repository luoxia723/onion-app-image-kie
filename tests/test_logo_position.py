from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from logo_reference import build_logo_reference, logo_position, logo_prompt_rule, validate_manifest_logo


@pytest.mark.parametrize('platform,size,expected',[
    ('喜马拉雅','720x1280','上方居中'),
    ('喜马拉雅','720x1559','上方居中'),
    ('喜马拉雅','1280x720','左上角'),
    ('喜马拉雅','1000x1000','左上角'),
    ('VIVO','720x1280','左上角'),
])
def test_logo_placement_exception(platform,size,expected):
    width,height=map(int,size.split('x'))
    config={'logo':'洋葱学园','placements':[{'platform':platform,'target_width':width,'target_height':height}]}
    assert logo_position(config)==expected
    refs=[build_logo_reference(config)]
    valid={'jobs':[{'prompt':logo_prompt_rule(position=expected),'references':refs}]}
    assert validate_manifest_logo(valid,config)
    wrong='左上角' if expected=='上方居中' else '上方居中'
    with pytest.raises(ValueError,match='必须放在'):
        validate_manifest_logo({'jobs':[{'prompt':logo_prompt_rule(position=wrong),'references':refs}]},config)
    with pytest.raises(ValueError,match='指令冲突'):
        validate_manifest_logo({'jobs':[{'prompt':logo_prompt_rule(position=expected)+logo_prompt_rule(position=wrong),'references':refs}]},config)
