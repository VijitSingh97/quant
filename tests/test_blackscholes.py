import math

from btcvol.core import blackscholes as bs


def test_norm_cdf_known_values():
    assert abs(bs.norm_cdf(0) - 0.5) < 1e-12
    assert abs(bs.norm_cdf(1.96) - 0.975) < 1e-3
    assert abs(bs.norm_cdf(-1.96) - 0.025) < 1e-3


def test_put_call_parity():
    # C - P == S - K  when r = 0
    S, K, T, sig = 60000, 62000, 30 / 365, 0.55
    c = bs.bs_price(S, K, T, sig, "C")
    p = bs.bs_price(S, K, T, sig, "P")
    assert abs((c - p) - (S - K)) < 1e-6


def test_atm_call_delta_near_half():
    d = bs.bs_delta(60000, 60000, 30 / 365, 0.55, "C")
    assert 0.5 < d < 0.62          # slightly above 0.5 for ATM with positive vol


def test_call_put_delta_relationship():
    S, K, T, sig = 60000, 65000, 0.1, 0.5
    dc = bs.bs_delta(S, K, T, sig, "C")
    dp = bs.bs_delta(S, K, T, sig, "P")
    assert abs((dc - dp) - 1.0) < 1e-9     # delta_call - delta_put == 1


def test_price_monotonic_in_vol():
    args = (60000, 60000, 0.1)
    assert bs.bs_price(*args, 0.3, "C") < bs.bs_price(*args, 0.6, "C")


def test_prob_between_bounds():
    pb = bs.prob_between(60000, 55000, 67000, 30 / 365, 0.5)
    assert 0.0 < pb < 1.0


def test_prob_st_below_monotonic():
    f = lambda x: bs.prob_st_below(60000, x, 0.1, 0.5)
    assert f(50000) < f(60000) < f(70000)


def test_expected_payoff_of_constant():
    # E[const] == const regardless of the measure
    ev = bs.expected_payoff(lambda st: 42.0, 60000, 0.1, 0.5)
    assert abs(ev - 42.0) < 1e-6


def test_expected_payoff_long_call_ge_intrinsic():
    # E[max(0, S_T - K)] under r=0 should be >= current intrinsic (here 0, OTM)
    K = 70000
    ev = bs.expected_payoff(lambda st: max(0.0, st - K), 60000, 0.2, 0.6)
    assert ev > 0
