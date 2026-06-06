"""Live monitor — CLI status from the audit store + market + (read-only) live account
+ the cross-asset carry opportunities and whether the engine is actually trading them.

Paper book always; if BTCVOL_HL_ADDRESS is set, also shows your real Hyperliquid
account (read-only — Phase 1). Run:  python3 -m btcvol.live.monitor
"""

import time

from . import config
from .status import build_status, opportunities
from .store import Store
from ..core import fmt_pct, safe


def main():
    store = Store(config.DB_PATH)
    opps = safe("opportunities", lambda: opportunities(top=8))
    s = build_status(store, opps=opps)
    sym = s["symbol"]
    bar = "=" * 64
    print(f"\n{bar}\nLIVE MONITOR ({s['mode'].upper()} / {s['venue']})\n{bar}")
    print(f"  kill switch: {'ACTIVE — halted' if s['kill'] else 'off'}")
    m = s["market"]
    print(f"  market       {sym} ${m['mark']:,.2f}   funding {m['funding_apr']*100:+.2f}% APR "
          f"({'carry ON' if s['carry_on'] else 'carry OFF — flat'})"
          + (f"   DVOL {m['dvol']*100:.0f}%" if m.get('dvol') else ""))

    b = s["paper"]
    print(f"\n  PAPER book   spot {b['spot']:+.4f}  perp {b['perp']:+.4f}  net delta {b['net_delta']:+.4f} {sym}")
    print(f"               cash ${b['cash']:,.2f}   funding earned ${b['funding_usd']:,.4f}   "
          f"equity ${s['equity']:,.2f}")
    t = s["target"]
    print(f"  target       spot {t['spot']:+.4f}  perp {t['perp']:+.4f}  (deploy {config.DEPLOY_FRACTION:.0%})")

    if s["live"]:
        lv = s["live"]
        if "error" in lv:
            print(f"\n  LIVE account ({lv['address'][:10]}…): {lv['error']}")
        else:
            print(f"\n  LIVE account ({lv['address'][:10]}…)   spot {lv['spot']:+.4f}  perp {lv['perp']:+.4f}  "
                  f"net delta {lv['net_delta']:+.4f} {sym}   equity ${lv['equity']:,.2f}")
    else:
        print(f"\n  LIVE account: set BTCVOL_HL_ADDRESS=0x… for read-only live view (Phase 1)")

    if opps:
        best = opps[0]
        print(f"\n  CARRY OPPORTUNITIES (persistent 14d-avg funding, all perps):")
        print(f"    {'coin':7} {'14d-avg':>9} {'now':>8} {'%hrs+':>6} {'OI':>8}")
        for o in opps:
            here = "  <- DEPLOYED" if o["coin"] == sym else ""
            posf = f"{o['pos_frac']*100:.0f}%" if o["pos_frac"] is not None else "—"
            print(f"    {o['coin']:7} {fmt_pct(o['avg_apr']):>9} {fmt_pct(o['now_apr']):>8} {posf:>6} "
                  f"${o['oi_usd']/1e6:>6.0f}M{here}")
        print(f"\n  TRADING: engine deploys {sym} (FIXED, auto-rotate OFF) at {fmt_pct(m['funding_apr'])} now.")
        if best["coin"] != sym:
            print(f"           best persistent carry is {best['coin']} ({fmt_pct(best['avg_apr'])} 14d-avg) — "
                  f"NOT being traded (no auto-selection yet).")

    print(f"\n  {s['config']}")
    print(f"\n  recent audit trail:")
    for e in reversed(s["audit"][:8]):
        ts = time.strftime("%H:%M:%S", time.gmtime(e["ts"]))
        print(f"    {ts}  {e['kind']:16} {(e['data'] or '')[:90]}")
    store.close()


if __name__ == "__main__":
    main()
