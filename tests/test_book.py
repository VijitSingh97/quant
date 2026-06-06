from basis.book import compute, hedge_btc


def _chain():
    # minimal synthetic chain: one ~30d put and call
    return {
        "index": 60000.0,
        "options": [
            {"instrument": "BTC-X-55000-P", "strike": 55000, "type": "P", "iv": 0.55, "dte": 30},
            {"instrument": "BTC-X-67000-C", "strike": 67000, "type": "C", "iv": 0.50, "dte": 30},
        ],
    }


def test_hedge_is_opposite_of_net():
    assert hedge_btc(0.2) == -0.2
    assert hedge_btc(-0.3) == 0.3


def test_carry_book_is_neutral():
    res = compute({"spot_btc": 1.0, "perps": [{"venue": "okx", "qty_btc": -1.0}]}, _chain())
    assert abs(res["net_btc"]) < 1e-12


def test_short_put_adds_positive_delta():
    res = compute({"options": [{"instrument": "BTC-X-55000-P", "qty": -1.0}]}, _chain())
    # short an OTM put -> positive position delta (put unit delta is negative)
    assert res["net_btc"] > 0
    leg = res["legs"][0]
    assert leg["unit"] < 0 and leg["delta"] > 0


def test_net_usd_scales_with_spot():
    res = compute({"spot_btc": 0.5}, _chain())
    assert abs(res["net_usd"] - 0.5 * 60000) < 1e-6


def test_missing_instrument_flagged_and_excluded():
    res = compute({"spot_btc": 1.0, "options": [{"instrument": "BTC-X-NOPE-C", "qty": -1.0}]}, _chain())
    assert any(l.get("missing") for l in res["legs"])
    assert abs(res["net_btc"] - 1.0) < 1e-12        # missing leg excluded from net
