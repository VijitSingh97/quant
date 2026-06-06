"""Live-trading configuration. PAPER unless BASIS_MODE=live is set explicitly.

All secrets come from the environment (a gitignored .env), never the code. Risk
limits are hard ceilings enforced by risk.py on every order.

Env vars are read as BASIS_* and fall back to the legacy BTCVOL_* names, so an
existing .env or launchd agent keeps working after the rename.
"""

import json
import os

from ..core.paths import DATA_DIR

# Tuner-applied parameter overrides (written by `basis-tune`, read here on start).
# Precedence: explicit env var > overrides file > hardcoded default. So an operator's
# env always wins; the tuner's persisted choices apply otherwise. (#18 Phase B)
OVERRIDES_PATH = DATA_DIR / "overrides.json"


def load_overrides():
    try:
        return json.loads(OVERRIDES_PATH.read_text())
    except (OSError, ValueError):
        return {}


_OVERRIDES = load_overrides()


def _env(name, default=None):
    """BASIS_<name> env > legacy BTCVOL_<name> env > tuner override > default."""
    v = os.environ.get(f"BASIS_{name}")
    if v is None:
        v = os.environ.get(f"BTCVOL_{name}")
    if v is None and name in _OVERRIDES:
        v = _OVERRIDES[name]
    return default if v is None else v


def _f(name, default):
    return float(_env(name, default))


def _i(name, default):
    return int(float(_env(name, default)))


# --- mode / venue (live requires a deliberate opt-in) ---
MODE = _env("MODE", "paper").lower()                       # "paper" | "live"
LIVE = MODE == "live"
VENUE = _env("VENUE", "hyperliquid").lower()

# Read-only Hyperliquid account address (public clearinghouseState — no secret needed)
HL_ADDRESS = _env("HL_ADDRESS", "")
# Live order signing key (agent/API wallet — CANNOT withdraw). Only read in live mode.
HL_API_SECRET = _env("HL_API_SECRET", "")

# --- strategy ---
SYMBOL = _env("SYMBOL", "BTC").upper()            # deploy asset (BTC/ETH/SOL/HYPE…)
CAPITAL_BTC = _f("CAPITAL_BTC", "0.1")            # paper seed / target capital
DEPLOY_FRACTION = _f("DEPLOY_FRACTION", "0.85")   # rest held as buffer
FUNDING_TIMED = _env("FUNDING_TIMED", "1") == "1"

# --- trading costs (charged on every fill so profitability is reported NET of fees) ---
TAKER_FEE_BPS = _f("TAKER_FEE_BPS", "4.5")        # HL taker ~4.5 bps (volume-tiered)
SLIPPAGE_BPS = _f("SLIPPAGE_BPS", "5.0")          # modelled adverse fill on a market order
COST_PER_LEG_BPS = TAKER_FEE_BPS + SLIPPAGE_BPS   # total per-fill transaction cost (one source of truth)

# --- hard risk limits (enforced pre-trade; USD so they're asset-agnostic) ---
MAX_NOTIONAL_USD = _f("MAX_NOTIONAL_USD", "10000")
MAX_LEVERAGE = _f("MAX_LEVERAGE", "2.0")
MAX_ABS_DELTA_USD = _f("MAX_ABS_DELTA_USD", "1200")   # net-delta reconcile band
MAX_ORDER_USD = _f("MAX_ORDER_USD", "3000")
MIN_ORDER_USD = _f("MIN_ORDER_USD", "10")

# --- auto-selection (rotating carry: pick the best asset from the funding scan) ---
AUTO_MIN_FUNDING = _f("AUTO_MIN_FUNDING", "0.05")        # min 14d-avg APR to deploy
AUTO_OI_FLOOR_USD = _f("AUTO_OI_FLOOR_USD", "20000000")  # liquidity floor
AUTO_SWITCH_MARGIN = _f("AUTO_SWITCH_MARGIN", "0.05")    # new must beat held by this APR
AUTO_EXIT_FUNDING = _f("AUTO_EXIT_FUNDING", "0.0")       # exit held if its avg drops below
AUTO_SPOT_ANY = _env("AUTO_SPOT_ANY", "0") == "1"
AUTO_SPOT_UNIVERSE = {s for s in _env(
    "AUTO_SPOT_UNIVERSE", "BTC,ETH,SOL,HYPE").upper().split(",") if s}

# --- scheduled self-validation (the `validate` cycle: re-check the rule on fresh data) ---
VALIDATE_INTERVAL_SECONDS = _i("VALIDATE_INTERVAL_SECONDS", "604800")   # default weekly
VALIDATE_DAYS = _i("VALIDATE_DAYS", "365")                              # history to backtest over

# --- paths ---
_db = _env("DB")
DB_PATH = (DATA_DIR / _db) if _db else (DATA_DIR / ("live.db" if SYMBOL == "BTC" else f"live_{SYMBOL.lower()}.db"))
RESEARCH_DB = DATA_DIR / "research.db"        # metrics timeseries + validation reports (all-in-DB)
KILL_FILE = DATA_DIR / "KILL_SWITCH"          # presence halts ALL trading (any asset)


def summary():
    return (f"mode={MODE} venue={VENUE} asset={SYMBOL} capital={CAPITAL_BTC}BTC "
            f"deploy={DEPLOY_FRACTION:.0%} timed={FUNDING_TIMED} "
            f"cost={COST_PER_LEG_BPS:.1f}bps/leg | limits: "
            f"notional<=${MAX_NOTIONAL_USD:,.0f} lev<={MAX_LEVERAGE} "
            f"order<=${MAX_ORDER_USD:,.0f} delta-band=${MAX_ABS_DELTA_USD:,.0f}")
