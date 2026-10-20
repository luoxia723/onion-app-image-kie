"""A triptych must transmit its own base PNG to both branches."""
import argparse
import copy
import json
import sys
from pathlib import Path

from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import direct_batch
import render
from logo_reference import build_logo_reference, logo_prompt_rule


@pytest.fixture(autouse=True)
def in_process_mock_worker(monkeypatch):
    monkeypatch.setattr(direct_batch, 'invoke_paid', lambda job, policy: direct_batch.invoke(job, False))


def triptych(tmp_path, monkeypatch):
    monkeypatch.setenv('ONION_IMAGE_WORKSPACE', str(tmp_path))
    output = tmp_path / '工作区/产物/03_候选'
    texts = ['这周我想把数学补起来', '洋葱AI按目标和基础排每日任务', '打开看今天学啥学完看进度']
    config = {'request_id': 'chain', 'logo': '洋葱学园', 'image_form': '三图',
              'placements': [{'image_count': 3, 'target_width': 320, 'target_height': 210}],
              'copy_refs': [{f'short{i+1}': t for i, t in enumerate(texts)}]}
    jobs = []
    for i, text in enumerate(texts, 1):
        refs = [build_logo_reference(config)] if i == 1 else [
            {'label': '参考图1', 'role': '同套首张基准图', 'path': str(output / 'base.png')}]
        jobs.append({'job_id': f'j{i}', 'set_id': 'set1', 'slot': i,
                     'copy_text': text,
                     'prompt': f'参考图1。画面文字白名单：{json.dumps([text, "洋葱学园"], ensure_ascii=False)}。'
                               + (logo_prompt_rule() if i == 1 else '继承参考图1，替换原主文案并改变学习状态。'),
                     'references': refs, 'resolution': '1K', 'size': '320x210',
                     'output': str(output / ('base.png' if i == 1 else f'branch{i}.png')),
                     'depends_on': [] if i == 1 else ['j1'],
                     **({} if i == 1 else {'base_job_id': 'j1'})})
    manifest = tmp_path / 'manifest.json'
    cfg = tmp_path / 'config.json'
    manifest.write_text(json.dumps({'request_id': 'chain', 'jobs': jobs}, ensure_ascii=False))
    cfg.write_text(json.dumps(config, ensure_ascii=False))
    args = argparse.Namespace(manifest=manifest, config=cfg, validate_only=True,
                              approved_in_current_task=False, approved_count=None, concurrency=1)
    return args, jobs


def test_missing_base_is_deferred_then_both_requests_use_base_only(tmp_path, monkeypatch):
    args, jobs = triptych(tmp_path, monkeypatch)
    monkeypatch.setattr(render, 'request_json', lambda *a, **k: pytest.fail('paid API during preflight'))
    assert direct_batch.execute(args) == 0
    calls = []
    uploaded = []
    def upload(base, key, paths, retries):
        uploaded.append(list(paths))
        assert all(p.is_file() for p in paths)
        return ['https://example.invalid/' + p.name for p in paths]
    def request(req, *a, **k):
        calls.append(json.loads(req.data))
        return {'data': {'taskId': f'task-{len(calls)}'}}
    def download(url, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (60, 40), 'white').save(path)
        return path
    monkeypatch.setattr(render, 'autoload_dotenv', lambda: None)
    monkeypatch.setenv('KIE_API_KEY', 'mock-key')
    monkeypatch.setattr(render, 'upload_references', upload)
    monkeypatch.setattr(render, 'request_json', request)
    monkeypatch.setattr(render, 'poll_task', lambda *a: ('https://example.invalid/result', {}))
    monkeypatch.setattr(render, 'download_image', download)
    args.validate_only = False
    args.approved_in_current_task = True
    assert direct_batch.execute(args) == 0
    assert len(calls) == 3
    base = Path(jobs[0]['output'])
    assert uploaded[1:] == [[base], [base]]
    assert all(c['input']['input_urls'] == ['https://example.invalid/base.png'] for c in calls[1:])
    assert direct_batch.execute(args) == 0
    assert len(calls) == 3  # resumed batch never creates duplicate paid tasks


@pytest.mark.parametrize('corruption', ['no_dependency', 'wrong_base', 'extra_assets', 'missing_slot', 'wrong_copy', 'foreign_text'])
def test_invalid_triptych_is_rejected_before_any_paid_task(tmp_path, monkeypatch, corruption):
    args, jobs = triptych(tmp_path, monkeypatch)
    if corruption == 'no_dependency': jobs[1]['depends_on'] = []
    if corruption == 'wrong_base': jobs[2]['references'][0]['path'] = jobs[1]['output']
    if corruption == 'extra_assets': jobs[1]['references'].append(copy.deepcopy(jobs[0]['references'][0]))
    if corruption == 'missing_slot': jobs.pop()
    if corruption == 'wrong_copy': jobs[0]['copy_text'] = '错误文案'
    if corruption == 'foreign_text': jobs[0]['prompt'] += '必须保留“洋葱AI”。'
    args.manifest.write_text(json.dumps({'request_id': 'chain', 'jobs': jobs}, ensure_ascii=False))
    monkeypatch.setattr(render, 'request_json', lambda *a, **k: pytest.fail('network reached'))
    with pytest.raises(ValueError):
        direct_batch.execute(args)


@pytest.mark.parametrize('conflict',['output_without_receipt','invalid_quality','invalid_state','uncertain_state'])
def test_branch_static_failures_are_found_before_paying_for_base(tmp_path,monkeypatch,conflict):
    args,jobs=triptych(tmp_path,monkeypatch)
    output=Path(jobs[1]['output']);output.parent.mkdir(parents=True)
    if conflict=='output_without_receipt':
        Image.new('RGB',(60,40),'white').save(output)
    elif conflict=='invalid_quality':
        jobs[1]['quality']='invalid'
    else:
        state=[] if conflict=='invalid_state' else {'status':'submitting','fingerprint':'unknown'}
        render.task_state_path(output).write_text(json.dumps(state))
    args.manifest.write_text(json.dumps({'request_id':'chain','jobs':jobs},ensure_ascii=False))
    monkeypatch.setattr(render,'request_json',lambda *a,**k:pytest.fail('paid before branch preflight'))
    args.validate_only=False;args.approved_in_current_task=True
    with pytest.raises((ValueError,render.KieError)):
        direct_batch.execute(args)


def test_blue_frame_branches_inherit_raw_base_without_extra_guide(tmp_path, monkeypatch):
    import blue_frame
    args, jobs = triptych(tmp_path, monkeypatch)
    layout = blue_frame.prepare_layout(720, 1559, tmp_path / 'layout')
    for job in jobs:
        job['frame_layout_path'] = layout['frame_layout_path']
        job['prompt'] += layout['prompt_rule'] if job['slot'] == 1 else blue_frame.prompt_rule('参考图1')
    jobs[0]['references'].append(layout['reference'])
    args.manifest.write_text(json.dumps({'request_id': 'chain', 'jobs': jobs}, ensure_ascii=False))
    cfg = json.loads(args.config.read_text())
    cfg['placements'][0].update(target_width=720, target_height=1559)
    args.config.write_text(json.dumps(cfg, ensure_ascii=False))
    monkeypatch.setattr(render, 'autoload_dotenv', lambda: None)
    monkeypatch.setenv('KIE_API_KEY', 'mock-key')
    uploads = []
    def upload(base, key, paths, retries):
        uploads.append(list(paths))
        return ['https://example.invalid/' + p.name for p in paths]
    monkeypatch.setattr(render, 'upload_references', upload)
    monkeypatch.setattr(render, 'request_json', lambda *a, **k: {'data': {'taskId': 'mock'}})
    monkeypatch.setattr(render, 'poll_task', lambda *a: ('https://example.invalid/image', {}))
    def download(url, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(layout['reference']['path']) as im:
            im.save(path)
        return path
    monkeypatch.setattr(render, 'download_image', download)
    assert direct_batch.execute(args) == 0
    args.validate_only = False
    args.approved_in_current_task = True
    assert direct_batch.execute(args) == 0
    assert uploads[1:] == [[Path(jobs[0]['output'])], [Path(jobs[0]['output'])]]
    result = json.loads((tmp_path / 'image-render-result.json').read_text())
    assert all(j['frame_status'] == 'processed' for j in result['jobs'])


def test_tampered_base_stops_branches_before_more_paid_calls(tmp_path, monkeypatch):
    args, jobs = triptych(tmp_path, monkeypatch)
    original = direct_batch.invoke
    submissions = []
    def invoke(job, validate):
        if validate:
            return original(job, True)
        submissions.append(job['job_id'])
        path = Path(job['output'])
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (60, 40), 'white').save(path)
        render.atomic_write_json(render.task_state_path(path), {'status': 'downloaded', 'sha256': 'wrong-hash'})
        return {'filepath': str(path)}
    monkeypatch.setattr(direct_batch, 'invoke', invoke)
    args.validate_only = False
    args.approved_in_current_task = True
    with pytest.raises(ValueError, match='receipt'):
        direct_batch.execute(args)
    assert submissions == ['j1']


def test_explicit_screen_labels_extend_only_the_current_slot_whitelist(tmp_path,monkeypatch):
    from series_chain import text_rule,validate_series
    args,jobs=triptych(tmp_path,monkeypatch)
    cfg=json.loads(args.config.read_text())
    branch=jobs[1]
    old=text_rule(branch['copy_text'],cfg['logo'])
    branch['ui_text']=['今日任务']
    branch['prompt']=branch['prompt'].replace(old,text_rule(branch['copy_text'],cfg['logo'],'',branch['ui_text']))
    branch['prompt']+='屏幕显示“今日任务”。'
    validate_series({'jobs':jobs},cfg)
    branch['prompt']+='屏幕显示“未经确认的提分结果”。'
    with pytest.raises(ValueError,match='outside'):validate_series({'jobs':jobs},cfg)
