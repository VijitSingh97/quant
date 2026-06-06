"""Exchange client interface + the Order type.

A 'leg' is "spot" or "perp"; qty is in BTC (always positive — direction is `side`).
The engine talks only to this interface, so paper vs live is just which client is
injected. Real venues credit funding automatically; the paper sim does it explicitly.
"""

import time
from dataclasses import dataclass, field


@dataclass
class Order:
    symbol: str
    side: str                 # "buy" | "sell"
    qty: float                # absolute BTC
    leg: str                  # "spot" | "perp"
    kind: str = "market"
    price: float = 0.0
    venue: str = ""
    client_id: str = field(default_factory=lambda: f"c{int(time.time() * 1000)}")

    @property
    def signed_qty(self):
        return self.qty if self.side == "buy" else -self.qty


class ExchangeClient:
    name = "base"

    def mark_price(self, symbol="BTC"):
        raise NotImplementedError

    def funding_apr(self, symbol="BTC"):
        raise NotImplementedError

    def funding_rate_1h(self, symbol="BTC"):
        raise NotImplementedError

    def positions(self):
        """-> {'spot': btc, 'perp': btc} (perp negative = short)."""
        raise NotImplementedError

    def equity_usd(self):
        raise NotImplementedError

    def accrue_funding(self, elapsed_hours):
        """No-op on real venues (auto-credited); paper sim overrides to credit funding."""
        return 0.0

    def place_order(self, order):
        raise NotImplementedError
