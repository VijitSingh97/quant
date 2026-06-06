"""Offline tests for the period performance report (seed the pnl table directly)."""

from basis.live.report import compute
from basis.live.store import Store

DAY = 86400.0


def _seed(store, points):
    """points: list of (ts, equity, note) inserted straight into the pnl table."""
    for ts, eq, note in points:
        store.db.execute("INSERT INTO pnl(ts, equity_usd, net_delta_btc, note) VALUES (?,?,?,?)",
                         (ts, eq, 0.0, note))
    store.db.commit()


def test_not_enough_history(tmp_path):
    s = Store(tmp_path / "b.db")
    _seed(s, [(0.0, 6000.0, "auto (BTC)")])
    assert compute(s)["ok"] is False
    s.close()


def test_period_return_and_apr(tmp_path):
    s = Store(tmp_path / "b.db")
    # 30 days, equity 6000 -> 6300 (+5% over the period)
    _seed(s, [(0.0, 6000.0, "auto (HYPE)"), (30 * DAY, 6300.0, "auto (HYPE)")])
    r = compute(s)
    assert r["ok"]
    assert abs(r["total_return"] - 0.05) < 1e-9
    assert abs(r["period_days"] - 30) < 1e-6
    assert r["apr"] > r["total_return"]            # annualized up from a 30d window
    assert r["deployed_frac"] == 1.0               # never in cash
    s.close()


def test_funding_fees_rotations_deployment(tmp_path):
    s = Store(tmp_path / "b.db")
    _seed(s, [(0.0, 6000.0, "auto (cash)"), (10 * DAY, 6000.0, "auto (cash)"),
              (20 * DAY, 6100.0, "auto (HYPE)")])
    s.set_position("funding_usd", 120.0, 0.0)
    s.set_position("fees_usd", -8.0, 0.0)
    s.log("rotate_in", {"to": "HYPE"})
    r = compute(s)
    assert r["funding_earned"] == 120.0 and r["fees_paid"] == -8.0
    assert r["rotations"] == 1
    assert abs(r["deployed_frac"] - 1 / 3) < 1e-9   # 1 of 3 snapshots deployed
    s.close()
