import math

from basis.backtests.structures import simulate_from, HOLD, YEAR


def _synthetic_market(n=65):
    # simulate_from never parses dates (they're just labels), so any unique strings work.
    dates = [f"d{i:03d}" for i in range(n)]
    S = [60000 * (1 + 0.02 * math.sin(i / 4.0)) for i in range(n)]   # non-constant -> cc_vol > 0
    IV = [0.55 for _ in range(n)]
    return {"dates": dates, "S": S, "IV": IV, "T": HOLD / YEAR,
            "iv_fn": None, "skew": False, "skew_note": "flat vol"}


def test_simulate_from_runs_rolls():
    m = _synthetic_market(65)
    sim = simulate_from(m, delta=0.20, wing_pct=0.08)
    assert len(sim["detail"]) >= 1
    assert len(sim["always"]) == len(sim["detail"]) == len(sim["filtered"])


def test_fee_reduces_pnl_by_fee_amount():
    m = _synthetic_market(65)
    base = simulate_from(m, delta=0.20, wing_pct=0.08, fee_bps=0.0)["detail"]
    fee = simulate_from(m, delta=0.20, wing_pct=0.08, fee_bps=200.0)["detail"]
    assert len(base) == len(fee) and base
    for k, (b, f) in enumerate(zip(base, fee)):
        st0 = m["S"][k * HOLD]                        # rolls start at 0, HOLD, 2*HOLD, ...
        expected_fee = 200.0 / 1e4 * st0             # 2% of that block's start spot
        assert abs((b["pnl"] - f["pnl"]) - expected_fee) < 1e-6
        assert f["pnl"] < b["pnl"]                   # fees strictly hurt
