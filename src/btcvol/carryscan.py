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

Run:  python3 -m btcvol.carryscan [--min-oi 10] [--top 15] [--days 14]
"""

import argparse

from .core import fmt_pct, safe
from .core.sources import (hl_all_funding, hl_funding_stats,
                           binance_all_funding, bybit_all_funding)

MAJORS = {"BTC", "ETH", "SOL"}        # deep spot + perp -> cleanly deployable carry


def _tier(oi):
    return "deep" if oi >= 100e6 else "good" if oi >= 30e6 else "ok"


def run(min_oi_musd=10.0, top=15, days=14):
    hl = safe("Hyperliquid", hl_all_funding) or {}
    binance = safe("Binance", binance_all_funding) or {}
    bybit = safe("Bybit", bybit_all_funding) or {}
    venues_up = ["HL"] + (["Binance"] if binance else []) + (["Bybit"] if bybit else [])

    liquid = sorted(((c, d) for c, d in hl.items() if d["oi_usd"] >= min_oi_musd * 1e6),
                    key=lambda kv: kv[1]["apr"], reverse=True)
    # rank by PERSISTENT funding: pull multi-day stats for the richest current candidates
    cands = liquid[: max(top * 2, 24)]
    rows = []
    for coin, d in cands:
        st = safe(coin, lambda c=coin: hl_funding_stats(c, days))
        cross = {"HL": d["apr"]}
        if coin in binance:
            cross["Binance"] = binance[coin]
        if coin in bybit:
            cross["Bybit"] = bybit[coin]
        best_v = max(cross, key=cross.get)
        rows.append({"coin": coin, "now": d["apr"], "oi": d["oi_usd"], "stats": st,
                     "best_v": best_v, "best": cross[best_v],
                     "spread": max(cross.values()) - min(cross.values()) if len(cross) > 1 else 0.0})
    rows.sort(key=lambda r: (r["stats"]["avg"] if r["stats"] else r["now"]), reverse=True)

    bar = "=" * 86
    print(f"\n{bar}\nCARRY SCANNER — best perp markets by PERSISTENT funding ({days}d avg)\n{bar}")
    print(f"{len(hl)} HL perps scanned · venues up: {', '.join(venues_up)}"
          + ("" if (binance or bybit) else "  (Binance/Bybit geo-blocked here — HL is the breadth base)"))
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

    top_row = rows[0] if rows else None
    print(f"\n{bar}\nREAD\n{bar}")
    if top_row and top_row["stats"]:
        print(f"• Hottest PERSISTENT carry: {top_row['coin']} — {fmt_pct(top_row['stats']['avg'])} {days}d-avg "
              f"({top_row['stats']['pos_frac']*100:.0f}% of hours positive). That's structural, not a spike.")
    print("• Rank by the AVERAGE, not the instantaneous rate — a high avg with a wild range (PURR-type) is")
    print("  a trap. Persistent + tight + high %hrs-positive = a real inefficiency you can harvest.")
    print("• You still need a spot leg to be delta-neutral; alts without co-located spot need cross-venue spot.")
    if not (binance or bybit):
        print("• Binance/Bybit are geo-blocked from this machine, so cross-venue is HL-only here; the code")
        print("  pulls them automatically where reachable.")


def main():
    ap = argparse.ArgumentParser(description="Cross-asset, cross-venue carry (funding) scanner")
    ap.add_argument("--min-oi", type=float, default=10.0, help="min open interest in $M (default 10)")
    ap.add_argument("--top", type=int, default=15, help="rows to show (default 15)")
    ap.add_argument("--days", type=int, default=14, help="persistence window in days (default 14)")
    args = ap.parse_args()
    run(min_oi_musd=args.min_oi, top=args.top, days=args.days)


if __name__ == "__main__":
    main()
