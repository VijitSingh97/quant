"""One-shot BTC market snapshot + interpreted "suggested direction".

Pulls spot/realized-vol (Coinbase), implied vol + futures basis (Deribit), and
perp funding/OI (OKX, Hyperliquid), prints a dashboard, and saves a JSON
snapshot to data/. Run:  python3 -m basis.dashboard
"""

import argparse
import json
import statistics
import time

from .core import fmt_pct, fmt_vol, safe, DATA_DIR
from .core.assets import get_asset
from .core.sources import (coinbase_spot_and_candles, okx_perp,
                           hyperliquid_perp, deribit_vol_and_basis)


def interpret(cb, okx, hl, der):
    lines = []

    # --- carry signal ---
    fundings = []
    if okx:
        fundings.append(("OKX", okx["funding_apr"]))
    if hl:
        fundings.append(("Hyperliquid", hl["funding_apr"]))
    if fundings:
        best = max(fundings, key=lambda x: x[1])
        avg = statistics.mean(f for _, f in fundings)
        if avg > 0.03:
            lines.append(f"CARRY: funding POSITIVE (~{fmt_pct(avg)} APR avg). Shorts get paid -> "
                         f"long spot / short perp (delta-neutral) earns this. Best venue: {best[0]} ({fmt_pct(best[1])}).")
        elif avg < -0.03:
            lines.append(f"CARRY: funding NEGATIVE (~{fmt_pct(avg)} APR avg). Longs get paid -> "
                         f"reverse carry (short spot / long perp) pays, OR just hold the long-perp side.")
        else:
            lines.append(f"CARRY: funding ~flat ({fmt_pct(avg)} APR). Thin carry; basis trade marginal right now.")

    if der and der.get("dated_basis"):
        b = der["dated_basis"]
        lines.append(f"BASIS: {b['instrument']} dated future = {b['annualized_basis_pct']:+.1f}% annualized "
                     f"cash-and-carry ({b['days_to_expiry']:.0f}d). "
                     f"{'Contango — sell future / buy spot.' if b['annualized_basis_pct']>0 else 'Backwardation — unusual, spot premium.'}")

    # --- vol premium signal ---
    if der and der.get("dvol") and cb and cb.get("rv_30d"):
        iv, rv = der["dvol"], cb["rv_30d"]
        vrp = iv - rv
        if vrp > 0.03:
            lines.append(f"VOL: implied (DVOL {fmt_vol(iv)}) > realized 30d ({fmt_vol(rv)}), VRP {fmt_vol(vrp)}. "
                         f"Options RICH -> favor SELLING vol (defined-risk: spreads/iron condor, covered calls).")
        elif vrp < -0.03:
            lines.append(f"VOL: implied (DVOL {fmt_vol(iv)}) < realized 30d ({fmt_vol(rv)}), VRP {fmt_vol(vrp)}. "
                         f"Options CHEAP -> favor BUYING vol (straddle / long gamma) if you expect moves to continue.")
        else:
            lines.append(f"VOL: implied ~ realized (DVOL {fmt_vol(iv)} vs RV {fmt_vol(rv)}). "
                         f"No strong vol edge; lean on carry instead.")

    # --- regime / correction depth ---
    if cb:
        below_ma = cb["spot"] < cb["ma_30d"]
        drawdown = cb["spot"] / cb["high_30d"] - 1
        trend = "DOWNTREND" if cb["spot"] < cb["ma_7d"] < cb["ma_30d"] else \
                "UPTREND" if cb["spot"] > cb["ma_7d"] > cb["ma_30d"] else "CHOP / no clear trend"
        vol_state = "HIGH" if (cb["rv_30d"] or 0) > 0.6 else "LOW" if (cb["rv_30d"] or 0) < 0.35 else "MODERATE"
        lines.append(f"REGIME: {trend}. Spot {'below' if below_ma else 'above'} 30d MA, "
                     f"{drawdown*100:.1f}% off 30d high, 30d return {fmt_pct(cb['ret_30d'])}. "
                     f"Realized-vol regime: {vol_state} ({fmt_vol(cb['rv_30d'])}).")
        lines.append("SIZING: vol-target — at {} RV, scale positions to a fixed $-risk; halve size if RV doubles."
                     .format(fmt_vol(cb['rv_30d'])))

    return lines


def _strip(cb):
    """Drop the bulky raw candle arrays from the saved snapshot."""
    if not cb:
        return cb
    return {k: v for k, v in cb.items() if k not in ("closes", "highs", "lows")}


def main():
    ap = argparse.ArgumentParser(description="One-shot BTC/ETH/... market snapshot")
    ap.add_argument("--asset", default="BTC", help="asset symbol (BTC, ETH, SOL, ...)")
    name = ap.parse_args().asset.upper()
    a = get_asset(name)

    print(f"Pulling {name} market snapshot ...\n")
    cb = safe("Coinbase", lambda: coinbase_spot_and_candles(a["coinbase"])) if a["coinbase"] else None
    okx = safe("OKX", lambda: okx_perp(a["okx"])) if a["okx"] else None
    hl = safe("Hyperliquid", lambda: hyperliquid_perp(a["hl"])) if a["hl"] else None
    der = safe("Deribit", lambda: deribit_vol_and_basis(a["deribit_ccy"], a["deribit_index"]))

    ts = int(time.time())
    bar = "=" * 70

    print(f"\n{bar}\n{name} VOLATILITY / CARRY DASHBOARD   {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n{bar}")

    if cb:
        print(f"\nSPOT (Coinbase)            ${cb['spot']:,.2f}")
        print(f"  7d / 30d return          {fmt_pct(cb['ret_7d'])}  /  {fmt_pct(cb['ret_30d'])}")
        print(f"  vs MA7 / MA30            ${cb['ma_7d']:,.0f}  /  ${cb['ma_30d']:,.0f}")
        print("\nREALIZED VOL (annualized)")
        print(f"  7d  / 14d / 30d (C2C)    {fmt_vol(cb['rv_7d'])} / {fmt_vol(cb['rv_14d'])} / {fmt_vol(cb['rv_30d'])}")
        print(f"  30d Parkinson (hi-lo)    {fmt_vol(cb['rv_parkinson_30d'])}")
        print(f"  last-24h intraday        {fmt_vol(cb['rv_24h_intraday'])}")

    if der:
        print("\nIMPLIED VOL & BASIS (Deribit)")
        print(f"  DVOL (30d implied)       {fmt_vol(der['dvol'])}")
        for b in der.get("term_structure", []):
            print(f"  {b['instrument']:18}     {b['annualized_basis_pct']:+5.1f}% ann. basis "
                  f"({b['raw_basis_pct']:+.2f}% over {b['days_to_expiry']:.0f}d)")

    print("\nPERP FUNDING / OPEN INTEREST")
    if okx:
        print(f"  OKX  funding (8h)        {okx['funding_rate_8h']*100:+.4f}%  -> {fmt_pct(okx['funding_apr'])} APR")
        print(f"       30d avg funding     {fmt_pct(okx['avg_funding_apr_30d'])} APR   premium {okx['perp_premium_bps']:+.1f}bps")
        if okx.get("open_interest_usd"):
            print(f"       open interest       ${okx['open_interest_usd']/1e9:,.2f}B")
    if hl:
        print(f"  HL   funding (1h)        {hl['funding_rate_1h']*100:+.4f}%  -> {fmt_pct(hl['funding_apr'])} APR")
        print(f"       open interest       ${hl['open_interest_usd']/1e9:,.2f}B   premium {hl['perp_premium_bps']:+.1f}bps")

    print(f"\n{bar}\nREAD & SUGGESTED DIRECTION\n{bar}")
    for ln in interpret(cb, okx, hl, der):
        print("• " + ln)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    snap = {"ts": ts, "asset": name, "coinbase": _strip(cb), "okx": okx, "hyperliquid": hl, "deribit": der}
    path = DATA_DIR / f"snapshot_{name}_{ts}.json"
    with open(path, "w") as f:
        json.dump(snap, f, indent=2, default=str)
    print(f"\nSnapshot saved -> {path}")
    print("\n(Educational tooling, not investment advice. Crypto leverage can liquidate you fast.)")


if __name__ == "__main__":
    main()
