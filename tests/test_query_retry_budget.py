"""Bounded query retry timing used by the current HTTP client."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import render



class Clock:
    def __init__(self): self.now = 1000.0
    def time(self): return self.now
    def sleep(self, seconds): self.now += seconds


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


