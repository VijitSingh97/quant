"""Is the BTC volatility-risk-premium harvestable?

Implied vol (DVOL) usually prints above subsequently-realized vol. If you
systematically SELL 30d vol, do you get paid — and what does the tail cost?

Model: every 30 days, sell a 30d ATM straddle, delta-hedged daily. To first order
that's a short variance swap:
  premium captured (vol points) = IV_t - RV(t -> t+30)
  variance-swap P&L             = IV_t^2 - RV^2
Positive when implied > realized. Rolls are non-overlapping (independent trades).

Data: Deribit DVOL (30d implied) + BTC-PERPETUAL daily closes (~400d).
Run:  python3 -m btcvol.backtests.vrp
"""

import math
import statistics
import time

from ..core import log_returns, DAYS, sharpe, sparkline, fmt_vol
from ..core.sources import deribit_dvol, deribit_chart

HOLD = 30                      # days per roll
# ATM straddle vega ~ 0.4*S*sqrt(T) -> ~0.11 of notional per 100 vol pts at 30d,
# i.e. ~0.11% of notional per vol point. Used only for an illustrative $ figure.
VEGA_PER_VOLPT = 0.4 * math.sqrt(HOLD / DAYS) / 100


def fwd_realized_vol(closes, i, horizon=HOLD):
    seg = closes[i:i + horizon + 1]
    if len(seg) < horizon + 1:
        return None
    return statistics.stdev(log_returns(seg)) * math.sqrt(DAYS)


def run(asset="BTC"):
    from ..core.assets import get_asset
    a = get_asset(asset)
    if not a["has_dvol"]:
        print(f"{asset.upper()} has no DVOL index — try BTC or ETH.")
        return
    dvol = deribit_dvol(days=1000, resolution="1D", currency=a["deribit_ccy"])   # ~3y free backfill
    chart = deribit_chart(a["deribit_perp"], days=1000, resolution="1D")
    ticks, closes = chart["ticks"], chart["close"]

    iv_by_date = {time.strftime("%Y-%m-%d", time.gmtime(ts / 1000)): iv for ts, iv in dvol}
    px_by_date = {time.strftime("%Y-%m-%d", time.gmtime(t / 1000)): c for t, c in zip(ticks, closes)}
    dates = sorted(set(iv_by_date) & set(px_by_date))
    px = [px_by_date[d] for d in dates]

    # ---- overlapping daily VRP: is the premium structurally there? ----
    daily_vrp = []
    for i, d in enumerate(dates):
        rv = fwd_realized_vol(px, i)
        if rv is not None:
            daily_vrp.append((d, iv_by_date[d], rv, iv_by_date[d] - rv))
    vrps = [x[3] for x in daily_vrp]
    pct_iv_over_rv = sum(1 for v in vrps if v > 0) / len(vrps) * 100
    mean_vrp, med_vrp = statistics.mean(vrps), statistics.median(vrps)

    # ---- non-overlapping rolls: the tradeable sim ----
    rolls = []
    i = 0
    while i + HOLD < len(px):
        d = dates[i]
        rv = fwd_realized_vol(px, i)
        if rv is not None:
            rolls.append({"date": d, "iv": iv_by_date[d], "rv": rv,
                          "vol_pts": iv_by_date[d] - rv,
                          "var_pnl": iv_by_date[d] ** 2 - rv ** 2})
        i += HOLD

    wins = sum(1 for r in rolls if r["vol_pts"] > 0)
    win_rate = wins / len(rolls) * 100
    avg_pts = statistics.mean(r["vol_pts"] for r in rolls)
    worst = min(rolls, key=lambda r: r["vol_pts"])
    best = max(rolls, key=lambda r: r["vol_pts"])
    roll_sharpe = sharpe([r["vol_pts"] for r in rolls], DAYS / HOLD)
    cum, s = [], 0.0
    for r in rolls:
        s += r["vol_pts"]
        cum.append(s)

    notional = 100_000
    per_roll_usd = avg_pts * 100 * VEGA_PER_VOLPT * notional
    annual_usd = per_roll_usd * (DAYS / HOLD)

    bar = "=" * 70
    print(f"\n{bar}\nVOL-RISK-PREMIUM BACKTEST  (sell 30d vol, delta-hedged)\n{bar}")
    print(f"Window           {dates[0]} -> {dates[-1]}  ({len(dates)} days)")
    print(f"\nIS THE PREMIUM THERE?  (overlapping daily, IV vs forward-30d RV)")
    print(f"  IV > RV            {pct_iv_over_rv:.0f}% of days")
    print(f"  mean VRP           {fmt_vol(mean_vrp)} vol pts   (median {fmt_vol(med_vrp)})")
    print(f"  IV / RV path       {sparkline([x[1] for x in daily_vrp])}  (implied)")
    print(f"                     {sparkline([x[2] for x in daily_vrp])}  (realized fwd)")

    print(f"\nTRADEABLE SIM  ({len(rolls)} non-overlapping 30d rolls, short straddle)")
    print(f"  win rate           {win_rate:.0f}%  ({wins}/{len(rolls)} rolls IV>RV)")
    print(f"  avg premium        {fmt_vol(avg_pts)} vol pts / roll")
    print(f"  best roll          +{best['vol_pts']*100:.1f} pts ({best['date']}, IV {fmt_vol(best['iv'])} vs RV {fmt_vol(best['rv'])})")
    print(f"  WORST roll         {worst['vol_pts']*100:+.1f} pts ({worst['date']}, IV {fmt_vol(worst['iv'])} vs RV {fmt_vol(worst['rv'])})")
    print(f"  Sharpe (rolls)     {roll_sharpe:.2f}" if roll_sharpe else "  Sharpe             n/a")
    print(f"  cum vol-pts        {sparkline(cum)}   total {cum[-1]*100:+.1f} pts")
    print(f"\n  illustrative $: short vol on ${notional:,} notional ~ ${per_roll_usd:,.0f}/roll "
          f"-> ~${annual_usd:,.0f}/yr edge")
    print("  (rough: ignores skew, discrete-hedge slippage, fees, and assumes you survive the tail)")

    print(f"\nREAD")
    if mean_vrp > 0.02 and win_rate > 60:
        print(f"• VRP is real and persistent: short vol won {win_rate:.0f}% of rolls, ~{fmt_vol(avg_pts)} pts avg.")
    elif mean_vrp > 0:
        print(f"• VRP is positive but thin/noisy ({fmt_vol(mean_vrp)} avg) — edge exists, conviction shouldn't be high.")
    else:
        print(f"• No harvestable premium in this window ({fmt_vol(mean_vrp)}). Don't sell vol here.")
    print(f"• The tail is the whole story: the worst roll lost {abs(worst['vol_pts'])*100:.0f} vol pts when "
          f"realized blew past implied ({worst['date']}).")
    print("  That single loss can erase many quiet wins -> SELL DEFINED-RISK (spreads/condors), never naked.")
    print("• Short-vol equity curves look like 'up the stairs, down the elevator'. Size for the elevator.")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Vol-risk-premium backtest")
    ap.add_argument("--asset", default="BTC", help="asset with a DVOL index (BTC or ETH)")
    run(asset=ap.parse_args().asset)


if __name__ == "__main__":
    main()
