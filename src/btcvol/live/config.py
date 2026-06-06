"""Live-trading configuration. PAPER unless BTCVOL_MODE=live is set explicitly.

All secrets come from the environment (a gitignored .env), never the code. Risk
limits are hard ceilings enforced by risk.py on every order.
"""

import os

from ..core.paths import DATA_DIR


def _f(name, default):
    return float(os.environ.get(name, default))


# --- mode / venue (live requires a deliberate opt-in) ---
MODE = os.environ.get("BTCVOL_MODE", "paper").lower()      # "paper" | "live"
LIVE = MODE == "live"
VENUE = os.environ.get("BTCVOL_VENUE", "hyperliquid").lower()

# Read-only Hyperliquid account address (public clearinghouseState — no secret needed)
HL_ADDRESS = os.environ.get("BTCVOL_HL_ADDRESS", "")
# Live order signing key (agent/API wallet — CANNOT withdraw). Only read in live mode.
HL_API_SECRET = os.environ.get("BTCVOL_HL_API_SECRET", "")

# --- strategy ---
SYMBOL = os.environ.get("BTCVOL_SYMBOL", "BTC").upper()   # deploy asset (BTC/ETH/SOL/HYPE…)
CAPITAL_BTC = _f("BTCVOL_CAPITAL_BTC", "0.1")     # paper seed / target capital
DEPLOY_FRACTION = _f("BTCVOL_DEPLOY_FRACTION", "0.85")   # rest held as buffer
FUNDING_TIMED = os.environ.get("BTCVOL_FUNDING_TIMED", "1") == "1"

# --- hard risk limits (enforced pre-trade; USD so they're asset-agnostic) ---
MAX_NOTIONAL_USD = _f("BTCVOL_MAX_NOTIONAL_USD", "10000")
MAX_LEVERAGE = _f("BTCVOL_MAX_LEVERAGE", "2.0")
MAX_ABS_DELTA_USD = _f("BTCVOL_MAX_ABS_DELTA_USD", "1200")   # net-delta reconcile band
MAX_ORDER_USD = _f("BTCVOL_MAX_ORDER_USD", "3000")
MIN_ORDER_USD = _f("BTCVOL_MIN_ORDER_USD", "10")

# --- auto-selection (rotating carry: pick the best asset from the funding scan) ---
AUTO_MIN_FUNDING = _f("BTCVOL_AUTO_MIN_FUNDING", "0.05")        # min 14d-avg APR to deploy
AUTO_OI_FLOOR_USD = _f("BTCVOL_AUTO_OI_FLOOR_USD", "20000000")  # liquidity floor
AUTO_SWITCH_MARGIN = _f("BTCVOL_AUTO_SWITCH_MARGIN", "0.05")    # new must beat held by this APR
AUTO_EXIT_FUNDING = _f("BTCVOL_AUTO_EXIT_FUNDING", "0.0")       # exit held if its avg drops below
AUTO_SPOT_ANY = os.environ.get("BTCVOL_AUTO_SPOT_ANY", "0") == "1"
AUTO_SPOT_UNIVERSE = {s for s in os.environ.get(
    "BTCVOL_AUTO_SPOT_UNIVERSE", "BTC,ETH,SOL,HYPE").upper().split(",") if s}

# --- paths ---
_db = os.environ.get("BTCVOL_DB")
DB_PATH = (DATA_DIR / _db) if _db else (DATA_DIR / ("live.db" if SYMBOL == "BTC" else f"live_{SYMBOL.lower()}.db"))
KILL_FILE = DATA_DIR / "KILL_SWITCH"          # presence halts ALL trading (any asset)


def summary():
    return (f"mode={MODE} venue={VENUE} asset={SYMBOL} capital={CAPITAL_BTC}BTC "
            f"deploy={DEPLOY_FRACTION:.0%} timed={FUNDING_TIMED} | limits: "
            f"notional<=${MAX_NOTIONAL_USD:,.0f} lev<={MAX_LEVERAGE} "
            f"order<=${MAX_ORDER_USD:,.0f} delta-band=${MAX_ABS_DELTA_USD:,.0f}")
