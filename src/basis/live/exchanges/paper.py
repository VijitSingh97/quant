"""Paper exchange — the default. Simulates fills at the live Hyperliquid mark and
persists positions/cash/funding/fees in the Store, so a paper run produces the same
audit trail a live run would.

Accounting (deliberately simple, documented): the carry is delta-neutral, so perp
price-P&L offsets the spot leg — the P&L that matters is funding, which we accrue
explicitly each cycle. EVERY fill (spot AND perp) is charged a transaction cost of
TAKER_FEE_BPS + SLIPPAGE_BPS on its notional, debited from cash, so reported equity is
NET OF FEES. equity = cash + spot·mark + accrued_funding  (fees already in cash).
"""

import time

from .base import ExchangeClient
from .. import config
from ...core.sources import hyperliquid_perp


class PaperExchange(ExchangeClient):
    name = "paper"

    def __init__(self, store, seed_usd, symbol=None):
        self.store = store
        self.symbol = symbol or config.SYMBOL
        if "cash_usd" not in store.positions():
            store.set_position("cash_usd", seed_usd, 1.0)
            store.set_position("spot", 0.0, 0.0)
            store.set_position("perp", 0.0, 0.0)
            store.set_position("funding_usd", 0.0, 0.0)
            store.set_position("fees_usd", 0.0, 0.0)      # cumulative trading cost (≤ 0)
            store.set_position("last_funding_ts", time.time(), 0.0)
            store.log("paper_seed", {"usd": seed_usd})

    def _meta(self):
        return hyperliquid_perp(self.symbol)

    def mark_price(self, symbol="BTC"):
        return self._meta()["mark"]

    def funding_apr(self, symbol="BTC"):
        return self._meta()["funding_apr"]

    def funding_rate_1h(self, symbol="BTC"):
        return self._meta()["funding_rate_1h"]

    def _q(self, leg):
        return self.store.positions().get(leg, {}).get("qty", 0.0)

    def positions(self):
        return {"spot": self._q("spot"), "perp": self._q("perp")}

    def equity_usd(self):
        return self._q("cash_usd") + self._q("spot") * self.mark_price() + self._q("funding_usd")

    def accrue_funding(self, elapsed_hours=None):
        """Credit funding to a short perp (or debit a long) since the last accrual."""
        now = time.time()
        last = self._q("last_funding_ts") or now
        hrs = elapsed_hours if elapsed_hours is not None else (now - last) / 3600.0
        perp, mark, rate = self._q("perp"), self.mark_price(), self.funding_rate_1h()
        credit = -perp * mark * rate * hrs          # short (perp<0) earns when rate>0
        self.store.set_position("funding_usd", self._q("funding_usd") + credit, 0.0)
        self.store.set_position("last_funding_ts", now, 0.0)
        return credit

    def place_order(self, order):
        mark = self.mark_price()
        # transaction cost (taker fee + slippage) on notional — charged on BOTH legs so
        # the perp leg's cost isn't invisible. Filled at mark; the cost is the explicit drag.
        cost = order.qty * mark * config.COST_PER_LEG_BPS / 1e4
        new_leg = self._q(order.leg) + order.signed_qty
        self.store.set_position(order.leg, new_leg, mark)
        if order.leg == "spot":                      # spot moves cash by notional; perp is margin
            self.store.set_position("cash_usd", self._q("cash_usd") - order.signed_qty * mark - cost, 1.0)
        else:
            self.store.set_position("cash_usd", self._q("cash_usd") - cost, 1.0)   # perp: just the fee
        self.store.set_position("fees_usd", self._q("fees_usd") - cost, 0.0)
        return {"status": "filled", "price": mark, "qty": order.qty, "cost": round(cost, 6)}
