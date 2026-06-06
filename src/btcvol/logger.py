"""Append ONE compact row of key metrics to data/timeseries.csv.

Designed to run under launchd (no LLM tokens). Over time this builds our own
dataset so we can later backtest on data captured live, not just vendor history —
including the IV-surface skew (RR25/BF25), which has no public historical source.

Run:  python3 -m btcvol.logger
"""

import csv

import time

from .core import safe, DATA_DIR
from .core.sources import (coinbase_spot_and_candles, okx_perp,
                           hyperliquid_perp, deribit_vol_and_basis,
                           deribit_option_chain)
from .core.surface import build_surface, summary_metrics

CSV_PATH = DATA_DIR / "timeseries.csv"
FIELDS = ["iso_time", "unix", "spot", "ret_30d", "rv_7d", "rv_30d", "dvol", "vrp",
          "okx_funding_apr", "hl_funding_apr", "okx_perp_premium_bps",
          "basis_near_ann_pct", "oi_total_usd",
          "atm_iv", "rr25", "bf25", "term_slope"]


def _r(x, n):
    return round(x, n) if x is not None else None


def collect():
    cb = safe("coinbase", coinbase_spot_and_candles)
    okx = safe("okx", okx_perp)
    hl = safe("hyperliquid", hyperliquid_perp)
    der = safe("deribit", deribit_vol_and_basis)
    surf = safe("surface", lambda: build_surface(deribit_option_chain()))
    sm = summary_metrics(surf) if surf else {}

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
        "spot": _r(cb["spot"], 2) if cb else None,
        "ret_30d": _r(cb["ret_30d"], 5) if cb and cb.get("ret_30d") is not None else None,
        "rv_7d": _r(cb["rv_7d"], 4) if cb and cb.get("rv_7d") else None,
        "rv_30d": _r(rv30, 4),
        "dvol": _r(dvol, 4),
        "vrp": _r(vrp, 4),
        "okx_funding_apr": _r(okx["funding_apr"], 4) if okx else None,
        "hl_funding_apr": _r(hl["funding_apr"], 4) if hl else None,
        "okx_perp_premium_bps": _r(okx["perp_premium_bps"], 2) if okx else None,
        "basis_near_ann_pct": _r(basis, 2),
        "oi_total_usd": round(oi) if oi else None,
        "atm_iv": _r(sm.get("atm_iv"), 4),
        "rr25": _r(sm.get("rr25"), 4),
        "bf25": _r(sm.get("bf25"), 4),
        "term_slope": _r(sm.get("term_slope"), 4),
    }


def append_row(path, fields, row):
    """Append a row, migrating an older-schema CSV in place (pads old rows).

    Keeps the logger forward-compatible when we add columns: if the existing
    header differs from `fields`, the file is rewritten with the new header and
    old rows get empty values for the new columns.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            old_fields = reader.fieldnames or []
            if old_fields != fields:
                existing = list(reader)
                with open(path, "w", newline="") as out:
                    w = csv.DictWriter(out, fieldnames=fields)
                    w.writeheader()
                    for er in existing:
                        w.writerow({k: er.get(k, "") for k in fields})
                    w.writerow(row)
                return
        with open(path, "a", newline="") as f:
            csv.DictWriter(f, fieldnames=fields, extrasaction="ignore").writerow(row)
    else:
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerow(row)


def main():
    row = collect()
    append_row(CSV_PATH, FIELDS, row)
    print(f"{row['iso_time']}  spot={row['spot']}  dvol={row['dvol']}  vrp={row['vrp']}  "
          f"rr25={row['rr25']}  bf25={row['bf25']}  hl_fund={row['hl_funding_apr']}  -> {CSV_PATH}")


if __name__ == "__main__":
    main()
