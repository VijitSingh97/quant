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
