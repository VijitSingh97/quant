"""Regime study (issue #17, Phase A) — does allocating carry-vs-vol BY REGIME beat
just always running carry?

This is the research foundation for a regime-based strategy switch. It does NOT trade
options live (that needs an options-execution layer — issue #17 Phase B). Here we reuse
the existing backtests to build two low-correlation per-block return streams —

  - CARRY   : levered, funding-timed delta-neutral carry  (carry_per_block)
  - CONDOR  : the defined-risk short-vol roll's return-on-risk  (structures.simulate)

then compare three books over the same monthly blocks, NET OF COST:

  1. always-carry          — the workhorse baseline
  2. static-combined       — carry + a fixed-weight condor when DVOL>RV (today's combined book)
  3. regime-weighted       — carry + a condor weight that scales with the vol regime
                             (richer vol-risk-premium ⇒ more; unstable vol ⇒ off)

The regime weight is computed CAUSALLY (expanding medians, no look-ahead), mirroring the
repo's vol-of-vol gate. Verdict: does regime-conditioning beat the simpler two?

Run:  python3 -m basis.backtests.regime [--leverage 3 --risk 0.15 --asset BTC]
"""

import argparse
import statistics

from ..core import fmt_pct, pearson
from ..core.sources import deribit_funding_history
from ..core.assets import get_asset
from ..live import config
from .structures import simulate
from .combined import carry_per_block, leg_stats

CONDOR_LEGS = 4                                  # iron condor = 4 option legs
CONDOR_COST = CONDOR_LEGS * config.COST_PER_LEG_BPS / 1e4   # round-trip cost per active roll (on weight)


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def regime_weights(vrps, vovs, risk):
    """Per-block condor weight, computed causally (expanding medians ⇒ no look-ahead):
    off when VRP≤0 (vol not rich) or vol-of-vol above its running median (unstable);
    otherwise scale the base `risk` up to 2x with how rich the VRP is vs its median."""
    out = []
    for i in range(len(vrps)):
        vrp, vov = vrps[i], vovs[i]
        vrp_med = _median(vrps[:i + 1])
        vov_med = _median(vovs[:i + 1])
        if vrp is None or vrp <= 0 or (vov is not None and vov_med is not None and vov > vov_med):
            out.append(0.0)
            continue
        scale = min(2.0, vrp / vrp_med) if (vrp_med and vrp_med > 0) else 1.0
        out.append(risk * scale)
    return out


def build_books(rolls, funding, leverage, risk, timed=True):
    """Return per-block streams for the three books + the regime features."""
    carry = carry_per_block(rolls, funding, leverage, timed=timed)
    vrps = [(r["iv"] - r["rv_trail"]) if (r["iv"] and r["rv_trail"]) else None for r in rolls]
    vovs = [r.get("vov") for r in rolls]
    w_reg = regime_weights(vrps, vovs, risk)

    always_carry, static_combined, regime = [], [], []
    for i, r in enumerate(rolls):
        ror = r["ror"]
        rich = (r["iv"] and r["rv_trail"] and r["iv"] > r["rv_trail"])   # DVOL>RV filter
        w_static = risk if rich else 0.0
        always_carry.append(carry[i])
        static_combined.append(carry[i] + w_static * ror - (CONDOR_COST * w_static if w_static else 0.0))
        regime.append(carry[i] + w_reg[i] * ror - (CONDOR_COST * w_reg[i] if w_reg[i] else 0.0))
    return {"always_carry": always_carry, "static_combined": static_combined, "regime": regime,
            "carry": carry, "vrps": vrps, "vovs": vovs, "weights": w_reg}


def run(leverage=3.0, risk=0.15, asset="BTC", timed=True):
    a = get_asset(asset)
    if not a["has_dvol"]:
        print(f"{asset.upper()} has no DVOL index — try BTC or ETH.")
        return
    sim = simulate(skew=True, asset=asset)
    rolls = sim["always"]                          # every month (raw ror + iv/rv/vov features)
    if not rolls:
        print("No rolls.")
        return
    funding = deribit_funding_history(a["deribit_perp"], days=1020)
    b = build_books(rolls, funding, leverage, risk, timed=timed)

    sc, ss, sr = leg_stats(b["always_carry"]), leg_stats(b["static_combined"]), leg_stats(b["regime"])
    print(f"\nREGIME STUDY ({asset.upper()}) — {len(rolls)} monthly blocks, "
          f"lev {leverage}x, condor risk {risk:.0%}, cost {config.COST_PER_LEG_BPS:.1f}bps/leg")
    print(f"\n  {'book':18} {'total':>9} {'CAGR':>9} {'Sharpe':>8} {'maxDD':>9}")
    print("  " + "-" * 56)
    for name, s in (("always-carry", sc), ("static-combined", ss), ("regime-weighted", sr)):
        sh = f"{s['sharpe']:.2f}" if s["sharpe"] is not None else "n/a"
        print(f"  {name:18} {fmt_pct(s['total']):>9} {fmt_pct(s['cagr']):>9} {sh:>8} {fmt_pct(s['mdd']):>9}")

    # regime breakdown: where does the condor actually earn?
    vol_rich = [i for i, w in enumerate(b["weights"]) if w > 0]
    print(f"\n  condor deployed in {len(vol_rich)}/{len(rolls)} blocks (vol-rich + stable)")
    if vol_rich:
        cond_pnl = sum(b["regime"][i] - b["carry"][i] for i in vol_rich)
        print(f"  condor overlay net contribution: {fmt_pct(cond_pnl)} (sum over deployed blocks)")
    corr = pearson(b["carry"], [r - c for r, c in zip(b["regime"], b["carry"])])
    if corr is not None:
        print(f"  carry vs condor-overlay correlation: r = {corr:+.2f}")

    best = max((("always-carry", sc), ("static-combined", ss), ("regime-weighted", sr)),
               key=lambda kv: (kv[1]["sharpe"] or -9))
    print(f"\n  VERDICT: best risk-adjusted book = {best[0]}.")
    if best[0] == "regime-weighted":
        print("  Regime-conditioning helps (historically). NEXT: issue #17 Phase B — a live")
        print("  options-execution path so the vol leg can actually be traded, not just modelled.")
    else:
        print("  Regime-conditioning did NOT beat the simpler book here — consistent with the")
        print("  finding that the condor is a marginal hedge, not a return source. Carry stays")
        print("  the workhorse; revisit with more history (#4) before building live vol execution.")
    print("\n  (Educational backtest; the vol leg is modelled, not live. Costs are an assumption.)")


def main():
    ap = argparse.ArgumentParser(description="Regime study: carry vs vol allocation by regime (#17 Phase A)")
    ap.add_argument("--leverage", type=float, default=3.0)
    ap.add_argument("--risk", type=float, default=0.15, help="base condor risk fraction")
    ap.add_argument("--asset", default="BTC")
    ap.add_argument("--no-timed", action="store_true", help="disable funding-timing on carry")
    a = ap.parse_args()
    run(leverage=a.leverage, risk=a.risk, asset=a.asset, timed=not a.no_timed)


if __name__ == "__main__":
    main()
