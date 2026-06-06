"""Does auto-ROTATING the carry across assets beat a fixed carry — net of costs?

The live `basis.live.auto` allocator rotates the delta-neutral carry to whichever
spot-able asset has the best PERSISTENT (trailing-avg) funding, with hysteresis so it
doesn't churn. This backtest answers whether that rule actually pays once you subtract
the cost of rotating, vs just holding a fixed BTC (or HYPE) carry.

What's modelled
  - Universe: the spot-able rotation set (default BTC,ETH,SOL,HYPE) — auto only deploys
    assets with a co-located spot leg, so XMR-style "hotter but un-shortable" names are
    correctly out of scope here.
  - Carry PnL per hour = the held asset's hourly funding rate (long spot / short perp
    RECEIVES funding when positive, PAYS when negative). Apples-to-apples: every
    strategy uses the same accrual, so the only difference is *which* asset is held.
  - The decision uses the REAL `select_asset` rule (trailing-avg rank + liquidity floor
    + spot universe + switch-margin hysteresis) — this validates the shipped logic.
  - Rotation cost: each switch pays taker+slippage on the legs it moves (2 legs to close
    the old carry, 2 to open the new), charged on the deployed notional.

Simplifications (stated honestly): no historical OI gate (these majors are always
liquid, so the floor never binds); funding-timing (going flat on negative hourly
funding) is NOT applied — we hold through dips so the comparison stays clean; spot
borrow/financing on the long leg is assumed ~0 (true for owned spot).

Data: Hyperliquid hourly funding history (paginated). HYPE's listing date bounds the
common window. Run:  python3 -m basis.backtests.rotation [--days 365 --window 14 ...]
"""

import argparse
import statistics
import time

from ..core import DAYS, fmt_pct, max_drawdown, sharpe
from ..core.sources import hl_funding_series
from ..live.selector import select_asset

HOURS_Y = 24 * DAYS


def _aligned(series):
    """{coin: [(ts,rate)]} -> (sorted common timestamps, {coin: [rate aligned]})."""
    maps = {c: dict(s) for c, s in series.items()}
    common = sorted(set.intersection(*(set(m) for m in maps.values())))
    rates = {c: [maps[c][t] for t in common] for c in maps}
    return common, rates


def _curve_stats(hourly):
    """hourly signed returns -> (total_return, apr, sharpe_daily, maxdd, equity_end)."""
    eq, lvl = [1.0], 1.0
    for r in hourly:
        lvl *= (1 + r)
        eq.append(lvl)
    daily = [sum(hourly[i:i + 24]) for i in range(0, len(hourly), 24)]
    apr = statistics.mean(hourly) * HOURS_Y if hourly else 0.0
    return lvl - 1, apr, sharpe(daily, DAYS), max_drawdown(eq), lvl


def run(days=365, window=14, cadence=24, min_funding=0.05, switch_margin=0.05,
        cost_bps=5.0, universe=("BTC", "ETH", "SOL", "HYPE")):
    print(f"\nPulling HL funding history ({days}d) for {', '.join(universe)} …")
    series = {}
    for j, c in enumerate(universe):
        if j:
            time.sleep(1.0)              # be polite between assets
        s = hl_funding_series(c, days)
        if s:
            series[c] = s
            print(f"  {c:5} {len(s):>5} hourly points")
        else:
            print(f"  {c:5} no data — skipped")
    if len(series) < 2:
        print("Need ≥2 assets with data. Aborting.")
        return

    common, rates = _aligned(series)
    N, n = window * 24, len(common)
    if n <= N + cadence:
        print(f"Only {n} aligned hours — need > {N + cadence}. Try a smaller --window.")
        return
    span_days = (common[-1] - common[0]) / 86400000
    assets = list(rates)
    print(f"\nCommon window: {n} hours (~{span_days:.0f} days), {len(assets)} assets, "
          f"trailing {window}d, decide every {cadence}h, cost {cost_bps:.0f}bps/leg.\n")

    # --- rotation sim over [N : n] (first N hours seed the trailing average) ---
    # The switch cost is folded into that hour's return, so `rot` stays one entry
    # per hour (clean APR / daily-Sharpe / drawdown).
    held, switches, cost_frac = None, 0, cost_bps / 1e4
    rot, holds, log = [], [], []
    for i in range(N, n):
        cost = 0.0
        if (i - N) % cadence == 0:
            opps = [{"coin": c, "avg_apr": statistics.mean(rates[c][i - N:i]) * HOURS_Y,
                     "oi_usd": 1e12, "pos_frac": None} for c in assets]
            held_avg = next((o["avg_apr"] for o in opps if o["coin"] == held), None)
            choice, reason = select_asset(
                opps, held, held_avg, spot_any=True, min_funding=min_funding,
                oi_floor=0, switch_margin=switch_margin, exit_funding=0.0)
            if choice != held:
                legs = (2 if held else 0) + (2 if choice else 0)   # close old + open new
                if legs:
                    cost = legs * cost_frac
                    switches += 1
                    log.append((i, reason))
                held = choice
        rot.append((rates[held][i] if held else 0.0) - cost)
        holds.append(1 if held else 0)

    # --- fixed-hold baselines over the same [N : n] window ---
    print(f"{'strategy':22} {'total':>9} {'APR':>9} {'Sharpe':>7} {'maxDD':>8}")
    print("  " + "-" * 56)
    results = {}
    for c in assets:
        results[c] = _curve_stats(rates[c][N:n])
    rot_stats = _curve_stats(rot)

    # baselines first (sorted by APR), then rotation
    for c, st in sorted(results.items(), key=lambda kv: kv[1][1], reverse=True):
        tot, apr, sh, dd, _ = st
        tag = "fixed " + c
        print(f"{tag:22} {fmt_pct(tot):>9} {fmt_pct(apr):>9} "
              f"{(f'{sh:.2f}' if sh else '—'):>7} {fmt_pct(dd):>8}")
    tot, apr, sh, dd, _ = rot_stats
    print(f"{'ROTATION (net cost)':22} {fmt_pct(tot):>9} {fmt_pct(apr):>9} "
          f"{(f'{sh:.2f}' if sh else '—'):>7} {fmt_pct(dd):>8}")

    # gross (no-cost) rotation to isolate cost drag — same path, costs removed
    held2, gros = None, []
    for i in range(N, n):
        if (i - N) % cadence == 0:
            opps = [{"coin": c, "avg_apr": statistics.mean(rates[c][i - N:i]) * HOURS_Y,
                     "oi_usd": 1e12, "pos_frac": None} for c in assets]
            held_avg = next((o["avg_apr"] for o in opps if o["coin"] == held2), None)
            choice, _ = select_asset(opps, held2, held_avg, spot_any=True,
                                     min_funding=min_funding, oi_floor=0,
                                     switch_margin=switch_margin, exit_funding=0.0)
            held2 = choice
        gros.append(rates[held2][i] if held2 else 0.0)
    g_tot, g_apr, _, _, _ = _curve_stats(gros)

    # --- verdict ---
    best_fixed = max(results.items(), key=lambda kv: kv[1][1])
    btc = results.get("BTC")
    deployed_frac = sum(holds) / max(1, len(holds))
    print("\n" + "=" * 58)
    print(f"  rotations: {switches}  (~1 per {span_days / max(1, switches):.0f} days)   "
          f"deployed {deployed_frac*100:.0f}% of the time")
    print(f"  cost drag: {fmt_pct(g_tot - tot)} of total return ({fmt_pct(g_apr)} APR gross "
          f"-> {fmt_pct(apr)} net)")
    if btc:
        d = apr - btc[1]
        print(f"  vs fixed BTC: {fmt_pct(d)} APR ({'BEATS' if d > 0 else 'LOSES TO'} a static BTC carry)")
    d2 = apr - best_fixed[1][1]
    print(f"  vs best fixed ({best_fixed[0]}): {fmt_pct(d2)} APR "
          f"({'beats the ex-post winner' if d2 > 0 else 'below the ex-post best single asset'})")
    verdict = ("ROTATION WINS net of costs" if (btc and apr > btc[1])
               else "rotation does NOT beat a fixed carry net of costs")
    print(f"  VERDICT: {verdict}.")
    print("=" * 58)
    if log:
        print("\n  switch log (first 12):")
        for i, reason in log[:12]:
            day = (common[i] - common[N]) / 86400000
            print(f"    d{day:>4.0f}  {reason}")


def main():
    ap = argparse.ArgumentParser(description="Backtest carry rotation vs fixed (net of cost)")
    ap.add_argument("--days", type=int, default=365, help="history to pull (HYPE bounds it)")
    ap.add_argument("--window", type=int, default=14, help="trailing avg window (days)")
    ap.add_argument("--cadence", type=int, default=24, help="rebalance decision interval (hours)")
    ap.add_argument("--min-funding", type=float, default=0.05, help="min trailing APR to deploy")
    ap.add_argument("--switch-margin", type=float, default=0.05, help="hysteresis: APR edge to rotate")
    ap.add_argument("--cost-bps", type=float, default=5.0, help="taker+slippage per leg")
    ap.add_argument("--universe", default="BTC,ETH,SOL,HYPE", help="comma list (spot-able)")
    a = ap.parse_args()
    run(days=a.days, window=a.window, cadence=a.cadence, min_funding=a.min_funding,
        switch_margin=a.switch_margin, cost_bps=a.cost_bps,
        universe=tuple(s.strip().upper() for s in a.universe.split(",") if s.strip()))


if __name__ == "__main__":
    main()
