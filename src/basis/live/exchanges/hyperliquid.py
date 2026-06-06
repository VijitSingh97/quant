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

    def _signer(self):
        """Build the HL exchange signer from the agent key. Lazy import: the crypto deps
        (eth_account + hyperliquid-python-sdk) are the OPTIONAL `[live]` extra — everything
        else stays stdlib-only. The agent/API wallet CANNOT withdraw by design."""
        if not config.HL_API_SECRET:
            raise RuntimeError("set BASIS_HL_API_SECRET (agent-wallet key, withdraw-disabled) for live")
        try:
            from eth_account import Account
            from hyperliquid.exchange import Exchange
            from hyperliquid.utils import constants
        except ImportError as e:
            raise RuntimeError('live trading needs the signer deps: pip install -e ".[live]"') from e
        wallet = Account.from_key(config.HL_API_SECRET)
        return Exchange(wallet, constants.MAINNET_API_URL, account_address=self.address or wallet.address)

    def place_order(self, order):
        # Triple gate so live trading can never happen by accident:
        if not config.LIVE:
            raise RuntimeError("place_order called outside live mode (paper sim should be used)")
        if config.KILL_FILE.exists():
            raise RuntimeError("KILL_SWITCH active — refusing to place a live order")
        if not config.LIVE_ARM:
            raise RuntimeError("live mode is NOT armed — set BASIS_LIVE_ARM=1 to send REAL orders "
                               "(deliberate two-step; run `basis-preflight` first)")
        # NOTE: this submission path is UNTESTED against the live venue (it cannot be tested
        # without placing real orders). Verify your FIRST order in the Hyperliquid UI before
        # trusting the loop — tick/lot rounding and spot-asset naming are venue-specific.
        ex = self._signer()
        is_buy = order.side == "buy"
        mark = self.mark_price(order.symbol)
        slip = config.SLIPPAGE_BPS / 1e4
        px = round(mark * (1 + slip) if is_buy else mark * (1 - slip), 6)      # marketable IOC limit
        coin = order.symbol if order.leg == "perp" else f"{order.symbol}/USDC"  # spot pair name
        resp = ex.order(coin, is_buy, order.qty, px, {"limit": {"tif": "Ioc"}})
        return {"status": "submitted", "price": px, "qty": order.qty, "resp": resp}
