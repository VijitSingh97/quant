"""Offline tests for the rotation backtest's pure helpers (no network)."""

from basis.backtests import rotation


def test_aligned_takes_common_timestamps():
    series = {
        "A": [(1, 0.1), (2, 0.2), (3, 0.3)],
        "B": [(2, 0.5), (3, 0.6), (4, 0.7)],
    }
    common, rates = rotation._aligned(series)
    assert common == [2, 3]                          # intersection only
    assert rates["A"] == [0.2, 0.3]
    assert rates["B"] == [0.5, 0.6]


def test_curve_stats_constant_positive():
    r = 0.0001
    hourly = [r] * 240                               # 10 full days, all positive
    total, apr, sharpe, mdd, end = rotation._curve_stats(hourly)
    assert abs(apr - r * rotation.HOURS_Y) < 1e-9    # APR = mean hourly * hours/yr
    assert mdd == 0.0                                 # monotonic up => no drawdown
    assert abs(end - (1 + r) ** 240) < 1e-6
    assert abs(total - ((1 + r) ** 240 - 1)) < 1e-9
    assert sharpe is None                            # all daily returns equal => stdev 0


def test_curve_stats_has_drawdown_and_sharpe():
    hourly = [0.01] * 24 + [-0.02] * 24              # up a day, down more the next
    total, apr, sharpe, mdd, end = rotation._curve_stats(hourly)
    assert mdd < 0                                    # there is a peak-to-trough drop
    assert sharpe is not None                         # two distinct daily returns
    assert end < 1.0                                  # net down
