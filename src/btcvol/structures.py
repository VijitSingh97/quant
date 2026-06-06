"""Defined-risk short-vol structures against Deribit's live BTC option chain.

Turns the volatility-risk-premium edge (implied > realized) into concrete,
capped-loss trades — iron condor, put credit spread, call credit spread. Legs are
priced off the live chain with conservative fills (sell at bid, buy wings at ask).
For each structure it reports max profit/loss, breakevens, probability of profit
(Black-Scholes under *implied* vol), and expected value under *realized* vol — the
direct test of whether the premium is rich enough to be +EV.

P&L is shown per 1 contract (1 BTC) in USD-equivalent at expiry. (Deribit options
settle in BTC, so realized BTC P&L varies slightly with the settlement price.)

Run:  python3 -m btcvol.structures [--dte 21] [--delta 0.20] [--wing 5000]
"""

import argparse

from .core import (fmt_pct, fmt_vol, cc_vol, safe,
                   bs_delta, prob_between, expected_payoff)
from .core.assets import get_asset
from .core.blackscholes import prob_st_below
from .core.sources import deribit_option_chain, deribit_chart

YEAR = 365.0


# --------------------------------------------------------------------------- #
# Selection & pricing primitives
# --------------------------------------------------------------------------- #
def _pick_expiry(opts, dte_target=None, dte_min=14):
    by_exp = {}
    for o in opts:
        by_exp.setdefault(o["expiry_ms"], o["dte"])
    items = sorted(by_exp.items(), key=lambda kv: kv[1])
    if dte_target is not None:
        return min(items, key=lambda kv: abs(kv[1] - dte_target))[0]
    eligible = [kv for kv in items if kv[1] >= dte_min]
    return (eligible[0] if eligible else items[0])[0]


def _nearest_delta(legs, target_abs, S, T):
    return min(legs, key=lambda o: abs(abs(bs_delta(S, o["strike"], T, o["iv"], o["type"])) - target_abs))


def _price_usd(o, side, index):
    """USD premium for a leg. Conservative: sell -> bid, buy -> ask; fallback mark."""
    btc = (o["bid_btc"] if side == "sell" else o["ask_btc"]) or o["mark_btc"] or 0.0
    return btc * index


def _intrinsic(K, kind, st):
    return max(0.0, st - K) if kind == "C" else max(0.0, K - st)


# --------------------------------------------------------------------------- #
# Structure analysis (legs = list of (option, 'sell'|'buy'))
# --------------------------------------------------------------------------- #
def analyze(name, legs, S, T, index, sigma_rv):
    credit = sum((1 if side == "sell" else -1) * _price_usd(o, side, index) for o, side in legs)

    def pnl(st):
        v = credit
        for o, side in legs:
            sign = 1 if side == "buy" else -1
            v += sign * _intrinsic(o["strike"], o["type"], st)
        return v

    # critical points (kinks at strikes) -> exact piecewise-linear evaluation
    strikes = sorted({o["strike"] for o, _ in legs})
    xs = [1.0] + strikes + [S * 5]
    vals = [pnl(x) for x in xs]
    max_profit = max(vals)
    max_loss = -min(vals)

    # breakevens: zero crossings of the piecewise-linear curve
    bes = []
    for i in range(1, len(xs)):
        a, b, fa, fb = xs[i - 1], xs[i], vals[i - 1], vals[i]
        if (fa <= 0 <= fb or fb <= 0 <= fa) and fa != fb:
            bes.append(a + (b - a) * (-fa) / (fb - fa))
    bes = sorted(set(round(x, 2) for x in bes))

    # probability of profit under IV (avg of the short legs' IV, skew-aware)
    short_ivs = [o["iv"] for o, side in legs if side == "sell"]
    sigma_iv = sum(short_ivs) / len(short_ivs)
    if len(bes) == 2:
        pop = prob_between(S, bes[0], bes[1], T, sigma_iv)
    elif len(bes) == 1:
        be = bes[0]
        pop = (1 - prob_st_below(S, be, T, sigma_iv)) if pnl(be * 1.001) > 0 else prob_st_below(S, be, T, sigma_iv)
    else:
        pop = None

    ev = expected_payoff(pnl, S, T, sigma_rv)        # EV under realized vol
    return {
        "name": name, "legs": legs, "credit": credit,
        "max_profit": max_profit, "max_loss": max_loss,
        "breakevens": bes, "pop": pop, "sigma_iv": sigma_iv,
        "ev": ev, "ror": credit / max_loss if max_loss > 0 else None,
        "ev_on_risk": ev / max_loss if max_loss > 0 else None,
        "pnl": pnl,
    }


# --------------------------------------------------------------------------- #
# ASCII payoff chart
# --------------------------------------------------------------------------- #
def ascii_payoff(res, S, rows=9, cols=56):
    strikes = [o["strike"] for o, _ in res["legs"]]
    x_lo = min(min(strikes), S) * 0.97
    x_hi = max(max(strikes), S) * 1.03
    pts = [res["pnl"](x_lo + (x_hi - x_lo) * c / (cols - 1)) for c in range(cols)]
    y_hi = max(res["max_profit"], 0.0)
    y_lo = min(-res["max_loss"], 0.0)
    rng = (y_hi - y_lo) or 1.0
    zero_row = int(round((y_hi - 0) / rng * (rows - 1)))

    grid = [[" "] * cols for _ in range(rows)]
    for c in range(cols):
        r = int(round((y_hi - pts[c]) / rng * (rows - 1)))
        r = max(0, min(rows - 1, r))
        grid[r][c] = "█"
    out = []
    for r in range(rows):
        axis = "┤" if r == zero_row else "│"
        label = f"{y_hi:+7.0f}" if r == 0 else (f"{y_lo:+7.0f}" if r == rows - 1 else (" " * 7))
        row = "".join(grid[r])
        if r == zero_row:
            row = "".join(ch if ch != " " else "·" for ch in row)
        out.append(f"  {label} {axis}{row}")
    # x-axis with spot marker
    spot_c = int(round((S - x_lo) / (x_hi - x_lo) * (cols - 1)))
    spot_c = max(0, min(cols - 1, spot_c))
    axis_line = ["─"] * cols
    axis_line[spot_c] = "▲"
    out.append("          └" + "".join(axis_line))
    out.append(f"          {'':<{spot_c}} ${S:,.0f} (spot)   [{x_lo:,.0f} … {x_hi:,.0f}]")
    return "\n".join(out)


def _legdesc(legs):
    return "  ".join(f"{side.upper()} {o['type']}{int(o['strike'])}" for o, side in legs)


def print_structure(res, S):
    print(f"\n{'-'*70}\n{res['name']}\n{'-'*70}")
    print(f"  legs           {_legdesc(res['legs'])}")
    print(f"  net credit     ${res['credit']:,.0f}   max profit ${res['max_profit']:,.0f}   max loss ${res['max_loss']:,.0f}")
    be = " / ".join(f"${b:,.0f}" for b in res["breakevens"]) or "n/a"
    print(f"  breakevens     {be}")
    print(f"  return on risk {fmt_pct(res['ror']) if res['ror'] is not None else 'n/a':>8}"
          f"   POP {fmt_pct(res['pop']) if res['pop'] is not None else 'n/a'} (under IV {fmt_vol(res['sigma_iv'])})")
    tag = "+EV" if res["ev"] > 0 else "-EV"
    print(f"  EV @ realized  ${res['ev']:+,.0f}  ({tag}, {fmt_pct(res['ev_on_risk'])} of max risk)")
    print(ascii_payoff(res, S))


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def run(short_delta=0.20, wing=5000.0, dte_target=None, asset="BTC"):
    a = get_asset(asset)
    chain = safe("Deribit chain", lambda: deribit_option_chain(a["deribit_ccy"], a["deribit_index"]))
    if not chain or not chain["options"]:
        print(f"No option chain for {asset}.")
        return
    S = chain["index"]
    opts = chain["options"]
    if wing is None:
        wing = 0.08 * S                  # scale the wing to the asset's price level

    # realized 30d vol (Deribit perp daily) for the EV measure
    perp = a["deribit_perp"] or "BTC-PERPETUAL"
    chart = safe("Deribit chart", lambda: deribit_chart(perp, days=60, resolution="1D"))
    rv = cc_vol(chart["close"], 30) if chart else None
    sigma_rv = rv or 0.5

    exp = _pick_expiry(opts, dte_target=dte_target)
    legs_at = [o for o in opts if o["expiry_ms"] == exp]
    dte = legs_at[0]["dte"]
    T = dte / YEAR
    calls = sorted((o for o in legs_at if o["type"] == "C"), key=lambda o: o["strike"])
    puts = sorted((o for o in legs_at if o["type"] == "P"), key=lambda o: o["strike"])
    if not calls or not puts:
        print("Chosen expiry lacks both calls and puts.")
        return

    short_call = _nearest_delta(calls, short_delta, S, T)
    short_put = _nearest_delta(puts, short_delta, S, T)
    long_call = min((c for c in calls if c["strike"] > short_call["strike"]),
                    key=lambda c: abs(c["strike"] - (short_call["strike"] + wing)), default=calls[-1])
    long_put = min((p for p in puts if p["strike"] < short_put["strike"]),
                   key=lambda p: abs(p["strike"] - (short_put["strike"] - wing)), default=puts[0])

    exp_name = legs_at[0]["instrument"].split("-")[1]
    avg_short_iv = (short_call["iv"] + short_put["iv"]) / 2
    bar = "=" * 70
    print(f"\n{bar}\nDEFINED-RISK SHORT-VOL STRUCTURES — Deribit {asset.upper()} options\n{bar}")
    print(f"Spot ${S:,.2f}   expiry {exp_name} ({dte:.0f} DTE)   short |Δ|≈{short_delta:.2f}   wings ${wing:,.0f}")
    print(f"Short-strike IV {fmt_vol(avg_short_iv)}  vs  realized-30d {fmt_vol(rv)}  "
          f"->  VRP {fmt_vol(avg_short_iv - (rv or 0))}  "
          f"({'rich — selling favored' if avg_short_iv > (rv or 0) else 'cheap — selling NOT favored'})")

    structures = [
        analyze("IRON CONDOR (neutral)",
                [(short_put, "sell"), (long_put, "buy"), (short_call, "sell"), (long_call, "buy")],
                S, T, S, sigma_rv),
        analyze("PUT CREDIT SPREAD (bullish/neutral)",
                [(short_put, "sell"), (long_put, "buy")], S, T, S, sigma_rv),
        analyze("CALL CREDIT SPREAD (bearish/neutral)",
                [(short_call, "sell"), (long_call, "buy")], S, T, S, sigma_rv),
    ]
    for res in structures:
        print_structure(res, S)

    # recommendation
    best = max(structures, key=lambda r: (r["ev_on_risk"] or -9))
    print(f"\n{bar}\nREAD\n{bar}")
    if avg_short_iv <= (rv or 0):
        print("• Implied <= realized at these strikes — the premium is NOT rich. Skip selling vol; wait or buy it.")
    else:
        print(f"• Premium is rich (IV {fmt_vol(avg_short_iv)} > RV {fmt_vol(rv)}). All three are defined-risk:")
        print(f"  max loss is capped at the wing width minus credit — no naked tail.")
        print(f"• Highest EV-on-risk: {best['name']} ({fmt_pct(best['ev_on_risk'])} of max risk, "
              f"POP {fmt_pct(best['pop'])}).")
        print("• In a downtrend the CALL credit spread also has directional tailwind; the CONDOR is the")
        print("  purest VRP harvest (neutral). Size so one max-loss is a small fraction of capital.")
    print("\n(Educational tooling, not investment advice. Illustrative fills; real P&L depends on")
    print(" execution, skew, early assignment-free European settlement, and surviving the tail.)")


def main():
    ap = argparse.ArgumentParser(description="Defined-risk short-vol structures on Deribit options")
    ap.add_argument("--asset", default="BTC", help="asset symbol (BTC, ETH, SOL, ...)")
    ap.add_argument("--dte", type=float, default=None, help="target days-to-expiry (default: nearest >= 14)")
    ap.add_argument("--delta", type=float, default=0.20, help="short-strike target |delta| (default 0.20)")
    ap.add_argument("--wing", type=float, default=None, help="wing width in USD (default: ~8%% of spot)")
    args = ap.parse_args()
    run(short_delta=args.delta, wing=args.wing, dte_target=args.dte, asset=args.asset)


if __name__ == "__main__":
    main()
