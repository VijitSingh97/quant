"""Offline tests for the simulated execution path: PaperExchange fills/accrual, the
reconcile loop convergence, and the auto allocator's flatten — using a fixed-mark
PaperExchange subclass so nothing hits the network.
"""

from basis.live import auto, engine
from basis.live.exchanges.base import Order
from basis.live.exchanges.paper import PaperExchange
from basis.live.status import paper_book, position_summary
from basis.live.store import Store


class FixedPaper(PaperExchange):
    """PaperExchange with a fixed mark / funding (no network)."""
    MARK = 60000.0
    FR1H = 1e-5                       # +0.001%/hr funding

    def mark_price(self, symbol=None):
        return self.MARK

    def funding_apr(self, symbol=None):
        return self.FR1H * 24 * 365

    def funding_rate_1h(self, symbol=None):
        return self.FR1H


def _px(tmp_path, seed=6000.0, name="p.db"):
    return FixedPaper(Store(tmp_path / name), seed)


# --- PaperExchange accounting ---
def test_buy_spot_reduces_cash(tmp_path):
    px = _px(tmp_path)
    px.place_order(Order("BTC", "buy", 0.05, "spot"))
    assert abs(px.positions()["spot"] - 0.05) < 1e-9
    assert px.store.positions()["cash_usd"]["qty"] < 6000      # cash spent on spot


def test_perp_is_margin_only_fee_moves_cash(tmp_path):
    from basis.live import config
    px = _px(tmp_path)
    cash0 = px.store.positions()["cash_usd"]["qty"]
    px.place_order(Order("BTC", "sell", 0.05, "perp"))
    assert abs(px.positions()["perp"] + 0.05) < 1e-9
    # perp is margin: cash only moves by the transaction FEE, not the notional
    fee = 0.05 * 60000 * config.COST_PER_LEG_BPS / 1e4
    assert abs((cash0 - px.store.positions()["cash_usd"]["qty"]) - fee) < 1e-6
    assert fee < 0.05 * 60000 * 0.01                          # fee << notional


def test_delta_neutral_equity_preserved(tmp_path):
    px = _px(tmp_path)
    px.place_order(Order("BTC", "buy", 0.05, "spot"))
    px.place_order(Order("BTC", "sell", 0.05, "perp"))
    assert abs(px.positions()["spot"] + px.positions()["perp"]) < 1e-9   # neutral
    assert 5980 < px.equity_usd() < 6000                                 # seed minus fees on both legs


def test_fees_reduce_equity_and_are_tracked(tmp_path):
    from basis.live import config
    px = _px(tmp_path)
    px.place_order(Order("BTC", "buy", 0.05, "spot"))
    px.place_order(Order("BTC", "sell", 0.05, "perp"))
    fees = px.store.positions()["fees_usd"]["qty"]
    expected = -2 * (0.05 * 60000 * config.COST_PER_LEG_BPS / 1e4)        # two legs
    assert abs(fees - expected) < 1e-6
    assert px.equity_usd() <= 6000 + fees + 1e-6                          # equity is net of fees


def test_accrue_funding_credits_short(tmp_path):
    px = _px(tmp_path)
    px.place_order(Order("BTC", "sell", 0.1, "perp"))          # short 0.1
    c = px.accrue_funding(elapsed_hours=1.0)
    assert abs(c - 0.1 * 60000 * 1e-5) < 1e-6                  # short earns funding
    assert abs(px.store.positions()["funding_usd"]["qty"] - 0.06) < 1e-6


# --- reconcile loop ---
def test_reconcile_converges_delta_neutral(tmp_path):
    store = Store(tmp_path / "e.db")
    px = FixedPaper(store, 6000)
    for _ in range(4):                          # clamped orders converge over cycles
        engine.reconcile(px, store)
    pos = px.positions()
    assert abs(pos["spot"] + pos["perp"]) < 1e-9               # delta-neutral
    assert pos["spot"] > 0 and pos["perp"] < 0                 # carry deployed (funding +)
    assert abs(pos["spot"] - 0.85 * px.equity_usd() / px.MARK) < 0.01   # reached target


# --- auto rotation bookkeeping ---
def test_auto_flatten_zeros_legs(tmp_path):
    store = Store(tmp_path / "a.db")
    px = FixedPaper(store, 6000)
    px.place_order(Order("X", "buy", 0.05, "spot"))
    px.place_order(Order("X", "sell", 0.05, "perp"))
    auto._flatten(px, store)
    pos = px.positions()
    assert abs(pos["spot"]) < 1e-9 and abs(pos["perp"]) < 1e-9


# --- position summary (the "what are we in right now" view) ---
def test_position_summary_deployed(tmp_path):
    px = _px(tmp_path)
    px.place_order(Order("BTC", "buy", 0.05, "spot"))
    px.place_order(Order("BTC", "sell", 0.05, "perp"))
    p = position_summary("BTC", px.MARK, paper_book(px.store), px.equity_usd(),
                         carry_on=True, kill=False)
    assert p["pair"] == "BTC-SPOT / BTC-PERP" and p["engaged"]
    assert "DEPLOYED" in p["state"]
    assert abs(p["net_delta_usd"]) < 1e-6 and 0.9 < p["leverage"] < 1.1   # neutral, ~1x gross


def test_position_summary_flat_in_cash(tmp_path):
    px = _px(tmp_path)
    p = position_summary("BTC", px.MARK, paper_book(px.store), px.equity_usd(),
                         carry_on=True, kill=False)
    assert not p["engaged"] and "FLAT" in p["state"] and p["gross_notional_usd"] == 0


def test_position_summary_halted_overrides(tmp_path):
    px = _px(tmp_path)
    px.place_order(Order("BTC", "buy", 0.05, "spot"))
    p = position_summary("BTC", px.MARK, paper_book(px.store), px.equity_usd(),
                         carry_on=True, kill=True)
    assert "HALTED" in p["state"]
