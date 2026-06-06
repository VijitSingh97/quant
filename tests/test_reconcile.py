"""Offline tests for the reconcile (our book vs the exchange account)."""

from basis.live.status import reconcile

BOOK = {"spot": 1.0, "perp": -1.0, "net_delta": 0.0, "cash": 100.0, "funding_usd": 0.0}


def test_unavailable_without_live():
    assert reconcile(6000.0, BOOK, None)["available"] is False
    assert reconcile(6000.0, BOOK, {"error": "boom"})["available"] is False


def test_matches_when_positions_agree():
    live = {"spot": 1.0, "perp": -1.0, "net_delta": 0.0, "equity": 6000.0}
    r = reconcile(6000.0, BOOK, live)
    assert r["available"] and r["match"] and r["spot_match"] and r["perp_match"]
    assert r["equity_diff"] == 0.0


def test_drift_when_positions_disagree():
    live = {"spot": 0.5, "perp": -1.0, "net_delta": -0.5, "equity": 5900.0}
    r = reconcile(6000.0, BOOK, live)
    assert not r["match"] and not r["spot_match"] and r["perp_match"]
    assert abs(r["equity_diff"] - 100.0) < 1e-9


def test_within_tolerance_counts_as_match():
    live = {"spot": 1.001, "perp": -0.999, "net_delta": 0.002, "equity": 6010.0}
    r = reconcile(6000.0, BOOK, live)
    assert r["match"]                       # 0.1% position diff is within the 2% tolerance
