"""Hyperliquid client — READ-ONLY first.

Market data (mark, funding) is public. Account state (positions, equity) is also
public given a wallet address — so Phase-1 read-only needs only BASIS_HL_ADDRESS,
no secret. Order placement is GATED: it raises until live mode + an agent-wallet
signer are wired (Phase 3), and agent wallets cannot withdraw by design.
"""

from .base import ExchangeClient
from .. import config
from ...core.http import http_post
from ...core.sources import hyperliquid_perp

INFO = "https://api.hyperliquid.xyz/info"


class HyperliquidClient(ExchangeClient):
    name = "hyperliquid"

    def __init__(self, address="", symbol=None):
        self.address = address or config.HL_ADDRESS
        self.symbol = symbol or config.SYMBOL

    def mark_price(self, symbol=None):
        return hyperliquid_perp(symbol or self.symbol)["mark"]

    def funding_apr(self, symbol=None):
        return hyperliquid_perp(symbol or self.symbol)["funding_apr"]

    def funding_rate_1h(self, symbol=None):
        return hyperliquid_perp(symbol or self.symbol)["funding_rate_1h"]

    def _require_address(self):
        if not self.address:
            raise RuntimeError("set BASIS_HL_ADDRESS for read-only account access")

    def positions(self):
        self._require_address()
        perp = http_post(INFO, {"type": "clearinghouseState", "user": self.address})
        perp_qty = 0.0
        for ap in perp.get("assetPositions", []):
            p = ap.get("position", {})
            if p.get("coin") == self.symbol:
                perp_qty = float(p.get("szi", 0.0))
        spot = http_post(INFO, {"type": "spotClearinghouseState", "user": self.address})
        spot_qty = sum(float(b["total"]) for b in spot.get("balances", []) if b.get("coin") == self.symbol)
        return {"spot": spot_qty, "perp": perp_qty}

    def equity_usd(self):
        self._require_address()
        st = http_post(INFO, {"type": "clearinghouseState", "user": self.address})
        return float(st.get("marginSummary", {}).get("accountValue", 0.0))

    def place_order(self, order):
        raise RuntimeError(
            "live order placement is not enabled (Phase 3). Requires BASIS_MODE=live and an "
            "agent/API-wallet signer (which cannot withdraw). Paper mode simulates fills instead.")
