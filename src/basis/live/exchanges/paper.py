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

    def _avg(self, leg):
        return self.store.positions().get(leg, {}).get("avg_price", 0.0)

    def positions(self):
        return {"spot": self._q("spot"), "perp": self._q("perp")}

    def equity_usd(self):
        # Mark BOTH legs: the spot leg via cash+spot·mark, the perp via its unrealized PnL
        # vs entry. For a delta-neutral book (spot = −perp at matched entries) the two price
        # exposures cancel, so equity moves only with funding and fees — NOT with price.
        mark = self.mark_price()
        perp_pnl = self._q("perp") * (mark - self._avg("perp"))
        return self._q("cash_usd") + self._q("spot") * mark + perp_pnl + self._q("funding_usd")

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
        # transaction cost (taker fee + slippage) on notional — charged on BOTH legs so the
        # perp leg's cost isn't invisible. Filled at mark; the cost is the explicit drag.
        cost = order.qty * mark * config.COST_PER_LEG_BPS / 1e4
        q0, dq = self._q(order.leg), order.signed_qty
        q1 = q0 + dq
        cash = self._q("cash_usd") - cost                       # the fee always hits cash
        if order.leg == "spot":
            cash -= dq * mark                                   # spot moves cash by notional (valued at mark)
            self.store.set_position("spot", q1, mark)
        else:
            # perp is margin (no notional cash flow). Track a weighted-average entry and
            # realize PnL into cash when the position is reduced/closed, so equity is exact.
            avg0 = self._avg("perp")
            if q0 != 0 and (q1 == 0 or (q0 > 0) != (q1 > 0) or abs(q1) < abs(q0)):
                if q1 != 0 and (q0 > 0) != (q1 > 0):            # flipped through zero
                    cash += q0 * (mark - avg0)                  # realize all of q0; remainder opens at mark
                    new_avg = mark
                else:                                           # reduced (or closed to zero), same side
                    cash += (q0 - q1) * (mark - avg0)
                    new_avg = avg0 if q1 != 0 else 0.0
            else:                                               # opening / adding in the same direction
                new_avg = (q0 * avg0 + dq * mark) / q1 if q1 != 0 else mark
            self.store.set_position("perp", q1, new_avg)
        self.store.set_position("cash_usd", cash, 1.0)
        self.store.set_position("fees_usd", self._q("fees_usd") - cost, 0.0)
        return {"status": "filled", "price": mark, "qty": order.qty, "cost": round(cost, 6)}
