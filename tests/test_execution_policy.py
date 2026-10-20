"""Paid attempt caps, wall-clock deadlines and actual concurrent worker isolation."""
import argparse
import io
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import direct_batch
import interactive_server
import render
from execution_policy import normalize_policy

REFERENCE = Path(__file__).parents[1] / 'assets/font-references/字体参考-01.png'


class Clock:
    def __init__(self): self.now = 1000.0
    def time(self): return self.now
    def sleep(self, seconds): self.now += seconds


def renderer(tmp_path, monkeypatch, *, limit=1, behavior='success'):
    from test_direct_api import args
    monkeypatch.setenv('ONION_IMAGE_WORKSPACE', str(tmp_path))
    monkeypatch.setattr(render, 'autoload_dotenv', lambda: None)
    monkeypatch.setattr(render, 'upload_references', lambda *a, **k: ['https://example.invalid/ref.png'])
    clock = Clock()
    monkeypatch.setattr(render.time, 'time', clock.time)
    monkeypatch.setattr(render.time, 'monotonic', clock.time)
    monkeypatch.setattr(render.time, 'sleep', clock.sleep)
    calls = []

    def request(req, *a, **kw):
        if req.method == 'POST':
            calls.append(json.loads(req.data))
            if behavior == 'uncertain_replacement' and len(calls) == 2:
                raise render.KieError('lost submit response', uncertain_submit=True)
            return {'data': {'taskId': f'attempt-{len(calls)}'}}
        if behavior == 'network':
            raise render.KieError('query connection lost')
        active = len(calls)
        if active == 1 or behavior == 'all_timeout':
            clock.now += 240
        success = behavior == 'boundary_success' or (active == 2 and behavior != 'all_timeout')
        return {'data': {'state': 'success' if success else 'generating',
                         'resultJson': json.dumps({'resultUrls': ['https://example.invalid/result.png']}),
                         'creditsConsumed': 3}}

    def download(url, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (16, 16)).save(path)
        return path

    monkeypatch.setattr(render, 'request_json', request)
    monkeypatch.setattr(render, 'download_image', download)
    a = args(tmp_path)
    a.poll_timeout = 240
    a.max_timeout_restarts = limit
    return a, calls, clock


def test_timeout_replacement_preserves_ids_and_cannot_repeat_on_resume(tmp_path, monkeypatch):
    a, calls, _ = renderer(tmp_path, monkeypatch)
    assert render.run(a) == 0
    assert len(calls) == 2 and calls[0] == calls[1]
    state = render.load_output_state(Path(a.output))
    assert state['task_id'] == 'attempt-2'
    assert state['attempt_history'][0]['task_id'] == 'attempt-1'
    assert state['attempt_history'][0]['cancellation_confirmed'] is False
    assert state['timeout_restarts'] == 1
    assert render.run(a) == 0 and len(calls) == 2


def test_second_timeout_stops_and_resume_never_creates_attempt_three(tmp_path, monkeypatch):
    a, calls, _ = renderer(tmp_path, monkeypatch, behavior='all_timeout')
    assert render.run(a) == 3 and len(calls) == 2
    assert render.run(a) == 3 and len(calls) == 2
    assert render.load_output_state(Path(a.output))['timeout_restarts'] == 1


@pytest.mark.parametrize('behavior,creates', [('network', 1), ('uncertain_replacement', 2)])
def test_unknown_transport_state_never_creates_an_extra_task(tmp_path, monkeypatch, behavior, creates):
    a, calls, _ = renderer(tmp_path, monkeypatch, behavior=behavior)
    assert render.run(a) == 3 and len(calls) == creates
    assert render.run(a) == 3 and len(calls) == creates


def test_success_at_deadline_is_downloaded_without_replacement(tmp_path, monkeypatch):
    a, calls, _ = renderer(tmp_path, monkeypatch, behavior='boundary_success')
    assert render.run(a) == 0 and len(calls) == 1


def test_old_configuration_has_no_implicit_replacement_authorization(tmp_path, monkeypatch):
    a, calls, _ = renderer(tmp_path, monkeypatch, limit=0, behavior='all_timeout')
    assert render.run(a) == 3 and len(calls) == 1
    assert normalize_policy(legacy=True)['max_timeout_restarts'] == 0


def test_resume_deadline_uses_original_submission_time(tmp_path, monkeypatch):
    a, _, clock = renderer(tmp_path, monkeypatch, limit=0)
    path = Path(a.output)
    fingerprint = render.request_fingerprint(render.MODEL, a.prompt, [REFERENCE], '1:1', '1K')
    render.atomic_write_json(render.task_state_path(path), {'status': 'generating', 'task_id': 'existing',
                             'fingerprint': fingerprint, 'submitted_at': 760})
    requests = []
    def query(req, *args, **kw):
        assert req.method == 'GET'
        requests.append(kw)
        return {'data': {'state': 'generating', 'createTime': 2000000}}
    monkeypatch.setattr(render, 'request_json', query)
    assert render.run(a) == 3
    assert clock.now == 1000 and len(requests) == 1
    assert requests[0]['request_timeout'] == 10


def test_new_card_saves_policy_and_shows_replacement_cost():
    body = {'delivery_name': '并发', 'placement_ids': ['oppo-rich-horizontal-big-1280x720']}
    cfg = interactive_server.normalize_config_result(body, interactive_server.slots_by_id())
    assert cfg['execution_policy'] == {'concurrency': 3, 'generation_timeout_seconds': 240, 'max_timeout_restarts': 1}
    from test_cta_flow import run_card
    actual = run_card({})
    assert actual['result']['execution_policy'] == cfg['execution_policy']
    assert '4分钟' in actual['summary'] and '6积分' in actual['summary']


@pytest.mark.parametrize('value', [{'max_timeout_restarts': 2}, {'concurrency': 0}, {'generation_timeout_seconds': -1}, {'concurrency': True}])
def test_invalid_execution_policy_is_rejected(value):
    with pytest.raises(ValueError): normalize_policy(value)


def test_workers_really_overlap_and_share_uploads_without_external_network(tmp_path, monkeypatch):
    monkeypatch.setenv('ONION_IMAGE_WORKSPACE', str(tmp_path))
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    stats = {'uploads': 0, 'creates': 0, 'live': 0, 'peak': 0}
    png = io.BytesIO(); Image.new('RGB', (16, 16)).save(png, format='PNG'); image_bytes = png.getvalue()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def send(self, payload, mime='application/json'):
            content = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(200); self.send_header('Content-Type', mime); self.send_header('Content-Length', str(len(content))); self.end_headers(); self.wfile.write(content)
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path.endswith('file-base64-upload'):
                with lock: stats['uploads'] += 1
                return self.send({'code': 200, 'data': {'downloadUrl': base + '/ref.png'}})
            assert payload['model'] == render.MODEL and payload['input']['resolution'] == '1K'
            with lock:
                stats['creates'] += 1; number = stats['creates']; stats['live'] += 1; stats['peak'] = max(stats['peak'], stats['live'])
            if number <= 2: barrier.wait(timeout=5)
            self.send({'code': 200, 'data': {'taskId': f'local-{number}'}})
        def do_GET(self):
            if self.path.startswith('/api/'):
                return self.send({'code': 200, 'data': {'state': 'success', 'resultJson': json.dumps({'resultUrls': [base + '/image.png']}), 'creditsConsumed': 3}})
            with lock: stats['live'] -= 1
            self.send(image_bytes, 'image/png')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    base = f'http://127.0.0.1:{server.server_port}'
    monkeypatch.setenv('KIE_BASE_URL', base); monkeypatch.setenv('KIE_UPLOAD_BASE_URL', base)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        jobs = [{'job_id': str(i), 'set_id': str(i), 'slot': 1, 'prompt': '测试广告', 'references': [str(REFERENCE)],
                 'output': str(tmp_path / f'工作区/产物/{i}.png'), 'depends_on': []} for i in range(3)]
        manifest = tmp_path / 'manifest.json'; manifest.write_text(json.dumps({'jobs': jobs}))
        config = tmp_path / 'config.json'; config.write_text(json.dumps({'request_id': 'isolated-workers', 'logo': '不用',
                 'placements': [{'target_width': 100, 'target_height': 100}], 'execution_policy': {'concurrency': 2, 'generation_timeout_seconds': 240, 'max_timeout_restarts': 1}}))
        args = argparse.Namespace(manifest=manifest, config=config, validate_only=False, approved_in_current_task=True, approved_count=None)
        assert direct_batch.execute(args) == 0
        assert stats == {'uploads': 1, 'creates': 3, 'live': 0, 'peak': 2}
        result = json.loads((tmp_path / 'image-render-result.json').read_text())
        assert len(result['jobs']) == 3 and all(Path(j['filepath']).is_file() for j in result['jobs'])
        assert direct_batch.execute(args) == 0 and stats['creates'] == 3
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_both_series_branches_run_together_after_verified_base(tmp_path, monkeypatch):
    from test_series_chain import triptych
    a, jobs = triptych(tmp_path, monkeypatch); a.validate_only = False; a.approved_in_current_task = True; a.concurrency = 3
    barrier = threading.Barrier(2); started = []
    def worker(job, policy):
        started.append(job['job_id'])
        if job['slot'] > 1:
            assert Path(jobs[0]['output']).is_file()
            barrier.wait(timeout=3)
        path = Path(job['output']); path.parent.mkdir(parents=True, exist_ok=True); Image.new('RGB', (60, 40)).save(path)
        refs = [render.resolve_reference_path(ref['path'], tmp_path, render.SCRIPT_DIR.parent) for ref in job['references']]
        fingerprint = render.request_fingerprint(render.MODEL, job['prompt'], refs, '3:2', '1K')
        render.atomic_write_json(render.task_state_path(path), {'status': 'downloaded', 'task_id': job['job_id'], 'fingerprint': fingerprint, 'sha256': render.sha256_file(path)})
        return {'filepath': str(path)}
    monkeypatch.setattr(direct_batch, 'invoke_paid', worker)
    assert direct_batch.execute(a) == 0
    assert started[0] == 'j1' and set(started[1:]) == {'j2', 'j3'}


@pytest.mark.parametrize('count,history', [(-1, []), (2, []), (1, []), (1, ['broken'])])
def test_corrupt_restart_journal_never_calls_provider(tmp_path, monkeypatch, count, history):
    a, calls, _ = renderer(tmp_path, monkeypatch)
    fingerprint = render.request_fingerprint(render.MODEL, a.prompt, [REFERENCE], '1:1', '1K')
    render.atomic_write_json(render.task_state_path(Path(a.output)), {'status': 'generating', 'task_id': 'old',
                             'fingerprint': fingerprint, 'timeout_restarts': count, 'attempt_history': history})
    assert render.run(a) == 1 and calls == []


def test_query_retry_budget_caps_network_wait(tmp_path, monkeypatch):
    import urllib.error
    clock = Clock()
    monkeypatch.setattr(render.time, 'monotonic', clock.time)
    monkeypatch.setattr(render.time, 'sleep', clock.sleep)
    observed = []
    def fail(req, timeout):
        observed.append(timeout); clock.now += timeout
        raise urllib.error.URLError('temporary connection loss')
    monkeypatch.setattr(render.urllib.request, 'urlopen', fail)
    with pytest.raises(render.KieError):
        render.request_json(render.build_status_request('http://127.0.0.1:9', 'fake', 'old'),
                            retries=3, request_timeout=5, retry_deadline=1010)
    assert observed == [5, 4] and clock.now == 1010


def test_failure_stops_unscheduled_jobs_and_retains_running_success(tmp_path, monkeypatch):
    monkeypatch.setenv('ONION_IMAGE_WORKSPACE', str(tmp_path))
    started = []
    def worker(job, policy):
        started.append(job['job_id'])
        if job['job_id'] == '0': raise render.KieError('replacement also timed out')
        time.sleep(.02)
        return {'filepath': job['output']}
    monkeypatch.setattr(direct_batch, 'invoke_paid', worker)
    jobs = [{'job_id': str(i), 'set_id': str(i), 'slot': 1, 'prompt': '测试', 'aspect_ratio': '1:1', 'references': [str(REFERENCE)],
             'output': str(tmp_path / f'工作区/产物/{i}.png')} for i in range(3)]
    manifest = tmp_path / 'manifest.json'; manifest.write_text(json.dumps({'jobs': jobs}))
    config = tmp_path / 'config.json'; config.write_text(json.dumps({'logo': '不用', 'placements': [{}]}))
    args = argparse.Namespace(manifest=manifest, config=config, validate_only=False, approved_in_current_task=True, approved_count=None, concurrency=2)
    with pytest.raises(render.KieError): direct_batch.execute(args)
    assert set(started) == {'0', '1'}
    result = json.loads((tmp_path / 'image-render-result.json').read_text())
    assert result['status'] == 'partial_failed' and result['jobs'][0]['job_id'] == '1'
