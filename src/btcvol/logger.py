"""Append ONE compact row of key metrics to data/timeseries.csv.

Designed to run under launchd (no LLM tokens). Over time this builds our own
dataset so we can later backtest on data captured live, not just vendor history.

Run:  python3 -m btcvol.logger
"""

import csv
import os

import time

from .core import safe, DATA_DIR
from .core.sources import (coinbase_spot_and_candles, okx_perp,
                           hyperliquid_perp, deribit_vol_and_basis)

CSV_PATH = DATA_DIR / "timeseries.csv"
FIELDS = ["iso_time", "unix", "spot", "ret_30d", "rv_7d", "rv_30d", "dvol", "vrp",
          "okx_funding_apr", "hl_funding_apr", "okx_perp_premium_bps",
          "basis_near_ann_pct", "oi_total_usd"]


def collect():
    cb = safe("coinbase", coinbase_spot_and_candles)
    okx = safe("okx", okx_perp)
    hl = safe("hyperliquid", hyperliquid_perp)
    der = safe("deribit", deribit_vol_and_basis)

    dvol = der.get("dvol") if der else None
    rv30 = cb.get("rv_30d") if cb else None
    vrp = (dvol - rv30) if (dvol is not None and rv30 is not None) else None
    basis = None
    if der and der.get("term_structure"):
        meaningful = [b for b in der["term_structure"] if b["days_to_expiry"] >= 7]
        basis = (meaningful[0]["annualized_basis_pct"] if meaningful
                 else der["term_structure"][0]["annualized_basis_pct"])
    oi = sum(x["open_interest_usd"] for x in (okx, hl)
             if x and x.get("open_interest_usd")) or None

    return {
        "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "unix": int(time.time()),
        "spot": round(cb["spot"], 2) if cb else None,
        "ret_30d": round(cb["ret_30d"], 5) if cb and cb.get("ret_30d") is not None else None,
        "rv_7d": round(cb["rv_7d"], 4) if cb and cb.get("rv_7d") else None,
        "rv_30d": round(rv30, 4) if rv30 else None,
        "dvol": round(dvol, 4) if dvol else None,
        "vrp": round(vrp, 4) if vrp is not None else None,
        "okx_funding_apr": round(okx["funding_apr"], 4) if okx else None,
        "hl_funding_apr": round(hl["funding_apr"], 4) if hl else None,
        "okx_perp_premium_bps": round(okx["perp_premium_bps"], 2) if okx else None,
        "basis_near_ann_pct": round(basis, 2) if basis is not None else None,
        "oi_total_usd": round(oi) if oi else None,
    }


def main():
    row = collect()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    new_file = not os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(row)
    print(f"{row['iso_time']}  spot={row['spot']}  rv30={row['rv_30d']}  "
          f"dvol={row['dvol']}  vrp={row['vrp']}  hl_fund={row['hl_funding_apr']}  -> {CSV_PATH}")


if __name__ == "__main__":
    main()
