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


def _rotate(rates, assets, common, N, n, cadence, min_funding, switch_margin, cost_frac):
    """Run the REAL select_asset rule over [N:n]; the switch cost is folded into the
    decision hour's return so the stream stays one entry/hour. Returns
    (hourly_returns, holds, switches, switch_log)."""
    held, switches, log = None, 0, []
    hourly, holds = [], []
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
        hourly.append((rates[held][i] if held else 0.0) - cost)
        holds.append(1 if held else 0)
    return hourly, holds, switches, log


def pull_series(universe, days, pause=1.0, log_fn=None):
    """Pull paginated HL funding history for each asset -> {coin: [(ts,rate)]}."""
    series = {}
    for j, c in enumerate(universe):
        if j and pause:
            time.sleep(pause)                          # be polite between assets
        s = hl_funding_series(c, days)
        if s:
            series[c] = s
        if log_fn:
            log_fn(c, len(s) if s else 0)
    return series


def compute(series, window=14, cadence=24, min_funding=0.05, switch_margin=0.05, cost_bps=5.0):
    """Pure (no network/printing): given funding series, return a structured result dict
    comparing rotation (net of cost) to each fixed-hold baseline. Reused by the CLI and
    the scheduled self-validation."""
    if len(series) < 2:
        return {"ok": False, "error": f"need ≥2 assets with data (got {len(series)})"}
    common, rates = _aligned(series)
    N, n = window * 24, len(common)
    if n <= N + cadence:
        return {"ok": False, "error": f"insufficient history: {n} aligned hours (need > {N + cadence})"}
    assets = list(rates)
    cost_frac = cost_bps / 1e4

    net, holds, switches, log = _rotate(rates, assets, common, N, n, cadence,
                                        min_funding, switch_margin, cost_frac)
    gross, _, _, _ = _rotate(rates, assets, common, N, n, cadence, min_funding, switch_margin, 0.0)
    tot, apr, sh, dd, _ = _curve_stats(net)
    _, g_apr, _, _, _ = _curve_stats(gross)

    fixed = {}
    for c in assets:
        ftot, fapr, fsh, fdd, _ = _curve_stats(rates[c][N:n])
        fixed[c] = {"total": ftot, "apr": fapr, "sharpe": fsh, "maxdd": fdd}
    best_fixed = max(fixed, key=lambda c: fixed[c]["apr"])
    btc_apr = fixed.get("BTC", {}).get("apr")
    span_days = (common[-1] - common[0]) / 86400000

    return {
        "ok": True, "window_days": window, "cadence_hours": cadence, "cost_bps": cost_bps,
        "min_funding": min_funding, "switch_margin": switch_margin,
        "assets": assets, "span_days": span_days, "n_hours": n,
        "rotation": {"total": tot, "apr": apr, "sharpe": sh, "maxdd": dd, "switches": switches,
                     "deployed_frac": sum(holds) / max(1, len(holds)),
                     "gross_apr": g_apr, "cost_drag_apr": g_apr - apr},
        "fixed": fixed, "best_fixed": best_fixed,
        "vs_btc_apr": (apr - btc_apr) if btc_apr is not None else None,
        "vs_best_apr": apr - fixed[best_fixed]["apr"],
        "verdict": ("rotation beats a fixed BTC carry net of cost"
                    if (btc_apr is not None and apr > btc_apr)
                    else "rotation does not beat a fixed carry net of cost"),
        "switch_log": [{"day": round((common[i] - common[N]) / 86400000), "reason": reason}
                       for i, reason in log[:12]],
    }


def _pct(x):
    return fmt_pct(x) if x is not None else "—"


def run(days=365, window=14, cadence=24, min_funding=0.05, switch_margin=0.05,
        cost_bps=5.0, universe=("BTC", "ETH", "SOL", "HYPE")):
    print(f"\nPulling HL funding history ({days}d) for {', '.join(universe)} …")
    series = pull_series(universe, days,
                         log_fn=lambda c, k: print(f"  {c:5} {k:>5} hourly points" if k else f"  {c:5} no data"))
    r = compute(series, window=window, cadence=cadence, min_funding=min_funding,
                switch_margin=switch_margin, cost_bps=cost_bps)
    if not r.get("ok"):
        print(f"\nCannot run: {r['error']}")
        return

    rot, fixed = r["rotation"], r["fixed"]
    print(f"\nCommon window: {r['n_hours']} hours (~{r['span_days']:.0f} days), {len(r['assets'])} assets, "
          f"trailing {window}d, decide every {cadence}h, cost {cost_bps:.0f}bps/leg.\n")
    def _sh(v):
        return f"{v:.2f}" if v else "—"

    print(f"{'strategy':22} {'total':>9} {'APR':>9} {'Sharpe':>7} {'maxDD':>8}")
    print("  " + "-" * 56)
    for c in sorted(fixed, key=lambda c: fixed[c]["apr"], reverse=True):
        f = fixed[c]
        print(f"{'fixed ' + c:22} {_pct(f['total']):>9} {_pct(f['apr']):>9} "
              f"{_sh(f['sharpe']):>7} {_pct(f['maxdd']):>8}")
    print(f"{'ROTATION (net cost)':22} {_pct(rot['total']):>9} {_pct(rot['apr']):>9} "
          f"{_sh(rot['sharpe']):>7} {_pct(rot['maxdd']):>8}")

    print("\n" + "=" * 58)
    print(f"  rotations: {rot['switches']}  (~1 per {r['span_days'] / max(1, rot['switches']):.0f} days)   "
          f"deployed {rot['deployed_frac']*100:.0f}% of the time")
    print(f"  cost drag: {_pct(rot['cost_drag_apr'])} APR ({_pct(rot['gross_apr'])} gross -> {_pct(rot['apr'])} net)")
    if r["vs_btc_apr"] is not None:
        print(f"  vs fixed BTC: {_pct(r['vs_btc_apr'])} APR "
              f"({'BEATS' if r['vs_btc_apr'] > 0 else 'LOSES TO'} a static BTC carry)")
    print(f"  vs best fixed ({r['best_fixed']}): {_pct(r['vs_best_apr'])} APR")
    print(f"  VERDICT: {r['verdict']}.")
    print("=" * 58)
    if r["switch_log"]:
        print("\n  switch log (first 12):")
        for e in r["switch_log"]:
            print(f"    d{e['day']:>4}  {e['reason']}")


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
