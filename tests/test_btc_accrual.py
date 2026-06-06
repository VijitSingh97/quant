from btcvol.backtests.btc_accrual import cc_factor, carry_factor


def test_covered_call_accrues_when_below_strike():
    # price ends below strike -> keep all BTC + premium -> > 1
    f = cc_factor(K=70000, ST=60000, premium_usd=1200)
    assert f > 1.0
    assert abs(f - (1.0 + 1200 / 60000)) < 1e-12


def test_covered_call_loses_btc_when_capped():
    # price blows past strike -> capped at K -> end with fewer BTC despite premium
    f = cc_factor(K=60000, ST=90000, premium_usd=1200)       # 60000/90000 + 1200/90000
    assert f < 1.0


def test_carry_is_short_btc_in_numeraire():
    # flat funding, BTC rallies -> carry loses BTC (USD-flat = short BTC)
    assert carry_factor(S0=60000, ST=90000, block_funding=0.0) < 1.0
    # BTC falls -> carry gains BTC
    assert carry_factor(S0=60000, ST=40000, block_funding=0.0) > 1.0


def test_carry_funding_adds():
    base = carry_factor(60000, 60000, 0.0)          # flat price, no funding -> 1.0
    withf = carry_factor(60000, 60000, 0.01)        # +1% funding -> 1.01
    assert abs(base - 1.0) < 1e-12 and abs(withf - 1.01) < 1e-12
