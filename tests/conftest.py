"""Tests may use loopback fixtures, never production credentials or endpoints."""
import pytest


@pytest.fixture(autouse=True)
def isolate_provider_network(monkeypatch):
    monkeypatch.setenv("KIE_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("KIE_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("KIE_UPLOAD_BASE_URL", "http://127.0.0.1:9")
