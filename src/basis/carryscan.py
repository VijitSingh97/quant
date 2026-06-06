"""Carry scanner — the best perp markets to harvest, across every asset and venue.

Scans ALL perps (not just BTC), ranks by **persistent** funding (multi-day average,
not a single noisy hour), and flags the structurally-hot markets — the ones "not
running efficiently" because one side is hard to access (e.g. XMR: hard to short, so
its perp funding stays rich). Cross-venue (Binance/Bybit) is included where reachable;
they're geo-blocked in some regions and skipped gracefully (Hyperliquid lists the most
perps, so it's the breadth base).

Delta-neutral carry (long spot / short perp) earns this funding. Caveats it flags:
you need a spot leg to be delta-neutral (easy for majors), and a high *average* with a
wild range (e.g. PURR) is a volatile trap, not a clean harvest.

Run:  python3 -m basis.carryscan [--min-oi 10] [--top 15] [--days 14]
"""

import argparse

from .core import fmt_pct, safe
from .core.sources import (hl_all_funding, hl_funding_stats, binance_all_funding,
                           bybit_all_funding, gate_all_funding, kucoin_all_funding,
                           dydx_all_funding)

MAJORS = {"BTC", "ETH", "SOL"}        # deep spot + perp -> cleanly deployable carry

# cross-venue funding sources (one call each). HL is the breadth base + persistence stats;
# these add cross-venue funding so we can spot the same asset paying differently by venue.
VENUES = {"Binance": binance_all_funding, "Bybit": bybit_all_funding,
          "Gate": gate_all_funding, "KuCoin": kucoin_all_funding, "dYdX": dydx_all_funding}


def _tier(oi):
    return "deep" if oi >= 100e6 else "good" if oi >= 30e6 else "ok"


def cross_venue(coin, hl_apr, others):
    """Pure: the cross-venue funding view for one coin — {venue: apr}, best/worst, spread.
    The spread is the perp-vs-perp arb edge (short best-funding venue, long worst)."""
    cross = {"HL": hl_apr}
    for name, fund in others.items():
        if coin in fund:
            cross[name] = fund[coin]
    best_v, worst_v = max(cross, key=cross.get), min(cross, key=cross.get)
    return {"cross": cross, "best_v": best_v, "best": cross[best_v], "worst_v": worst_v,
            "spread": cross[best_v] - cross[worst_v] if len(cross) > 1 else 0.0}


def run(min_oi_musd=10.0, top=15, days=14):
    hl = safe("Hyperliquid", hl_all_funding) or {}
    other = {name: (safe(name, fn) or {}) for name, fn in VENUES.items()}
    venues_up = ["HL"] + [name for name, d in other.items() if d]

    liquid = sorted(((c, d) for c, d in hl.items() if d["oi_usd"] >= min_oi_musd * 1e6),
                    key=lambda kv: kv[1]["apr"], reverse=True)
    # rank by PERSISTENT funding: pull multi-day stats for the richest current candidates
    cands = liquid[: max(top * 2, 24)]
    rows = []
    for coin, d in cands:
        st = safe(coin, lambda c=coin: hl_funding_stats(c, days))
        cv = cross_venue(coin, d["apr"], other)
        rows.append({"coin": coin, "now": d["apr"], "oi": d["oi_usd"], "stats": st, **cv})
    rows.sort(key=lambda r: (r["stats"]["avg"] if r["stats"] else r["now"]), reverse=True)

    bar = "=" * 86
    print(f"\n{bar}\nCARRY SCANNER — best perp markets by PERSISTENT funding ({days}d avg)\n{bar}")
    down = [name for name, d in other.items() if not d]
    print(f"{len(hl)} HL perps scanned · venues up: {', '.join(venues_up)}"
          + (f"  (unreachable here: {', '.join(down)})" if down else ""))
    print(f"\n  {'coin':7} {'now':>8} {f'{days}d avg':>9} {'%hrs+':>6} {'range (lo..hi)':>18} {'OI':>8} {'best venue':>11}  notes")
    for r in rows[:top]:
        st = r["stats"]
        avg = fmt_pct(st["avg"]) if st else "n/a"
        posf = f"{st['pos_frac']*100:.0f}%" if st else "—"
        rng = f"{st['lo']*100:+.0f}..{st['hi']*100:+.0f}%" if st else "—"
        flags = []
        if r["coin"] in MAJORS:
            flags.append("MAJOR")
        elif st and st["avg"] > 0.15 and st["pos_frac"] > 0.8:
            flags.append("structurally hot (persistent)")
        if st and (st["hi"] - st["lo"]) > 5.0:
            flags.append("⚠ wild range — volatile trap")
        bestv = f"{r['best_v']}" + (f" +{fmt_pct(r['spread'])}" if r["spread"] > 0.02 else "")
        print(f"  {r['coin']:7} {fmt_pct(r['now']):>8} {avg:>9} {posf:>6} {rng:>18} "
              f"${r['oi']/1e6:>6.0f}M {bestv:>11}  {', '.join(flags)}")

    print(f"\n  majors (cleanly-deployable, deep spot+perp):")
    for c in ("BTC", "ETH", "SOL"):
        if c in hl:
            st = safe(c, lambda cc=c: hl_funding_stats(cc, days))
            avg = fmt_pct(st["avg"]) if st else "n/a"
            print(f"    {c:5} now {fmt_pct(hl[c]['apr']):>8}   {days}d avg {avg:>8}   ${hl[c]['oi_usd']/1e6:,.0f}M OI")

    # cross-venue funding SPREADS — same asset paying differently by venue (perp-vs-perp arb
    # candidates: long the perp where funding is most negative, short where most positive).
    spreads = sorted((r for r in rows if r["spread"] > 0.05 and len(r["cross"]) > 1),
                     key=lambda r: r["spread"], reverse=True)
    if spreads:
        print(f"\n  cross-venue funding spreads (perp-vs-perp arb candidates — no spot leg needed):")
        for r in spreads[:6]:
            legs = "  ".join(f"{v}:{fmt_pct(a)}" for v, a in sorted(r["cross"].items(),
                                                                    key=lambda kv: kv[1], reverse=True))
            print(f"    {r['coin']:7} spread {fmt_pct(r['spread']):>8}   short {r['best_v']} / long {r['worst_v']}   [{legs}]")

    top_row = rows[0] if rows else None
    print(f"\n{bar}\nREAD\n{bar}")
    if top_row and top_row["stats"]:
        print(f"• Hottest PERSISTENT carry: {top_row['coin']} — {fmt_pct(top_row['stats']['avg'])} {days}d-avg "
              f"({top_row['stats']['pos_frac']*100:.0f}% of hours positive). That's structural, not a spike.")
    print("• Rank by the AVERAGE, not the instantaneous rate — a high avg with a wild range (PURR-type) is")
    print("  a trap. Persistent + tight + high %hrs-positive = a real inefficiency you can harvest.")
    print("• You still need a spot leg to be delta-neutral; alts without co-located spot need cross-venue spot.")
    if spreads:
        print(f"• Cross-venue spreads above net the funding DIFFERENCE delta-neutrally via two perps (no spot),")
        print(f"  but cost 2x fees + margin on both venues + transfer to rebalance — only worth it above ~20-40% APR.")
    if down:
        print(f"• Unreachable from here ({', '.join(down)}) are geo/network-blocked; a VPS in an allowed region")
        print(f"  would add them — the code pulls every venue automatically where reachable.")


def main():
    ap = argparse.ArgumentParser(description="Cross-asset, cross-venue carry (funding) scanner")
    ap.add_argument("--min-oi", type=float, default=10.0, help="min open interest in $M (default 10)")
    ap.add_argument("--top", type=int, default=15, help="rows to show (default 15)")
    ap.add_argument("--days", type=int, default=14, help="persistence window in days (default 14)")
    args = ap.parse_args()
    run(min_oi_musd=args.min_oi, top=args.top, days=args.days)


if __name__ == "__main__":
    main()
