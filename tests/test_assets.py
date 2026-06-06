import pytest

from basis.core.assets import get_asset, ASSETS, get_macro, MACRO_ASSETS
from basis.backtests.structures import _nice_grid


def test_btc_default_and_has_dvol():
    a = get_asset("BTC")
    assert a["deribit_perp"] == "BTC-PERPETUAL" and a["has_dvol"] is True


def test_case_insensitive_and_none_defaults_to_btc():
    assert get_asset("eth")["deribit_ccy"] == "ETH"
    assert get_asset(None)["deribit_ccy"] == "BTC"


def test_unknown_asset_raises():
    with pytest.raises(ValueError):
        get_asset("NOPE")


def test_paxg_is_vol_only():
    a = get_asset("PAXG")
    assert a["has_perp"] is False and a["okx"] is None and a["deribit_index"] == "paxg_usd"


def test_nice_grid_scales_to_price():
    assert _nice_grid(60000) == 1000      # BTC
    assert _nice_grid(1600) == 25         # ETH
    assert _nice_grid(65) == 1            # SOL


def test_macro_registry():
    m = get_macro("spx")
    assert m["underlying"] == "^GSPC" and m["vol_index"] == "^VIX"
    assert get_macro("GOLD")["vol_index"] == "^GVZ"


def test_macro_unknown_raises():
    with pytest.raises(ValueError):
        get_macro("DOGE")
