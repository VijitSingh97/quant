"""basis-tune — the guarded apply path for self-validation suggestions (#18 Phase B).

The scheduled self-validation (validate.py) only SUGGESTS parameter changes. This is the
human-in-the-loop way to APPLY one safely. Nothing here runs automatically — the scheduler
never tunes; YOU run this command, and that is the approval.

Guards:
  - bounded      — a value outside its safe range is rejected
  - OOS-gated    — by default only applies a report whose suggestion beat current
                   out-of-sample (walk-forward); --force overrides
  - auditable    — every change is logged to research.db (from -> to + the report id)
  - reversible   — --rollback undoes the last change; --reset clears all overrides

Applying writes data/overrides.json (read by config on the next start), so restart the
scheduler to take effect:  docker compose restart basis

  basis-tune --list                 # recent suggestions + report ids + current overrides
  basis-tune --apply <report_id>    # apply that report's recommendation
  basis-tune --rollback             # undo the last applied change
  basis-tune --reset                # clear all overrides (back to defaults)
"""

import argparse
import json
import time

from . import config
from .store import Store

# safe ranges for the tunable parameters (reject anything outside)
BOUNDS = {
    "AUTO_SWITCH_MARGIN": (0.01, 0.20),     # hysteresis margin
    "AUTO_MIN_FUNDING": (0.0, 0.30),        # min trailing APR to deploy
}


def _write_overrides(d):
    config.OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.OVERRIDES_PATH.write_text(json.dumps(d, indent=2))


def _bounds_ok(params):
    for k, v in params.items():
        lo, hi = BOUNDS.get(k, (None, None))
        if lo is not None and not (lo <= v <= hi):
            return False, f"{k}={v} outside safe range [{lo}, {hi}]"
    return True, "ok"


def list_cmd(store):
    print("Current overrides (applied):", config.load_overrides() or "(none — using defaults)")
    print(f"Effective: AUTO_SWITCH_MARGIN={config.AUTO_SWITCH_MARGIN:.0%}  "
          f"AUTO_MIN_FUNDING={config.AUTO_MIN_FUNDING:.0%}\n")
    reports = store.recent_reports("validation", 10)
    if not reports:
        print("No validation reports yet — run `make validate` (or wait for the weekly cycle).")
        return
    print(f"{'id':>4}  {'when':<20} {'rec?':<5} suggestion")
    print("  " + "-" * 78)
    for r in reports:
        d = r.get("data") or {}
        rec = "no" if d.get("at_optimum", True) else "YES"
        when = time.strftime("%Y-%m-%d %H:%M", time.gmtime(r["ts"]))
        print(f"{r['id']:>4}  {when:<20} {rec:<5} {(r.get('summary') or '')[:74]}")
    print("\nApply one with:  basis-tune --apply <id>   (only 'rec?=YES' reports change anything)")


def apply_cmd(store, report_id, force=False):
    rep = store.get_report(report_id)
    if not rep or rep["kind"] != "validation":
        print(f"No validation report with id {report_id}. Use `basis-tune --list`.")
        return 1
    d = rep.get("data") or {}
    if not d.get("ok"):
        print(f"Report {report_id} did not complete successfully — nothing to apply.")
        return 1
    if d.get("at_optimum") and not force:
        print(f"Report {report_id} recommends NO change (current settings near-optimal / didn't "
              f"beat current out-of-sample). Use --force to apply anyway.")
        return 1

    best = d["best_in_sweep"]
    new = {"AUTO_SWITCH_MARGIN": float(best["switch_margin"]),
           "AUTO_MIN_FUNDING": float(best["min_funding"])}
    ok, why = _bounds_ok(new)
    if not ok:
        print(f"Rejected: {why}")
        return 1

    old = config.load_overrides()
    merged = {**old, **new}
    _write_overrides(merged)
    store.add_report("config_change", f"applied report #{report_id}: {new}",
                     {"from_overrides": old, "to_overrides": merged, "report_id": report_id,
                      "params": new, "ts": time.time()})
    print(f"Applied report #{report_id}:")
    print(f"  AUTO_SWITCH_MARGIN -> {new['AUTO_SWITCH_MARGIN']:.0%}")
    print(f"  AUTO_MIN_FUNDING   -> {new['AUTO_MIN_FUNDING']:.0%}")
    print(f"  written to {config.OVERRIDES_PATH}")
    print("  RESTART the scheduler to take effect:  docker compose restart basis")
    return 0


def rollback_cmd(store):
    changes = store.recent_reports("config_change", 1)
    if not changes:
        print("No config changes to roll back.")
        return 1
    last = changes[0]["data"] or {}
    prev = last.get("from_overrides", {})
    if prev:
        _write_overrides(prev)
    else:
        config.OVERRIDES_PATH.unlink(missing_ok=True)
    store.add_report("config_change", "rollback", {"from_overrides": last.get("to_overrides", {}),
                                                   "to_overrides": prev, "rollback_of": last})
    print(f"Rolled back to: {prev or '(defaults)'}")
    print("  RESTART the scheduler to take effect:  docker compose restart basis")
    return 0


def reset_cmd(store):
    had = config.load_overrides()
    config.OVERRIDES_PATH.unlink(missing_ok=True)
    store.add_report("config_change", "reset to defaults", {"from_overrides": had, "to_overrides": {}})
    print("Cleared all overrides — back to defaults. Restart the scheduler to take effect.")
    return 0


def cli():
    ap = argparse.ArgumentParser(description="Guarded apply path for self-validation suggestions (#18)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--list", action="store_true", help="list recent suggestions + current overrides")
    g.add_argument("--apply", type=int, metavar="REPORT_ID", help="apply a report's recommendation")
    g.add_argument("--rollback", action="store_true", help="undo the last applied change")
    g.add_argument("--reset", action="store_true", help="clear all overrides")
    ap.add_argument("--force", action="store_true", help="apply even if the report recommends no change")
    a = ap.parse_args()

    store = Store(config.RESEARCH_DB)
    try:
        if a.apply is not None:
            raise SystemExit(apply_cmd(store, a.apply, force=a.force))
        if a.rollback:
            raise SystemExit(rollback_cmd(store))
        if a.reset:
            raise SystemExit(reset_cmd(store))
        list_cmd(store)          # default
    finally:
        store.close()


if __name__ == "__main__":
    cli()
