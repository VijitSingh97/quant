"""Hyperliquid client — READ-ONLY first.

Market data (mark, funding) is public. Account state (positions, equity) is also
public given a wallet address — so Phase-1 read-only needs only BTCVOL_HL_ADDRESS,
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

    def __init__(self, address=""):
        self.address = address or config.HL_ADDRESS

    def mark_price(self, symbol="BTC"):
        return hyperliquid_perp(symbol)["mark"]

    def funding_apr(self, symbol="BTC"):
        return hyperliquid_perp(symbol)["funding_apr"]

    def funding_rate_1h(self, symbol="BTC"):
        return hyperliquid_perp(symbol)["funding_rate_1h"]

    def _require_address(self):
        if not self.address:
            raise RuntimeError("set BTCVOL_HL_ADDRESS for read-only account access")

    def positions(self):
        self._require_address()
        perp = http_post(INFO, {"type": "clearinghouseState", "user": self.address})
        perp_btc = 0.0
        for ap in perp.get("assetPositions", []):
            p = ap.get("position", {})
            if p.get("coin") == "BTC":
                perp_btc = float(p.get("szi", 0.0))
        spot = http_post(INFO, {"type": "spotClearinghouseState", "user": self.address})
        spot_btc = sum(float(b["total"]) for b in spot.get("balances", []) if b.get("coin") == "BTC")
        return {"spot": spot_btc, "perp": perp_btc}

    def equity_usd(self):
        self._require_address()
        st = http_post(INFO, {"type": "clearinghouseState", "user": self.address})
        return float(st.get("marginSummary", {}).get("accountValue", 0.0))

    def place_order(self, order):
        raise RuntimeError(
            "live order placement is not enabled (Phase 3). Requires BTCVOL_MODE=live and an "
            "agent/API-wallet signer (which cannot withdraw). Paper mode simulates fills instead.")
