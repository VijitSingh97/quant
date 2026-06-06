"""Offline tests for the cross-venue funding logic (the perp-vs-perp spread)."""

from basis.carryscan import cross_venue


def test_single_venue_zero_spread():
    cv = cross_venue("BTC", 0.10, {})
    assert cv["spread"] == 0.0 and cv["best_v"] == "HL" and cv["worst_v"] == "HL"


def test_spread_and_best_worst_across_venues():
    others = {"Gate": {"BTC": -0.05}, "KuCoin": {"BTC": 0.20}, "dYdX": {"ETH": 0.99}}
    cv = cross_venue("BTC", 0.10, others)
    assert cv["best_v"] == "KuCoin" and cv["worst_v"] == "Gate"   # short KuCoin / long Gate
    assert abs(cv["spread"] - 0.25) < 1e-9                        # 0.20 - (-0.05)
    assert "dYdX" not in cv["cross"]                              # dYdX has no BTC -> excluded


def test_coin_absent_on_some_venues():
    cv = cross_venue("XMR", 0.32, {"Gate": {"BTC": 0.1}})         # XMR only on HL here
    assert cv["spread"] == 0.0 and set(cv["cross"]) == {"HL"}
