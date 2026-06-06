"""Read Deribit's live BTC implied-vol surface: term structure, skew, and the smile.

Shows, per expiry, ATM vol, 25-delta put/call vol, risk-reversal (RR25 = call - put;
negative = puts richer = downside fear) and butterfly (BF25 = wing convexity), the
ATM term structure (contango vs backwardation), and an ASCII smile for the ~30d
expiry. Also fits a parametric skew shape that the condor backtest can reuse.

Run:  python3 -m basis.skew
"""

import argparse

from .core import fmt_vol, safe
from .core.assets import get_asset
from .core.sources import deribit_option_chain
from .core.surface import build_surface, fit_skew, skew_iv


def _smile_chart(rec, S, rows=9, cols=58):
    pts = sorted((o["strike"], o["iv"]) for o in rec["options"]
                 if 0.02 < abs(o["delta"]) < 0.98)
    if len(pts) < 3:
        return "  (insufficient strikes for a smile)"
    x_lo = min(S * 0.6, pts[0][0])
    x_hi = max(S * 1.6, pts[-1][0])
    ivs = [iv for _, iv in pts]
    y_lo, y_hi = min(ivs), max(ivs)
    rng = (y_hi - y_lo) or 1.0

    from .core.surface import _interp
    grid = [[" "] * cols for _ in range(rows)]
    for c in range(cols):
        k = x_lo + (x_hi - x_lo) * c / (cols - 1)
        iv = _interp(pts, k)
        r = int(round((y_hi - iv) / rng * (rows - 1)))
        grid[max(0, min(rows - 1, r))][c] = "█"
    out = []
    for r in range(rows):
        lab = fmt_vol(y_hi) if r == 0 else (fmt_vol(y_lo) if r == rows - 1 else " " * 5)
        out.append(f"  {lab:>5} │" + "".join(grid[r]))
    spot_c = max(0, min(cols - 1, int(round((S - x_lo) / (x_hi - x_lo) * (cols - 1)))))
    axis = ["─"] * cols
    axis[spot_c] = "▲"
    out.append("        └" + "".join(axis))
    out.append(f"        {'':<{spot_c}} ${S:,.0f}     [${x_lo:,.0f} … ${x_hi:,.0f}], IV vs strike")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Read the live implied-vol surface / skew")
    ap.add_argument("--asset", default="BTC", help="asset symbol (BTC, ETH, SOL, ...)")
    name = ap.parse_args().asset.upper()
    a = get_asset(name)

    chain = safe("Deribit chain", lambda: deribit_option_chain(a["deribit_ccy"], a["deribit_index"]))
    if not chain or not chain["options"]:
        print(f"No option chain for {name}.")
        return
    surf = build_surface(chain)
    S = surf["S"]
    bar = "=" * 74

    print(f"\n{bar}\n{name} IMPLIED-VOL SURFACE — Deribit   spot ${S:,.2f}\n{bar}")
    print(f"{'expiry':10} {'DTE':>4} {'ATM':>7} {'25dP':>7} {'25dC':>7} {'RR25':>8} {'BF25':>7}  skew")
    for e in surf["expiries"][:9]:
        if e["rr25"] is None:
            continue
        lean = "put-skew" if e["rr25"] < -0.005 else "call-skew" if e["rr25"] > 0.005 else "flat"
        print(f"{e['name']:10} {e['dte']:>4.0f} {fmt_vol(e['atm']):>7} {fmt_vol(e['put25']):>7} "
              f"{fmt_vol(e['call25']):>7} {e['rr25']*100:>+7.1f}% {e['bf25']*100:>+6.1f}%  {lean}")

    # term structure read
    es = [e for e in surf["expiries"] if e["atm"]]
    front, back = es[0], es[min(len(es) - 1, 5)]
    ts = "CONTANGO (back > front — calm)" if back["atm"] > front["atm"] else \
         "BACKWARDATION (front > back — stress/event premium up front)"
    ref = min(surf["expiries"], key=lambda e: abs(e["dte"] - 30))

    print(f"\nSMILE — {ref['name']} ({ref['dte']:.0f} DTE)")
    print(_smile_chart(ref, S))

    fit = fit_skew(surf)
    a0, a1, a2 = fit["coeffs"]
    # sample the fitted skew at +-1 sigma to express it in vol points
    atm, T = fit["ref_atm"], ref["T"]
    dn = skew_iv(fit["coeffs"], atm, T, S * 0.90, S)   # ~downside
    up = skew_iv(fit["coeffs"], atm, T, S * 1.10, S)   # ~upside

    print(f"\n{bar}\nREAD\n{bar}")
    print(f"• ATM term structure: {ts}  (front {fmt_vol(front['atm'])} -> "
          f"{back['dte']:.0f}d {fmt_vol(back['atm'])}).")
    if ref["rr25"] is not None:
        if ref["rr25"] < -0.005:
            print(f"• {ref['name']} is PUT-SKEWED (RR25 {ref['rr25']*100:+.1f}%): downside puts bid for "
                  f"protection. Selling put spreads collects that fear premium — but it's fear for a reason.")
        elif ref["rr25"] > 0.005:
            print(f"• {ref['name']} is CALL-SKEWED (RR25 {ref['rr25']*100:+.1f}%): upside calls bid "
                  f"(chase/squeeze). Call spreads collect more here.")
        else:
            print(f"• {ref['name']} smile is ~symmetric (RR25 {ref['rr25']*100:+.1f}%).")
    print(f"• Fitted skew shape (iv/atm = {a0:.3f} {a1:+.3f}·x {a2:+.3f}·x², x=ln(K/S)/(atm√T), "
          f"n={fit['n']}):")
    print(f"    -10% strike IV {fmt_vol(dn)}   ATM {fmt_vol(atm)}   +10% strike IV {fmt_vol(up)}  "
          f"-> {'put wing richer' if dn > up else 'call wing richer'}")
    print("• This shape feeds `basis.backtests.structures --skew` so synthetic condor credits")
    print("  reflect real put-richness instead of flat vol.")
    print("\n(Educational tooling, not investment advice.)")


if __name__ == "__main__":
    main()
