from pathlib import Path
import argparse
import json
import sys
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import render

REFERENCE = Path(__file__).parents[1] / "assets/font-references/字体参考-01.png"


def args(tmp_path, approved=True):
    return argparse.Namespace(input_json=None, prompt='教育广告测试', aspect_ratio='1:1', size=None,
        resolution=None, quality=None, reference=[str(REFERENCE)], output=str(tmp_path/'工作区/产物/test.png'),
        api_base=None, upload_base=None, retries=1, poll_timeout=1,
        validate_only=False, approved_in_current_task=approved)


def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('ONION_IMAGE_WORKSPACE', str(tmp_path))
    monkeypatch.setenv('KIE_API_KEY','mock-key')
    monkeypatch.setattr(render, 'autoload_dotenv', lambda: None)
    monkeypatch.setattr(render, 'upload_references', lambda *a: ['https://example.invalid/font.png'])


def test_unknown_submission_never_resubmits(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    calls=[]
    def request(*a, **k):
        calls.append(1)
        raise render.KieError('invalid response')
    monkeypatch.setattr(render,'request_json',request)
    assert render.run(args(tmp_path)) == 3
    assert render.run(args(tmp_path)) == 3
    assert len(calls) == 1


def test_success_resume_does_not_create_again(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    calls=[]
    def request(*a,**k):
        calls.append(1)
        return {'data': {'taskId': 'mock-task'}}
    monkeypatch.setattr(render,'request_json',request)
    monkeypatch.setattr(render,'poll_task',lambda *a: ('https://example.invalid/image',{}))
    def download(url, path):
        from PIL import Image
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB',(16,16)).save(path)
        return path
    monkeypatch.setattr(render,'download_image',download)
    assert render.run(args(tmp_path)) == 0
    assert render.run(args(tmp_path)) == 0
    assert len(calls) == 1


def test_missing_approval_never_calls_api(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch)
    monkeypatch.setattr(render,'request_json',lambda *a,**k: pytest.fail('network called'))
    assert render.run(args(tmp_path,False)) == 2


def test_interrupted_submit_blocks_create(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch)
    a=args(tmp_path)
    fingerprint=render.request_fingerprint(render.MODEL,a.prompt,[REFERENCE],'1:1','1K')
    render.atomic_write_json(render.task_state_path(Path(a.output)),{'status':'submitting','fingerprint':fingerprint})
    monkeypatch.setattr(render,'request_json',lambda *a,**k: pytest.fail('duplicate submit'))
    assert render.run(a) == 3


def test_lock_rejects_concurrent_output(tmp_path):
    output=tmp_path/'candidate.png'
    with render.output_lock(output):
        with pytest.raises(render.KieError):
            with render.output_lock(output):
                pass


def test_request_matches_provider_contract():
    request=render.build_create_request(render.DEFAULT_API_BASE,'fake','prompt','9:16','1K',['https://example.invalid/ref.png'])
    payload=json.loads(request.data)
    assert request.full_url == 'https://api.kie.ai/api/v1/jobs/createTask'
    assert payload['model']=='gpt-image-2-5-sunburst-image-to-image'
    assert payload['input']['input_urls']==['https://example.invalid/ref.png']
    assert payload['input']['resolution']=='1K'
    assert payload['input']['background']=='opaque'


@pytest.mark.parametrize('resolution',['2K','4K'])
def test_more_expensive_tiers_are_rejected_before_network(tmp_path, monkeypatch, resolution):
    setup(tmp_path,monkeypatch)
    monkeypatch.setattr(render,'request_json',lambda *a,**k: pytest.fail('network called'))
    request=args(tmp_path)
    request.resolution=resolution
    assert render.run(request)==1


def test_missing_reference_cannot_fall_back_to_another_model(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch)
    monkeypatch.setattr(render,'request_json',lambda *a,**k: pytest.fail('network called'))
    request=args(tmp_path)
    request.reference=[]
    assert render.run(request)==1
    with pytest.raises(ValueError,match='reference image'):
        render.build_create_request(render.DEFAULT_API_BASE,'fake','prompt','9:16','1K',[])


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
    with pytest.raises(ValueError,match='conflicts'):
        render.generation_geometry('720x1559','16:9')


def test_six_percent_review_boundary_applies_before_and_after_generation(tmp_path):
    from PIL import Image
    from kie_model import geometry_report
    assert geometry_report(940,1000,'1:1')['needs_safe_area']
    assert not geometry_report(941,1000,'1:1')['needs_safe_area']
    source=tmp_path/'square.png'
    Image.new('RGB',(1000,1000),'white').save(source)
    assert render.output_geometry(source,'940x1000')['review_findings']
    assert not render.output_geometry(source,'941x1000')['review_findings']


def test_config_matches_request_ratio_for_every_existing_placement():
    import interactive_server
    from kie_model import geometry_report
    slots=interactive_server.load_platform_slots()
    for slot in slots:
        report=geometry_report(slot['target_width'],slot['target_height'])
        assert slot['render_aspect_ratio']==report['aspect_ratio']
        assert slot['resolution']=='1K'
        assert slot['geometry']==report


def test_batch_uses_saved_target_geometry_and_keeps_review_findings(tmp_path,monkeypatch):
    import direct_batch
    import build_selection_page
    from PIL import Image
    setup(tmp_path,monkeypatch)
    import blue_frame
    layout=blue_frame.prepare_layout(720,1559,tmp_path/'layout')
    manifest=tmp_path/'manifest.json'
    config=tmp_path/'config.json'
    output=tmp_path/'工作区/产物/candidate.png'
    job={'job_id':'one','set_id':'set-one','slot':1,'prompt':'教育广告测试','size':'1024x1024','references':[str(REFERENCE)],'output':str(output)}
    job.update(frame_layout_path=layout['frame_layout_path'], prompt='教育广告测试。'+layout['prompt_rule'])
    job['references'].append(layout['reference'])
    manifest.write_text(json.dumps({'request_id':'test','jobs':[job]}))
    config.write_text(json.dumps({'request_id':'test','logo':'不用','placements':[{'target_width':720,'target_height':1559}]}))
    calls=[]
    def request(req,*a,**kw):
        calls.append(json.loads(req.data))
        return {'data':{'taskId':'mock-task'}}
    monkeypatch.setattr(render,'request_json',request)
    monkeypatch.setattr(render,'poll_task',lambda *a:('https://example.invalid/image',{}))
    def download(url,path):
        Image.open(layout['reference']['path']).save(path)
        return path
    monkeypatch.setattr(render,'download_image',download)
    a=argparse.Namespace(manifest=manifest,config=config,validate_only=False,approved_in_current_task=True,approved_count=None)
    assert direct_batch.execute(a)==0
    assert len(calls)==1
    assert calls[0]['model']=='gpt-image-2-5-sunburst-image-to-image'
    assert calls[0]['input']['resolution']=='1K'
    assert calls[0]['input']['aspect_ratio']=='9:16'
    result=json.loads((tmp_path/'image-render-result.json').read_text())
    assert result['jobs'][0]['default_cover_crop_percent']==pytest.approx(17.9,abs=.01)
    assert result['jobs'][0]['frame_status']=='processed'
    candidate=result['sets'][0]['images'][0]
    assert candidate!=str(output)
    assert Image.open(candidate).size==(720,1559)
    assert result['sets'][0]['review_findings']
    _,sets=build_selection_page.normalize_sets(result,tmp_path)
    assert any('确认' in item for item in sets[0]['meta']['review_findings'])


def test_model_switch_cannot_resubmit_old_task_state(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch)
    request=args(tmp_path)
    fingerprint=render.request_fingerprint('gpt-image-2-image-to-image',request.prompt,[REFERENCE],'1:1','2K')
    render.atomic_write_json(render.task_state_path(Path(request.output)),{'status':'waiting','task_id':'old-task','fingerprint':fingerprint})
    monkeypatch.setattr(render,'request_json',lambda *a,**k:pytest.fail('network called'))
    assert render.run(request)==1


def test_large_crop_requires_frame_before_any_network(tmp_path,monkeypatch):
    import direct_batch
    setup(tmp_path,monkeypatch)
    monkeypatch.setattr(render,'request_json',lambda *a,**k:pytest.fail('network called'))
    manifest=tmp_path/'manifest.json';config=tmp_path/'config.json'
    manifest.write_text(json.dumps({'jobs':[{'job_id':'one','set_id':'one','prompt':'测试','output':str(tmp_path/'工作区/产物/raw.png'),'references':[str(REFERENCE)]}]}))
    config.write_text(json.dumps({'logo':'不用','placements':[{'target_width':720,'target_height':1559}]}))
    request=argparse.Namespace(manifest=manifest,config=config,validate_only=False,approved_in_current_task=True,approved_count=None)
    with pytest.raises(ValueError,match='frame_layout_path'):
        direct_batch.execute(request)


def test_batch_dry_run_then_mock_execution(tmp_path,monkeypatch):
    import direct_batch
    setup(tmp_path,monkeypatch)
    manifest=tmp_path/'manifest.json'
    config=tmp_path/'config.json'
    job={'job_id':'one','set_id':'set-one','slot':1,'prompt':'教育广告测试','aspect_ratio':'1:1','references':[str(REFERENCE)],'output':str(tmp_path/'工作区/产物/candidate.png')}
    manifest.write_text(json.dumps({'request_id':'test','jobs':[job]}))
    config.write_text(json.dumps({'request_id':'test','logo':'不用','placements':[{'size':'1024x1024'}]}))
    a=argparse.Namespace(manifest=manifest,config=config,validate_only=True,approved_in_current_task=False,approved_count=None)
    assert direct_batch.execute(a)==0
    a.validate_only=False
    with pytest.raises(ValueError,match='approved-in-current-task'):
        direct_batch.execute(a)
    monkeypatch.setattr(render,'request_json',lambda *a,**k:{'data':{'taskId':'mock-task'}})
    monkeypatch.setattr(render,'poll_task',lambda *a:('https://example.invalid/image',{}))
    def download(url,path):
        from PIL import Image
        Image.new('RGB',(16,16)).save(path)
        return path
    monkeypatch.setattr(render,'download_image',download)
    a.approved_in_current_task=True
    assert direct_batch.execute(a)==0
    result=json.loads((tmp_path/'image-render-result.json').read_text())
    assert result['sets'][0]['status']=='completed'
    assert result['jobs'][0]['task_id']=='mock-task'
