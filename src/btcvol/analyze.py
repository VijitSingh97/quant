"""Analyze our own captured time series (data/timeseries.csv).

The launchd logger accumulates spot, realized/implied vol, VRP, funding, basis, OI,
and IV-surface skew at known timestamps. This summarizes that captured window —
distinct from vendor history because it's data we recorded ourselves. Degrades
gracefully: with few rows it still prints what it can and says so.

Run:  python3 -m btcvol.analyze
"""

import csv
import statistics

from .core import fmt_pct, fmt_vol, DATA_DIR, pearson

CSV_PATH = DATA_DIR / "timeseries.csv"
MIN_CORR_N = 20

NUMERIC = ["spot", "ret_30d", "rv_7d", "rv_30d", "dvol", "vrp", "okx_funding_apr",
           "hl_funding_apr", "okx_perp_premium_bps", "basis_near_ann_pct",
           "oi_total_usd", "atm_iv", "rr25", "bf25", "term_slope"]


def load_series(path):
    rows = []
    with open(path, newline="") as f:
        for raw in csv.DictReader(f):
            row = {"iso_time": raw.get("iso_time"), "unix": raw.get("unix")}
            for k in NUMERIC:
                v = raw.get(k, "")
                row[k] = float(v) if v not in ("", None) else None
            rows.append(row)
    return rows


def _vals(rows, key):
    return [r[key] for r in rows if r.get(key) is not None]


def column_stats(vals):
    if not vals:
        return None
    s = sorted(vals)
    def pct(p):
        return s[min(len(s) - 1, max(0, int(p * (len(s) - 1))))]
    return {"n": len(vals), "mean": statistics.mean(vals), "median": statistics.median(vals),
            "min": s[0], "max": s[-1], "p10": pct(0.10), "p90": pct(0.90)}


def pct_true(vals, pred):
    v = [x for x in vals if x is not None]
    return (sum(1 for x in v if pred(x)) / len(v) * 100) if v else None


def main():
    if not CSV_PATH.exists():
        print(f"No captured data yet at {CSV_PATH}. Run `make log` or install the launchd agent.")
        return
    rows = load_series(CSV_PATH)
    n = len(rows)
    bar = "=" * 70
    print(f"\n{bar}\nCAPTURED-DATA ANALYSIS — {CSV_PATH.name}\n{bar}")
    if n == 0:
        print("File has a header but no rows yet.")
        return
    span_h = (float(rows[-1]["unix"]) - float(rows[0]["unix"])) / 3600 if n > 1 else 0
    print(f"window {rows[0]['iso_time']} -> {rows[-1]['iso_time']}   {n} rows (~{span_h:.0f}h)")
    if n < MIN_CORR_N:
        print(f"NOTE: limited history (N={n}); figures are preliminary, correlations deferred until N>={MIN_CORR_N}.")

    vrp = _vals(rows, "vrp")
    if vrp:
        st = column_stats(vrp)
        print(f"\nVRP (implied - realized)")
        print(f"  mean {fmt_vol(st['mean'])}  median {fmt_vol(st['median'])}  "
              f"[{fmt_vol(st['min'])} .. {fmt_vol(st['max'])}]")
        print(f"  implied > realized {pct_true(vrp, lambda x: x > 0):.0f}% of rows")

    print(f"\nFUNDING (APR)")
    for label, key in [("OKX", "okx_funding_apr"), ("HL ", "hl_funding_apr")]:
        st = column_stats(_vals(rows, key))
        if st:
            pos = pct_true(_vals(rows, key), lambda x: x > 0)
            print(f"  {label}  mean {fmt_pct(st['mean'])}  [{fmt_pct(st['p10'])} .. {fmt_pct(st['p90'])}]  "
                  f"positive {pos:.0f}%")
    okx, hl = _vals(rows, "okx_funding_apr"), _vals(rows, "hl_funding_apr")
    disp = [h - o for h, o in zip(hl, okx)]
    if disp:
        print(f"  HL-OKX dispersion  mean {fmt_pct(statistics.mean(disp))}  max {fmt_pct(max(disp, key=abs))}")

    rr = _vals(rows, "rr25")
    if rr:
        bf = column_stats(_vals(rows, "bf25"))
        ts = column_stats(_vals(rows, "term_slope"))
        print(f"\nSKEW (~30d)")
        print(f"  RR25 mean {fmt_vol(statistics.mean(rr))}  put-skewed {pct_true(rr, lambda x: x < 0):.0f}% of rows"
              + (f"   BF25 mean {fmt_vol(bf['mean'])}" if bf else "")
              + (f"   term-slope mean {fmt_vol(ts['mean'])}" if ts else ""))
    else:
        print(f"\nSKEW: not captured in this window (added by issue #1 — accrues going forward).")

    basis = column_stats(_vals(rows, "basis_near_ann_pct"))
    oi = column_stats(_vals(rows, "oi_total_usd"))
    if basis or oi:
        print(f"\nBASIS / OI")
        if basis:
            print(f"  near basis  mean {basis['mean']:+.1f}% ann")
        if oi:
            print(f"  open interest  mean ${oi['mean']/1e9:,.2f}B")

    print(f"\nCORRELATIONS (exploratory, contemporaneous)")
    if n >= MIN_CORR_N:
        for label, a, b in [("funding(OKX) vs 30d return", "okx_funding_apr", "ret_30d"),
                            ("VRP vs 7d realized vol", "vrp", "rv_7d"),
                            ("RR25 vs 30d return", "rr25", "ret_30d")]:
            c = pearson([r[a] for r in rows], [r[b] for r in rows])
            print(f"  {label:30} r = {c:+.2f}" if c is not None else f"  {label:30} n/a")
    else:
        print(f"  need >={MIN_CORR_N} rows (have {n}) — keep the logger running.")

    print(f"\nREAD")
    if vrp:
        sign = "rich (sell-vol favored)" if statistics.mean(vrp) > 0 else "cheap"
        print(f"• Over our captured window VRP averaged {fmt_vol(statistics.mean(vrp))} — implied {sign}.")
    if rr:
        print(f"• Skew has been {'put-heavy (downside fear)' if statistics.mean(rr) < 0 else 'call-heavy'} "
              f"on average — consistent with the regime.")
    print(f"• This is OUR captured series; it gets statistically meaningful as the launchd logger runs.")
    print("\n(Educational tooling, not investment advice.)")


if __name__ == "__main__":
    main()
