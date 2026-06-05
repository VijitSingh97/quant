"""Live BTC perp funding across venues + the cross-venue spread.

Two uses:
  1. Carry: place the short-perp leg on whichever venue pays the most.
  2. Arb: when one venue pays longs and another pays shorts, go long the
     paying-long venue and short the paying-short venue -> delta-neutral, both legs paid.

Run:  python3 -m btcvol.monitor
"""

import time

from .core import (http_get, http_post, safe, DAYS, fmt_pct,
                   OKX_FUNDINGS_PER_DAY, HL_FUNDINGS_PER_DAY, DERIBIT_FUNDINGS_PER_DAY)


def _okx():
    inst = "BTC-USDT-SWAP"
    d = http_get(f"https://www.okx.com/api/v5/public/funding-rate?instId={inst}")["data"][0]
    rate = float(d["fundingRate"])
    return {"venue": "OKX", "interval": "8h", "rate": rate,
            "apr": rate * OKX_FUNDINGS_PER_DAY * DAYS,
            "next_apr": float(d.get("nextFundingRate") or "nan") * OKX_FUNDINGS_PER_DAY * DAYS}


def _hyperliquid():
    meta, ctxs = http_post("https://api.hyperliquid.xyz/info", {"type": "metaAndAssetCtxs"})
    i = next(k for k, a in enumerate(meta["universe"]) if a["name"] == "BTC")
    rate = float(ctxs[i]["funding"])
    return {"venue": "Hyperliquid", "interval": "1h", "rate": rate,
            "apr": rate * HL_FUNDINGS_PER_DAY * DAYS, "next_apr": None}


def _deribit():
    tk = http_get("https://www.deribit.com/api/v2/public/ticker?instrument_name=BTC-PERPETUAL")["result"]
    rate = float(tk.get("funding_8h") or 0.0)
    return {"venue": "Deribit", "interval": "8h", "rate": rate,
            "apr": rate * DERIBIT_FUNDINGS_PER_DAY * DAYS, "next_apr": None}


def _kraken():
    data = http_get("https://futures.kraken.com/derivatives/api/v3/tickers")["tickers"]
    t = next(x for x in data if x.get("symbol", "").lower() == "pf_xbtusd")
    # Kraken funding is hourly and quoted ABSOLUTE (quote ccy/contract); normalize by price.
    px = float(t.get("indexPrice") or t.get("markPrice"))
    rel = float(t["relativeFundingRate"]) if t.get("relativeFundingRate") is not None \
        else float(t["fundingRate"]) / px
    nxt = (float(t["fundingRatePrediction"]) / px) if t.get("fundingRatePrediction") is not None else None
    return {"venue": "Kraken", "interval": "1h", "rate": rel,
            "apr": rel * 24 * DAYS, "next_apr": nxt * 24 * DAYS if nxt is not None else None}


def main():
    rows = [r for r in (safe("OKX", _okx), safe("Hyperliquid", _hyperliquid),
                        safe("Deribit", _deribit), safe("Kraken", _kraken)) if r]
    rows.sort(key=lambda r: r["apr"], reverse=True)

    bar = "=" * 70
    print(f"\n{bar}\nLIVE BTC PERP FUNDING  {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n{bar}")
    print(f"{'venue':12} {'interval':9} {'rate/period':>13} {'APR':>10}   {'(next APR)':>10}")
    for r in rows:
        nxt = fmt_pct(r['next_apr']) if r.get('next_apr') is not None and r['next_apr'] == r['next_apr'] else "—"
        print(f"{r['venue']:12} {r['interval']:9} {r['rate']*100:>12.4f}% {fmt_pct(r['apr']):>10}   {nxt:>10}")

    if len(rows) >= 2:
        hi, lo = rows[0], rows[-1]
        spread = hi["apr"] - lo["apr"]
        avg = sum(r["apr"] for r in rows) / len(rows)
        print(f"\nCROSS-VENUE SPREAD")
        print(f"  highest: {hi['venue']} {fmt_pct(hi['apr'])}   lowest: {lo['venue']} {fmt_pct(lo['apr'])}")
        print(f"  spread:  {fmt_pct(spread)} APR")

        print(f"\nREAD")
        if avg > 0.05:
            print(f"• Funding broadly POSITIVE (avg {fmt_pct(avg)}). Long-spot/short-perp carry is paying;")
            print(f"  place the short leg on {hi['venue']} ({fmt_pct(hi['apr'])}) for the best yield.")
        elif avg < -0.05:
            print(f"• Funding broadly NEGATIVE (avg {fmt_pct(avg)}). Longs are paid; reverse-carry or")
            print(f"  hold the long-perp side. Shorts are crowded — squeeze risk elevated.")
        else:
            print(f"• Funding ~flat (avg {fmt_pct(avg)}). Thin directional carry.")

        if spread > 0.10 and hi["apr"] > 0 > lo["apr"]:
            print(f"• ARB: {hi['venue']} pays shorts while {lo['venue']} pays longs — short {hi['venue']} /")
            print(f"  long {lo['venue']} is delta-neutral and collects ~{fmt_pct(spread)} gross (mind fees & margin both sides).")
        elif spread > 0.10:
            print(f"• {fmt_pct(spread)} dispersion across venues — route your leg to the extreme, "
                  f"but same-sign so it's yield optimization, not a clean arb.")
        else:
            print(f"• Venues tight ({fmt_pct(spread)} spread) — no cross-venue edge right now.")


if __name__ == "__main__":
    main()
