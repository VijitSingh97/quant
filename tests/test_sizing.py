from btcvol.core import sizing


def test_vol_target_halves_when_vol_doubles():
    s1 = sizing.vol_target_scale(0.15, 0.30)
    s2 = sizing.vol_target_scale(0.15, 0.60)
    assert abs(s1 - 0.5) < 1e-12
    assert abs(s2 - s1 / 2) < 1e-12


def test_vol_target_caps_when_vol_tiny():
    assert sizing.vol_target_scale(0.15, 0.001, max_scale=3.0) == 3.0
    assert sizing.vol_target_scale(0.15, 0.0) == 3.0       # guard against div-by-zero


def test_kelly_fraction_known_value():
    # p=0.6, b=1 -> 0.6 - 0.4/1 = 0.2
    assert abs(sizing.kelly_fraction(0.6, 1.0) - 0.2) < 1e-12


def test_kelly_negative_when_no_edge():
    # coin flip, even payoff -> zero edge
    assert abs(sizing.kelly_fraction(0.5, 1.0)) < 1e-12
    # bad bet -> negative full Kelly
    assert sizing.kelly_fraction(0.5, 0.5) < 0


def test_fractional_kelly_capped_and_nonnegative():
    # strong edge -> quarter-Kelly, but capped
    assert sizing.fractional_kelly(0.9, 2.0, fraction=0.25, cap=0.1) == 0.1
    # no edge -> 0 (never negative)
    assert sizing.fractional_kelly(0.4, 1.0) == 0.0


def test_fractional_kelly_quarter_of_full():
    full = sizing.kelly_fraction(0.7, 1.5)
    assert abs(sizing.fractional_kelly(0.7, 1.5, fraction=0.25, cap=1.0) - 0.25 * full) < 1e-12
