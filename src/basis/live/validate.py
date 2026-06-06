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
import statistics
import time

from . import config
from .store import Store
from ..backtests import rotation

GRID_SWITCH = (0.02, 0.05, 0.10)        # hysteresis margins to try
GRID_MINFUND = (0.03, 0.05, 0.08)       # min-funding floors to try
MATERIAL_GAIN = 0.01                     # <1% APR edge = "not worth changing"


def _due(store, interval):
    last = store.latest_report("validation")
    return (last is None) or (time.time() - last["ts"] >= interval)


def _slice(series, lo, hi):
    """Sub-series over the [lo, hi) fraction of the aligned common timeline."""
    common, rates = rotation._aligned(series)
    n = len(common)
    a, b = int(n * lo), int(n * hi)
    return {c: list(zip(common[a:b], rates[c][a:b])) for c in rates}


def walk_forward(series, folds=4):
    """Out-of-sample check: on each fold, pick the best params IN-SAMPLE (train slice),
    then score them + the current config OUT-OF-SAMPLE (next slice). The honest question
    isn't 'what won in-sample' (that overfits) but 'does re-tuning beat current OOS'."""
    cur_sm, cur_mf = config.AUTO_SWITCH_MARGIN, config.AUTO_MIN_FUNDING
    edges = [i / (folds + 1) for i in range(folds + 2)]      # folds+1 contiguous chunks
    cur_oos, retuned_oos, picks = [], [], []
    for i in range(1, folds + 1):
        train, test = _slice(series, edges[i - 1], edges[i]), _slice(series, edges[i], edges[i + 1])
        best, best_apr = (cur_sm, cur_mf), None
        for sm in sorted(set(GRID_SWITCH) | {cur_sm}):
            for mf in sorted(set(GRID_MINFUND) | {cur_mf}):
                r = rotation.compute(train, switch_margin=sm, min_funding=mf)
                if r.get("ok") and (best_apr is None or r["rotation"]["apr"] > best_apr):
                    best_apr, best = r["rotation"]["apr"], (sm, mf)
        rc = rotation.compute(test, switch_margin=cur_sm, min_funding=cur_mf)
        rt = rotation.compute(test, switch_margin=best[0], min_funding=best[1])
        if rc.get("ok") and rt.get("ok"):
            cur_oos.append(rc["rotation"]["apr"])
            retuned_oos.append(rt["rotation"]["apr"])
            picks.append({"switch_margin": best[0], "min_funding": best[1]})
    if not cur_oos:
        return {"ok": False, "error": "not enough history for walk-forward folds"}
    cur, ret = statistics.mean(cur_oos), statistics.mean(retuned_oos)
    return {"ok": True, "folds": len(cur_oos),
            "current_oos_apr": cur, "retuned_oos_apr": ret, "retune_edge_apr": ret - cur,
            "retune_helps_oos": (ret - cur) > MATERIAL_GAIN, "picks": picks}


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
    in_sample_optimum = (best["switch_margin"] == cur_sm and best["min_funding"] == cur_mf) or gain < MATERIAL_GAIN

    # The decisive check: does re-tuning actually beat current OUT-OF-SAMPLE (walk-forward)?
    wf = walk_forward(series)

    if in_sample_optimum:
        suggestion = "current settings are at/near the sweep optimum — no change suggested"
        at_optimum = True
    elif wf.get("ok") and not wf["retune_helps_oos"]:
        # in-sample prefers a change, but it does NOT generalise -> the anti-overfit guard
        suggestion = (f"in-sample sweep prefers switch_margin={best['switch_margin']:.0%}/"
                      f"min_funding={best['min_funding']:.0%} (+{gain*100:.1f}% APR), but it does NOT "
                      f"beat current out-of-sample (walk-forward) — KEEP current settings")
        at_optimum = True
    elif wf.get("ok") and wf["retune_helps_oos"]:
        suggestion = (f"consider switch_margin={best['switch_margin']:.0%}, "
                      f"min_funding={best['min_funding']:.0%} — beats current both in-sample "
                      f"(+{gain*100:.1f}%) AND out-of-sample (+{wf['retune_edge_apr']*100:.1f}% walk-forward); "
                      f"still review before changing")
        at_optimum = False
    else:   # not enough history for a walk-forward verdict yet
        suggestion = (f"in-sample sweep prefers switch_margin={best['switch_margin']:.0%}/"
                      f"min_funding={best['min_funding']:.0%} (+{gain*100:.1f}% APR), but history is too "
                      f"short for an out-of-sample check — re-validate as data accumulates")
        at_optimum = False

    return {
        "ok": True, "ts": time.time(), "universe": list(universe), "days": days,
        "window_days": base["window_days"], "span_days": base["span_days"], "n_hours": base["n_hours"],
        "current": {"switch_margin": cur_sm, "min_funding": cur_mf,
                    "apr": base["rotation"]["apr"], "sharpe": base["rotation"]["sharpe"],
                    "maxdd": base["rotation"]["maxdd"], "switches": base["rotation"]["switches"],
                    "vs_btc_apr": base["vs_btc_apr"], "vs_best_apr": base["vs_best_apr"],
                    "best_fixed": base["best_fixed"], "verdict": base["verdict"]},
        "fixed": base["fixed"], "best_in_sweep": best, "sweep": sweep,
        "walk_forward": wf, "at_optimum": at_optimum, "suggestion": suggestion,
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
