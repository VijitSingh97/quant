"""Shared status assembler — one source of truth for the CLI monitor and the web GUI.

build_status() reads the audit store + a (cached) market snapshot + optional read-only
live account, and returns a plain dict ready to print or serialize to JSON.
"""

import time

from . import config
from .allocator import carry_target
from ..core.sources import hyperliquid_perp, deribit_dvol


def market_snapshot(symbol=None):
    symbol = symbol or config.SYMBOL
    hl = hyperliquid_perp(symbol)
    try:
        dv = deribit_dvol(days=2, resolution="1D")
        dvol = dv[-1][1] if dv else None
    except Exception:       # noqa: BLE001
        dvol = None
    return {"symbol": symbol, "mark": hl["mark"], "funding_apr": hl["funding_apr"],
            "funding_rate_1h": hl["funding_rate_1h"], "dvol": dvol, "ts": time.time()}


def opportunities(top=8, days=14, min_oi_usd=10e6):
    """Top perp markets by PERSISTENT funding (the carry scan, for the live tracker).
    1 broad call + a few history calls — cache it (funding moves slowly)."""
    from ..core.sources import hl_all_funding, hl_funding_stats
    hl = hl_all_funding()
    liquid = sorted(((c, d) for c, d in hl.items() if d["oi_usd"] >= min_oi_usd),
                    key=lambda kv: kv[1]["apr"], reverse=True)
    out = []
    for coin, d in liquid[: max(top * 2, 16)]:
        st = None
        try:
            st = hl_funding_stats(coin, days)
        except Exception:       # noqa: BLE001
            pass
        out.append({"coin": coin, "now_apr": d["apr"], "oi_usd": d["oi_usd"],
                    "avg_apr": st["avg"] if st else d["apr"],
                    "pos_frac": st["pos_frac"] if st else None})
    out.sort(key=lambda r: r["avg_apr"], reverse=True)
    return out[:top]


def paper_book(store):
    p = store.positions()
    spot = p.get("spot", {}).get("qty", 0.0)
    perp = p.get("perp", {}).get("qty", 0.0)
    return {"spot": spot, "perp": perp, "net_delta": spot + perp,
            "cash": p.get("cash_usd", {}).get("qty", 0.0),
            "funding_usd": p.get("funding_usd", {}).get("qty", 0.0),
            "fees_usd": p.get("fees_usd", {}).get("qty", 0.0)}


def position_summary(symbol, mark, book, equity, *, carry_on, kill):
    """One clear read of WHAT we're in right now: the pair, the state, the legs,
    the gross notional, and the leverage. Shared by the CLI and the web GUI."""
    spot, perp = book["spot"], book["perp"]
    gross = (abs(spot) + abs(perp)) * mark           # total notional working
    net_delta_usd = (spot + perp) * mark
    leverage = (gross / equity) if equity else 0.0
    engaged = gross > max(equity * 0.04, 50)         # >~4% of equity actually deployed
    if kill:
        state = "HALTED — kill switch active"
    elif not engaged:
        state = "FLAT — in cash" + ("" if carry_on else " (carry OFF: funding ≤ 0)")
    elif carry_on:
        state = "DEPLOYED — delta-neutral carry"
    else:
        state = "WINDING DOWN — carry turned off (funding ≤ 0)"
    return {
        "pair": f"{symbol}-SPOT / {symbol}-PERP",
        "asset": symbol, "venue": config.VENUE,
        "state": state, "engaged": engaged,
        "long_leg": f"{spot:+.4f} {symbol} spot",
        "short_leg": f"{perp:+.4f} {symbol} perp",
        "spot_qty": spot, "perp_qty": perp,
        "spot_notional_usd": spot * mark, "perp_notional_usd": perp * mark,
        "gross_notional_usd": gross, "net_delta_usd": net_delta_usd,
        "leverage": leverage,
    }


def live_account(client):
    try:
        pos = client.positions()
        return {"address": client.address, "spot": pos["spot"], "perp": pos["perp"],
                "net_delta": pos["spot"] + pos["perp"], "equity": client.equity_usd()}
    except Exception as e:  # noqa: BLE001
        return {"address": getattr(client, "address", ""), "error": str(e)[:90]}


def reconcile(our_equity, book, live):
    """Do OUR numbers match the EXCHANGE's? Compare our book (positions/equity) to the
    read-only exchange account. Meaningful when both run the SAME strategy — e.g. a paper
    book vs your testnet account running the same engine (GOING_LIVE.md Step 2.5)."""
    if not live or live.get("error"):
        return {"available": False,
                "reason": (live or {}).get("error") or "set BASIS_HL_ADDRESS (e.g. your testnet account)"}

    def _match(a, b):
        return abs(a - b) <= max(1e-4, 0.02 * max(abs(a), abs(b)))   # within 2% (or dust)

    os_, op = book["spot"], book["perp"]
    ts, tp = live.get("spot", 0.0), live.get("perp", 0.0)
    their_eq = live.get("equity", 0.0)
    spot_ok, perp_ok = _match(os_, ts), _match(op, tp)
    return {
        "available": True,
        "our_spot": os_, "their_spot": ts, "spot_match": spot_ok,
        "our_perp": op, "their_perp": tp, "perp_match": perp_ok,
        "our_delta": book["net_delta"], "their_delta": live.get("net_delta", 0.0),
        "our_equity": our_equity, "their_equity": their_eq,
        "equity_diff": our_equity - their_eq,
        "equity_pct": ((our_equity - their_eq) / their_eq) if their_eq else None,
        "match": spot_ok and perp_ok,
    }


def build_status(store, market=None, include_live=True, opps=None):
    # the displayed asset is whatever the book holds (auto allocator), else the configured one
    symbol = store.get_meta("held_symbol") or config.SYMBOL
    if market is None or (market.get("symbol") and market["symbol"] != symbol):
        market = market_snapshot(symbol)
    pnl = store.latest_pnl()
    equity = pnl["equity_usd"] if pnl else config.CAPITAL_BTC * market["mark"]
    book = paper_book(store)
    live = None
    if include_live and config.HL_ADDRESS:
        from .exchanges.hyperliquid import HyperliquidClient
        live = live_account(HyperliquidClient())
    kill = config.KILL_FILE.exists()
    engaged = (abs(book["spot"]) + abs(book["perp"])) * market["mark"] > config.MIN_ORDER_USD
    # carry_on reflects the hysteretic target: stay on while deployed unless funding < exit;
    # deploy from flat only above enter.
    carry_on = (not config.FUNDING_TIMED) or (
        market["funding_apr"] > (config.FUNDING_EXIT_APR if engaged else config.FUNDING_ENTER_APR))
    return {
        "ts": time.time(), "mode": config.MODE, "venue": config.VENUE, "symbol": symbol,
        "kill": kill,
        "market": market,
        "carry_on": carry_on,
        "target": carry_target(equity, market["mark"], market["funding_apr"], currently_on=engaged),
        "position": position_summary(symbol, market["mark"], book, equity,
                                     carry_on=carry_on, kill=kill),
        "paper": book, "live": live, "equity": equity,
        "reconcile": reconcile(equity, book, live),
        # cross-asset opportunities + whether the engine actually trades the best
        "deployed": {"symbol": symbol, "funding_apr": market["funding_apr"],
                     "auto_rotate": store.get_meta("auto") == "1"},
        "opportunities": opps,
        "config": config.summary(),
        "pnl_history": store.pnl_history(300),
        "audit": store.recent_events(15),
    }
