"""Robustness / anti-overfit checks for the condor rule.

Everything rests on ~13 rolls — trivially easy to overfit. This stress-tests the
result three ways, reusing one market pull:
  1. PARAMETER SWEEP — short Δ × wing width. Is the edge broad, or a knife-edge?
  2. WALK-FORWARD — pick the best params on the first half, test them on the second.
  3. COSTS — re-run with a round-trip fee and quantify the drag.

Verdict leans conservative: a one-year, 13-roll sample can't *confirm* an edge, only
flag whether it's fragile. Real confidence needs the accumulating dataset (issue #4).

Run:  python3 -m basis.backtests.robustness [--risk 0.20] [--fee-bps 15] [--flat]
"""

import argparse
import statistics

from ..core import fmt_pct, sharpe, max_drawdown
from .structures import load_market, simulate_from, _summarize, ROLLS_PER_YEAR

DELTAS = [0.10, 0.15, 0.20, 0.25, 0.30]
WINGS = [0.05, 0.08, 0.12]


def _metrics(rolls, risk):
    s = _summarize("", rolls, risk)
    return s["cagr"], s["sharpe"], s["mdd"], s["win_rate"]


def run(risk=0.20, fee_bps=15.0, skew=True, asset="BTC"):
    from ..core.assets import get_asset
    if not get_asset(asset)["has_dvol"]:
        print(f"{asset.upper()} has no DVOL index — try BTC or ETH.")
        return
    market = load_market(skew=skew, asset=asset)
    bar = "=" * 78
    print(f"\n{bar}\nROBUSTNESS / ANTI-OVERFIT — condor rule\n{bar}")
    print(f"window {market['dates'][0]} -> {market['dates'][-1]}   condor: {market['skew_note']}   "
          f"risk {risk:.0%}/roll")

    # ---- 1. parameter sweep (filtered variant) ----
    print(f"\n1) PARAMETER SWEEP — filtered condor, CAGR (Sharpe) by short Δ × wing")
    corner = "Δ / wing"
    print(f"   {corner:>9} " + " ".join(f"{int(w*100):>14}%" for w in WINGS))
    sweep = {}
    for d in DELTAS:
        cells = []
        for w in WINGS:
            sim = simulate_from(market, delta=d, wing_pct=w)
            cagr, shp, mdd, _ = _metrics(sim["filtered"], risk)
            sweep[(d, w)] = (cagr, shp, mdd)
            cells.append(f"{fmt_pct(cagr):>8}({shp:>4.1f})" if shp is not None else f"{fmt_pct(cagr):>8}( n/a)")
        print(f"   {d:>9.2f} " + " ".join(cells))
    cagrs = [v[0] for v in sweep.values()]
    pos = sum(1 for c in cagrs if c > 0)
    print(f"   -> {pos}/{len(cagrs)} combos positive; CAGR range "
          f"{fmt_pct(min(cagrs))} .. {fmt_pct(max(cagrs))}")

    # ---- 2. walk-forward (pick best Sharpe in-sample, test out-of-sample) ----
    print(f"\n2) WALK-FORWARD — pick best params on 1st half, test on 2nd half")
    best, best_shp, wf = None, -9, None
    for (d, w) in sweep:
        sim = simulate_from(market, delta=d, wing_pct=w)
        rolls = sim["filtered"]
        half = len(rolls) // 2
        ins = _summarize("", rolls[:half], risk)
        if ins["sharpe"] is not None and ins["sharpe"] > best_shp:
            best_shp, best = ins["sharpe"], (d, w, rolls, half)
    if best:
        d, w, rolls, half = best
        oos = _summarize("", rolls[half:], risk)
        ins = _summarize("", rolls[:half], risk)
        wf = (ins["sharpe"], oos["sharpe"])
        print(f"   best in-sample: Δ{d:.2f}/wing{int(w*100)}%  "
              f"in-sample CAGR {fmt_pct(ins['cagr'])} (Sharpe {ins['sharpe']:.2f})")
        oos_shp = f"{oos['sharpe']:.2f}" if oos['sharpe'] is not None else "n/a"
        print(f"   -> OUT-OF-SAMPLE CAGR {fmt_pct(oos['cagr'])} (Sharpe {oos_shp})  "
              f"[{half} in / {len(rolls)-half} out rolls — tiny]")

    # ---- 3. cost drag ----
    print(f"\n3) COSTS — round-trip fee drag at the base params (Δ0.20 / wing 8%)")
    base = simulate_from(market, delta=0.20, wing_pct=0.08)
    base_c = _summarize("", base["filtered"], risk)
    withfee = simulate_from(market, delta=0.20, wing_pct=0.08, fee_bps=fee_bps)
    fee_c = _summarize("", withfee["filtered"], risk)
    print(f"   no fees:   CAGR {fmt_pct(base_c['cagr'])}  Sharpe {base_c['sharpe']:.2f}")
    print(f"   {fee_bps:.0f}bps/roll: CAGR {fmt_pct(fee_c['cagr'])}  Sharpe {fee_c['sharpe']:.2f}   "
          f"(drag {fmt_pct(fee_c['cagr']-base_c['cagr'])} CAGR)")

    # ---- verdict ----
    frac_pos = pos / len(cagrs)
    print(f"\n{bar}\nVERDICT\n{bar}")
    if frac_pos >= 0.8:
        print(f"• Edge is BROAD: {pos}/{len(cagrs)} parameter combos positive — not a single lucky corner.")
    elif frac_pos >= 0.5:
        print(f"• Edge is MIXED: only {pos}/{len(cagrs)} combos positive — sensitive to parameters, treat with caution.")
    else:
        print(f"• Edge is FRAGILE: just {pos}/{len(cagrs)} combos positive — likely overfit. Do not size up.")
    if wf and wf[0] is not None and wf[1] is not None and wf[1] < wf[0] - 1:
        print(f"• OVERFIT FLAG: the best in-sample params (Sharpe {wf[0]:.1f}) collapsed out-of-sample "
              f"(Sharpe {wf[1]:.1f}). Classic — don't trust optimized parameters on this little data.")
    print(f"• Walk-forward and cost checks above are directional only — {len(base['filtered'])} rolls is far too few")
    print(f"  to conclude. This tool flags fragility; it can't certify an edge. Confidence needs issue #4's data.")
    print("\n(Educational tooling, not investment advice.)")


def main():
    ap = argparse.ArgumentParser(description="Robustness / anti-overfit checks for the condor rule")
    ap.add_argument("--risk", type=float, default=0.20, help="capital fraction risked per roll (default 0.20)")
    ap.add_argument("--fee-bps", type=float, default=15.0, help="round-trip fee in bps for the cost check (default 15)")
    ap.add_argument("--flat", action="store_true", help="flat-vol pricing (default: real skew)")
    ap.add_argument("--asset", default="BTC", help="asset with a DVOL index (BTC or ETH)")
    args = ap.parse_args()
    run(risk=args.risk, fee_bps=args.fee_bps, skew=not args.flat, asset=args.asset)


if __name__ == "__main__":
    main()
