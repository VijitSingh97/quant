"""Market-data sources — public REST pulls for spot, funding, vol, and basis.

Reachable without geo-blocks / keys: Coinbase, OKX, Hyperliquid, Kraken Futures,
Deribit. (Binance is 451 and Bybit 403 from many regions.) Each function returns
plain dicts/lists; presentation lives in the tool modules.
"""

import gzip
import math
import statistics
import socket
import time
import urllib.error
import urllib.request
from urllib.parse import quote

from .http import http_get, http_post, UA, TIMEOUT
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


def deribit_dvol(days=400, resolution="1D", currency="BTC"):
    """Deribit DVOL (30d implied vol index) -> [(ts_ms, close_fraction)] oldest->newest.
    Only BTC and ETH have a DVOL index."""
    now = int(time.time() * 1000)
    start = now - days * 24 * 3600 * 1000
    data = http_get(f"https://www.deribit.com/api/v2/public/get_volatility_index_data"
                    f"?currency={currency}&start_timestamp={start}&end_timestamp={now}"
                    f"&resolution={resolution}")["result"]["data"]
    return [(row[0], row[4] / 100.0) for row in data]   # close, % -> fraction


def tardis_options_chain(date, currency="BTC", window_us=300_000_000, max_rows=600_000):
    """Historical Deribit option chain from a Tardis.dev free monthly snapshot.

    `date` must be the 1st of a month ('YYYY-MM-01') — the free tier. Streams the
    gzipped options_chain CSV and keeps the first snapshot per symbol within a short
    window, returning our standard chain dict {index, options}. Free back to 2020-03.
    """
    y, m, d = date.split("-")
    url = f"https://datasets.tardis.dev/v1/deribit/options_chain/{y}/{m}/{d}/OPTIONS.csv.gz"
    resp = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60)
    gz = gzip.GzipFile(fileobj=resp)
    gz.readline()                                   # header
    pre = (currency + "-").encode()
    seen, first_ts, index, n = {}, None, None, 0
    for raw in gz:
        n += 1
        if n > max_rows:
            break
        p = raw.split(b",")
        if len(p) < 20:
            continue
        ts = int(p[2])
        if first_ts is None:
            first_ts = ts
        if ts > first_ts + window_us:
            break
        sym = p[1]
        if not sym.startswith(pre) or sym in seen:
            continue
        miv = p[16]
        if not miv or float(miv) <= 0:
            continue
        if index is None and p[18]:
            index = float(p[18])
        expiry_ms = int(p[6]) // 1000
        seen[sym] = {"instrument": sym.decode(), "type": "C" if p[4] == b"call" else "P",
                     "strike": float(p[5]), "expiry_ms": expiry_ms,
                     "iv": float(miv) / 100.0, "oi": float(p[7] or 0), "volume": None,
                     "dte": (expiry_ms - first_ts // 1000) / 86400000.0,
                     "mark_btc": float(p[15]) if p[15] else None, "bid_btc": None, "ask_btc": None}
    resp.close()
    return {"index": index, "options": [o for o in seen.values() if o["dte"] > 0]}


def yahoo_chart(symbol, rng="2y", interval="1d"):
    """Yahoo Finance daily OHLC -> {'ts', 'closes'} (oldest->newest, Nones dropped).

    The non-crypto data source (#10): equity/commodity ETFs and the CBOE vol indices
    (^VIX/^GVZ/^OVX) — the implied-vol analogues of Deribit DVOL.
    """
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}"
           f"?interval={interval}&range={rng}")
    res = http_get(url)["chart"]["result"][0]
    ts = res["timestamp"]
    closes = res["indicators"]["quote"][0]["close"]
    pairs = [(t, c) for t, c in zip(ts, closes) if c is not None]
    return {"ts": [t for t, _ in pairs], "closes": [c for _, c in pairs]}


def hl_all_funding():
    """Every Hyperliquid perp -> {coin: {apr, oi_usd, mark}} in one call (the broad scan)."""
    meta, ctxs = http_post("https://api.hyperliquid.xyz/info", {"type": "metaAndAssetCtxs"})
    out = {}
    for a, c in zip(meta["universe"], ctxs):
        try:
            px = float(c["oraclePx"])
            out[a["name"]] = {"apr": float(c["funding"]) * 24 * 365,
                              "oi_usd": float(c["openInterest"]) * px, "mark": px}
        except (KeyError, ValueError, TypeError):
            continue
    return out


def hl_funding_stats(coin, days=14):
    """Persistence of HL funding over `days`: annualized mean, range, % hours positive.
    A high mean with most hours positive = structurally hot (e.g. hard-to-short XMR)."""
    start = int(time.time() * 1000) - days * 24 * 3600 * 1000
    rows = http_post("https://api.hyperliquid.xyz/info",
                     {"type": "fundingHistory", "coin": coin, "startTime": start})
    r = [float(x["fundingRate"]) for x in rows]
    if not r:
        return None
    k = 24 * 365
    return {"avg": statistics.mean(r) * k, "lo": min(r) * k, "hi": max(r) * k,
            "pos_frac": sum(1 for x in r if x > 0) / len(r), "n": len(r)}


def hl_funding_series(coin, days=365, pause=0.35):
    """Paginated hourly HL funding history -> [(ts_ms, rate), ...] oldest→newest.
    HL returns ≤500 rows/call, so we walk startTime forward, pausing between pages
    and backing off on 429 to stay under the rate limit. Used for backtests."""
    now = int(time.time() * 1000)
    start = now - days * 24 * 3600 * 1000
    seen, out = set(), []
    while start < now:
        rows = None
        for attempt in range(5):
            try:
                rows = http_post("https://api.hyperliquid.xyz/info",
                                 {"type": "fundingHistory", "coin": coin, "startTime": start})
                break
            except (urllib.error.URLError, socket.timeout) as e:   # 429, timeout, transient
                if attempt < 4:
                    time.sleep(2.0 * (attempt + 1))                # exponential-ish backoff
                    continue
                raise
        if not rows:
            break
        for x in rows:
            t = int(x["time"])
            if t not in seen:
                seen.add(t)
                out.append((t, float(x["fundingRate"])))
        last = int(rows[-1]["time"])
        if last < start or len(rows) < 500:    # caught up
            break
        start = last + 1
        time.sleep(pause)
    out.sort()
    return out


def binance_all_funding():
    """All Binance USDT perps -> {coin: apr} in one call (geo-blocked in some regions)."""
    data = http_get("https://fapi.binance.com/fapi/v1/premiumIndex")
    return {d["symbol"][:-4]: float(d["lastFundingRate"]) * 3 * 365
            for d in data if d.get("symbol", "").endswith("USDT") and d.get("lastFundingRate")}


def bybit_all_funding():
    """All Bybit linear USDT perps -> {coin: apr} in one call (geo-blocked in some regions)."""
    lst = http_get("https://api.bybit.com/v5/market/tickers?category=linear")["result"]["list"]
    return {d["symbol"][:-4]: float(d["fundingRate"]) * 3 * 365
            for d in lst if d.get("symbol", "").endswith("USDT") and d.get("fundingRate")}


def gate_all_funding():
    """All Gate.io USDT perps -> {coin: apr} in one call (usually reachable; ~700 markets).
    funding_interval is per-contract seconds, so annualize exactly."""
    data = http_get("https://api.gateio.ws/api/v4/futures/usdt/contracts")
    out = {}
    for d in data:
        name, fr = d.get("name", ""), d.get("funding_rate")
        if not name.endswith("_USDT") or fr is None:
            continue
        interval = float(d.get("funding_interval") or 28800)        # default 8h
        out[name[:-5]] = float(fr) * (31536000.0 / interval)
    return out


def kucoin_all_funding():
    """All KuCoin USDT-margined perps -> {coin: apr} in one call (funding is 8h)."""
    data = http_get("https://api-futures.kucoin.com/api/v1/contracts/active")["data"]
    out = {}
    for d in data:
        sym, fr = d.get("symbol", ""), d.get("fundingFeeRate")
        if not sym.endswith("USDTM") or fr is None:
            continue
        coin = sym[:-5]
        out["BTC" if coin == "XBT" else coin] = float(fr) * 3 * 365   # XBT is KuCoin's BTC ticker
    return out


def dydx_all_funding():
    """All dYdX v4 perps -> {coin: apr} in one call (nextFundingRate is hourly)."""
    markets = http_get("https://indexer.dydx.trade/v4/perpetualMarkets")["markets"]
    out = {}
    for ticker, m in markets.items():
        fr = m.get("nextFundingRate")
        if fr is None:
            continue
        out[ticker.split("-")[0]] = float(fr) * 24 * 365
    return out


def deribit_option_chain(currency="BTC", index_name="btc_usd"):
    """Live BTC option chain -> {'index', 'options': [...]}.

    Strikes/expiries/types come from get_instruments (robust, no name parsing);
    mark IV and bid/ask/mark prices (quoted in BTC) come from the book summary.
    One call each — greeks/probabilities are computed locally from IV.
    """
    base = "https://www.deribit.com/api/v2/public"
    instruments = http_get(f"{base}/get_instruments?currency={currency}&kind=option&expired=false")["result"]
    summary = http_get(f"{base}/get_book_summary_by_currency?currency={currency}&kind=option")["result"]
    sm = {s["instrument_name"]: s for s in summary}
    index = http_get(f"{base}/get_index_price?index_name={index_name}")["result"]["index_price"]
    now = int(time.time() * 1000)

    opts = []
    for ins in instruments:
        s = sm.get(ins["instrument_name"])
        if not s or s.get("mark_iv") is None:
            continue
        opts.append({
            "instrument": ins["instrument_name"],
            "expiry_ms": ins["expiration_timestamp"],
            "dte": (ins["expiration_timestamp"] - now) / (1000 * 86400),
            "strike": float(ins["strike"]),
            "type": "C" if ins["option_type"] == "call" else "P",
            "iv": s["mark_iv"] / 100.0,          # % -> fraction
            "mark_btc": s.get("mark_price"),
            "bid_btc": s.get("bid_price"),
            "ask_btc": s.get("ask_price"),
            "oi": s.get("open_interest"),
            "volume": s.get("volume"),
        })
    return {"index": index, "options": opts}


# --------------------------------------------------------------------------- #
# Live snapshots (for dashboard / logger)
# --------------------------------------------------------------------------- #
def coinbase_spot_and_candles(product="BTC-USD"):
    """Spot + daily candles (RV/trend) + hourly candles (short-term RV)."""
    base = "https://api.exchange.coinbase.com/products"
    spot = float(http_get(f"{base}/{product}/ticker")["price"])

    # daily candles: [time, low, high, open, close, volume], newest first, max 300
    daily = http_get(f"{base}/{product}/candles?granularity=86400")
    daily = sorted(daily, key=lambda c: c[0])          # oldest -> newest
    closes = [c[4] for c in daily]
    highs = [c[2] for c in daily]
    lows = [c[1] for c in daily]

    hourly = http_get(f"{base}/{product}/candles?granularity=3600")
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
    idx_inst = inst.replace("-SWAP", "")        # BTC-USDT-SWAP -> BTC-USDT (index ticker)
    fr = http_get(f"{base}/public/funding-rate?instId={inst}")["data"][0]
    mark = float(http_get(f"{base}/public/mark-price?instType=SWAP&instId={inst}")["data"][0]["markPx"])
    idx = float(http_get(f"{base}/market/index-tickers?instId={idx_inst}")["data"][0]["idxPx"])
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


def deribit_vol_and_basis(currency="BTC", index_name="btc_usd"):
    """Current DVOL + dated-future basis term structure (annualized cash-and-carry).
    DVOL is None for assets without a volatility index (only BTC/ETH have one)."""
    base = "https://www.deribit.com/api/v2/public"
    index = http_get(f"{base}/get_index_price?index_name={index_name}")["result"]["index_price"]

    now_ms = int(time.time() * 1000)
    start_ms = now_ms - 3 * 24 * 3600 * 1000
    try:
        dv = http_get(f"{base}/get_volatility_index_data?currency={currency}"
                      f"&start_timestamp={start_ms}&end_timestamp={now_ms}&resolution=3600")["result"]["data"]
        dvol = dv[-1][4] / 100.0 if dv else None
    except Exception:       # noqa: BLE001 — no DVOL index for this currency
        dvol = None

    # Skip contracts inside 2 days: annualizing ~0 basis over ~0 time is noise.
    instruments = http_get(f"{base}/get_instruments?currency={currency}&kind=future&expired=false")["result"]
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
