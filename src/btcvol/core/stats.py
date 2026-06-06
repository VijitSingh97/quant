"""Volatility / performance statistics — pure functions, no I/O."""

import math
import statistics

DAYS = 365
OKX_FUNDINGS_PER_DAY = 3       # OKX pays funding every 8h
HL_FUNDINGS_PER_DAY = 24       # Hyperliquid pays funding hourly
DERIBIT_FUNDINGS_PER_DAY = 3   # Deribit perp funding quoted per 8h


def log_returns(closes):
    return [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]


def ann_vol(returns, periods_per_year=DAYS):
    if len(returns) < 2:
        return None
    return statistics.stdev(returns) * math.sqrt(periods_per_year)


def cc_vol(closes, window=None, periods_per_year=DAYS):
    """Close-to-close annualized realized vol from closes (oldest->newest)."""
    if window:
        closes = closes[-(window + 1):]
    return ann_vol(log_returns(closes), periods_per_year)


def parkinson_vol(highs, lows, window=30):
    """Parkinson high-low range estimator (annualized); more efficient than C2C."""
    highs, lows = highs[-window:], lows[-window:]
    n = min(len(highs), len(lows))
    if n < 2:
        return None
    s = sum(math.log(highs[i] / lows[i]) ** 2 for i in range(n))
    return math.sqrt(s / (4 * math.log(2) * n)) * math.sqrt(DAYS)


def garman_klass(opens, highs, lows, closes, window=30):
    """Garman-Klass annualized vol from OHLC — uses the whole bar, far more efficient
    than close-to-close. Assumes no drift / no overnight gap."""
    o, h, lo, c = opens[-window:], highs[-window:], lows[-window:], closes[-window:]
    n = min(len(o), len(h), len(lo), len(c))
    if n < 2:
        return None
    s = sum(0.5 * math.log(h[i] / lo[i]) ** 2
            - (2 * math.log(2) - 1) * math.log(c[i] / o[i]) ** 2 for i in range(n))
    return math.sqrt(s / n) * math.sqrt(DAYS)


def yang_zhang(opens, highs, lows, closes, window=30):
    """Yang-Zhang annualized vol — drift-independent and handles overnight gaps;
    the most efficient of the range estimators. Needs >= ~3 bars."""
    o, h, lo, c = opens[-window:], highs[-window:], lows[-window:], closes[-window:]
    n = min(len(o), len(h), len(lo), len(c))
    if n < 3:
        return None
    # overnight (close->open) and open->close variances
    on = [math.log(o[i] / c[i - 1]) for i in range(1, n)]
    oc = [math.log(c[i] / o[i]) for i in range(1, n)]
    mu_on, mu_oc = statistics.mean(on), statistics.mean(oc)
    v_on = sum((x - mu_on) ** 2 for x in on) / (n - 2)
    v_oc = sum((x - mu_oc) ** 2 for x in oc) / (n - 2)
    # Rogers-Satchell (drift-independent intraday)
    rs = sum(math.log(h[i] / c[i]) * math.log(h[i] / o[i])
             + math.log(lo[i] / c[i]) * math.log(lo[i] / o[i]) for i in range(1, n)) / (n - 1)
    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    return math.sqrt(v_on + k * v_oc + (1 - k) * rs) * math.sqrt(DAYS)


def vol_of_vol(implied_series, window=30):
    """Annualized vol of the implied-vol (DVOL) series — the 'vol-of-vol' that recent
    work (Du 2025) finds is a priced risk factor. implied_series: DVOL levels
    (fractions), oldest->newest. High VOV = an unstable vol regime (tail risk up)."""
    seg = implied_series[-(window + 1):] if len(implied_series) > window + 1 else implied_series
    chg = [math.log(seg[i] / seg[i - 1]) for i in range(1, len(seg))
           if seg[i - 1] > 0 and seg[i] > 0]
    if len(chg) < 2:
        return None
    return statistics.stdev(chg) * math.sqrt(DAYS)


def max_drawdown(equity):
    """Max peak-to-trough drawdown of an equity curve (list of levels)."""
    peak, mdd = equity[0], 0.0
    for v in equity:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    return mdd


def sharpe(period_returns, periods_per_year):
    if len(period_returns) < 2:
        return None
    mu = statistics.mean(period_returns)
    sd = statistics.stdev(period_returns)
    if sd == 0:
        return None
    return (mu / sd) * math.sqrt(periods_per_year)


def pearson(xs, ys):
    """Pearson correlation; ignores pairs where either value is None. None if degenerate."""
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    xs2, ys2 = [p[0] for p in pairs], [p[1] for p in pairs]
    if len(set(xs2)) < 2 or len(set(ys2)) < 2:
        return None
    mx, my = statistics.mean(xs2), statistics.mean(ys2)
    num = sum((x - mx) * (y - my) for x, y in pairs)
    den = (sum((x - mx) ** 2 for x in xs2) * sum((y - my) ** 2 for y in ys2)) ** 0.5
    return num / den if den else None
