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
| `btcvol.backtests.vrp` / `btcvol-vrp` | Backtests selling 30d vol *naked* (DVOL vs forward realized). Win rate, avg premium, worst tail roll, Sharpe. |
| `btcvol.backtests.robustness` / `btcvol-robust` | **Anti-overfit checks**: parameter sweep (Δ × wing), walk-forward (in/out-of-sample), and fee-drag — reuses one market pull. Verdict flags whether the edge is broad or a knife-edge. Flags: `--risk`, `--fee-bps`, `--flat`. |
| `btcvol.backtests.combined` / `btcvol-combined` | **Combines the two engines into one book**: funding carry (levered) + the filtered, skew-priced condor, over a common window. Reports each leg vs combined (total/CAGR/Sharpe/maxDD) and the leg correlation. Flags: `--leverage`, `--risk`, `--flat`. |
| `btcvol.backtests.structures` / `btcvol-condor-bt` | Backtests the **monthly defined-risk condor rule**: rolls a delta-based iron condor (synthetic credit @ historical DVOL, real price path for the payoff), compares sell-every-month vs a DVOL>RV filter, and shows the capped tail vs the naked book. Flags: `--delta`, `--wing-pct`, `--risk`. |
| `btcvol.structures` / `btcvol-structures` | Builds **defined-risk** short-vol structures (iron condor, put/call credit spreads) from the live Deribit chain. Prices legs conservatively (sell at bid, buy wings at ask) and reports max loss, breakevens, probability of profit (BS under implied), expected value under realized, and an ASCII payoff diagram. Flags: `--dte`, `--delta`, `--wing`. |
| `btcvol.skew` / `btcvol-skew` | Reads the live implied-vol **surface**: per-expiry ATM/25Δ vols, risk-reversal (RR25) and butterfly (BF25), the ATM term structure (contango/backwardation), an ASCII smile, and a fitted parametric skew shape that the condor backtest reuses. |
| `btcvol.monitor` / `btcvol-monitor` | Live perp funding across 4 venues, normalized to APR, plus the cross-venue spread / arb flag. |
| `btcvol.size` / `btcvol-size` | **Position sizer.** Vol-target scale (halve size when vol doubles) + fractional-Kelly stake from a win-rate/payoff. Flags: `--target-vol`, `--position-vol`, `--win-prob`, `--win-loss`. |
| `btcvol.book` / `btcvol-book` | **Delta-neutral book monitor.** Reads a positions file (spot/perp/option legs), prices each leg's delta off the live chain, reports net delta (BTC + USD), and suggests the perp hedge to flatten. `--threshold`, `--strict` (exit nonzero on drift). See `examples/positions.example.json`. |
| `btcvol.analyze` / `btcvol-analyze` | Summarizes our **own captured** `data/timeseries.csv`: VRP, funding, skew (RR25/BF25), basis/OI distributions and exploratory correlations. Degrades gracefully with little history. |
| `btcvol.logger` / `btcvol-log` | Appends one compact metrics row to `data/timeseries.csv` (spot, RV, DVOL, VRP, funding, basis, OI, and the IV-surface **ATM/RR25/BF25/term-slope** — skew has no public historical source, so we capture our own). The launchd target; migrates the CSV schema in place when columns are added. |

### Example

```bash
make dashboard      # what's the regime + which engine is favored right now?
make monitor        # where is funding richest, and is there a cross-venue arb?
make carry YEARS=2  # has carry actually paid over 2 years?
make vrp            # is the implied-vs-realized premium harvestable?
make structures     # turn the VRP edge into a concrete capped-loss trade
make skew           # read the live vol surface / skew
make condor-bt      # backtest the monthly condor rule (add --skew for real skew)
```

### Multi-asset

Every tool takes `--asset` (default `BTC`). `BTC`/`ETH` are fully supported (DVOL +
options + perp funding); `SOL` has perps + options but no DVOL (so the vol backtests
skip it); `PAXG` (tokenized gold) is a Deribit index/vol reference only.

```bash
PYTHONPATH=src python3 -m btcvol.dashboard --asset ETH
PYTHONPATH=src python3 -m btcvol.skew --asset ETH
PYTHONPATH=src python3 -m btcvol.backtests.combined --asset ETH --vol-target 0.18
PYTHONPATH=src python3 -m btcvol.logger --asset ETH      # -> data/eth_timeseries.csv
```

The logger writes each asset to its own `data/<asset>_timeseries.csv` (BTC stays
`timeseries.csv`); backtests that need a volatility index require BTC or ETH.

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
│   ├── skew.py               live implied-vol surface / skew reader
│   ├── size.py               position sizer (vol-target + fractional Kelly)
│   ├── book.py               delta-neutral book monitor (net-delta drift)
│   ├── analyze.py            analyze our own captured timeseries.csv
│   ├── logger.py             compact CSV time-series logger (launchd target)
│   ├── backtests/
│   │   ├── carry.py          funding-carry backtest
│   │   ├── vrp.py            volatility-risk-premium backtest (naked)
│   │   ├── structures.py     monthly condor-rule backtest (flat or --skew)
│   │   ├── combined.py       carry + filtered-condor combined-book backtest
│   │   └── robustness.py     param sweep / walk-forward / cost anti-overfit checks
│   └── core/                 shared layer (no presentation)
│       ├── http.py           keyless REST helpers
│       ├── stats.py          vol math: cc/parkinson vol, sharpe, drawdown
│       ├── blackscholes.py   BS pricing, delta, strike-from-delta, prob/EV
│       ├── surface.py        IV surface: smile metrics, interpolation, skew fit
│       ├── sizing.py         vol-target + fractional-Kelly sizing
│       ├── assets.py         per-asset venue symbols (BTC/ETH/SOL/PAXG)
│       ├── format.py         fmt_pct / fmt_vol / sparkline
│       ├── sources.py        all exchange data pulls (asset-parameterized)
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
> multi-year hourly funding instead. Per-asset symbols live in `core/assets.py`.

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

## Findings (≈3y of DVOL, ~33 condor rolls)

Backtests run on the full free history (DVOL backfills ~3y on Deribit; we use all of it).

- **Carry is the core edge.** Long spot / short perp earned **+24.5% CAGR at 3×**
  (Sharpe 3.3, −0.8% *modelled* drawdown) over 3 years — unlevered ~+5.6%, cyclical
  (+8.6% 2024 → +5.4% 2025 → +1.0% in the 2026 correction). Caveat: the real tail
  (exchange insolvency / short-leg liquidation) isn't in that curve, so the Sharpe is flattered.
- **Vol-risk-premium is real but tail-driven.** Implied > realized most days; selling
  30d vol *naked* wins often, but one spike (Jan-2026: realized 67% vs implied 39%,
  **−28.8 vol pts**) erases many wins ⇒ sell **defined-risk**, never naked.
- **The condor edge is narrow and modest — the 1-year sample flattered it.** On 3 years,
  the defined-risk condor at the *default* 20Δ/8% wings is roughly **break-even, and
  negative after 15bps/roll fees**. A real edge survives only in a tight corner (~25Δ
  short strikes, 5% wings: ~+25% CAGR) — just **8/15** parameter combos are positive.
  Real **skew** lowers the credit further (the long wing you buy is richer than the short you sell).
- **The combined book works through diversification, not condor return.** Over the full
  cycle the legs are **negatively correlated (r≈−0.3)**, so the condor is a partial *hedge*
  to carry rather than a standalone earner. Vol-targeted combined: **+21% CAGR, Sharpe
  1.55, maxDD −11%** — sizing (vol-target), not selection, drives the risk-adjusted result.

**Takeaway:** **carry is the workhorse; the condor is a marginal, parameter-sensitive
overlay that earns its place as a vol-targeted *hedge*, not a return source.** Sell
defined-risk and filtered (DVOL>RV), never naked, sized small. Even 33 rolls is short —
keep [#4](https://github.com/VijitSingh97/quant/issues/4) accumulating before sizing up.

---

## Roadmap

The roadmap is tracked in **[GitHub Issues](https://github.com/VijitSingh97/quant/issues)** —
completed work is closed there (each feature commit references its issue), open work is:

- [#4](https://github.com/VijitSingh97/quant/issues/4) — data-accumulation tracker (always-on; do not close)
- [#6](https://github.com/VijitSingh97/quant/issues/6) — historical-skew condor backtest (blocked on #4 accruing)
- [#9](https://github.com/VijitSingh97/quant/issues/9) — multi-asset (ETH/SOL/XRP/BNB + PAXG gold proxy)
- [#10](https://github.com/VijitSingh97/quant/issues/10) — cross-asset equities/commodities/macro adapters
- [#11](https://github.com/VijitSingh97/quant/issues/11) — richer log fields + extend free history backfill
