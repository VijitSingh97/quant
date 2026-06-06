from btcvol.live.selector import select_asset

# opportunities: list of {coin, avg_apr, oi_usd, now_apr}
OPPS = [
    {"coin": "XMR", "avg_apr": 0.32, "oi_usd": 40e6, "now_apr": 0.11},   # hot but not spot-able
    {"coin": "HYPE", "avg_apr": 0.14, "oi_usd": 1200e6, "now_apr": 0.11},
    {"coin": "ETH", "avg_apr": 0.07, "oi_usd": 1000e6, "now_apr": 0.04},
    {"coin": "BTC", "avg_apr": 0.04, "oi_usd": 2000e6, "now_apr": -0.05},
]
UNIV = {"BTC", "ETH", "SOL", "HYPE"}          # spot-able set (XMR excluded)


def _sel(opps, held, held_avg, **kw):
    kw.setdefault("spot_universe", UNIV)
    kw.setdefault("min_funding", 0.05)
    kw.setdefault("oi_floor", 20e6)
    kw.setdefault("switch_margin", 0.05)
    kw.setdefault("exit_funding", 0.0)
    kw.setdefault("spot_any", False)
    return select_asset(opps, held, held_avg, **kw)


def test_picks_best_spotable_not_the_hot_non_spotable():
    # XMR is hottest but not spot-able -> picks HYPE
    sym, _ = _sel(OPPS, None, None)
    assert sym == "HYPE"


def test_spot_any_allows_xmr():
    sym, _ = _sel(OPPS, None, None, spot_any=True)
    assert sym == "XMR"


def test_oi_floor_excludes_thin_markets():
    opps = [{"coin": "HYPE", "avg_apr": 0.5, "oi_usd": 5e6, "now_apr": 0.5}]  # too thin
    sym, why = _sel(opps, None, None)
    assert sym is None and "no carry" in why


def test_nothing_qualifies_goes_to_cash():
    cold = [{"coin": "BTC", "avg_apr": 0.01, "oi_usd": 2000e6, "now_apr": 0.0}]
    sym, _ = _sel(cold, None, None)
    assert sym is None


def test_hysteresis_holds_when_edge_below_margin():
    # held HYPE at 0.14; best spot-able is HYPE itself -> hold
    sym, why = _sel(OPPS, "HYPE", 0.14)
    assert sym == "HYPE" and "hold" in why


def test_hysteresis_holds_even_if_slightly_beaten():
    # held ETH 0.13; HYPE 0.14 -> edge 0.01 < 0.05 margin -> stay in ETH
    sym, _ = _sel(OPPS, "ETH", 0.13)
    assert sym == "ETH"


def test_rotates_when_edge_exceeds_margin():
    # held ETH 0.05; HYPE 0.14 -> edge 0.09 > margin -> rotate
    sym, why = _sel(OPPS, "ETH", 0.05)
    assert sym == "HYPE" and "rotate" in why


def test_rotates_when_held_stops_qualifying():
    # held ETH funding collapsed below exit -> rotate to best
    sym, why = _sel(OPPS, "ETH", -0.10)
    assert sym == "HYPE" and "no longer qualifies" in why
