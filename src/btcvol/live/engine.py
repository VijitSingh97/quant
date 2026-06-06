"""Reconcile engine — one cycle: read state, compute carry target, diff to orders,
risk-gate each, (paper-)fill, and audit everything. Never sends live orders unless
BTCVOL_MODE=live (then it's the live client's place_order, still risk-gated).

Run one cycle:  python3 -m btcvol.live.engine
"""

from . import config, risk
from .allocator import carry_target
from .exchanges.base import Order
from .store import Store


def build_client(store):
    if config.LIVE and config.VENUE == "hyperliquid":
        from .exchanges.hyperliquid import HyperliquidClient
        return HyperliquidClient()
    from .exchanges.paper import PaperExchange
    from ..core.sources import hyperliquid_perp
    return PaperExchange(store, config.CAPITAL_BTC * hyperliquid_perp("BTC")["mark"])


def plan_orders(current, target, mark, venue):
    orders = []
    for leg in ("spot", "perp"):
        diff = target.get(leg, 0.0) - current.get(leg, 0.0)
        if abs(diff) < config.MIN_ORDER_BTC:
            continue
        qty = min(abs(diff), config.MAX_ORDER_BTC)           # clamp; next cycle finishes the rest
        orders.append(Order(symbol=config.SYMBOL, side="buy" if diff > 0 else "sell",
                            qty=qty, leg=leg, price=mark, venue=venue))
    return orders


def reconcile(client, store):
    mark = client.mark_price()
    funding = client.funding_apr()
    credited = client.accrue_funding()
    if credited:
        store.log("funding_accrued", {"usd": round(credited, 6)})

    equity = client.equity_usd()
    target = carry_target(equity, mark, funding)
    current = client.positions()
    target_delta = target["spot"] + target["perp"]
    store.log("cycle", {"mark": mark, "funding_apr": round(funding, 4), "equity": round(equity, 2),
                        "current": current, "target": target})

    orders = plan_orders(current, target, mark, client.name)
    placed = 0
    for o in orders:
        after = dict(current)
        after[o.leg] = after.get(o.leg, 0.0) + o.signed_qty
        ctx = {"notional_usd_after": abs(after.get("perp", 0.0)) * mark,
               "leverage_after": (abs(after.get("perp", 0.0)) * mark / equity) if equity > 0 else 0,
               "net_delta_after_btc": target_delta}          # strategy target is neutral by construction
        ok, reason = risk.check_order(o, ctx)
        oid = store.add_order(o, "accepted" if ok else "blocked", reason)
        store.log("order_intent", {"order_id": oid, "leg": o.leg, "side": o.side,
                                   "qty": o.qty, "ok": ok, "reason": reason, "mode": config.MODE})
        if ok:
            res = client.place_order(o)
            store.add_fill(oid, o.symbol, res["qty"], res["price"])
            store.log("fill", {"order_id": oid, "qty": res["qty"], "price": res["price"]})
            current[o.leg] = current.get(o.leg, 0.0) + o.signed_qty
            placed += 1

    pos = client.positions()
    net_delta = pos["spot"] + pos["perp"]
    store.snapshot_pnl(client.equity_usd(), net_delta, f"cycle ({config.MODE})")
    return {"mark": mark, "funding_apr": funding, "equity": client.equity_usd(),
            "positions": pos, "net_delta": net_delta, "orders_placed": placed, "orders_planned": len(orders)}


def main():
    store = Store(config.DB_PATH)
    store.log("engine_start", {"config": config.summary()})
    if risk.kill_active():
        print("KILL_SWITCH active — no trading. Remove", config.KILL_FILE, "to resume.")
        store.log("kill_active", {})
        return
    client = build_client(store)
    r = reconcile(client, store)
    bar = "=" * 64
    print(f"\n{bar}\nRECONCILE ({config.MODE.upper()} / {client.name})\n{bar}")
    print(f"  mark ${r['mark']:,.0f}   funding {r['funding_apr']*100:+.2f}% APR   equity ${r['equity']:,.2f}")
    print(f"  positions  spot {r['positions']['spot']:+.4f}  perp {r['positions']['perp']:+.4f}  "
          f"net delta {r['net_delta']:+.4f} BTC")
    print(f"  orders     {r['orders_placed']} placed / {r['orders_planned']} planned")
    print(f"\n  {config.summary()}")
    if config.MODE == "paper":
        print("  (PAPER — simulated fills, no real orders. Run repeatedly to accrue carry.)")
    store.close()


if __name__ == "__main__":
    main()
