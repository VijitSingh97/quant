"""Live monitor — CLI status from the audit store + market + (read-only) live account.

Paper book always; if BTCVOL_HL_ADDRESS is set, also shows your real Hyperliquid
account (positions/equity) read-only — Phase 1. Run:  python3 -m btcvol.live.monitor
"""

import time

from . import config
from .status import build_status
from .store import Store


def main():
    store = Store(config.DB_PATH)
    s = build_status(store)
    bar = "=" * 64
    print(f"\n{bar}\nLIVE MONITOR ({s['mode'].upper()} / {s['venue']})\n{bar}")
    sym = s["symbol"]
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

    print(f"\n  {s['config']}")
    print(f"\n  recent audit trail:")
    for e in reversed(s["audit"][:10]):
        ts = time.strftime("%H:%M:%S", time.gmtime(e["ts"]))
        print(f"    {ts}  {e['kind']:16} {(e['data'] or '')[:90]}")
    store.close()


if __name__ == "__main__":
    main()
