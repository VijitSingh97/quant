"""Black-Scholes option maths (rates = 0), stdlib only.

BTC is treated as a non-dividend asset with r = 0 (a fine approximation for short
tenors); sigma is the annualized implied vol as a fraction. Provides pricing,
delta, and the lognormal terminal-price probabilities used for POP / EV.
"""

import math

_SQRT2 = math.sqrt(2.0)
_SQRT2PI = math.sqrt(2.0 * math.pi)


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


def d1_d2(S, K, T, sigma):
    v = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / v
    return d1, d1 - v


def bs_price(S, K, T, sigma, kind):
    """European option price. kind is 'C' or 'P'. Degenerate inputs -> intrinsic."""
    v = (sigma * math.sqrt(T)) if (sigma > 0 and T > 0) else 0.0
    if v <= 0 or S <= 0 or K <= 0:                # no div-by-zero / log-domain ever
        return max(0.0, S - K) if kind == "C" else max(0.0, K - S)
    d1 = (math.log(S / K) + 0.5 * v * v) / v
    d2 = d1 - v
    if kind == "C":
        return S * norm_cdf(d1) - K * norm_cdf(d2)
    return K * norm_cdf(-d2) - S * norm_cdf(-d1)


def bs_delta(S, K, T, sigma, kind):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        if kind == "C":
            return 1.0 if S > K else 0.0
        return -1.0 if S < K else 0.0
    d1, _ = d1_d2(S, K, T, sigma)
    return norm_cdf(d1) if kind == "C" else norm_cdf(d1) - 1.0


def strike_for_delta(S, T, sigma, target, kind, lo_mult=0.2, hi_mult=3.0, iters=64):
    """Invert BS delta -> the strike with delta == target.

    Both call delta (N(d1)) and put delta (N(d1)-1) are monotonically decreasing
    in K, so a plain bisection converges. `target` is signed: e.g. +0.20 for a
    call, -0.20 for a put.
    """
    lo, hi = S * lo_mult, S * hi_mult
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if bs_delta(S, mid, T, sigma, kind) > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def prob_st_below(S, x, T, sigma):
    """Risk-neutral P(S_T <= x) under the r=0 lognormal."""
    if T <= 0 or sigma <= 0:
        return 1.0 if S <= x else 0.0
    return norm_cdf((math.log(x / S) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T)))


def prob_between(S, lo, hi, T, sigma):
    return max(0.0, prob_st_below(S, hi, T, sigma) - prob_st_below(S, lo, T, sigma))


def lognormal_pdf(S, x, T, sigma):
    """Density of the terminal price S_T at x (r=0)."""
    if x <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    s = sigma * math.sqrt(T)
    m = math.log(S) - 0.5 * sigma * sigma * T
    return math.exp(-((math.log(x) - m) ** 2) / (2 * s * s)) / (x * s * _SQRT2PI)


def expected_payoff(pnl_fn, S, T, sigma, lo=0.25, hi=3.0, n=600):
    """E[pnl_fn(S_T)] under the r=0 lognormal with vol `sigma` (numerical)."""
    xs = [S * (lo + (hi - lo) * i / n) for i in range(1, n + 1)]
    w = [lognormal_pdf(S, x, T, sigma) for x in xs]
    tot = sum(w) or 1.0
    return sum(pnl_fn(x) * wi for x, wi in zip(xs, w)) / tot
