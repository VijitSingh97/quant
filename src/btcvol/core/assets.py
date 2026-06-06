"""Asset registry — per-asset venue symbols, so the toolkit isn't BTC-hardcoded.

Each entry maps an asset to the symbols its data sources use. `has_dvol` flags the
two assets Deribit publishes a volatility index for (BTC, ETH) — the vol backtests
need it. Assets without a field (None) are simply skipped by tools that need it.
"""

ASSETS = {
    "BTC": {"coinbase": "BTC-USD", "okx": "BTC-USDT-SWAP", "hl": "BTC", "kraken": "PF_XBTUSD",
            "deribit_ccy": "BTC", "deribit_perp": "BTC-PERPETUAL", "deribit_index": "btc_usd",
            "has_dvol": True, "has_perp": True},
    "ETH": {"coinbase": "ETH-USD", "okx": "ETH-USDT-SWAP", "hl": "ETH", "kraken": "PF_ETHUSD",
            "deribit_ccy": "ETH", "deribit_perp": "ETH-PERPETUAL", "deribit_index": "eth_usd",
            "has_dvol": True, "has_perp": True},
    "SOL": {"coinbase": "SOL-USD", "okx": "SOL-USDT-SWAP", "hl": "SOL", "kraken": "PF_SOLUSD",
            "deribit_ccy": "SOL", "deribit_perp": "SOL-PERPETUAL", "deribit_index": "sol_usd",
            "has_dvol": False, "has_perp": True},
    # PAXG = tokenized gold: Deribit options + index only, no perp/funding (vol tools only).
    "PAXG": {"coinbase": None, "okx": None, "hl": None, "kraken": None,
             "deribit_ccy": "PAXG", "deribit_perp": None, "deribit_index": "paxg_usd",
             "has_dvol": False, "has_perp": False},
}


def get_asset(name):
    a = ASSETS.get((name or "BTC").upper())
    if not a:
        raise ValueError(f"unknown asset '{name}'; known: {', '.join(ASSETS)}")
    return a
