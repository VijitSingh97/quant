"""Cross-asset vol-risk-premium for equities / commodities (non-crypto, via Yahoo).

The vol-selling engine ports outside crypto: a CBOE vol index (^VIX/^GVZ/^OVX) is
the implied-vol analogue of Deribit DVOL, and the underlying (^GSPC/GLD/USO) gives
realized vol. This reads implied vs realized — the same VRP lens as the crypto
tools — for the S&P, gold, or oil.

What does NOT port: funding carry (no perpetual funding outside crypto). You'd
harvest this VRP with index options / VIX futures, not a long-spot/short-perp book.

Run:  python3 -m basis.macro [--asset SPX|GOLD|OIL]
"""

import argparse
import math
import statistics

from .core import cc_vol, log_returns, fmt_vol, fmt_pct, sparkline, DAYS, safe
from .core.assets import get_macro
from .core.sources import yahoo_chart

HOLD = 30


def _fwd_rv(closes, i, horizon=HOLD):
    seg = closes[i:i + horizon + 1]
    if len(seg) < horizon + 1:
        return None
    return statistics.stdev(log_returns(seg)) * math.sqrt(DAYS)


def run(asset="SPX"):
    m = get_macro(asset)
    vix = safe("vol index", lambda: yahoo_chart(m["vol_index"], rng="2y"))
    und = safe("underlying", lambda: yahoo_chart(m["underlying"], rng="2y"))
    if not vix or not und:
        return
    iv = [c / 100.0 for c in vix["closes"]]      # vol index is in percentage points
    px = und["closes"]
    n = min(len(iv), len(px))                     # both share the NYSE calendar
    iv, px = iv[-n:], px[-n:]

    iv_now = iv[-1]
    rv30 = cc_vol(px, 30)
    rv7 = cc_vol(px, 7)
    vrp_now = iv_now - rv30

    # historical: implied today vs realized over the NEXT 30d (same lens as the crypto VRP)
    diffs = []
    for i in range(n - HOLD):
        rvf = _fwd_rv(px, i)
        if rvf is not None:
            diffs.append(iv[i] - rvf)
    pct_pos = sum(1 for d in diffs if d > 0) / len(diffs) * 100 if diffs else None
    mean_vrp = statistics.mean(diffs) if diffs else None

    bar = "=" * 72
    print(f"\n{bar}\n{m['label']} VOL-RISK-PREMIUM — implied ({m['vol_index']}) vs realized ({m['underlying']})\n{bar}")
    print(f"  implied now      {fmt_vol(iv_now)}   ({m['vol_index']})")
    print(f"  realized 7d/30d  {fmt_vol(rv7)} / {fmt_vol(rv30)}")
    print(f"  VRP now          {fmt_vol(vrp_now)}   ({'rich — selling favored' if vrp_now > 0 else 'cheap'})")
    rv_fwd_series = [_fwd_rv(px, i) for i in range(n - HOLD)]
    ds = max(1, len(iv) // 100)                  # downsample long daily series for the sparkline
    print(f"\n  history (~2y, implied vs forward-30d realized)")
    print(f"    implied > realized {pct_pos:.0f}% of days   mean VRP {fmt_vol(mean_vrp)}")
    print(f"    implied path     {sparkline(iv[::ds])}")
    print(f"    realized fwd     {sparkline(rv_fwd_series[::ds])}")

    print(f"\n{bar}\nREAD\n{bar}")
    if mean_vrp and mean_vrp > 0:
        print(f"• {m['label']} carries a positive VRP too ({fmt_vol(mean_vrp)} avg, implied>realized "
              f"{pct_pos:.0f}% of days) — the same edge as crypto, harvested via index options / VIX futures.")
    else:
        print(f"• No positive VRP here over this window — don't sell {m['label']} vol now.")
    print("• Funding carry does NOT apply outside crypto (no perpetual funding). Only the")
    print("  defined-risk vol-selling engine ports; size it the same way (vol-target, never naked).")
    print("\n(Educational tooling, not investment advice. Yahoo data; ETF realized ≈ index realized.)")


def main():
    ap = argparse.ArgumentParser(description="Cross-asset VRP (equities/commodities via Yahoo)")
    ap.add_argument("--asset", default="SPX", help="macro asset: SPX, GOLD, OIL")
    run(asset=ap.parse_args().asset)


if __name__ == "__main__":
    main()
