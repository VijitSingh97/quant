"""Market-data sources — public REST pulls for spot, funding, vol, and basis.

Reachable without geo-blocks / keys: Coinbase, OKX, Hyperliquid, Kraken Futures,
Deribit. (Binance is 451 and Bybit 403 from many regions.) Each function returns
plain dicts/lists; presentation lives in the tool modules.
"""

import math
import statistics
import time

from .http import http_get, http_post
from .stats import (DAYS, OKX_FUNDINGS_PER_DAY, HL_FUNDINGS_PER_DAY,
                    cc_vol, parkinson_vol, log_returns)


# --------------------------------------------------------------------------- #
# History pulls (for backtests)
# --------------------------------------------------------------------------- #
def okx_funding_history(inst="BTC-USDT-SWAP", pages=24):
    """Paginated OKX funding history -> [(ts_ms, rate)] oldest->newest.

    Note: OKX's public endpoint only serves ~3 months; use
    deribit_funding_history for multi-year backtests.
    """
    base = "https://www.okx.com/api/v5/public/funding-rate-history"
    out, cursor = [], None
    for _ in range(pages):
        url = f"{base}?instId={inst}&limit=100" + (f"&after={cursor}" if cursor else "")
        data = http_get(url)["data"]
        if not data:
            break
        out.extend((int(d["fundingTime"]), float(d["fundingRate"])) for d in data)
        cursor = data[-1]["fundingTime"]
    out.sort(key=lambda x: x[0])
    return out


def deribit_funding_history(instrument="BTC-PERPETUAL", days=730, window_days=28):
    """Paginated Deribit hourly funding -> [(ts_ms, interest_1h)] oldest->newest.

    Deribit caps each call at ~744 hourly rows (~31d), so we walk the window
    backward. interest_1h is the funding actually accrued that hour. ~3y deep.
    """
    now = int(time.time() * 1000)
    target = now - days * 24 * 3600 * 1000
    step = window_days * 24 * 3600 * 1000
    end, out, seen = now, [], set()
    base = "https://www.deribit.com/api/v2/public/get_funding_rate_history"
    while end > target:
        start = end - step
        rows = http_get(f"{base}?instrument_name={instrument}"
                        f"&start_timestamp={start}&end_timestamp={end}")["result"]
        if not rows:
            break
        for r in rows:
            ts = r["timestamp"]
            if ts not in seen:
                seen.add(ts)
                out.append((ts, r["interest_1h"]))
        end = start
    out.sort(key=lambda x: x[0])
    return out


def deribit_chart(instrument="BTC-PERPETUAL", days=400, resolution="1D"):
    """Deribit OHLC -> dict with 'ticks','open','high','low','close' (oldest->newest)."""
    now = int(time.time() * 1000)
    start = now - days * 24 * 3600 * 1000
    return http_get(f"https://www.deribit.com/api/v2/public/get_tradingview_chart_data"
                    f"?instrument_name={instrument}&start_timestamp={start}"
                    f"&end_timestamp={now}&resolution={resolution}")["result"]


def deribit_dvol(days=400, resolution="1D"):
    """Deribit DVOL (30d implied vol index) -> [(ts_ms, close_fraction)] oldest->newest."""
    now = int(time.time() * 1000)
    start = now - days * 24 * 3600 * 1000
    data = http_get(f"https://www.deribit.com/api/v2/public/get_volatility_index_data"
                    f"?currency=BTC&start_timestamp={start}&end_timestamp={now}"
                    f"&resolution={resolution}")["result"]["data"]
    return [(row[0], row[4] / 100.0) for row in data]   # close, % -> fraction


# --------------------------------------------------------------------------- #
# Live snapshots (for dashboard / logger)
# --------------------------------------------------------------------------- #
def coinbase_spot_and_candles():
    """Spot + daily candles (RV/trend) + hourly candles (short-term RV)."""
    spot = float(http_get("https://api.exchange.coinbase.com/products/BTC-USD/ticker")["price"])

    # daily candles: [time, low, high, open, close, volume], newest first, max 300
    daily = http_get("https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=86400")
    daily = sorted(daily, key=lambda c: c[0])          # oldest -> newest
    closes = [c[4] for c in daily]
    highs = [c[2] for c in daily]
    lows = [c[1] for c in daily]

    hourly = http_get("https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=3600")
    hourly = sorted(hourly, key=lambda c: c[0])
    h_closes = [c[4] for c in hourly]
    h_rets = log_returns(h_closes)
    rv_24h = statistics.stdev(h_rets[-24:]) * math.sqrt(24 * DAYS) if len(h_rets) >= 24 else None

    return {
        "spot": spot,
        "closes": closes, "highs": highs, "lows": lows,
        "rv_7d": cc_vol(closes, 7),
        "rv_14d": cc_vol(closes, 14),
        "rv_30d": cc_vol(closes, 30),
        "rv_parkinson_30d": parkinson_vol(highs, lows, 30),
        "rv_24h_intraday": rv_24h,
        "ret_7d": closes[-1] / closes[-8] - 1 if len(closes) > 8 else None,
        "ret_30d": closes[-1] / closes[-31] - 1 if len(closes) > 31 else None,
        "ma_7d": sum(closes[-7:]) / 7,
        "ma_30d": sum(closes[-30:]) / 30,
        "high_30d": max(highs[-30:]),
    }


def okx_perp(inst="BTC-USDT-SWAP"):
    base = "https://www.okx.com/api/v5"
    fr = http_get(f"{base}/public/funding-rate?instId={inst}")["data"][0]
    mark = float(http_get(f"{base}/public/mark-price?instType=SWAP&instId={inst}")["data"][0]["markPx"])
    idx = float(http_get(f"{base}/market/index-tickers?instId=BTC-USDT")["data"][0]["idxPx"])
    oi = http_get(f"{base}/public/open-interest?instType=SWAP&instId={inst}")["data"][0]

    hist = http_get(f"{base}/public/funding-rate-history?instId={inst}&limit=90")["data"]
    hist_rates = [float(h["fundingRate"]) for h in hist]
    avg_funding = statistics.mean(hist_rates) if hist_rates else None

    rate = float(fr["fundingRate"])
    return {
        "funding_rate_8h": rate,
        "funding_apr": rate * OKX_FUNDINGS_PER_DAY * DAYS,
        "next_funding_rate_8h": float(fr.get("nextFundingRate") or "nan"),
        "avg_funding_8h_30d": avg_funding,
        "avg_funding_apr_30d": avg_funding * OKX_FUNDINGS_PER_DAY * DAYS if avg_funding is not None else None,
        "mark": mark, "index": idx,
        "perp_premium_bps": (mark / idx - 1) * 1e4,
        "open_interest_btc": float(oi["oi"]),
        "open_interest_usd": float(oi["oiCcy"]) * idx if oi.get("oiCcy") else None,
    }


def hyperliquid_perp(coin="BTC"):
    meta, ctxs = http_post("https://api.hyperliquid.xyz/info", {"type": "metaAndAssetCtxs"})
    i = next(k for k, a in enumerate(meta["universe"]) if a["name"] == coin)
    c = ctxs[i]
    rate = float(c["funding"])                 # hourly
    mark = float(c["markPx"])
    oracle = float(c["oraclePx"])
    return {
        "funding_rate_1h": rate,
        "funding_apr": rate * HL_FUNDINGS_PER_DAY * DAYS,
        "mark": mark, "oracle": oracle,
        "perp_premium_bps": (mark / oracle - 1) * 1e4,
        "open_interest_btc": float(c["openInterest"]),
        "open_interest_usd": float(c["openInterest"]) * oracle,
    }


def deribit_vol_and_basis():
    """Current DVOL + dated-future basis term structure (annualized cash-and-carry)."""
    base = "https://www.deribit.com/api/v2/public"
    index = http_get(f"{base}/get_index_price?index_name=btc_usd")["result"]["index_price"]

    now_ms = int(time.time() * 1000)
    start_ms = now_ms - 3 * 24 * 3600 * 1000
    dv = http_get(f"{base}/get_volatility_index_data?currency=BTC"
                  f"&start_timestamp={start_ms}&end_timestamp={now_ms}&resolution=3600")["result"]["data"]
    dvol = dv[-1][4] / 100.0 if dv else None

    # Skip contracts inside 2 days: annualizing ~0 basis over ~0 time is noise.
    instruments = http_get(f"{base}/get_instruments?currency=BTC&kind=future&expired=false")["result"]
    dated = sorted((i for i in instruments if i["settlement_period"] != "perpetual"),
                   key=lambda i: i["expiration_timestamp"])
    term = []
    for inst in dated:
        days = (inst["expiration_timestamp"] - now_ms) / (1000 * 86400)
        if days < 2:
            continue
        tk = http_get(f"{base}/ticker?instrument_name={inst['instrument_name']}")["result"]
        fut = tk["mark_price"]
        term.append({
            "instrument": inst["instrument_name"],
            "days_to_expiry": days,
            "future_mark": fut,
            "raw_basis_pct": (fut / index - 1) * 100,
            "annualized_basis_pct": (fut / index - 1) * (DAYS / days) * 100,
        })
    basis = term[0] if term else None
    return {"index": index, "dvol": dvol, "dated_basis": basis, "term_structure": term}
