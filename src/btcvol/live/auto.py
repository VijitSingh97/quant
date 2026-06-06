"""Auto-selecting carry allocator (PAPER) — deploy to the best persistent-funding asset
and rotate with hysteresis. Picks from the funding scan (selector.py), risk-gates every
order, audits everything, on its own book (data/live_auto.db).

Run:  python3 -m btcvol.live.auto
View it:  BTCVOL_DB=live_auto.db make live-monitor   (or  make live-web)
"""

from . import config, risk
from .allocator import carry_target
from .exchanges.base import Order
from .exchanges.paper import PaperExchange
from .selector import select_asset
from .status import opportunities
from .store import Store
from ..core import fmt_pct, safe
from ..core.sources import hyperliquid_perp, hl_funding_stats

AUTO_DB = config.DATA_DIR / "live_auto.db"


def _flatten(px, store):
    """Close both legs of the held asset to cash, at its current mark."""
    pos = px.positions()
    for leg in ("spot", "perp"):
        q = pos[leg]
        if abs(q) > 1e-12:
            px.place_order(Order(px.symbol, "sell" if q > 0 else "buy", abs(q), leg, venue="paper"))
            store.log("flatten", {"leg": leg, "qty": round(-q, 6), "symbol": px.symbol})


def _reconcile(px, store, target, mark, equity):
    min_qty, max_qty = config.MIN_ORDER_USD / mark, config.MAX_ORDER_USD / mark
    cur = px.positions()
    for leg in ("spot", "perp"):
        diff = target.get(leg, 0.0) - cur.get(leg, 0.0)
        if abs(diff) < min_qty:
            continue
        qty = min(abs(diff), max_qty)
        o = Order(px.symbol, "buy" if diff > 0 else "sell", qty, leg, price=mark, venue="paper")
        perp_after = abs(cur.get("perp", 0.0) + (o.signed_qty if leg == "perp" else 0.0)) * mark
        ctx = {"order_notional_usd": qty * mark, "notional_usd_after": perp_after,
               "leverage_after": perp_after / equity if equity > 0 else 0.0, "net_delta_usd_after": 0.0}
        ok, why = risk.check_order(o, ctx)
        oid = store.add_order(o, "accepted" if ok else "blocked", why)
        store.log("order_intent", {"order_id": oid, "symbol": px.symbol, "leg": leg,
                                   "side": o.side, "qty": o.qty, "ok": ok, "reason": why})
        if ok:
            res = px.place_order(o)
            store.add_fill(oid, px.symbol, res["qty"], res["price"])
            cur[leg] = cur.get(leg, 0.0) + o.signed_qty


def cycle(store):
    px = PaperExchange(store, config.CAPITAL_BTC * hyperliquid_perp("BTC")["mark"])
    store.set_meta("auto", "1")          # mark this as the auto-rotating book (for the tracker)
    held = store.get_meta("held_symbol") or None
    if held:
        px.symbol = held

    opps = opportunities(top=10) or []
    held_avg = next((o["avg_apr"] for o in opps if o["coin"] == held), None)
    if held and held_avg is None:
        st = safe("held stats", lambda: hl_funding_stats(held))
        held_avg = st["avg"] if st else None

    target, reason = select_asset(opps, held, held_avg)
    store.log("auto_select", {"held": held, "held_avg": held_avg, "target": target, "reason": reason})

    if held and target != held:                       # leave the old asset
        _flatten(px, store)
        store.log("rotate_out", {"from": held})
        held = None
    if target and not held:                           # enter the chosen asset
        px.symbol = target
        store.set_meta("held_symbol", target)
        store.log("rotate_in", {"to": target, "reason": reason})
        held = target
    if target is None:                                # confirmed flat to cash
        store.set_meta("held_symbol", "")

    if held:
        credited = px.accrue_funding()
        if credited:
            store.log("funding_accrued", {"usd": round(credited, 6)})
        mark, funding, equity = px.mark_price(), px.funding_apr(), px.equity_usd()
        _reconcile(px, store, carry_target(equity, mark, funding), mark, equity)

    pos = px.positions()
    net = pos["spot"] + pos["perp"]
    store.snapshot_pnl(px.equity_usd(), net, f"auto ({held or 'cash'})")
    return {"held": held, "target": target, "reason": reason,
            "equity": px.equity_usd(), "net_delta": net, "opps": opps}


def main():
    store = Store(AUTO_DB)
    store.log("auto_start", {"config": config.summary()})
    if risk.kill_active():
        print("KILL_SWITCH active — no trading. Remove", config.KILL_FILE)
        return
    r = cycle(store)
    bar = "=" * 66
    print(f"\n{bar}\nAUTO ALLOCATOR (PAPER) — rotating carry, hysteresis on\n{bar}")
    print(f"  decision : {r['reason']}")
    print(f"  HELD     : {r['held'] or 'CASH'}    equity ${r['equity']:,.2f}    net delta {r['net_delta']:+.4f}")
    if r["opps"]:
        print(f"\n  top persistent carries (spot-able set deploys; others advisory):")
        for o in r["opps"][:6]:
            tag = " <- HELD" if o["coin"] == r["held"] else (
                "" if (config.AUTO_SPOT_ANY or o["coin"] in config.AUTO_SPOT_UNIVERSE) else "  (no co-located spot)")
            print(f"    {o['coin']:7} {fmt_pct(o['avg_apr']):>9} 14d-avg   ${o['oi_usd']/1e6:>6.0f}M{tag}")
    print(f"\n  spot universe: {sorted(config.AUTO_SPOT_UNIVERSE)}"
          f"{' (+ANY override)' if config.AUTO_SPOT_ANY else ''}")
    print(f"  book -> data/{AUTO_DB.name}   view: BTCVOL_DB={AUTO_DB.name} make live-monitor")
    print("  (PAPER — simulated fills, no real orders.)")
    store.close()


if __name__ == "__main__":
    main()
