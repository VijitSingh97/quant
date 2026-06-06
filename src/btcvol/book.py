"""Delta-neutral book monitor — track a book's net delta and flag drift.

The carry trade (long spot / short perp) and the option structures are meant to be
delta-neutral, but delta drifts as price moves (perps stay ~1.0; option deltas move
with spot). This reads a positions file, prices each leg's delta off the live chain,
reports the net, and suggests the perp hedge to flatten it.

Positions JSON:
  {
    "spot_btc": 1.0,
    "perps":   [{"venue": "okx", "qty_btc": -1.0}],
    "options": [{"instrument": "BTC-26JUN26-55000-P", "qty": -1.0}]
  }
qty is signed: negative = short. Option qty is in contracts (1 BTC each).

Run:  python3 -m btcvol.book [--positions FILE] [--threshold 0.05] [--strict]
"""

import argparse
import json

from .core import fmt_pct, safe, bs_delta
from .core.sources import deribit_option_chain


def hedge_btc(net_btc):
    """Perp trade (in BTC) that flattens the book: opposite of net delta."""
    return -net_btc


def compute(positions, chain):
    S = chain["index"]
    by_name = {o["instrument"]: o for o in chain["options"]}
    legs = []

    if positions.get("spot_btc"):
        q = positions["spot_btc"]
        legs.append({"name": "spot", "qty": q, "unit": 1.0, "delta": q})
    for p in positions.get("perps", []):
        q = p["qty_btc"]
        legs.append({"name": f"perp:{p.get('venue', '?')}", "qty": q, "unit": 1.0, "delta": q})
    for op in positions.get("options", []):
        o = by_name.get(op["instrument"])
        if not o:
            legs.append({"name": op["instrument"], "qty": op["qty"], "unit": None,
                         "delta": None, "missing": True})
            continue
        T = o["dte"] / 365.0
        unit = bs_delta(S, o["strike"], T, o["iv"], o["type"])
        legs.append({"name": op["instrument"], "qty": op["qty"], "unit": unit,
                     "delta": op["qty"] * unit})

    net = sum(l["delta"] for l in legs if l.get("delta") is not None)
    return {"S": S, "legs": legs, "net_btc": net, "net_usd": net * S}


def demo_positions(chain):
    """A small illustrative book: carry (long spot/short perp) + a short ~20Δ put,
    so net delta is non-zero and the hedge suggestion is meaningful."""
    S = chain["index"]
    puts = [o for o in chain["options"] if o["type"] == "P"]
    by_exp = {}
    for o in puts:
        by_exp.setdefault(o["expiry_ms"], []).append(o)
    grp = by_exp[min(by_exp, key=lambda e: abs(by_exp[e][0]["dte"] - 30))]
    T = grp[0]["dte"] / 365.0
    short_put = min(grp, key=lambda o: abs(abs(bs_delta(S, o["strike"], T, o["iv"], o["type"])) - 0.20))
    return {"spot_btc": 1.0, "perps": [{"venue": "okx", "qty_btc": -1.0}],
            "options": [{"instrument": short_put["instrument"], "qty": -1.0}]}


def main():
    ap = argparse.ArgumentParser(description="Delta-neutral book monitor")
    ap.add_argument("--positions", help="path to positions JSON (default: a demo book)")
    ap.add_argument("--threshold", type=float, default=0.05, help="net-delta alert threshold in BTC (default 0.05)")
    ap.add_argument("--strict", action="store_true", help="exit nonzero when net delta exceeds the threshold")
    args = ap.parse_args()

    chain = safe("Deribit chain", deribit_option_chain)
    if not chain:
        return
    if args.positions:
        with open(args.positions) as f:
            positions = json.load(f)
        demo = False
    else:
        positions = demo_positions(chain)
        demo = True

    res = compute(positions, chain)
    S = res["S"]
    bar = "=" * 70
    print(f"\n{bar}\nDELTA-NEUTRAL BOOK MONITOR   spot ${S:,.0f}"
          f"{'   [DEMO book — pass --positions FILE]' if demo else ''}\n{bar}")
    print(f"{'leg':28} {'qty':>8} {'unit Δ':>8} {'pos Δ (BTC)':>13}")
    for l in res["legs"]:
        if l.get("missing"):
            print(f"{l['name']:28} {l['qty']:>8.2f} {'n/a':>8} {'(not in chain)':>13}")
            continue
        print(f"{l['name']:28} {l['qty']:>8.2f} {l['unit']:>+8.3f} {l['delta']:>+13.3f}")

    net = res["net_btc"]
    print(f"\n  NET DELTA   {net:+.3f} BTC   (${res['net_usd']:+,.0f})")
    over = abs(net) > args.threshold
    if over:
        h = hedge_btc(net)
        side = "SHORT" if h < 0 else "LONG"
        print(f"  ALERT: |net delta| > {args.threshold} BTC threshold.")
        print(f"  HEDGE: {side} {abs(h):.3f} BTC of perp to flatten (net -> ~0).")
    else:
        print(f"  OK: within +/-{args.threshold} BTC of neutral — no hedge needed.")
    if any(l.get("missing") for l in res["legs"]):
        print("  (some option legs were not found in the live chain — check instrument names/expiry.)")

    print("\n(Educational tooling, not investment advice.)")
    if args.strict and over:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
