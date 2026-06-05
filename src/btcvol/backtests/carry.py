"""Does the delta-neutral funding carry actually pay?

Strategy modelled: long BTC spot, short an equal-notional BTC perp (delta-neutral).
You don't care about price direction; each funding interval you RECEIVE the funding
rate when it's positive (longs pay shorts) and PAY it when negative.

  per-period return = +funding_rate          (we are short the perp)
  costs             = one-time round-trip taker fees (4 legs)
  assumptions       = low leverage so the short perp isn't liquidated; no basis
                      slippage. Real-world tail risk is exchange/liquidation, NOT
                      in this curve.

Data: Deribit BTC-PERPETUAL funding history (hourly, paginated multi-year).
Run:  python3 -m btcvol.backtests.carry [years]
"""

import statistics
import sys
import time

from ..core import DAYS, max_drawdown, sharpe, sparkline, fmt_pct
from ..core.sources import deribit_funding_history

ROUND_TRIP_FEE = 0.0010   # ~10 bps all-in to open+close both legs (taker, conservative)
PERIODS_PER_YEAR = 24 * DAYS              # funding accrues hourly
WIN = 30 * 24                            # 30-day rolling window in hourly prints


def run(years=2):
    hist = deribit_funding_history("BTC-PERPETUAL", days=int(years * DAYS))
    if not hist:
        print("No funding history returned.")
        return
    rates = [r for _, r in hist]
    n = len(rates)
    span_days = (hist[-1][0] - hist[0][0]) / (1000 * 86400)

    equity = [1.0]
    for r in rates:
        equity.append(equity[-1] * (1 + r))
    gross_total = equity[-1] - 1
    net_total = gross_total - ROUND_TRIP_FEE
    cagr = (1 + net_total) ** (DAYS / span_days) - 1

    ann_funding_apr = statistics.mean(rates) * PERIODS_PER_YEAR
    shp = sharpe(rates, PERIODS_PER_YEAR)
    mdd = max_drawdown(equity)
    pct_neg = sum(1 for r in rates if r < 0) / n
    worst = min(rates) * 100
    best = max(rates) * 100

    roll = [statistics.mean(rates[i - WIN:i]) * PERIODS_PER_YEAR for i in range(WIN, n + 1)]
    roll_min = min(roll) if roll else None
    roll_max = max(roll) if roll else None
    roll_spark = roll[:: max(1, len(roll) // 120)] if roll else []

    by_year = {}
    for ts, r in hist:
        by_year.setdefault(time.gmtime(ts / 1000).tm_year, []).append(r)

    bar = "=" * 70
    print(f"\n{bar}\nFUNDING-CARRY BACKTEST  (long spot / short perp, Deribit BTC-PERPETUAL)\n{bar}")
    print(f"Window           {span_days:.0f} days  "
          f"({time.strftime('%Y-%m-%d', time.gmtime(hist[0][0]/1000))} -> "
          f"{time.strftime('%Y-%m-%d', time.gmtime(hist[-1][0]/1000))}),  {n} funding prints")
    print(f"\nRETURN")
    print(f"  mean funding         {fmt_pct(ann_funding_apr)} APR")
    print(f"  gross total          {fmt_pct(gross_total)}")
    print(f"  net total (–{ROUND_TRIP_FEE*100:.2f}% fees) {fmt_pct(net_total)}   ->  CAGR {fmt_pct(cagr)}")
    print(f"\nRISK (of the funding stream — excludes exchange/liquidation tail)")
    print(f"  Sharpe (funding)     {shp:.2f}" if shp else "  Sharpe               n/a")
    print(f"  max drawdown         {fmt_pct(mdd)}")
    print(f"  % periods negative   {pct_neg*100:.1f}%   (worst print {worst:+.4f}% / best {best:+.4f}% per 1h)")
    if roll:
        print(f"  rolling-30d APR      min {fmt_pct(roll_min)}  /  max {fmt_pct(roll_max)}")
        print(f"  rolling-30d APR path {sparkline(roll_spark)}")
    print(f"\nBY YEAR (annualized funding)")
    for y in sorted(by_year):
        seg = by_year[y]
        apr = statistics.mean(seg) * PERIODS_PER_YEAR
        neg = sum(1 for r in seg if r < 0) / len(seg) * 100
        print(f"  {y}   {fmt_pct(apr):>8}   ({len(seg)} prints, {neg:.0f}% negative)")
    eq_spark = equity[:: max(1, len(equity) // 120)]
    print(f"\nequity curve  {sparkline(eq_spark)}")

    print(f"\nREAD")
    if cagr > 0.04:
        print(f"• Carry was net positive (~{fmt_pct(cagr)} CAGR) — the boring base layer holds up.")
    else:
        print(f"• Carry was thin (~{fmt_pct(cagr)} CAGR) — barely worth the operational risk on its own.")
    print(f"• {pct_neg*100:.0f}% of periods had you PAYING funding; the edge is the positive-skew majority.")
    print("• Sharpe looks high because funding is steady — but it understates tail risk:")
    print("  the real danger is exchange insolvency / the short leg liquidating in a vertical rally.")
    print("  Keep leverage low and split venues. Returns scale with leverage; so does ruin.")


def main():
    years = float(sys.argv[1]) if len(sys.argv) > 1 else 2
    run(years)


if __name__ == "__main__":
    main()
