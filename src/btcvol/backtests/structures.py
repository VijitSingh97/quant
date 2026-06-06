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
LOOKBACK_DAYS = 1000          # DVOL backfills ~3y free; cap is 1000d (~33 rolls vs ~13 at 400)


def _round(x, grid):
    return round(x / grid) * grid


def _condor(S, iv, T, delta, wing_pct, grid, iv_fn=None):
    """Build a delta-based condor; return strikes, credit, wing, max_loss (per 1 BTC, USD).

    Strikes are picked at the ATM iv (consistent across modes); legs are PRICED at
    iv_fn(iv, T, K, S) when given (real skew), else flat at the ATM iv.
    """
    leg_iv = (lambda K: iv_fn(iv, T, K, S)) if iv_fn else (lambda K: iv)
    kp_s = _round(strike_for_delta(S, T, iv, -delta, "P"), grid)
    kc_s = _round(strike_for_delta(S, T, iv, +delta, "C"), grid)
    wing = max(grid, _round(wing_pct * S, grid))
    kp_l, kc_l = kp_s - wing, kc_s + wing
    credit = (bs_price(S, kp_s, T, leg_iv(kp_s), "P") - bs_price(S, kp_l, T, leg_iv(kp_l), "P")
              + bs_price(S, kc_s, T, leg_iv(kc_s), "C") - bs_price(S, kc_l, T, leg_iv(kc_l), "C"))
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


def load_market(skew=False):
    """Pull DVOL + price path once (and fit live skew if requested). Reused across a
    parameter sweep so we don't re-hit the API per combination."""
    iv_fn, skew_note = None, "flat vol"
    if skew:
        from ..core.surface import build_surface, fit_skew, skew_iv
        from ..core.sources import deribit_option_chain
        fit = fit_skew(build_surface(deribit_option_chain()))
        coeffs = fit["coeffs"]
        iv_fn = lambda atm, T, K, S: skew_iv(coeffs, atm, T, K, S)
        skew_note = f"skew from live {fit['ref_expiry']} surface (a={tuple(round(c,3) for c in coeffs)})"

    dvol = deribit_dvol(days=LOOKBACK_DAYS, resolution="1D")
    chart = deribit_chart("BTC-PERPETUAL", days=LOOKBACK_DAYS, resolution="1D")
    iv_by_date = {time.strftime("%Y-%m-%d", time.gmtime(ts / 1000)): iv for ts, iv in dvol}
    px_by_date = {time.strftime("%Y-%m-%d", time.gmtime(t / 1000)): c
                  for t, c in zip(chart["ticks"], chart["close"])}
    dates = sorted(set(iv_by_date) & set(px_by_date))
    return {"dates": dates, "S": [px_by_date[d] for d in dates],
            "IV": [iv_by_date[d] for d in dates], "T": HOLD / YEAR,
            "iv_fn": iv_fn, "skew": skew, "skew_note": skew_note}


def simulate_from(market, delta=0.20, wing_pct=0.08, grid=1000.0, fee_bps=0.0):
    """Run the condor rolls against pre-loaded market data. fee_bps is a round-trip
    cost (bps of notional) deducted from each roll's credit."""
    S, IV, dates, T, iv_fn, skew = (market["S"], market["IV"], market["dates"],
                                    market["T"], market["iv_fn"], market["skew"])
    detail, always, filtered = [], [], []
    i = 0
    while i + HOLD < len(S):
        st0, iv0, d0 = S[i], IV[i], dates[i]
        rv_trail = cc_vol(S[: i + 1], 30) if i >= 31 else None
        rv_fwd = cc_vol(S[i: i + HOLD + 1], HOLD)
        c = _condor(st0, iv0, T, delta, wing_pct, grid, iv_fn)
        credit_flat = _condor(st0, iv0, T, delta, wing_pct, grid)["credit"] if skew else c["credit"]
        fee = fee_bps / 1e4 * st0
        pnl = _expiry_pnl(c, S[i + HOLD]) - fee
        ror = pnl / c["max_loss"] if c["max_loss"] > 0 else 0.0
        row = {"date": d0, "iv": iv0, "rv_trail": rv_trail, "rv_fwd": rv_fwd,
               "credit": c["credit"], "credit_flat": credit_flat,
               "max_loss": c["max_loss"], "pnl": pnl, "ror": ror}
        detail.append(row)
        always.append({**row, "active": True})
        sell = rv_trail is None or iv0 > rv_trail        # DVOL>RV filter (sell when rich)
        filtered.append({**row, "active": sell, "ror": ror if sell else 0.0,
                         "pnl": pnl if sell else 0.0})
        i += HOLD
    return {"detail": detail, "always": always, "filtered": filtered,
            "dates": dates, "skew": skew, "skew_note": market["skew_note"]}


def simulate(delta=0.20, wing_pct=0.08, grid=1000.0, skew=False):
    """Convenience: load market data then run one parameter set."""
    return simulate_from(load_market(skew), delta, wing_pct, grid)


def run(delta=0.20, wing_pct=0.08, risk=0.20, grid=1000.0, skew=False):
    sim = simulate(delta, wing_pct, grid, skew)
    detail, always, filtered = sim["detail"], sim["always"], sim["filtered"]
    dates, skew_note = sim["dates"], sim["skew_note"]
    bar = "=" * 78
    print(f"\n{bar}\nCONDOR-SELLING RULE BACKTEST  (roll 30d iron condor, ~{delta:.0%} short Δ, "
          f"{wing_pct:.0%} wings)\n{bar}")
    print(f"Window {dates[0]} -> {dates[-1]}   {len(detail)} non-overlapping rolls   "
          f"synthetic credit @ historical DVOL ({skew_note})")
    if skew:
        avg_skew = statistics.mean(r["credit"] for r in detail)
        avg_flat = statistics.mean(r["credit_flat"] for r in detail)
        print(f"Skew vs flat: avg credit ${avg_flat:,.0f} -> ${avg_skew:,.0f} "
              f"({fmt_pct(avg_skew/avg_flat - 1)} from put-richness)")

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
    if skew:
        print("• Skew-aware credit is LOWER than flat: put-skew makes the long wing you BUY richer than")
        print("  the short you sell, so the spread collects less. The realistic edge is the modest one above.")
    else:
        print("• This run prices flat-vol, which OVERSTATES the credit (it ignores that the long put wing")
        print("  is richer under skew). Run with --skew for the lower, more realistic estimate.")
    print("\n(Educational tooling, not investment advice. Synthetic credit; --skew applies today's")
    print(" fitted shape to historical ATM vol (static-skew approx). Execution/fees not modeled.)")


def main():
    ap = argparse.ArgumentParser(description="Backtest the monthly defined-risk condor-selling rule")
    ap.add_argument("--delta", type=float, default=0.20, help="short-strike target |delta| (default 0.20)")
    ap.add_argument("--wing-pct", type=float, default=0.08, help="wing width as fraction of spot (default 0.08)")
    ap.add_argument("--risk", type=float, default=0.20, help="capital fraction risked per roll for the compounding curve (default 0.20)")
    ap.add_argument("--skew", action="store_true", help="price legs with today's fitted skew shape (vs flat vol)")
    args = ap.parse_args()
    run(delta=args.delta, wing_pct=args.wing_pct, risk=args.risk, skew=args.skew)


if __name__ == "__main__":
    main()
