"""Cross-asset carry scanner — where is the delta-neutral funding richest right now?

Delta-neutral carry (long spot / short perp) earns the funding rate, and funding
varies hugely across assets. This ranks every Hyperliquid perp by funding APR,
filtered to liquid markets, so capital goes where the carry is best.

It flags the catches: (1) you need a SPOT leg to be delta-neutral — trivial for
BTC/ETH/SOL, needs cross-venue spot for alts; (2) very high funding usually means
thin / volatile / about-to-flip, so the microcap top of the list is a trap, not a gift.

Run:  python3 -m btcvol.carryscan [--min-oi 10] [--top 15]
"""

import argparse

from .core import fmt_pct
from .core.http import http_post

HL_INFO = "https://api.hyperliquid.xyz/info"
MAJORS = {"BTC", "ETH", "SOL"}        # deep spot + perp -> cleanly deployable carry


def scan():
    meta, ctxs = http_post(HL_INFO, {"type": "metaAndAssetCtxs"})
    out = []
    for a, c in zip(meta["universe"], ctxs):
        try:
            px = float(c["oraclePx"])
            out.append({"coin": a["name"], "apr": float(c["funding"]) * 24 * 365,
                        "oi_usd": float(c["openInterest"]) * px, "mark": px})
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _tier(oi):
    return "deep" if oi >= 100e6 else "good" if oi >= 30e6 else "ok"


def run(min_oi_musd=10.0, top=15):
    rows = scan()
    liquid = sorted((r for r in rows if r["oi_usd"] >= min_oi_musd * 1e6),
                    key=lambda r: r["apr"], reverse=True)
    bar = "=" * 70
    print(f"\n{bar}\nCARRY SCANNER — Hyperliquid funding (long spot / short perp earns this)\n{bar}")
    print(f"{len(rows)} perps, {len(liquid)} with >${min_oi_musd:.0f}M OI\n")
    print(f"  {'coin':8} {'funding APR':>12} {'OI':>9}  liquidity  notes")
    for r in liquid[:top]:
        flags = []
        if r["coin"] in MAJORS:
            flags.append("MAJOR (spot easy)")
        if r["apr"] > 0.50:
            flags.append("⚠ very high — likely transient/thin")
        if r["coin"] not in MAJORS:
            flags.append("needs spot leg elsewhere")
        print(f"  {r['coin']:8} {fmt_pct(r['apr']):>12} ${r['oi_usd']/1e6:>6.0f}M  {_tier(r['oi_usd']):>8}   "
              + ", ".join(flags))

    print(f"\n  majors (the cleanly-deployable carry universe):")
    for r in sorted((x for x in rows if x["coin"] in MAJORS), key=lambda x: -x["apr"]):
        state = "earns" if r["apr"] > 0 else "PAYS (flat/cash via timing)"
        print(f"    {r['coin']:5} {fmt_pct(r['apr']):>9} ${r['oi_usd']/1e6:>6.0f}M  -> {state}")

    best_major = max((x for x in rows if x["coin"] in MAJORS), key=lambda x: x["apr"])
    best_liquid = liquid[0] if liquid else None
    print(f"\n{bar}\nREAD\n{bar}")
    if best_major["apr"] > 0:
        print(f"• Best clean carry now: {best_major['coin']} at {fmt_pct(best_major['apr'])} — deep spot+perp, deploy directly.")
    else:
        print(f"• All majors are negative ({best_major['coin']} {fmt_pct(best_major['apr'])}) — the timed carry "
              f"correctly sits in CASH on majors right now.")
    if best_liquid and best_liquid["coin"] not in MAJORS and best_liquid["apr"] > 0.05:
        print(f"• Richest liquid carry: {best_liquid['coin']} {fmt_pct(best_liquid['apr'])} (${best_liquid['oi_usd']/1e6:.0f}M OI) "
              f"— but you'd need spot {best_liquid['coin']} elsewhere to be delta-neutral, and alt funding flips fast.")
    print("• Deploy to the best LIQUID asset you can hold spot for; don't chase microcap funding (it's a trap).")
    print("• Funding is hourly and mean-reverting — re-scan before rotating, and don't churn on noise.")
    print("• BTC-NUMERAIRE WARNING: to accrue BTC, carrying a non-BTC asset means parking capital in")
    print("  USDC/alt = implicitly SHORT BTC. It only out-accrues BTC if its funding edge beats BTC's")
    print("  own drift. BTC-collateralized BTC-carry keeps you in BTC; alt-carry is a short-BTC-for-yield bet.")


def main():
    ap = argparse.ArgumentParser(description="Cross-asset carry (funding) scanner")
    ap.add_argument("--min-oi", type=float, default=10.0, help="min open interest in $M (default 10)")
    ap.add_argument("--top", type=int, default=15, help="rows to show (default 15)")
    args = ap.parse_args()
    run(min_oi_musd=args.min_oi, top=args.top)


if __name__ == "__main__":
    main()
