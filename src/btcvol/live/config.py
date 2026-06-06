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
SYMBOL = "BTC"
CAPITAL_BTC = _f("BTCVOL_CAPITAL_BTC", "0.1")     # paper seed / target capital
DEPLOY_FRACTION = _f("BTCVOL_DEPLOY_FRACTION", "0.85")   # rest held as buffer
FUNDING_TIMED = os.environ.get("BTCVOL_FUNDING_TIMED", "1") == "1"

# --- hard risk limits (enforced pre-trade) ---
MAX_NOTIONAL_USD = _f("BTCVOL_MAX_NOTIONAL_USD", "10000")
MAX_LEVERAGE = _f("BTCVOL_MAX_LEVERAGE", "2.0")
MAX_ABS_DELTA_BTC = _f("BTCVOL_MAX_ABS_DELTA_BTC", "0.02")   # reconcile band
MAX_ORDER_BTC = _f("BTCVOL_MAX_ORDER_BTC", "0.05")
MIN_ORDER_BTC = _f("BTCVOL_MIN_ORDER_BTC", "0.0001")

# --- paths ---
DB_PATH = DATA_DIR / "live.db"
KILL_FILE = DATA_DIR / "KILL_SWITCH"          # presence halts ALL trading


def summary():
    return (f"mode={MODE} venue={VENUE} capital={CAPITAL_BTC}BTC deploy={DEPLOY_FRACTION:.0%} "
            f"timed={FUNDING_TIMED} | limits: notional<=${MAX_NOTIONAL_USD:,.0f} "
            f"lev<={MAX_LEVERAGE} order<={MAX_ORDER_BTC}BTC delta-band={MAX_ABS_DELTA_BTC}BTC")
