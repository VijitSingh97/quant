"""Backfill historical IV-surface skew from Tardis.dev free monthly snapshots.

Writes data/<asset>_skew_history.csv (BTC -> skew_history.csv): one row per month
with ATM / RR25 / BF25 / RR10 / BF10 / put-call OI, reconstructed from the free
Deribit options_chain snapshot for the 1st of each month (back to 2020-03). This is
the historical skew series the condor backtest needs — without waiting months (#4).

Resumable: re-running only fetches months not already in the CSV.
Run:  python3 -m basis.backfill [--asset BTC] [--start 2023-09]
"""

import argparse
import csv
import time

from .core import DATA_DIR, safe
from .core.assets import get_asset
from .core.sources import tardis_options_chain
from .core.surface import build_surface, summary_metrics

FIELDS = ["date", "asset", "index", "atm_iv", "rr25", "bf25", "rr10", "bf10",
          "pc_oi_ratio", "n_options"]


def month_firsts(start, end_ts):
    sy, sm = (int(x) for x in start.split("-")[:2])
    t = time.gmtime(end_ts)
    out, y, m = [], sy, sm
    while (y, m) <= (t.tm_year, t.tm_mon):
        out.append(f"{y:04d}-{m:02d}-01")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def _path(asset):
    return DATA_DIR / ("skew_history.csv" if asset.upper() == "BTC"
                       else f"{asset.lower()}_skew_history.csv")


def _existing_dates(path):
    if not path.exists():
        return set()
    with open(path, newline="") as f:
        return {r["date"] for r in csv.DictReader(f)}


def _r(x, n):
    return round(x, n) if x is not None else None


def run(asset="BTC", start="2020-03", end_ts=None):
    a = get_asset(asset)
    path = _path(asset)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    done = _existing_dates(path)
    months = [d for d in month_firsts(start, end_ts or time.time()) if d not in done]
    print(f"Backfilling {asset.upper()} skew from Tardis: {len(months)} months to fetch "
          f"({len(done)} already present) -> {path.name}")

    new_file = not path.exists()
    added = 0
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for date in months:
            ch = safe(date, lambda: tardis_options_chain(date, a["deribit_ccy"]))
            if not ch or not ch.get("options"):
                continue
            sm = summary_metrics(build_surface(ch))
            if not sm:
                continue
            w.writerow({"date": date, "asset": asset.upper(),
                        "index": _r(ch["index"], 2), "atm_iv": _r(sm.get("atm_iv"), 4),
                        "rr25": _r(sm.get("rr25"), 4), "bf25": _r(sm.get("bf25"), 4),
                        "rr10": _r(sm.get("rr10"), 4), "bf10": _r(sm.get("bf10"), 4),
                        "pc_oi_ratio": _r(sm.get("pc_oi_ratio"), 3), "n_options": len(ch["options"])})
            f.flush()
            added += 1
            print(f"  {date}  ATM {(_r(sm.get('atm_iv'),3) or 0)*100:5.1f}%  "
                  f"RR25 {(_r(sm.get('rr25'),3) or 0)*100:+5.1f}%  ({len(ch['options'])} opts)")
    print(f"Done: +{added} months. Total dataset -> {path}")


def main():
    ap = argparse.ArgumentParser(description="Backfill historical skew from Tardis free snapshots")
    ap.add_argument("--asset", default="BTC", help="BTC / ETH / SOL")
    ap.add_argument("--start", default="2020-03", help="first month YYYY-MM (default 2020-03)")
    args = ap.parse_args()
    run(asset=args.asset, start=args.start)


if __name__ == "__main__":
    main()
