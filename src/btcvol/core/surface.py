"""Implied-volatility surface: per-expiry smile metrics, interpolation, skew fit.

Built from a Deribit option chain. Delta is computed per option from its own mark
IV. Provides:
  - per-expiry ATM IV, 25-delta put/call IV, risk-reversal (RR25) and butterfly (BF25)
  - IV interpolation by strike or by delta
  - a fitted parametric skew (ratio-to-ATM vs standardized moneyness) so other tools
    can apply a realistic smile to a single ATM vol (e.g. historical DVOL)
"""

import math

from .blackscholes import bs_delta


# --------------------------------------------------------------------------- #
# Interpolation
# --------------------------------------------------------------------------- #
def _interp(points, x):
    """Linear interpolation over (x, y) points; clamps outside the range."""
    pts = sorted(points)
    if not pts:
        return None
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1 and x1 != x0:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def iv_at_strike(opts, strike):
    pts = {o["strike"]: o["iv"] for o in opts}
    return _interp(list(pts.items()), strike)


def iv_at_delta(otm_opts, target_abs):
    """IV at a target |delta|, interpolated over one OTM wing (single option type)."""
    pts = [(abs(o["delta"]), o["iv"]) for o in otm_opts if 0.01 < abs(o["delta"]) < 0.99]
    return _interp(pts, target_abs) if pts else None


# --------------------------------------------------------------------------- #
# Surface construction
# --------------------------------------------------------------------------- #
def build_surface(chain):
    S = chain["index"]
    by_exp = {}
    for o in chain["options"]:
        if o["dte"] <= 0 or not o.get("iv") or o["iv"] <= 0:
            continue
        T = o["dte"] / 365.0
        rec = {**o, "T": T, "delta": bs_delta(S, o["strike"], T, o["iv"], o["type"])}
        by_exp.setdefault(o["expiry_ms"], []).append(rec)

    expiries = []
    for ems in sorted(by_exp):
        grp = by_exp[ems]
        dte = grp[0]["dte"]
        atm = iv_at_strike(grp, S)
        otm_puts = [o for o in grp if o["type"] == "P" and o["strike"] <= S]
        otm_calls = [o for o in grp if o["type"] == "C" and o["strike"] >= S]
        put25 = iv_at_delta(otm_puts, 0.25)
        call25 = iv_at_delta(otm_calls, 0.25)
        rec = {
            "name": grp[0]["instrument"].split("-")[1], "dte": dte, "T": dte / 365.0,
            "atm": atm, "put25": put25, "call25": call25,
            "rr25": (call25 - put25) if (put25 and call25) else None,
            "bf25": ((call25 + put25) / 2 - atm) if (put25 and call25 and atm) else None,
            "n": len(grp), "options": grp,
        }
        expiries.append(rec)
    return {"S": S, "expiries": expiries}


# --------------------------------------------------------------------------- #
# Parametric skew fit:  iv/atm  =  a0 + a1*x + a2*x^2 ,  x = ln(K/S)/(atm*sqrt(T))
# --------------------------------------------------------------------------- #
def _solve3(A, b):
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(3):
        piv = max(range(c, 3), key=lambda r: abs(M[r][c]))
        M[c], M[piv] = M[piv], M[c]
        if abs(M[c][c]) < 1e-15:
            continue
        pv = M[c][c]
        M[c] = [v / pv for v in M[c]]
        for r in range(3):
            if r != c:
                f = M[r][c]
                M[r] = [M[r][k] - f * M[c][k] for k in range(4)]
    return [M[i][3] for i in range(3)]


def polyfit2(xs, ys):
    """Least-squares fit of y = a0 + a1*x + a2*x^2."""
    n = len(xs)
    Sx = sum(xs); Sx2 = sum(x * x for x in xs)
    Sx3 = sum(x ** 3 for x in xs); Sx4 = sum(x ** 4 for x in xs)
    Sy = sum(ys); Sxy = sum(x * y for x, y in zip(xs, ys))
    Sx2y = sum(x * x * y for x, y in zip(xs, ys))
    return _solve3([[n, Sx, Sx2], [Sx, Sx2, Sx3], [Sx2, Sx3, Sx4]], [Sy, Sxy, Sx2y])


def fit_skew(surface, target_dte=30, max_x=2.5):
    """Fit the smile shape on the expiry nearest target_dte. Returns a dict with
    coefficients and the reference ATM/expiry, plus a callable iv(atm, T, K)."""
    S = surface["S"]
    rec = min(surface["expiries"], key=lambda e: abs(e["dte"] - target_dte))
    atm, T = rec["atm"], rec["T"]
    xs, ys = [], []
    for o in rec["options"]:
        if not (0.02 < abs(o["delta"]) < 0.98):
            continue
        x = math.log(o["strike"] / S) / (atm * math.sqrt(T))
        if abs(x) <= max_x:
            xs.append(x)
            ys.append(o["iv"] / atm)
    a0, a1, a2 = polyfit2(xs, ys)
    return {"coeffs": (a0, a1, a2), "ref_expiry": rec["name"], "ref_dte": rec["dte"],
            "ref_atm": atm, "n": len(xs)}


def skew_iv(coeffs, atm, T, K, S):
    """Apply a fitted skew shape to an ATM vol -> per-strike IV (floored at 5%)."""
    a0, a1, a2 = coeffs
    if atm <= 0 or T <= 0 or K <= 0 or S <= 0:
        return atm
    x = math.log(K / S) / (atm * math.sqrt(T))
    return max(0.05, atm * (a0 + a1 * x + a2 * x * x))


def summary_metrics(surface, ref_dte=30):
    """Headline surface metrics for logging: ATM, RR25, BF25 at ~ref_dte, plus the
    ATM term-structure slope (~90d minus front). Returns {} if the surface is empty."""
    exps = [e for e in surface["expiries"] if e["atm"]]
    if not exps:
        return {}
    ref = min(exps, key=lambda e: abs(e["dte"] - ref_dte))
    near90 = min(exps, key=lambda e: abs(e["dte"] - 90))
    front = min(exps, key=lambda e: e["dte"])
    slope = (near90["atm"] - front["atm"]) if (near90["atm"] and front["atm"]) else None
    return {"atm_iv": ref["atm"], "rr25": ref["rr25"], "bf25": ref["bf25"],
            "ref_dte": ref["dte"], "term_slope": slope}
