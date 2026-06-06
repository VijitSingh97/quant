"""Historical-skew condor backtest (#6) — price each roll with the skew we LOGGED
that day, not one static live fit.

The static-skew backtest applies today's fitted smile to every historical roll
(an approximation, since no historical surface is public). As the launchd logger
accumulates RR25/BF25/RR10/BF10 in data/<asset>_timeseries.csv, this reconstructs a
per-roll skew from those captured metrics and reprices the condor — then compares to
the static-skew result. Everything (price path, implied, skew) comes from OUR data.

It needs enough history to form a few 30d rolls, so it degrades gracefully until the
dataset grows (see #4). Run:  python3 -m btcvol.backtests.histskew [--asset BTC]
"""

import argparse
import statistics

from ..core import cc_vol, fmt_pct, fmt_vol, sharpe, max_drawdown, DATA_DIR
from ..core.surface import skew_from_metrics, skew_iv
from .structures import _condor, _expiry_pnl, _nice_grid, HOLD, ROLLS_PER_YEAR
from ..analyze import load_series

MIN_ROLLS = 3


def _daily(rows):
    """Collapse hourly logger rows to one row per UTC day (last of the day wins)."""
    by_day = {}
    for r in rows:
        if r.get("spot") is None or not r.get("iso_time"):
            continue
        by_day[r["iso_time"][:10]] = r
    return [by_day[d] for d in sorted(by_day)]


def _ivfn(coeffs):
    return lambda a, T, K, S: skew_iv(coeffs, a, T, K, S)


def simulate_logged(rows, delta=0.20, wing_pct=0.08):
    """Roll the condor over daily logged rows, pricing each with (a) the skew logged
    that day and (b) a single static skew (the latest row). Pure — testable offline."""
    spot = [r["spot"] for r in rows]
    n = len(rows)
    n_rolls_possible = max(0, (n - 1 - HOLD) // HOLD + 1) if n > HOLD else 0
    if n_rolls_possible < MIN_ROLLS:
        return {"n_rolls": 0, "n_days": n, "need_days": MIN_ROLLS * HOLD + 1}

    grid = _nice_grid(statistics.median(spot))
    T = HOLD / 365.0
    latest = rows[-1]
    static = skew_from_metrics(latest.get("atm_iv") or latest.get("dvol"),
                               latest.get("rr25"), latest.get("bf25"),
                               latest.get("rr10"), latest.get("bf10"))
    dyn_rors, stat_rors = [], []
    i = 0
    while i + HOLD < n:
        r = rows[i]
        S0, atm = spot[i], (r.get("dvol") or r.get("atm_iv"))
        if not S0 or not atm:
            i += HOLD
            continue
        day_skew = skew_from_metrics(r.get("atm_iv") or atm, r.get("rr25"), r.get("bf25"),
                                     r.get("rr10"), r.get("bf10"))
        for coeffs, acc in ((day_skew, dyn_rors), (static, stat_rors)):
            c = _condor(S0, atm, T, delta, wing_pct, grid, _ivfn(coeffs))
            pnl = _expiry_pnl(c, spot[i + HOLD])
            acc.append(pnl / c["max_loss"] if c["max_loss"] > 0 else 0.0)
        i += HOLD
    return {"n_rolls": len(dyn_rors), "n_days": n, "dyn": dyn_rors, "static": stat_rors}


def _summary(rors, risk):
    eq = [1.0]
    for r in rors:
        eq.append(eq[-1] * (1 + risk * r))
    cagr = eq[-1] ** (ROLLS_PER_YEAR / len(rors)) - 1 if rors else 0.0
    return cagr, sharpe(rors, ROLLS_PER_YEAR), max_drawdown(eq)


def run(asset="BTC", delta=0.20, wing_pct=0.08, risk=0.20, csv_path=None):
    path = csv_path or (DATA_DIR / ("timeseries.csv" if asset.upper() == "BTC"
                                    else f"{asset.lower()}_timeseries.csv"))
    bar = "=" * 74
    print(f"\n{bar}\nHISTORICAL-SKEW CONDOR BACKTEST (#6) — {asset.upper()}, on OUR logged skew\n{bar}")
    if not path.exists():
        print(f"No logged data at {path}. Run the launchd logger / `make log` (#4).")
        return
    rows = _daily(load_series(path))
    res = simulate_logged(rows, delta, wing_pct)
    if res["n_rolls"] < MIN_ROLLS:
        print(f"Have {res['n_days']} daily rows -> {res['n_rolls']} complete 30d rolls. "
              f"Need ~{res.get('need_days', MIN_ROLLS*HOLD+1)} days for {MIN_ROLLS} rolls.")
        print("The launchd logger is accruing the skew series (no free historical source).")
        print("Revisit once it has a few months — this is exactly what tracker #4 is for.")
        return

    dc, ds, dd = _summary(res["dyn"], risk)
    sc, ss, sd = _summary(res["static"], risk)
    print(f"{res['n_days']} daily rows -> {res['n_rolls']} rolls\n")
    print(f"  {'pricing':16} {'CAGR':>9} {'Sharpe':>8} {'maxDD':>9}")
    print(f"  {'logged skew':16} {fmt_pct(dc):>9} {ds if ds is None else f'{ds:.2f}':>8} {fmt_pct(dd):>9}")
    print(f"  {'static skew':16} {fmt_pct(sc):>9} {ss if ss is None else f'{ss:.2f}':>8} {fmt_pct(sd):>9}")
    print(f"\nREAD\n• Per-roll skew (what we captured) vs one static fit. A gap means the static")
    print(f"  assumption was materially wrong; agreement validates it. Still a small sample.")


def main():
    ap = argparse.ArgumentParser(description="Historical-skew condor backtest on logged data")
    ap.add_argument("--asset", default="BTC")
    ap.add_argument("--risk", type=float, default=0.20)
    args = ap.parse_args()
    run(asset=args.asset, risk=args.risk)


if __name__ == "__main__":
    main()
