# btcvol — BTC volatility & funding-carry toolkit

A dependency-free (Python stdlib only) research toolkit for monetizing **BTC
volatility** with risk control. It's built around two market-neutral "steady
income" engines — **delta-neutral funding carry** and **defined-risk volatility
selling** — plus the live data and backtests to decide *when* each is worth running.

> **Disclaimer.** Educational tooling, **not investment advice**. Backtests smooth
> over fees, skew, slippage, and the tail events that actually blow up short-vol and
> levered-carry books. Crypto leverage can liquidate you fast. Size accordingly.

---

## Why these two strategies

"Profit from volatility" and "steady, consistent profit" pull in opposite
directions — vol is what makes returns lumpy. The strategies that monetize it most
consistently are *market-neutral*: you stop betting on direction and get paid a
premium instead.

| Engine | You collect | Direction risk | Main tail risk |
|---|---|---|---|
| **Funding carry** — long spot / short perp | Perp funding (+ basis) | None (delta-neutral) | Exchange insolvency, short-leg liquidation |
| **Vol selling** — sell options, delta-hedged | Implied-vs-realized vol premium | None (hedged) | A realized-vol spike (the "elevator down") |

The tools quantify both edges on live and historical data so you can size them.

---

## Install

Python ≥ 3.9, no third-party dependencies.

```bash
# editable install -> gives you the btcvol-* console commands
pip install -e .

# or run without installing (every tool is a module)
PYTHONPATH=src python3 -m btcvol.dashboard
```

A `Makefile` wraps the common commands: `make dashboard`, `make monitor`,
`make carry YEARS=2`, `make vrp`, `make test`, `make log`.

---

## Tools

| Module / command | What it does |
|---|---|
| `btcvol.dashboard` / `btcvol-dashboard` | One-shot snapshot: spot, realized vol, DVOL implied vol, futures-basis term structure, perp funding/OI — plus an interpreted **suggested direction**. Saves a JSON snapshot to `data/`. |
| `btcvol.backtests.carry` / `btcvol-carry [years]` | Backtests long-spot/short-perp funding carry on multi-year Deribit hourly funding. APR, Sharpe, drawdown, % negative, yearly breakdown. |
| `btcvol.backtests.vrp` / `btcvol-vrp` | Backtests selling 30d vol (DVOL vs forward realized). Win rate, avg premium, worst tail roll, Sharpe. |
| `btcvol.structures` / `btcvol-structures` | Builds **defined-risk** short-vol structures (iron condor, put/call credit spreads) from the live Deribit chain. Prices legs conservatively (sell at bid, buy wings at ask) and reports max loss, breakevens, probability of profit (BS under implied), expected value under realized, and an ASCII payoff diagram. Flags: `--dte`, `--delta`, `--wing`. |
| `btcvol.monitor` / `btcvol-monitor` | Live perp funding across 4 venues, normalized to APR, plus the cross-venue spread / arb flag. |
| `btcvol.logger` / `btcvol-log` | Appends one compact metrics row to `data/timeseries.csv`. The launchd target. |

### Example

```bash
make dashboard      # what's the regime + which engine is favored right now?
make monitor        # where is funding richest, and is there a cross-venue arb?
make carry YEARS=2  # has carry actually paid over 2 years?
make vrp            # is the implied-vs-realized premium harvestable?
make structures     # turn the VRP edge into a concrete capped-loss trade
```

---

## Project layout

```
quant/
├── pyproject.toml            packaging + console scripts + pytest config
├── Makefile                  convenience targets
├── README.md  LICENSE  .gitignore
├── src/btcvol/
│   ├── __init__.py
│   ├── dashboard.py          market snapshot + interpretation
│   ├── monitor.py            cross-venue funding monitor
│   ├── structures.py         defined-risk option structures vs live chain
│   ├── logger.py             compact CSV time-series logger (launchd target)
│   ├── backtests/
│   │   ├── carry.py          funding-carry backtest
│   │   └── vrp.py            volatility-risk-premium backtest
│   └── core/                 shared layer (no presentation)
│       ├── http.py           keyless REST helpers
│       ├── stats.py          vol math: cc/parkinson vol, sharpe, drawdown
│       ├── blackscholes.py   BS pricing, delta, lognormal probabilities / EV
│       ├── format.py         fmt_pct / fmt_vol / sparkline
│       ├── sources.py        all exchange data pulls (incl. option chain)
│       └── paths.py          project-root-anchored data dir
├── scripts/
│   ├── run_logger.sh         what launchd actually executes
│   ├── install_launchd.sh    render plist + load the agent
│   └── uninstall_launchd.sh  unload + remove
├── deploy/
│   └── com.vijit.btcvol.logger.plist   launchd template (__ROOT__ substituted on install)
├── tests/                    pure-function unit tests (no network)
└── data/                     snapshots, timeseries.csv, logs (git-ignored)
```

**Design:** `core/` is the data/maths layer with no printing; the tool modules are
thin presentation + interpretation on top. That separation is what makes the
backtests and the live tools share exactly one set of data pulls and vol formulas.

---

## Data sources

All public, no API keys. Chosen because they're reachable without geo-blocks:

| Source | Used for |
|---|---|
| **Coinbase** | Spot + daily/hourly candles → realized vol, trend |
| **Deribit** | DVOL (30d implied vol), dated-futures basis, BTC-PERPETUAL funding history (hourly, ~3y) |
| **OKX**, **Hyperliquid**, **Kraken Futures** | Live perp funding + open interest |

> Blocked from many regions: **Binance** (HTTP 451) and **Bybit** (HTTP 403) — not
> used. Endpoints require a browser `User-Agent` (handled in `core/http.py`). OKX's
> *public* funding history only serves ~3 months, so backtests use Deribit's
> multi-year hourly funding instead.

---

## Automated logging (launchd)

A launchd **user agent** appends a metrics row hourly — no LLM tokens, and unlike
cron it survives sleep (the timer fires on wake).

```bash
make launchd-install      # render plist into ~/Library/LaunchAgents and load it
make launchd-uninstall    # unload + remove (leaves data/ intact)
launchctl list | grep btcvol     # check it's loaded
```

- Dataset grows in `data/timeseries.csv`; agent stdout/stderr in
  `data/launchd.{out,err}.log`.
- `RunAtLoad` writes one row immediately on install, so you can verify right away.
- **macOS note:** the agent runs while you're logged in; if the Mac sleeps, the
  hourly tick fires on the next wake. The first run may prompt once for folder access.

Over time this builds our *own* dataset — captured at known timestamps — so later
strategies can be backtested on live-captured funding/IV, not just vendor history.

---

## Testing

```bash
make test         # or: PYTHONPATH=src python3 -m pytest -q
```

Tests cover the pure functions (vol math, Sharpe, drawdown, formatting) and run
offline — no network calls.

---

## Findings snapshot (2026-06-05, mid-correction)

- **Carry** (2y, unlevered): **+5.6% CAGR** net of fees; +8.6% (2024) → +5.4%
  (2025) → **+1.0% (2026)**. Funding follows the cycle and thins out in corrections.
- **Vol-risk-premium** (~1y): implied > realized **72% of days**; selling 30d vol
  **won 77% of rolls** (~+4.2 vol pts avg, Sharpe ~1.0) — but the **worst roll lost
  -28.8 vol pts** (Jan 2026, realized 67% vs implied 39%). One tail erases many wins.

**Takeaway:** both edges are real but tail-driven. Combine them, vol-target your
size, and **sell defined-risk (spreads/condors), never naked**.

---

## Roadmap

- ~~Defined-risk option spread / iron-condor modeler against the live Deribit chain~~ — done (`btcvol.structures`)
- Vol-surface & skew reader (sell the right strikes across the whole surface, not just ~20Δ)
- Backtest the structure-selling rule historically (roll condors on DVOL>RV, measure tail)
- Backtest on our own `timeseries.csv` once it has history
- Delta-neutral book monitor (alert when net delta drifts)
