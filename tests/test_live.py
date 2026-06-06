from btcvol.live.allocator import carry_target
from btcvol.live import risk, config
from btcvol.live.store import Store
from btcvol.live.engine import plan_orders
from btcvol.live.exchanges.base import Order
from btcvol.live.status import build_status, paper_book


# --- allocator ---
def test_carry_target_is_delta_neutral_when_funding_positive():
    t = carry_target(6000, 60000, 0.06)
    assert abs(t["spot"] + t["perp"]) < 1e-12      # net delta 0
    assert t["spot"] > 0 and t["perp"] < 0


def test_carry_target_flat_when_funding_negative_and_timed():
    assert carry_target(6000, 60000, -0.03, timed=True) == {"spot": 0.0, "perp": 0.0}


def test_carry_target_holds_pair_when_not_timed():
    t = carry_target(6000, 60000, -0.03, timed=False)
    assert t["spot"] > 0 and abs(t["spot"] + t["perp"]) < 1e-12


def test_carry_target_respects_deploy_fraction():
    t = carry_target(6000, 60000, 0.06, deploy=0.5)
    assert abs(t["spot"] - (6000 * 0.5 / 60000)) < 1e-12


# --- risk gate (USD-based, asset-agnostic) ---
def _ctx(order_usd=1000, notional=1000, lev=0.5, delta_usd=0.0):
    return {"order_notional_usd": order_usd, "notional_usd_after": notional,
            "leverage_after": lev, "net_delta_usd_after": delta_usd}


def test_risk_passes_clean_order():
    ok, _ = risk.check_order(Order("BTC", "buy", 0.01, "spot"), _ctx())
    assert ok


def test_risk_blocks_oversize_order():
    ok, why = risk.check_order(Order("BTC", "buy", 1.0, "spot"), _ctx(order_usd=config.MAX_ORDER_USD * 2))
    assert not ok and "max" in why


def test_risk_blocks_over_leverage_and_notional():
    assert not risk.check_order(Order("BTC", "sell", 0.01, "perp"), _ctx(lev=3.0))[0]
    assert not risk.check_order(Order("BTC", "sell", 0.01, "perp"), _ctx(notional=999999))[0]


def test_risk_blocks_delta_breach():
    assert not risk.check_order(Order("BTC", "buy", 0.01, "spot"), _ctx(delta_usd=999999))[0]


# --- engine planning ---
def test_plan_orders_diffs_and_clamps():
    orders = plan_orders({"spot": 0.0, "perp": 0.0}, {"spot": 0.085, "perp": -0.085}, 60000, "paper")
    assert {o.leg for o in orders} == {"spot", "perp"}
    assert all(o.qty <= config.MAX_ORDER_USD / 60000 + 1e-9 for o in orders)   # clamped by $ size


def test_plan_orders_noop_at_target():
    assert plan_orders({"spot": 0.085, "perp": -0.085},
                       {"spot": 0.085, "perp": -0.085}, 60000, "paper") == []


# --- audit store ---
def test_store_roundtrip(tmp_path):
    s = Store(tmp_path / "t.db")
    s.log("hello", {"x": 1})
    oid = s.add_order(Order("BTC", "buy", 0.01, "spot", venue="paper"), "accepted", "ok")
    s.add_fill(oid, "BTC", 0.01, 60000)
    s.set_position("spot", 0.01, 60000)
    s.snapshot_pnl(6000, 0.0, "t")
    assert s.positions()["spot"]["qty"] == 0.01
    assert s.recent_events(5)[0]["kind"] == "hello"
    assert s.latest_pnl()["equity_usd"] == 6000
    s.close()


# --- status assembler (offline, injected market) ---
def test_paper_book_net_delta(tmp_path):
    s = Store(tmp_path / "b.db")
    s.set_position("spot", 0.085, 60000)
    s.set_position("perp", -0.085, 60000)
    s.set_position("funding_usd", 1.5, 0)
    b = paper_book(s)
    assert abs(b["net_delta"]) < 1e-9 and b["funding_usd"] == 1.5
    s.close()


def test_build_status_offline(tmp_path):
    s = Store(tmp_path / "b.db")
    s.set_position("spot", 0.0, 0)
    s.set_position("perp", 0.0, 0)
    s.snapshot_pnl(6000, 0.0, "t")
    market = {"mark": 60000, "funding_apr": 0.06, "funding_rate_1h": 6.8e-6, "dvol": 0.5, "ts": 0}
    st = build_status(s, market=market, include_live=False)   # no network
    assert st["carry_on"] is True and st["target"]["spot"] > 0
    assert st["live"] is None and "pnl_history" in st and "audit" in st
    s.close()
