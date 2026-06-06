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


def _synthetic_surface():
    return {"S": 60000, "expiries": [
        {"name": "A", "dte": 7, "atm": 0.60, "rr25": -0.10, "bf25": 0.02},
        {"name": "B", "dte": 30, "atm": 0.50, "rr25": -0.08, "bf25": 0.015},
        {"name": "C", "dte": 90, "atm": 0.45, "rr25": -0.05, "bf25": 0.01},
    ]}


def test_summary_metrics_picks_ref_and_slope():
    m = sf.summary_metrics(_synthetic_surface(), ref_dte=30)
    assert m["atm_iv"] == 0.50 and m["rr25"] == -0.08 and m["bf25"] == 0.015
    assert abs(m["term_slope"] - (0.45 - 0.60)) < 1e-12     # ~90d ATM minus front ATM


def test_summary_metrics_empty_surface():
    assert sf.summary_metrics({"S": 60000, "expiries": []}) == {}


def test_summary_metrics_tail_skew_and_pc_oi():
    surf = {"S": 60000, "expiries": [
        {"name": "B", "dte": 30, "atm": 0.50, "rr25": -0.08, "bf25": 0.01,
         "rr10": -0.15, "bf10": 0.03,
         "options": [{"type": "P", "oi": 30}, {"type": "P", "oi": 30}, {"type": "C", "oi": 40}]},
        {"name": "C", "dte": 90, "atm": 0.45, "rr25": -0.05, "bf25": 0.01, "options": []},
    ]}
    m = sf.summary_metrics(surf, ref_dte=30)
    assert m["rr10"] == -0.15 and m["bf10"] == 0.03                 # tail skew from ref expiry
    assert abs(m["pc_oi_ratio"] - (60 / 40)) < 1e-9                 # 60 put OI / 40 call OI
