"""Shared status assembler — one source of truth for the CLI monitor and the web GUI.

build_status() reads the audit store + a (cached) market snapshot + optional read-only
live account, and returns a plain dict ready to print or serialize to JSON.
"""

import time

from . import config
from .allocator import carry_target
from ..core.sources import hyperliquid_perp, deribit_dvol


def market_snapshot():
    hl = hyperliquid_perp(config.SYMBOL)
    try:
        dv = deribit_dvol(days=2, resolution="1D")
        dvol = dv[-1][1] if dv else None
    except Exception:       # noqa: BLE001
        dvol = None
    return {"mark": hl["mark"], "funding_apr": hl["funding_apr"],
            "funding_rate_1h": hl["funding_rate_1h"], "dvol": dvol, "ts": time.time()}


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


def build_status(store, market=None, include_live=True):
    market = market or market_snapshot()
    pnl = store.latest_pnl()
    equity = pnl["equity_usd"] if pnl else config.CAPITAL_BTC * market["mark"]
    book = paper_book(store)
    live = None
    if include_live and config.HL_ADDRESS:
        from .exchanges.hyperliquid import HyperliquidClient
        live = live_account(HyperliquidClient())
    return {
        "ts": time.time(), "mode": config.MODE, "venue": config.VENUE, "symbol": config.SYMBOL,
        "kill": config.KILL_FILE.exists(),
        "market": market,
        "carry_on": (market["funding_apr"] > 0) or (not config.FUNDING_TIMED),
        "target": carry_target(equity, market["mark"], market["funding_apr"]),
        "paper": book, "live": live, "equity": equity,
        "config": config.summary(),
        "pnl_history": store.pnl_history(300),
        "audit": store.recent_events(15),
    }
