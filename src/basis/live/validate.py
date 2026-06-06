"""Scheduled self-validation — periodically re-check the live rotation rule on the
latest data and REPORT whether the current settings still look best.

It runs the real rotation backtest for the *current* config, then sweeps the two key
knobs (switch_margin, min_funding) over a small grid, and writes a report that says
"current settings are near-optimal" or "consider X (+Y% APR in-sample)". It only ever
**suggests** — it never changes live config (auto-tuning live capital is how you overfit
yourself into a loss). Every report is stored in the research DB, shown on the dashboard,
and exportable.

Self-throttles via the last report's timestamp, so it can sit in the scheduler's task
list and only actually compute once per BASIS_VALIDATE_INTERVAL_SECONDS (default weekly).

Run on demand:  python3 -m basis.live.validate [--force]
"""

import argparse
import time

from . import config
from .store import Store
from ..backtests import rotation

GRID_SWITCH = (0.02, 0.05, 0.10)        # hysteresis margins to try
GRID_MINFUND = (0.03, 0.05, 0.08)       # min-funding floors to try
MATERIAL_GAIN = 0.01                     # <1% APR in-sample edge = "not worth changing"


def _due(store, interval):
    last = store.latest_report("validation")
    return (last is None) or (time.time() - last["ts"] >= interval)


def compute_report(days=None, universe=None):
    """Pull funding once, backtest current config, sweep the grid. Returns a report dict."""
    days = days or config.VALIDATE_DAYS
    universe = tuple(universe or sorted(config.AUTO_SPOT_UNIVERSE))
    series = rotation.pull_series(universe, days)
    cur_sm, cur_mf = config.AUTO_SWITCH_MARGIN, config.AUTO_MIN_FUNDING

    base = rotation.compute(series, switch_margin=cur_sm, min_funding=cur_mf)
    if not base.get("ok"):
        return {"ok": False, "error": base.get("error", "compute failed"),
                "universe": list(universe), "days": days}

    sweep, best = [], {"apr": base["rotation"]["apr"], "switch_margin": cur_sm, "min_funding": cur_mf}
    for sm in sorted(set(GRID_SWITCH) | {cur_sm}):
        for mf in sorted(set(GRID_MINFUND) | {cur_mf}):
            r = rotation.compute(series, switch_margin=sm, min_funding=mf)
            if not r.get("ok"):
                continue
            apr = r["rotation"]["apr"]
            sweep.append({"switch_margin": sm, "min_funding": mf, "apr": apr,
                          "sharpe": r["rotation"]["sharpe"], "switches": r["rotation"]["switches"],
                          "is_current": (sm == cur_sm and mf == cur_mf)})
            if apr > best["apr"]:
                best = {"apr": apr, "switch_margin": sm, "min_funding": mf}

    gain = best["apr"] - base["rotation"]["apr"]
    at_optimum = (best["switch_margin"] == cur_sm and best["min_funding"] == cur_mf) or gain < MATERIAL_GAIN
    if at_optimum:
        suggestion = "current settings are at/near the sweep optimum — no change suggested"
    else:
        suggestion = (f"consider switch_margin={best['switch_margin']:.0%}, "
                      f"min_funding={best['min_funding']:.0%} (+{gain*100:.1f}% APR in-sample; "
                      f"review before changing — in-sample edges overfit)")

    return {
        "ok": True, "ts": time.time(), "universe": list(universe), "days": days,
        "window_days": base["window_days"], "span_days": base["span_days"], "n_hours": base["n_hours"],
        "current": {"switch_margin": cur_sm, "min_funding": cur_mf,
                    "apr": base["rotation"]["apr"], "sharpe": base["rotation"]["sharpe"],
                    "maxdd": base["rotation"]["maxdd"], "switches": base["rotation"]["switches"],
                    "vs_btc_apr": base["vs_btc_apr"], "vs_best_apr": base["vs_best_apr"],
                    "best_fixed": base["best_fixed"], "verdict": base["verdict"]},
        "fixed": base["fixed"], "best_in_sweep": best, "sweep": sweep,
        "at_optimum": at_optimum, "suggestion": suggestion,
    }


def main(force=False):
    store = Store(config.RESEARCH_DB)
    try:
        if not force and not _due(store, config.VALIDATE_INTERVAL_SECONDS):
            last = store.latest_report("validation")
            age_d = (time.time() - last["ts"]) / 86400
            print(f"[validate] not due (last run {age_d:.1f}d ago; interval "
                  f"{config.VALIDATE_INTERVAL_SECONDS/86400:.0f}d) — skipping")
            return None
        print("[validate] computing self-validation report (this pulls funding history)…")
        rep = compute_report()
        summary = rep["suggestion"] if rep.get("ok") else f"failed: {rep.get('error')}"
        store.add_report("validation", summary, rep)
        if rep.get("ok"):
            cur = rep["current"]
            print(f"[validate] rotation {cur['apr']*100:+.1f}% APR (current "
                  f"sm={cur['switch_margin']:.0%}/mf={cur['min_funding']:.0%}); {summary}")
        else:
            print(f"[validate] {summary}")
        return rep
    finally:
        store.close()


def cli():
    ap = argparse.ArgumentParser(description="Scheduled self-validation of the rotation rule")
    ap.add_argument("--force", action="store_true", help="run now, ignoring the weekly throttle")
    main(force=ap.parse_args().force)


if __name__ == "__main__":
    cli()
