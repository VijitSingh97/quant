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
| `btcvol.backtests.combined` / `btcvol-combined` | **Combines the two engines into one book**: funding carry (levered) + the filtered, skew-priced condor, over a common window. Reports each leg vs combined (total/CAGR/Sharpe/maxDD) and the leg correlation. Flags: `--leverage`, `--risk`, `--flat`. |
| `btcvol.backtests.structures` / `btcvol-condor-bt` | Backtests the **monthly defined-risk condor rule**: rolls a delta-based iron condor (synthetic credit @ historical DVOL, real price path for the payoff), compares sell-every-month vs a DVOL>RV filter, and shows the capped tail vs the naked book. Flags: `--delta`, `--wing-pct`, `--risk`. |
| `btcvol.structures` / `btcvol-structures` | Builds **defined-risk** short-vol structures (iron condor, put/call credit spreads) from the live Deribit chain. Prices legs conservatively (sell at bid, buy wings at ask) and reports max loss, breakevens, probability of profit (BS under implied), expected value under realized, and an ASCII payoff diagram. Flags: `--dte`, `--delta`, `--wing`. |
| `btcvol.skew` / `btcvol-skew` | Reads the live implied-vol **surface**: per-expiry ATM/25Δ vols, risk-reversal (RR25) and butterfly (BF25), the ATM term structure (contango/backwardation), an ASCII smile, and a fitted parametric skew shape that the condor backtest reuses. |
| `btcvol.monitor` / `btcvol-monitor` | Live perp funding across 4 venues, normalized to APR, plus the cross-venue spread / arb flag. |
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
│   ├── book.py               delta-neutral book monitor (net-delta drift)
│   ├── analyze.py            analyze our own captured timeseries.csv
│   ├── logger.py             compact CSV time-series logger (launchd target)
│   ├── backtests/
│   │   ├── carry.py          funding-carry backtest
│   │   ├── vrp.py            volatility-risk-premium backtest (naked)
│   │   ├── structures.py     monthly condor-rule backtest (flat or --skew)
│   │   └── combined.py       carry + filtered-condor combined-book backtest
│   └── core/                 shared layer (no presentation)
│       ├── http.py           keyless REST helpers
│       ├── stats.py          vol math: cc/parkinson vol, sharpe, drawdown
│       ├── blackscholes.py   BS pricing, delta, strike-from-delta, prob/EV
│       ├── surface.py        IV surface: smile metrics, interpolation, skew fit
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
- **Condor rule** (~1y, 13 rolls): the defined-risk version won **85%** of months;
  the two losing months lost a **bounded** max instead of the naked tail.
  - *Flat-vol* pricing looked great (CAGR +21%, Sharpe 0.74) — but it **overstates**
    the credit. Adding **real skew** (`--skew`) cuts avg credit ~17% and the edge
    with it: unconditional drops to CAGR +5% / Sharpe 0.32, because in a put-skewed
    market the long wing you *buy* is richer than the short you *sell*.
  - The **DVOL>RV filter** is what keeps it viable under skew: CAGR ~+11%, Sharpe
    0.55, maxDD −20% (vs −28% unconditional). Sample is small — directional, not conclusive.

- **Combined book** (carry 3× + filtered condor 15%/roll, ~1y): **~doubles carry's
  return** (CAGR ~+24% vs ~+13%) for a bounded ~−15% maxDD coming almost entirely
  from the condor leg. Combined Sharpe (~1.2) sits below carry-only's (~3.4) — but
  carry's Sharpe is *flattered* (its liquidation tail isn't in the curve). Legs are
  only mildly correlated (r≈+0.3): both prefer calm, so the hedge between them is partial.

**Takeaway:** both edges are real but tail-driven, and **skew makes defined-risk
selling less generous than flat-vol intuition suggests**. The combined book is the
strategy: carry base + filtered defined-risk condor overlay, vol-targeted, never naked.

---

## Roadmap

- ~~Defined-risk option spread / iron-condor modeler against the live Deribit chain~~ — done (`btcvol.structures`)
- ~~Backtest the condor-selling rule historically (roll on DVOL>RV, measure the tail)~~ — done (`btcvol.backtests.structures`)
- ~~Vol-surface & skew reader~~ — done (`btcvol.skew`); also feeds `--skew` into the condor backtest (which revealed flat-vol was over-optimistic)
- ~~Capture 25Δ RR/BF over time in the logger~~ — done ([#1](https://github.com/VijitSingh97/quant/issues/1)); RR25/BF25/ATM/term-slope now logged
- ~~Delta-neutral book monitor~~ — done (`btcvol.book`, [#3](https://github.com/VijitSingh97/quant/issues/3))
- ~~Analyze strategies on our own captured `timeseries.csv`~~ — done (`btcvol.analyze`, [#2](https://github.com/VijitSingh97/quant/issues/2)); grows useful as history accrues
- ~~Combined-book backtest (carry + filtered condor as one strategy)~~ — done (`btcvol.backtests.combined`, [#5](https://github.com/VijitSingh97/quant/issues/5))
- Open issues: [#6](https://github.com/VijitSingh97/quant/issues/6) historical-skew backtest (blocked on [#4](https://github.com/VijitSingh97/quant/issues/4) data) · [#7](https://github.com/VijitSingh97/quant/issues/7) robustness/anti-overfit · [#8](https://github.com/VijitSingh97/quant/issues/8) position sizer (vol-target + fractional Kelly)
