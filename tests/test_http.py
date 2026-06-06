"""Offline tests for the HTTP retry/backoff layer (the network-resilience core)."""

import urllib.error

import pytest

import basis.core.http as http


class _Resp:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def _patch_urlopen(monkeypatch, handler):
    monkeypatch.setattr(http, "BACKOFF", 0)        # no real sleeping in tests
    monkeypatch.setattr(http.urllib.request, "urlopen", handler)


def test_retries_transient_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def handler(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.URLError("temporary dns failure")
        return _Resp(b'{"ok": 1}')

    _patch_urlopen(monkeypatch, handler)
    assert http.http_get("http://x")["ok"] == 1
    assert calls["n"] == 3                          # retried twice, succeeded on the 3rd


def test_retries_on_429(monkeypatch):
    calls = {"n": 0}

    def handler(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 2:
            raise urllib.error.HTTPError("http://x", 429, "rate limited", {}, None)
        return _Resp(b'{"ok": 2}')

    _patch_urlopen(monkeypatch, handler)
    assert http.http_get("http://x")["ok"] == 2
    assert calls["n"] == 2


def test_fast_fails_on_4xx_geoblock(monkeypatch):
    calls = {"n": 0}

    def handler(req, timeout=None):
        calls["n"] += 1
        raise urllib.error.HTTPError("http://x", 451, "unavailable for legal reasons", {}, None)

    _patch_urlopen(monkeypatch, handler)
    with pytest.raises(urllib.error.HTTPError):
        http.http_get("http://x")
    assert calls["n"] == 1                          # 451 is definitive — no wasted retries


def test_raises_after_exhausting_retries(monkeypatch):
    calls = {"n": 0}

    def handler(req, timeout=None):
        calls["n"] += 1
        raise urllib.error.URLError("down")

    _patch_urlopen(monkeypatch, handler)
    with pytest.raises(urllib.error.URLError):
        http.http_get("http://x")
    assert calls["n"] == http.RETRIES               # tried the full budget
