"""Offline tests for live readiness: the preflight checks + the place_order triple-gate."""

import pytest

from basis.live import config, preflight
from basis.live.exchanges.base import Order
from basis.live.exchanges.hyperliquid import HyperliquidClient


# --- preflight pure logic ---
def test_caps_pass_when_sane():
    res = preflight.check_caps(max_order=200, max_notional=10000, max_lev=2.0, deploy=0.85)
    assert all(r["level"] != preflight.FAIL for r in res)


def test_caps_fail_on_bad_values():
    res = preflight.check_caps(max_order=0, max_notional=0, max_lev=2.0, deploy=1.5)
    assert any(r["level"] == preflight.FAIL for r in res)


def test_caps_warn_on_large_first_order():
    res = preflight.check_caps(max_order=5000, max_notional=10000, max_lev=2.0, deploy=0.85)
    assert any(r["level"] == preflight.WARN for r in res)   # big first order -> warn, not fail


def test_verdict_go_and_nogo():
    assert preflight.verdict([{"name": "a", "level": preflight.PASS, "detail": ""}])[0] == "GO"
    assert preflight.verdict([{"name": "a", "level": preflight.FAIL, "detail": ""}])[0] == "NO-GO"


def test_check_key_fails_without_secret(monkeypatch):
    monkeypatch.setattr(config, "HL_API_SECRET", "")
    assert preflight.check_key()["level"] == preflight.FAIL


# --- the place_order triple-gate (no SDK/network reached) ---
def test_order_blocked_outside_live(monkeypatch):
    monkeypatch.setattr(config, "LIVE", False)
    with pytest.raises(RuntimeError, match="outside live mode"):
        HyperliquidClient(address="0xabc").place_order(Order("BTC", "buy", 0.01, "perp"))


def test_order_blocked_when_not_armed(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LIVE", True)
    monkeypatch.setattr(config, "LIVE_ARM", False)
    monkeypatch.setattr(config, "KILL_FILE", tmp_path / "none")
    with pytest.raises(RuntimeError, match="armed"):
        HyperliquidClient(address="0xabc").place_order(Order("BTC", "buy", 0.01, "perp"))


def test_order_blocked_by_kill_switch(monkeypatch, tmp_path):
    k = tmp_path / "KILL_SWITCH"
    k.write_text("x")
    monkeypatch.setattr(config, "LIVE", True)
    monkeypatch.setattr(config, "LIVE_ARM", True)
    monkeypatch.setattr(config, "KILL_FILE", k)
    with pytest.raises(RuntimeError, match="KILL_SWITCH"):
        HyperliquidClient(address="0xabc").place_order(Order("BTC", "buy", 0.01, "perp"))
