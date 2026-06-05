import math

from btcvol.core import surface as sf


def test_interp_linear_midpoint():
    pts = [(0.0, 10.0), (1.0, 20.0)]
    assert abs(sf._interp(pts, 0.5) - 15.0) < 1e-12


def test_interp_clamps_outside():
    pts = [(0.0, 10.0), (1.0, 20.0)]
    assert sf._interp(pts, -5) == 10.0
    assert sf._interp(pts, 5) == 20.0


def test_iv_at_strike():
    opts = [{"strike": 50000, "iv": 0.6}, {"strike": 60000, "iv": 0.5}, {"strike": 70000, "iv": 0.55}]
    assert abs(sf.iv_at_strike(opts, 55000) - 0.55) < 1e-9


def test_iv_at_delta_interpolates_one_wing():
    # OTM puts: |delta| decreasing toward 0 as strike falls; IV rises into the wing
    otm_puts = [
        {"strike": 58000, "iv": 0.50, "delta": -0.40},
        {"strike": 54000, "iv": 0.55, "delta": -0.20},
        {"strike": 50000, "iv": 0.62, "delta": -0.10},
    ]
    iv25 = sf.iv_at_delta(otm_puts, 0.25)
    assert 0.50 < iv25 < 0.62


def test_polyfit2_recovers_quadratic():
    a = (1.0, -0.12, 0.07)
    xs = [-2, -1, -0.5, 0, 0.5, 1, 2]
    ys = [a[0] + a[1] * x + a[2] * x * x for x in xs]
    a0, a1, a2 = sf.polyfit2(xs, ys)
    assert abs(a0 - a[0]) < 1e-6 and abs(a1 - a[1]) < 1e-6 and abs(a2 - a[2]) < 1e-6


def test_skew_iv_put_wing_richer_when_a1_negative():
    coeffs = (1.0, -0.12, 0.07)        # negative linear term -> put skew
    S, T, atm = 60000, 30 / 365, 0.50
    iv_put = sf.skew_iv(coeffs, atm, T, S * 0.9, S)    # downside strike
    iv_call = sf.skew_iv(coeffs, atm, T, S * 1.1, S)   # upside strike
    assert iv_put > atm > iv_call * 0.999              # puts above ATM, calls below


def test_skew_iv_atm_is_atm():
    coeffs = (1.0, -0.12, 0.07)
    atm = 0.5
    assert abs(sf.skew_iv(coeffs, atm, 30 / 365, 60000, 60000) - atm) < 1e-9
