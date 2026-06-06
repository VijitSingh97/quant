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
            "funding_usd": p.get("funding_usd", {}).get("qty", 0.0)}


def live_account(client):
    try:
        pos = client.positions()
        return {"address": client.address, "spot": pos["spot"], "perp": pos["perp"],
                "net_delta": pos["spot"] + pos["perp"], "equity": client.equity_usd()}
    except Exception as e:  # noqa: BLE001
        return {"address": getattr(client, "address", ""), "error": str(e)[:90]}


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
    return {
        "ts": time.time(), "mode": config.MODE, "venue": config.VENUE, "symbol": symbol,
        "kill": config.KILL_FILE.exists(),
        "market": market,
        "carry_on": (market["funding_apr"] > 0) or (not config.FUNDING_TIMED),
        "target": carry_target(equity, market["mark"], market["funding_apr"]),
        "paper": book, "live": live, "equity": equity,
        # cross-asset opportunities + whether the engine actually trades the best
        "deployed": {"symbol": symbol, "funding_apr": market["funding_apr"],
                     "auto_rotate": store.get_meta("auto") == "1"},
        "opportunities": opps,
        "config": config.summary(),
        "pnl_history": store.pnl_history(300),
        "audit": store.recent_events(15),
    }
