"""Live monitor — read-only status from the audit store: mode, positions, net delta,
equity / funding earned, kill-switch state, and the recent audit trail.

Run:  python3 -m btcvol.live.monitor
"""

import time

from . import config, risk
from .store import Store


def main():
    store = Store(config.DB_PATH)
    pos = store.positions()
    pnl = store.latest_pnl()
    bar = "=" * 64
    print(f"\n{bar}\nLIVE MONITOR ({config.MODE.upper()} / {config.VENUE})\n{bar}")
    print(f"  kill switch: {'ACTIVE — halted' if risk.kill_active() else 'off'}")
    spot = pos.get("spot", {}).get("qty", 0.0)
    perp = pos.get("perp", {}).get("qty", 0.0)
    print(f"  positions    spot {spot:+.4f} BTC   perp {perp:+.4f} BTC   net delta {spot + perp:+.4f} BTC")
    if "cash_usd" in pos:
        print(f"  paper book   cash ${pos['cash_usd']['qty']:,.2f}   funding earned "
              f"${pos.get('funding_usd', {}).get('qty', 0.0):,.4f}")
    if pnl:
        age = (time.time() - pnl["ts"]) / 60
        print(f"  equity       ${pnl['equity_usd']:,.2f}   (last cycle {age:.0f} min ago)")
    print(f"\n  {config.summary()}")
    print(f"\n  recent audit trail:")
    for e in reversed(store.recent_events(10)):
        t = time.strftime("%H:%M:%S", time.gmtime(e["ts"]))
        print(f"    {t}  {e['kind']:16} {e['data'] or ''}")
    store.close()


if __name__ == "__main__":
    main()
