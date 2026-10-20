"""CTA survives saved config -> prompt -> provider request as an actual button."""
import json
from pathlib import Path
import sys

import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import interactive_server as server
from positive_prompt import compose
import visual_directions as visual
import render
from logo_reference import build_logo_reference


def configured(count=1, cta='立即体验'):
    ids={1:'oppo-rich-horizontal-big-1280x720',2:'oppo-app-slot-slot-474x768',3:'oppo-app-slot-slot-320x210'}
    body={'request_id':'cta-flow','delivery_name':'CTA排查','placement_ids':[ids[count]],'sets':1,
          'cta':cta,'logo':'洋葱学园','ip':'不用','font_reference_enabled':False,
          'visual_style_mode':'coordinated','visual_direction':{'style_id':'commercial_anime'},
          'copy_refs':[{'copyDraftId':'math','mainTitle':'这周我想把数学补起来','subtitle':'洋葱AI按目标和基础排每日任务',
                        'short1':'这周我想把数学补起来','short2':'洋葱AI按目标和基础排每日任务','short3':'打开看今天学啥学完看进度'}]}
    cfg=server.normalize_config_result(body,server.slots_by_id())
    cfg['visual_concepts']=[{'name':'学生按任务开始学习','prompt':'窗边学生对照练习册和手机中的今日任务，握笔准备开始，标题位于上方留白。',
        'slot_actions':['学生拿着题页犹豫先学什么。','学生对照每日任务开始练习。','学生完成练习后查看进度。'][:count],
        'art_direction':{'world':'现代家庭','scene':'窗边学习桌','story':'从拿不准先学什么到按任务开始学习','composition':'人物手势引向屏幕与标题','lighting_materials':'自然窗光与柔和色块'},
        'learner_story':{'protagonist':'一位穿浅蓝上衣的原创初中学生','pain_point':'学生想补数学，却拿不准从哪章开始。','product_action':'按目标和基础安排每日任务','visible_change':'看清任务后开始练习'},
        'screen_text':[]}]
    return cfg


@pytest.mark.parametrize('count',[1,2,3])
def test_saved_cta_is_a_visible_button_in_every_provider_prompt(count):
    cfg=configured(count);d=visual.plan_directions(cfg)['directions'][0]
    assert cfg['cta']=='立即体验'
    for slot in range(1,count+1):
        refs=[build_logo_reference(cfg)] if slot==1 else [{'label':'参考图1','path':'base.png'}]
        prompt=compose(cfg,d,slot,refs)
        request=render.build_create_request('https://example.invalid','test-key',prompt,'16:9','1K',['https://example.invalid/reference.png'])
        actual=json.loads(request.data)['input']['prompt']
        assert 'CTA按钮' in actual
        assert '立即体验' in actual
        assert '底部' in actual and '按钮文字' in actual


def run_card(context, action='collect'):
    """Execute the real rendered card JS with DOM controls, then its save payload."""
    import re,shutil,subprocess
    node=shutil.which('node')
    if not node: pytest.skip('Node is needed to execute the actual config-card script')
    payload=server.build_config_payload('cta-ui',context)
    markup=server.build_config_html(payload)
    script=re.findall(r'<script>(.*?)</script>',markup,re.S)[-1]
    # Avoid boot UI work; call the actual controls and collection functions below.
    pos=script.rfind('renderAll();');script=script[:pos]+script[pos:].replace('renderAll();','',1)
    harness=r'''
const vm=require('vm'),fs=require('fs');const input=JSON.parse(fs.readFileSync(0,'utf8'));
const elements={};function element(id){return elements[id]??={value:'',checked:false,innerHTML:'',textContent:'',style:{},classList:{values:new Set(),toggle(k,enabled){if(enabled)this.values.add(k);else this.values.delete(k);},contains(k){return this.values.has(k);}}};}
const ctx={document:{getElementById:element},window:{location:{search:''}},URLSearchParams,console};
vm.createContext(ctx);vm.runInContext(input.script,ctx);
vm.runInContext("state.selectedSlotIds=['oppo-rich-horizontal-big-1280x720'];state.deliveryName='CTA排查';renderControls();",ctx);
if(input.action==='edit')vm.runInContext("document.getElementById('cta').value=' 立即体验 ';",ctx);
if(input.action==='clear')vm.runInContext("document.getElementById('cta').value='';",ctx);
const result=vm.runInContext('collectResult()',ctx);
process.stdout.write(JSON.stringify({result,visible:!element('ctaField').classList.contains('hidden'),summary:element('summary').innerHTML}));
'''
    result=subprocess.run([node,'-e',harness],input=json.dumps({'script':script,'action':action}),capture_output=True,text=True,check=True)
    return json.loads(result.stdout)


def test_config_card_cta_control_shows_and_preserves_input_through_save():
    actual=run_card({},'edit')
    assert actual['visible']
    assert 'CTA按钮' in actual['summary'] and '立即体验' in actual['summary']
    assert actual['result']['cta']=='立即体验'
    saved=server.normalize_config_result(actual['result'],server.slots_by_id())
    assert saved['cta']=='立即体验'


def test_config_card_keeps_upstream_cta_and_allows_user_to_clear_it():
    context={'image_form':'单图','platform':'OPPO','cta':'立即体验'}
    actual=run_card(context)
    assert actual['result']['cta']=='立即体验'
    assert run_card(context,'clear')['result']['cta']==''


@pytest.mark.parametrize('key',['ctaText','cta_text','CTA'])
def test_backend_preserves_confirmed_cta_aliases_and_trims_spaces(key):
    body=configured(cta='');body.pop('cta');body[key]=' 立即体验 '
    assert server.normalize_config_result(body,server.slots_by_id())['cta']=='立即体验'


def test_explicit_clear_wins_over_upstream_context():
    body=configured(cta='');body['context']={'cta':'立即体验'}
    assert server.normalize_config_result(body,server.slots_by_id())['cta']==''


def test_empty_cta_does_not_create_a_button_instruction():
    cfg=configured(cta='');d=visual.plan_directions(cfg)['directions'][0]
    assert 'cta' in cfg and cfg['cta']==''
    assert 'CTA按钮' not in compose(cfg,d,references=[build_logo_reference(cfg)])


def test_weakened_cta_text_only_is_rejected_before_submission():
    from cta_rules import prompt_rule
    from series_chain import validate_series
    cfg=configured();d=visual.plan_directions(cfg)['directions'][0]
    refs=[build_logo_reference(cfg)]
    prompt=compose(cfg,d,references=refs)
    job={'job_id':'one','set_id':d['set_id'],'slot':1,'copy_text':'这周我想把数学补起来\n洋葱AI按目标和基础排每日任务',
         'prompt':prompt,'references':refs,'output':'one.png','depends_on':[]}
    validate_series({'jobs':[job]},cfg)
    job['prompt']=prompt.replace(prompt_rule(cfg['cta']),'行动文案呈现“立即体验”。')
    with pytest.raises(ValueError,match='as a button'):validate_series({'jobs':[job]},cfg)


@pytest.mark.parametrize('policy,cta',[('required',''),('forbidden','立即体验')])
def test_server_respects_explicit_placement_cta_policy(policy,cta):
    slots=server.slots_by_id();slot='oppo-rich-horizontal-big-1280x720';slots[slot]={**slots[slot],'cta_policy':policy}
    with pytest.raises(ValueError,match='CTA'):
        server.normalize_config_result({'delivery_name':'CTA排查','placement_ids':[slot],'cta':cta},slots)


def test_cta_validation_also_applies_when_copy_metadata_is_absent():
    from series_chain import validate_series
    from cta_rules import prompt_rule
    cfg=configured();d=visual.plan_directions(cfg)['directions'][0]
    prompt=compose(cfg,d,references=[build_logo_reference(cfg)])
    cfg['copy_refs']=[]
    job={'job_id':'one','set_id':'one','slot':1,'prompt':prompt.replace(prompt_rule(cfg['cta']),'行动文案为“立即体验”。'),'depends_on':[]}
    with pytest.raises(ValueError,match='as a button'):validate_series({'jobs':[job]},cfg)
