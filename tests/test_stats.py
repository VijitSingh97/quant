import math

from btcvol.core import stats


def test_log_returns():
    r = stats.log_returns([100, 110, 121])
    assert len(r) == 2
    assert abs(r[0] - math.log(1.1)) < 1e-12
    assert abs(r[1] - math.log(1.1)) < 1e-12


def test_cc_vol_constant_series_is_zero():
    assert stats.cc_vol([100, 100, 100, 100]) == 0.0


def test_cc_vol_window_uses_last_n():
    # a late jump should register only inside the short window
    closes = [100] * 10 + [100, 130]
    assert stats.cc_vol(closes, window=2) > stats.cc_vol(closes, window=5)


def test_ann_vol_scales_with_sqrt_periods():
    rets = [0.01, -0.01, 0.02, -0.02, 0.0]
    v1 = stats.ann_vol(rets, 1)
    v365 = stats.ann_vol(rets, 365)
    assert abs(v365 - v1 * math.sqrt(365)) < 1e-12


def test_ann_vol_too_few_points_is_none():
    assert stats.ann_vol([0.01]) is None


def test_max_drawdown():
    assert abs(stats.max_drawdown([1.0, 1.2, 0.9, 1.1]) - (0.9 / 1.2 - 1)) < 1e-12


def test_max_drawdown_monotonic_up_is_zero():
    assert stats.max_drawdown([1, 2, 3, 4]) == 0.0


def test_sharpe_zero_vol_is_none():
    assert stats.sharpe([0.01, 0.01, 0.01], 365) is None


def test_sharpe_positive_when_mean_positive():
    s = stats.sharpe([0.02, 0.01, 0.015, 0.005], 365)
    assert s is not None and s > 0


def test_parkinson_vol_positive():
    highs = [105, 106, 104, 107]
    lows = [100, 101, 99, 102]
    v = stats.parkinson_vol(highs, lows, window=4)
    assert v is not None and v > 0
