"""BTC-accrual backtest — which strategy grows the BTC stack the most?

The scorecard is BTC count (start 1.0 BTC), not USD. Compares, over the full DVOL/
price window, rolling 30d:
  - HODL            — hold 1 BTC (count stays 1; the benchmark)
  - COVERED CALL    — overwrite the stack with a 30d call at ~Δ; premium buys more BTC,
                      but price above the strike caps you (you end with fewer BTC)
  - DELTA-NEUTRAL CARRY — earn funding, but USD-flat = short BTC in the numeraire

Covered-call BTC compounding per roll, starting `b` BTC at S0, strike K, premium p (USD):
    b' = b · ( min(1, K/S_T) + p/S_T )
Carry (rebuy BTC at expiry): b' = b · S0·(1+funding)/S_T.

Caveat: call premiums are priced at ATM DVOL (flat) — real put-skew makes calls a bit
cheaper, so covered-call premiums here are slightly optimistic.

Run:  python3 -m btcvol.backtests.btc_accrual
"""

import calendar
import statistics
import time

from ..core import cc_vol, fmt_pct, sparkline, DAYS
from ..core.blackscholes import bs_price, strike_for_delta
from ..core.sources import deribit_dvol, deribit_chart, deribit_funding_history

HOLD = 30
T = HOLD / DAYS
DELTAS = [0.10, 0.20, 0.30]


def _date_ms(d):
    return calendar.timegm(time.strptime(d, "%Y-%m-%d")) * 1000


def _block_funding(funding, start_ms):
    end = start_ms + HOLD * 86400 * 1000
    return sum(f for ts, f in funding if start_ms <= ts < end)


def cc_factor(K, ST, premium_usd):
    """BTC multiplier for one covered-call roll: keep BTC up to the strike + premium."""
    return min(1.0, K / ST) + premium_usd / ST


def carry_factor(S0, ST, block_funding):
    """BTC multiplier for one delta-neutral carry roll (rebuy BTC at expiry)."""
    return S0 * (1 + block_funding) / ST


def run():
    dvol = deribit_dvol(days=1000, resolution="1D")
    chart = deribit_chart("BTC-PERPETUAL", days=1000, resolution="1D")
    iv_by = {time.strftime("%Y-%m-%d", time.gmtime(ts / 1000)): iv for ts, iv in dvol}
    px_by = {time.strftime("%Y-%m-%d", time.gmtime(t / 1000)): c
             for t, c in zip(chart["ticks"], chart["close"])}
    dates = sorted(set(iv_by) & set(px_by))
    S = [px_by[d] for d in dates]
    IV = [iv_by[d] for d in dates]
    funding = deribit_funding_history("BTC-PERPETUAL", days=1020)

    names = ["HODL"] + [f"CC{int(d*100)}Δ" for d in DELTAS] + ["CARRY"]
    btc = {n: 1.0 for n in names}
    curve = {n: [1.0] for n in names}
    wins = {n: 0 for n in names}          # rolls beating HODL
    n_rolls = 0
    bull_btc = {n: 1.0 for n in names}    # accrual only over up-rolls
    chop_btc = {n: 1.0 for n in names}

    i = 0
    while i + HOLD < len(S):
        S0, iv0, ST = S[i], IV[i], S[i + HOLD]
        up = ST > S0
        factors = {"HODL": 1.0}
        for d in DELTAS:
            K = strike_for_delta(S0, T, iv0, d, "C")
            factors[f"CC{int(d*100)}Δ"] = cc_factor(K, ST, bs_price(S0, K, T, iv0, "C"))
        factors["CARRY"] = carry_factor(S0, ST, _block_funding(funding, _date_ms(dates[i])))
        for n in names:
            btc[n] *= factors[n]
            curve[n].append(btc[n])
            (bull_btc if up else chop_btc)[n] *= factors[n]
            if factors[n] > factors["HODL"] + 1e-9:
                wins[n] += 1
        n_rolls += 1
        i += HOLD

    span_yrs = n_rolls * HOLD / DAYS
    bar = "=" * 74
    print(f"\n{bar}\nBTC-ACCRUAL BACKTEST — terminal BTC from 1.00 (start), scorecard = BTC count\n{bar}")
    print(f"window {dates[0]} -> {dates[-1]}   {n_rolls} rolls (~{span_yrs:.1f}y)   "
          f"BTC {S[0]:,.0f} -> {S[-1]:,.0f} ({fmt_pct(S[-1]/S[0]-1)})")
    print(f"\n  {'strategy':10} {'final BTC':>10} {'BTC CAGR':>10} {'vs HODL':>9} {'beat HODL':>10}  curve")
    for n in names:
        cagr = btc[n] ** (1 / span_yrs) - 1 if span_yrs else 0
        vshodl = btc[n] - btc["HODL"]
        wr = f"{wins[n]}/{n_rolls}" if n != "HODL" else "—"
        print(f"  {n:10} {btc[n]:>10.4f} {fmt_pct(cagr):>10} {vshodl:>+9.4f} {wr:>10}  {sparkline(curve[n])}")

    print(f"\n  regime split (BTC accrued vs HODL):")
    print(f"    {'strategy':10} {'UP rolls':>12} {'DOWN/flat rolls':>16}")
    for n in names:
        print(f"    {n:10} {bull_btc[n]-bull_btc['HODL']:>+12.4f} {chop_btc[n]-chop_btc['HODL']:>+16.4f}")

    best = max(names, key=lambda n: btc[n])
    print(f"\n{bar}\nREAD\n{bar}")
    print(f"• Best BTC accrual over this window: {best} ({btc[best]:.4f} BTC vs HODL 1.0000).")
    if best == "HODL":
        print("• HODL won — over a strongly BULL window, overwriting/carry capped or shorted the BTC upside.")
        print("  This matches the research: covered calls & USD-neutral carry LOSE BTC in a rally.")
    print("• The regime split is the key: these strategies accrue BTC in DOWN/flat rolls and give it")
    print("  back (or worse) in UP rolls. They're a bet that BTC is range-bound — not a free BTC machine.")
    print("• Implication: harvest premium/funding tactically when you're neutral/bearish; lean HODL when bullish.")


def main():
    run()


if __name__ == "__main__":
    main()
