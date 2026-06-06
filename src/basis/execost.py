"""basis-execost — what would the carry actually cost to fill, at REAL order-book depth?

For each spot-able asset it pulls the live Hyperliquid L2 book and walks it to show the
true slippage to ENTER (buy) and EXIT (sell) at your deploy size — then compares to the
flat slippage the paper sim assumes, so you can see whether that assumption is realistic
(usually it's conservative for liquid majors). This is the in-house answer to "what would
the fills actually be" — same realism Hummingbot paper gives, but keeping funding accrual.

Note: shown for the PERP book (the reliably-addressable one); the spot leg is comparable
for majors. Run:  python3 -m basis.execost [--usd 5000] [--universe BTC,ETH,SOL,HYPE]
"""

import argparse

from .core import fmt_pct, safe
from .core.execution import quote
from .core.sources import hl_l2_book
from .live import config


def run(usd=5000.0, universe=("BTC", "ETH", "SOL", "HYPE")):
    flat = config.SLIPPAGE_BPS
    bar = "=" * 78
    print(f"\n{bar}\nEXECUTION COST — real L2 depth, ${usd:,.0f} per leg (perp book)\n{bar}")
    print(f"paper assumes a flat {flat:.1f} bps slippage/leg ({2*flat:.1f} bps round-trip). "
          f"Real depth below:\n")
    print(f"  {'asset':6} {'mid':>11} {'enter(buy)':>11} {'exit(sell)':>11} {'round-trip':>11}  verdict")
    print("  " + "-" * 72)
    for c in universe:
        book = safe(c, lambda cc=c: hl_l2_book(cc))
        if not book or book["mid"] <= 0:
            print(f"  {c:6} {'no book':>11}")
            continue
        buy = quote(book, usd, "buy")
        sell = quote(book, usd, "sell")
        rt = buy["slippage_bps"] + sell["slippage_bps"]
        warn = " ⚠ thin (order exhausts book)" if (buy["exhausted"] or sell["exhausted"]) else ""
        verdict = ("flat assumption is CONSERVATIVE" if rt < 2 * flat
                   else "flat assumption UNDERSTATES — raise BASIS_SLIPPAGE_BPS")
        print(f"  {c:6} ${book['mid']:>10,.2f} {buy['slippage_bps']:>9.1f}b {sell['slippage_bps']:>9.1f}b "
              f"{rt:>9.1f}b  {verdict}{warn}")
    print(f"\n{bar}\nREAD\n{bar}")
    print("• 'round-trip' = enter + exit slippage on one leg, in bps, at your size.")
    print(f"• Compare to the paper assumption ({2*flat:.1f} bps round-trip/leg). If real depth is")
    print("  cheaper, the paper P&L is pessimistic on cost; if pricier (thin alts), raise the assumption.")
    print("• Taker fee (BASIS_TAKER_FEE_BPS) is separate and added on top of slippage.")
    print("• Set BASIS_REAL_DEPTH=1 to make the paper engine fill against live depth instead of the flat rate.")


def main():
    ap = argparse.ArgumentParser(description="Real order-book execution cost for the carry legs")
    ap.add_argument("--usd", type=float, default=5000.0, help="per-leg notional to price (default 5000)")
    ap.add_argument("--universe", default="BTC,ETH,SOL,HYPE", help="comma list of assets")
    a = ap.parse_args()
    run(usd=a.usd, universe=tuple(s.strip().upper() for s in a.universe.split(",") if s.strip()))


if __name__ == "__main__":
    main()
