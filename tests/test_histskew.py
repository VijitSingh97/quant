import math

from basis.backtests.histskew import simulate_logged, _daily, MIN_ROLLS
from basis.backtests.structures import HOLD


def _rows(n, rr25=-0.05, bf25=0.01):
    return [{
        "iso_time": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}T00:00:00Z",
        "spot": 60000 * (1 + 0.03 * math.sin(i / 7)),
        "dvol": 0.50, "atm_iv": 0.50,
        "rr25": rr25, "bf25": bf25, "rr10": -0.10, "bf10": 0.03,
    } for i in range(n)]


def test_gates_when_too_few_rolls():
    res = simulate_logged(_rows(40))            # < MIN_ROLLS*HOLD days
    assert res["n_rolls"] == 0 and "need_days" in res


def test_runs_with_enough_history():
    res = simulate_logged(_rows(95))            # -> 3 rolls
    assert res["n_rolls"] >= MIN_ROLLS
    assert len(res["dyn"]) == res["n_rolls"] == len(res["static"])


def test_constant_skew_dyn_equals_static():
    res = simulate_logged(_rows(95))            # identical metrics every day
    assert res["dyn"] == res["static"]


def test_daily_collapses_to_one_row_per_day():
    rows = [
        {"iso_time": "2026-06-01T01:00:00Z", "spot": 100},
        {"iso_time": "2026-06-01T05:00:00Z", "spot": 200},   # later same day wins
        {"iso_time": "2026-06-02T03:00:00Z", "spot": 300},
        {"iso_time": "2026-06-02T09:00:00Z", "spot": None},  # null spot dropped
    ]
    daily = _daily(rows)
    assert [r["spot"] for r in daily] == [200, 300]
