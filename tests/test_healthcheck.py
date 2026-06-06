"""Offline tests for the container healthcheck exit codes."""

import os
import time

import pytest

import basis.live.healthcheck as hc


def test_missing_heartbeat_is_unhealthy(monkeypatch, tmp_path):
    monkeypatch.setattr(hc, "HEARTBEAT", tmp_path / "heartbeat")
    with pytest.raises(SystemExit) as e:
        hc.main()
    assert e.value.code == 1


def test_fresh_heartbeat_is_healthy(monkeypatch, tmp_path):
    hb = tmp_path / "heartbeat"
    hb.write_text(str(int(time.time())))
    monkeypatch.setattr(hc, "HEARTBEAT", hb)
    with pytest.raises(SystemExit) as e:
        hc.main()
    assert e.value.code == 0


def test_stale_heartbeat_is_unhealthy(monkeypatch, tmp_path):
    hb = tmp_path / "heartbeat"
    hb.write_text("0")
    old = time.time() - 10 * 3600                    # well beyond 2 cycles + grace
    os.utime(hb, (old, old))
    monkeypatch.setattr(hc, "HEARTBEAT", hb)
    with pytest.raises(SystemExit) as e:
        hc.main()
    assert e.value.code == 1
