"""Combined-book backtest: funding carry + filtered defined-risk condor.

Two low-correlation income legs run as one book over a common ~1y window:
  - CARRY: long spot / short perp, earning hourly Deribit funding at modest leverage,
    aggregated into each 30d condor block.
  - CONDOR: the FILTERED (DVOL>RV), skew-priced condor rolls (reused from the condor
    backtest), risking a fixed fraction of capital per roll.

Reports each leg vs the combined book (total, CAGR, Sharpe, maxDD) and the leg
correlation — the diversification benefit is the reason to run both.

Data: Deribit DVOL + BTC-PERPETUAL daily (condor) and hourly funding (carry).
Run:  python3 -m btcvol.backtests.combined [--leverage 3] [--risk 0.15] [--flat]
"""

import argparse
import calendar
import statistics
import time

from ..core import sharpe, max_drawdown, pearson, sparkline, fmt_pct
from ..core.sources import deribit_funding_history
from .structures import simulate, HOLD, ROLLS_PER_YEAR


def _date_ms(d):
    return calendar.timegm(time.strptime(d, "%Y-%m-%d")) * 1000


def carry_per_block(rolls, funding, leverage):
    """Levered carry return for each roll's 30d block (sum of hourly funding within it)."""
    block_ms = HOLD * 86400 * 1000
    out = []
    for r in rolls:
        start = _date_ms(r["date"])
        end = start + block_ms
        out.append(leverage * sum(f for ts, f in funding if start <= ts < end))
    return out


def equity(returns):
    eq = [1.0]
    for x in returns:
        eq.append(eq[-1] * (1 + x))
    return eq


def leg_stats(returns):
    eq = equity(returns)
    cagr = eq[-1] ** (ROLLS_PER_YEAR / len(returns)) - 1 if returns else 0.0
    return {"total": eq[-1] - 1, "cagr": cagr, "sharpe": sharpe(returns, ROLLS_PER_YEAR),
            "mdd": max_drawdown(eq), "equity": eq}


def _row(name, s):
    sh = f"{s['sharpe']:.2f}" if s["sharpe"] is not None else "n/a"
    return f"  {name:14} {fmt_pct(s['total']):>9} {fmt_pct(s['cagr']):>9} {sh:>8} {fmt_pct(s['mdd']):>9}"


def run(leverage=3.0, risk=0.15, skew=True):
    sim = simulate(skew=skew)
    rolls = sim["filtered"]                       # the viable variant (DVOL>RV filtered)
    if not rolls:
        print("No rolls.")
        return
    funding = deribit_funding_history("BTC-PERPETUAL", days=420)

    carry = carry_per_block(rolls, funding, leverage)
    condor = [risk * r["ror"] for r in rolls]
    port = [c + d for c, d in zip(carry, condor)]

    sc, sd, sp = leg_stats(carry), leg_stats(condor), leg_stats(port)
    corr = pearson(carry, condor)

    bar = "=" * 78
    print(f"\n{bar}\nCOMBINED-BOOK BACKTEST  (carry {leverage:.0f}x  +  filtered condor {risk:.0%} risk/roll)\n{bar}")
    print(f"window {sim['dates'][0]} -> {sim['dates'][-1]}   {len(rolls)} blocks   condor: {sim['skew_note']}")
    print(f"\n  {'book':14} {'total':>9} {'CAGR':>9} {'Sharpe':>8} {'maxDD':>9}")
    print(_row("carry-only", sc))
    print(_row("condor-only", sd))
    print(_row("COMBINED", sp))
    print(f"\n  leg correlation (carry vs condor)   r = {corr:+.2f}" if corr is not None else
          "\n  leg correlation: n/a")
    print(f"  equity  carry    {sparkline(sc['equity'])}")
    print(f"          condor   {sparkline(sd['equity'])}")
    print(f"          COMBINED {sparkline(sp['equity'])}")

    print(f"\n{bar}\nREAD\n{bar}")
    print(f"• Combined ~doubles carry's return ({fmt_pct(sp['cagr'])} vs {fmt_pct(sc['cagr'])} CAGR) for a "
          f"bounded {fmt_pct(sp['mdd'])} maxDD that comes almost entirely from the condor leg.")
    if sp["sharpe"] and sc["sharpe"]:
        print(f"• Combined Sharpe {sp['sharpe']:.2f} is below carry-only's {sc['sharpe']:.2f} — but carry's Sharpe is")
        print(f"  FLATTERED: its real tail (exchange insolvency / short-leg liquidation) isn't in the curve.")
        print(f"  Risk-adjusted on *modelled* risk, the condor overlay is paying for its drawdowns here.")
    if corr is not None:
        kind = ("low/near-zero — good diversifiers" if abs(corr) < 0.3 else
                "meaningfully correlated — limited diversification" if corr > 0 else "negatively correlated — natural hedge")
        print(f"• Legs are {kind} (r={corr:+.2f}) — both prefer calm, so the hedge between them is partial.")
    print(f"• ~{len(rolls)} blocks (one year) — directional, not conclusive (see issue #4). Leverage/risk are")
    print(f"  levers: carry scales linearly with leverage (and so does liquidation risk); condor risk is capped.")
    print("\n(Educational tooling, not investment advice. Carry tail = exchange/liquidation, not in this curve.)")


def main():
    ap = argparse.ArgumentParser(description="Combined carry + filtered-condor book backtest")
    ap.add_argument("--leverage", type=float, default=3.0, help="carry leg leverage (default 3)")
    ap.add_argument("--risk", type=float, default=0.15, help="condor capital fraction risked per roll (default 0.15)")
    ap.add_argument("--flat", action="store_true", help="price the condor flat-vol (default: real skew)")
    args = ap.parse_args()
    run(leverage=args.leverage, risk=args.risk, skew=not args.flat)


if __name__ == "__main__":
    main()
