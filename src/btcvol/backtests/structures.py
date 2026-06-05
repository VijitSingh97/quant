"""Backtest the defined-risk condor-selling RULE: does rolling it monthly compound?

Every 30 days, sell a delta-based iron condor and hold to expiry. Because the
structure is wing-capped, a vol-spike month loses its (bounded) max instead of the
open-ended loss a naked straddle takes — this backtest measures whether that cap
turns the volatility-risk-premium into something that actually compounds, and what
the tail looks like across the sample.

Each condor is reconstructed synthetically (no historical chain is public):
  - implied: real historical **DVOL** at the roll date prices every leg (flat vol,
    no skew — a disclosed simplification that slightly understates real credit)
  - realized: the real historical **price path** determines the expiry payoff
Two variants are compared: sell EVERY month, vs sell only when DVOL > trailing
realized vol (the "vol is rich" filter).

Data: Deribit DVOL (implied) + BTC-PERPETUAL daily closes (~400d, ~13 rolls).
Run:  python3 -m btcvol.backtests.structures [--delta 0.20] [--wing-pct 0.08] [--risk 0.20]
"""

import argparse
import statistics
import time

from ..core import (cc_vol, sharpe, max_drawdown, sparkline, fmt_pct, fmt_vol,
                    bs_price, strike_for_delta)
from ..core.sources import deribit_dvol, deribit_chart

HOLD = 30
YEAR = 365.0
ROLLS_PER_YEAR = YEAR / HOLD


def _round(x, grid):
    return round(x / grid) * grid


def _condor(S, iv, T, delta, wing_pct, grid):
    """Build a delta-based condor; return strikes, credit, wing, max_loss (per 1 BTC, USD)."""
    kp_s = _round(strike_for_delta(S, T, iv, -delta, "P"), grid)
    kc_s = _round(strike_for_delta(S, T, iv, +delta, "C"), grid)
    wing = max(grid, _round(wing_pct * S, grid))
    kp_l, kc_l = kp_s - wing, kc_s + wing
    credit = (bs_price(S, kp_s, T, iv, "P") - bs_price(S, kp_l, T, iv, "P")
              + bs_price(S, kc_s, T, iv, "C") - bs_price(S, kc_l, T, iv, "C"))
    return {"kp_s": kp_s, "kp_l": kp_l, "kc_s": kc_s, "kc_l": kc_l,
            "wing": wing, "credit": credit, "max_loss": wing - credit}


def _expiry_pnl(c, st):
    put_payoff = min(max(c["kp_s"] - st, 0.0), c["wing"])
    call_payoff = min(max(st - c["kc_s"], 0.0), c["wing"])
    return c["credit"] - (put_payoff + call_payoff)


def _summarize(name, rolls, risk):
    """rolls: list of dicts with 'ror' (return on risk) and 'active'. Cash months ror=0."""
    rors = [r["ror"] for r in rolls]
    active = [r for r in rolls if r["active"]]
    wins = sum(1 for r in active if r["pnl"] > 0)
    equity = [1.0]
    for r in rors:
        equity.append(equity[-1] * (1 + risk * r))
    cagr = equity[-1] ** (ROLLS_PER_YEAR / len(rors)) - 1 if rors else 0.0
    worst = min(active, key=lambda r: r["ror"]) if active else None
    return {
        "name": name, "n": len(rolls), "n_active": len(active),
        "win_rate": wins / len(active) * 100 if active else 0.0,
        "avg_ror": statistics.mean(rors) if rors else 0.0,
        "avg_ror_active": statistics.mean(r["ror"] for r in active) if active else 0.0,
        "sharpe": sharpe(rors, ROLLS_PER_YEAR),
        "total": equity[-1] - 1, "cagr": cagr,
        "mdd": max_drawdown(equity), "equity": equity, "worst": worst,
    }


def _print_summary(s, risk):
    print(f"\n{s['name']}")
    print(f"  rolls            {s['n_active']}/{s['n']} active "
          f"(skipped {s['n']-s['n_active']} cash months)")
    print(f"  win rate         {s['win_rate']:.0f}% of active rolls")
    print(f"  avg return/risk  {fmt_pct(s['avg_ror_active'])} active   ({fmt_pct(s['avg_ror'])} incl. cash)")
    print(f"  Sharpe           {s['sharpe']:.2f}" if s['sharpe'] else "  Sharpe           n/a")
    print(f"  compounded @ {int(risk*100)}% risk/roll:  total {fmt_pct(s['total'])}   "
          f"CAGR {fmt_pct(s['cagr'])}   maxDD {fmt_pct(s['mdd'])}")
    if s["worst"]:
        w = s["worst"]
        print(f"  worst roll       {fmt_pct(w['ror'])} on risk  ({w['date']}, "
              f"IV {fmt_vol(w['iv'])} vs realized {fmt_vol(w['rv_fwd'])})")
    print(f"  equity curve     {sparkline(s['equity'])}")


def run(delta=0.20, wing_pct=0.08, risk=0.20, grid=1000.0):
    dvol = deribit_dvol(days=400, resolution="1D")
    chart = deribit_chart("BTC-PERPETUAL", days=400, resolution="1D")
    ticks, closes = chart["ticks"], chart["close"]

    iv_by_date = {time.strftime("%Y-%m-%d", time.gmtime(ts / 1000)): iv for ts, iv in dvol}
    px_by_date = {time.strftime("%Y-%m-%d", time.gmtime(t / 1000)): c for t, c in zip(ticks, closes)}
    dates = sorted(set(iv_by_date) & set(px_by_date))
    S = [px_by_date[d] for d in dates]
    IV = [iv_by_date[d] for d in dates]
    T = HOLD / YEAR

    detail = []
    always, filtered = [], []
    i = 0
    while i + HOLD < len(S):
        st0, iv0, d0 = S[i], IV[i], dates[i]
        rv_trail = cc_vol(S[: i + 1], 30) if i >= 31 else None
        rv_fwd = cc_vol(S[i: i + HOLD + 1], HOLD)
        c = _condor(st0, iv0, T, delta, wing_pct, grid)
        pnl = _expiry_pnl(c, S[i + HOLD])
        ror = pnl / c["max_loss"] if c["max_loss"] > 0 else 0.0
        row = {"date": d0, "iv": iv0, "rv_trail": rv_trail, "rv_fwd": rv_fwd,
               "credit": c["credit"], "max_loss": c["max_loss"], "pnl": pnl, "ror": ror}
        detail.append(row)

        always.append({**row, "active": True})
        sell = rv_trail is None or iv0 > rv_trail        # DVOL>RV filter (sell when rich)
        filtered.append({**row, "active": sell, "ror": ror if sell else 0.0,
                         "pnl": pnl if sell else 0.0})
        i += HOLD

    bar = "=" * 78
    print(f"\n{bar}\nCONDOR-SELLING RULE BACKTEST  (roll 30d iron condor, ~{delta:.0%} short Δ, "
          f"{wing_pct:.0%} wings)\n{bar}")
    print(f"Window {dates[0]} -> {dates[-1]}   {len(detail)} non-overlapping rolls   "
          f"synthetic credit @ historical DVOL (flat vol)")

    # per-roll table (small N -> show them all)
    print(f"\n{'roll date':11} {'IV':>6} {'RV_fwd':>7} {'credit$':>8} {'maxloss$':>9} "
          f"{'P&L$':>8} {'on risk':>8}  result")
    for r in detail:
        flag = "WIN " if r["pnl"] > 0 else "LOSS"
        cap = "  <- capped max loss" if r["ror"] < -0.95 else ""
        print(f"{r['date']:11} {fmt_vol(r['iv']):>6} {fmt_vol(r['rv_fwd']):>7} "
              f"{r['credit']:>8,.0f} {r['max_loss']:>9,.0f} {r['pnl']:>+8,.0f} "
              f"{fmt_pct(r['ror']):>8}  {flag}{cap}")

    s_always = _summarize("SELL EVERY MONTH (unconditional)", always, risk)
    s_filt = _summarize("SELL ONLY WHEN DVOL > TRAILING RV (filtered)", filtered, risk)
    _print_summary(s_always, risk)
    _print_summary(s_filt, risk)

    print(f"\n{bar}\nREAD\n{bar}")
    print(f"• Defined-risk caps the disaster: losing months lose a BOUNDED {fmt_pct(s_always['worst']['ror'])} of a")
    print(f"  small risk budget. In Jan-2026 realized hit ~68% vs ~39% implied — the naked-vol backtest")
    print(f"  (btcvol.backtests.vrp) took -28.8 vol pts that month; here it's a capped wing loss. The point.")
    better = "filter HELPS" if s_filt["mdd"] > s_always["mdd"] else "filter doesn't help here"
    print(f"• DVOL>RV filter: {better} (maxDD {fmt_pct(s_filt['mdd'])} vs {fmt_pct(s_always['mdd'])}; "
          f"CAGR {fmt_pct(s_filt['cagr'])} vs {fmt_pct(s_always['cagr'])}).")
    print(f"• Sample is ~{len(detail)} rolls (one year of DVOL) — directional, not conclusive. The shape")
    print(f"  (many small wins, rare capped losses) is the structural signature of selling vol with wings.")
    print(f"• Compounding shown at {int(risk*100)}% of capital risked per roll; scale that lever to taste,")
    print(f"  but one capped max-loss should stay a small, survivable fraction of the account.")
    print("\n(Educational tooling, not investment advice. Flat-vol synthetic credit ignores skew;")
    print(" real condors collect a bit more on the put wing. Execution/fees not modeled.)")


def main():
    ap = argparse.ArgumentParser(description="Backtest the monthly defined-risk condor-selling rule")
    ap.add_argument("--delta", type=float, default=0.20, help="short-strike target |delta| (default 0.20)")
    ap.add_argument("--wing-pct", type=float, default=0.08, help="wing width as fraction of spot (default 0.08)")
    ap.add_argument("--risk", type=float, default=0.20, help="capital fraction risked per roll for the compounding curve (default 0.20)")
    args = ap.parse_args()
    run(delta=args.delta, wing_pct=args.wing_pct, risk=args.risk)


if __name__ == "__main__":
    main()
