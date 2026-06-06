"""Live-venue smoke tests (OPT-IN — network).

Excluded from the default offline suite; run with:  make test-integration
(or: PYTHONPATH=src python3 -m pytest -q -m integration)

These hit the real endpoints and assert the *shape* of what comes back, so we catch
upstream API drift. A network/geo failure SKIPS (so transient outages and geo-blocked
venues like Binance/Bybit don't fail the suite); a wrong shape FAILS (that's the point).
"""

import pytest

from basis.core.sources import (
    hyperliquid_perp, hl_all_funding, hl_funding_stats, coinbase_spot_and_candles,
    deribit_vol_and_basis, deribit_dvol, deribit_option_chain, deribit_funding_history,
    okx_perp, yahoo_chart, tardis_options_chain, binance_all_funding, bybit_all_funding,
    gate_all_funding, kucoin_all_funding, dydx_all_funding,
)
from basis.live.exchanges.hyperliquid import HyperliquidClient

pytestmark = pytest.mark.integration

HLP_VAULT = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"   # public HL vault for read-only smoke


def fetch(fn):
    """Run a network call; SKIP on any failure (outage/geo), so only shape-asserts fail."""
    try:
        return fn()
    except Exception as e:       # noqa: BLE001
        pytest.skip(f"venue unavailable: {str(e)[:90]}")


# --- Hyperliquid (the carry venue) ---
def test_hl_perp_shape():
    d = fetch(lambda: hyperliquid_perp("BTC"))
    assert d["mark"] > 0 and d["open_interest_usd"] > 0
    for k in ("funding_apr", "funding_rate_1h", "oracle"):
        assert k in d


def test_hl_all_funding_shape():
    m = fetch(hl_all_funding)
    assert "BTC" in m and m["BTC"]["mark"] > 0 and m["BTC"]["oi_usd"] > 0
    assert len(m) > 50           # HL lists 100s of perps


def test_hl_funding_stats_shape():
    st = fetch(lambda: hl_funding_stats("BTC", days=7))
    assert 0.0 <= st["pos_frac"] <= 1.0 and st["n"] > 0
    assert st["lo"] <= st["avg"] <= st["hi"]


def test_hl_readonly_account_by_address():
    c = HyperliquidClient(address=HLP_VAULT)
    pos = fetch(c.positions)
    assert set(pos) == {"spot", "perp"}
    assert fetch(c.equity_usd) > 0          # the HLP vault has real equity


# --- Coinbase (spot / realized vol) ---
def test_coinbase_shape():
    cb = fetch(coinbase_spot_and_candles)
    assert cb["spot"] > 0 and cb["rv_30d"] > 0 and len(cb["closes"]) > 30


# --- Deribit (DVOL, basis, option chain, funding history) ---
def test_deribit_vol_and_basis_shape():
    d = fetch(deribit_vol_and_basis)
    assert d["index"] > 0 and d["dvol"] and d["dvol"] > 0      # BTC has a DVOL index
    assert isinstance(d["term_structure"], list)


def test_deribit_dvol_history_shape():
    dv = fetch(lambda: deribit_dvol(days=30))
    assert len(dv) > 10 and 0 < dv[-1][1] < 5     # (ts, fraction); vol as a fraction


def test_deribit_option_chain_shape():
    ch = fetch(deribit_option_chain)
    assert ch["index"] > 0 and len(ch["options"]) > 50
    o = ch["options"][0]
    assert o["type"] in ("C", "P") and o["strike"] > 0 and o["iv"] > 0


def test_deribit_funding_history_shape():
    fh = fetch(lambda: deribit_funding_history("BTC-PERPETUAL", days=10))
    assert len(fh) > 24 and isinstance(fh[0][0], int)


# --- OKX (cross-venue funding) ---
def test_okx_perp_shape():
    d = fetch(lambda: okx_perp("BTC-USDT-SWAP"))
    assert d["mark"] > 0 and d["index"] > 0 and "funding_apr" in d


# --- Yahoo (cross-asset / macro: VIX) ---
def test_yahoo_vix_shape():
    ch = fetch(lambda: yahoo_chart("^VIX", rng="1mo"))
    assert len(ch["closes"]) > 5 and ch["closes"][-1] > 0


# --- Tardis (free historical option chain) ---
def test_tardis_monthly_snapshot_shape():
    ch = fetch(lambda: tardis_options_chain("2024-06-01"))
    assert ch["index"] > 0 and len(ch["options"]) > 50
    assert ch["options"][0]["iv"] > 0


# --- Geo-blocked venues: SKIP if unreachable, assert shape if reachable ---
def test_binance_all_funding_if_reachable():
    m = fetch(binance_all_funding)          # 451 in many regions -> skip
    assert "BTC" in m and isinstance(m["BTC"], float)


def test_bybit_all_funding_if_reachable():
    m = fetch(bybit_all_funding)            # 403 in many regions -> skip
    assert "BTC" in m and isinstance(m["BTC"], float)


# --- Additional cross-venue funding sources (usually reachable; one call each) ---
def test_gate_all_funding_shape():
    m = fetch(gate_all_funding)
    assert "BTC" in m and isinstance(m["BTC"], float) and len(m) > 100


def test_kucoin_all_funding_shape():
    m = fetch(kucoin_all_funding)
    assert "BTC" in m and isinstance(m["BTC"], float) and len(m) > 100   # XBT normalised to BTC


def test_dydx_all_funding_shape():
    m = fetch(dydx_all_funding)
    assert "BTC" in m and isinstance(m["BTC"], float) and len(m) > 20
