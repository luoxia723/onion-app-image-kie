"""Only drawing context crosses the new image prompt boundary; old receipts stay stable."""
import copy
import json
import pytest

from local_app.learning_pipeline import preview
from local_app.learning_prompts import build
from local_app.learning_runtime_support import compile_baseline
from scripts.kie_model import GPT_IMAGE_26_FLARE


def setup_context():
    compiled=build(preview({'t1':'拍题','ip':'none','font':'none','style':'craft-clay'},seed='context'),GPT_IMAGE_26_FLARE)
    scene={key:'视觉内容：'+key for key in compiled['scene_planning']['output_schema']['required']}
    scene['communication_goal']='传播任务，仅供规划节点，不转发图片模型'
    return {'compiled':compiled,'asset_bindings':[]},scene


def test_new_baseline_passes_visual_scene_fields_without_planning_bookkeeping():
    run,scene=setup_context()
    result=compile_baseline(run,scene)
    assert scene['communication_goal'] not in result['prompt']
    assert all(scene[key] in result['prompt'] for key in scene if key!='communication_goal')
    assert '场景规划（服务端已验证）数据' not in result['prompt']
    assert result['scene_plan']==scene


@pytest.mark.history
def test_legacy_baseline_template_keeps_exact_scene_serialization_for_request_recovery():
    run,scene=setup_context();run=copy.deepcopy(run)
    baseline=run['compiled']['baseline'];baseline.pop('prompt_contract_version',None)
    baseline['prompt']='历史冻结模板\n场景规划：〈生成基准图时填入场景方案〉'
    result=compile_baseline(run,scene)
    assert result['prompt']=='历史冻结模板\n场景规划（服务端已验证）数据：'+json.dumps(scene,ensure_ascii=False,sort_keys=True)
