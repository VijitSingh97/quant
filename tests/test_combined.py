from btcvol.backtests.combined import _date_ms, equity, leg_stats, carry_per_block
from btcvol.backtests.structures import HOLD


def test_date_ms_epoch():
    assert _date_ms("1970-01-01") == 0
    assert _date_ms("1970-01-02") == 86400 * 1000


def test_equity_compounds():
    eq = equity([0.1, -0.5, 0.2])
    assert abs(eq[-1] - (1.1 * 0.5 * 1.2)) < 1e-12
    assert eq[0] == 1.0


def test_leg_stats_total_matches_curve():
    s = leg_stats([0.1, 0.1, 0.1])
    assert abs(s["total"] - (1.1 ** 3 - 1)) < 1e-12
    assert s["mdd"] == 0.0          # monotonic up


def test_leg_stats_drawdown_negative_on_loss():
    s = leg_stats([0.2, -0.5, 0.1])
    assert s["mdd"] < 0


def test_carry_per_block_timed_avoids_negative_stretches():
    h = 3600 * 1000
    funding = ([(i * h, 0.001) for i in range(24)]            # 24 positive hours
               + [((24 + i) * h, -0.001) for i in range(48)])  # then a negative stretch
    rolls = [{"date": "1970-01-01"}]
    untimed = carry_per_block(rolls, funding, 1.0, timed=False)[0]
    timed = carry_per_block(rolls, funding, 1.0, timed=True)[0]
    assert untimed < 0                 # raw stream is net negative
    assert timed > untimed             # timing skips the predicted-negative tail


def test_carry_per_block_buckets_and_levers():
    # one roll starting at epoch; funding inside the 30d block counts, outside doesn't
    rolls = [{"date": "1970-01-01"}]
    inside = HOLD * 86400 * 1000 // 2          # ts in the middle of the block
    outside = HOLD * 86400 * 1000 + 1          # ts just past the block
    funding = [(inside, 0.001), (inside + 1, 0.002), (outside, 9.9)]
    out = carry_per_block(rolls, funding, leverage=2.0)
    assert abs(out[0] - 2.0 * (0.001 + 0.002)) < 1e-12     # levered sum of in-block funding only
