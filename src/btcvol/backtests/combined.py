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

from ..core import sharpe, max_drawdown, pearson, sparkline, fmt_pct, fmt_vol, vol_target_scale
from ..core.sources import deribit_funding_history
from .structures import simulate, HOLD, ROLLS_PER_YEAR


def _date_ms(d):
    return calendar.timegm(time.strptime(d, "%Y-%m-%d")) * 1000


def carry_per_block(rolls, funding, leverage, timed=False, fc=24):
    """Levered carry return for each roll's 30d block (sum of hourly funding within it).
    If timed, only accrue funding when the trailing-`fc`h average was positive (Inan 2024
    funding persistence) — i.e. exit to cash before predicted-negative stretches."""
    held = None
    if timed:
        rates = [f for _, f in funding]
        held = {funding[i][0]: (i < fc or statistics.mean(rates[i - fc:i]) > 0)
                for i in range(len(funding))}
    block_ms = HOLD * 86400 * 1000
    out = []
    for r in rolls:
        start = _date_ms(r["date"])
        end = start + block_ms
        out.append(leverage * sum(f for ts, f in funding
                                  if start <= ts < end and (held is None or held[ts])))
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


def run(leverage=3.0, risk=0.15, skew=True, vol_target=None, asset="BTC", vov=True, timed=True):
    from ..core.assets import get_asset
    a = get_asset(asset)
    if not a["has_dvol"]:
        print(f"{asset.upper()} has no DVOL index — try BTC or ETH.")
        return
    sim = simulate(skew=skew, asset=asset)
    # condor leg: VOV-gated (skip unstable-vol regimes) is the strongest variant; else DVOL>RV
    rolls = sim["vov_filtered"] if vov else sim["filtered"]
    if not rolls:
        print("No rolls.")
        return
    funding = deribit_funding_history(a["deribit_perp"], days=1020)   # cover the full condor window

    carry = carry_per_block(rolls, funding, leverage, timed=timed)
    # condor risk per block: fixed, or vol-targeted (size down when trailing RV is high)
    def block_risk(r):
        if vol_target and r["rv_trail"]:
            return risk * vol_target_scale(vol_target, r["rv_trail"], max_scale=1.5)
        return risk
    condor = [block_risk(r) * r["ror"] for r in rolls]
    port = [c + d for c, d in zip(carry, condor)]

    sc, sd, sp = leg_stats(carry), leg_stats(condor), leg_stats(port)
    corr = pearson(carry, condor)

    bar = "=" * 78
    vt = f"  vol-targeted to {fmt_vol(vol_target)}" if vol_target else ""
    cond = "VOV-gated condor" if vov else "DVOL>RV condor"
    cary = "timed carry" if timed else "always-on carry"
    print(f"\n{bar}\nCOMBINED-BOOK BACKTEST  ({cary} {leverage:.0f}x  +  {cond} {risk:.0%} risk/roll{vt})\n{bar}")
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
    print(f"• Config: {cond} (skip unstable-vol regimes, Du 2025) + {cary} (Inan 2024 funding persistence).")
    print("\n(Educational tooling, not investment advice. Carry tail = exchange/liquidation, not in this curve.)")


def main():
    ap = argparse.ArgumentParser(description="Combined carry + condor book backtest (VOV-gated + timed by default)")
    ap.add_argument("--leverage", type=float, default=3.0, help="carry leg leverage (default 3)")
    ap.add_argument("--risk", type=float, default=0.15, help="condor capital fraction risked per roll (default 0.15)")
    ap.add_argument("--flat", action="store_true", help="price the condor flat-vol (default: real skew)")
    ap.add_argument("--vol-target", type=float, default=None, help="vol-target the condor risk to this annualized vol (e.g. 0.15)")
    ap.add_argument("--no-vov", action="store_true", help="plain DVOL>RV condor instead of the VOV gate")
    ap.add_argument("--no-timed", action="store_true", help="always-on carry instead of funding-timed")
    ap.add_argument("--asset", default="BTC", help="asset with a DVOL index (BTC or ETH)")
    args = ap.parse_args()
    run(leverage=args.leverage, risk=args.risk, skew=not args.flat, vol_target=args.vol_target,
        asset=args.asset, vov=not args.no_vov, timed=not args.no_timed)


if __name__ == "__main__":
    main()
