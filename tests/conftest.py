"""Tests may use loopback fixtures, never production credentials or endpoints."""
import urllib.parse
import urllib.request

import pytest


@pytest.fixture(autouse=True)
def isolate_provider_network(monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("KIE_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("KIE_UPLOAD_BASE_URL", "http://127.0.0.1:9")
    original = urllib.request.urlopen

    def local_only(request, *args, **kwargs):
        url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
        if urllib.parse.urlparse(url).hostname not in {"127.0.0.1", "localhost", "::1"}:
            pytest.fail("A test attempted external network access")
        return original(request, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", local_only)
