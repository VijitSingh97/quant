"""Offline tests for the regime study's pure logic (no network)."""

from basis.backtests import regime


def test_weights_off_when_vrp_not_positive():
    assert regime.regime_weights([-0.1, 0.0], [0.05, 0.05], risk=0.15) == [0.0, 0.0]


def test_weights_on_when_rich_and_stable():
    w = regime.regime_weights([0.1, 0.2, 0.15], [0.05, 0.05, 0.05], risk=0.15)
    assert w[0] == 0.15                      # first block: vrp == its own median -> scale 1
    assert all(x > 0 for x in w)             # all vol-rich + stable -> deployed
    assert w[1] > w[0]                        # richer VRP -> larger weight (capped at 2x)


def test_weights_off_when_vol_unstable():
    # vol-of-vol spikes above its running median in the last block -> condor off
    w = regime.regime_weights([0.1, 0.1, 0.1, 0.1], [0.05, 0.05, 0.05, 0.50], risk=0.15)
    assert w[-1] == 0.0


def test_build_books_shape_and_filters():
    rolls = [{"date": "2025-01-01", "iv": 0.6, "rv_trail": 0.4, "vov": 0.05, "ror": 0.1},
             {"date": "2025-01-31", "iv": 0.5, "rv_trail": 0.5, "vov": 0.05, "ror": -0.2}]
    b = regime.build_books(rolls, funding=[], leverage=3.0, risk=0.15, timed=False)
    assert {"always_carry", "static_combined", "regime", "carry", "weights"} <= set(b)
    assert len(b["regime"]) == 2
    assert b["carry"] == [0.0, 0.0]          # no funding supplied
    assert b["weights"][0] > 0               # block 0: VRP=+0.2, stable -> deployed
    assert b["weights"][1] == 0.0            # block 1: VRP=0 -> not deployed
