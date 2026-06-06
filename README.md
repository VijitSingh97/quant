# basis — market-neutral crypto carry & volatility toolkit

A dependency-free (Python stdlib only) toolkit for steady, **market-neutral**
income from crypto. It's built around two engines — **delta-neutral funding carry**
(the *basis trade*: long spot / short perp, across all liquid perp markets) and
**defined-risk volatility selling** — plus the live data, backtests, and a
paper-first execution layer to decide *when* each is worth running and to run it.

> **New here?** Start with the **[User Guide (GUIDE.md)](GUIDE.md)** — install, run, read
> the dashboard, and tune for better returns in ~10 minutes. Ready for real money? See
> **[GOING_LIVE.md](GOING_LIVE.md)** (staged rollout, preflight, and how long to validate first).

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
# editable install -> gives you the basis-* console commands
pip install -e .

# or run without installing (every tool is a module)
PYTHONPATH=src python3 -m basis.dashboard
```

A `Makefile` wraps the common commands: `make dashboard`, `make monitor`,
`make carry YEARS=2`, `make vrp`, `make test`, `make log`.

---

## Tools

| Module / command | What it does |
|---|---|
| `basis.dashboard` / `basis-dashboard` | One-shot snapshot: spot, realized vol, DVOL implied vol, futures-basis term structure, perp funding/OI — plus an interpreted **suggested direction**. Saves a JSON snapshot to `data/`. |
| `basis.backtests.carry` / `basis-carry [years]` | Backtests long-spot/short-perp funding carry on multi-year Deribit hourly funding. APR, Sharpe, drawdown, % negative, yearly breakdown. |
| `basis.backtests.vrp` / `basis-vrp` | Backtests selling 30d vol *naked* (DVOL vs forward realized). Win rate, avg premium, worst tail roll, Sharpe. |
| `basis.backtests.robustness` / `basis-robust` | **Anti-overfit checks**: parameter sweep (Δ × wing), walk-forward (in/out-of-sample), and fee-drag — reuses one market pull. Verdict flags whether the edge is broad or a knife-edge. Flags: `--risk`, `--fee-bps`, `--flat`. |
| `basis.backtests.combined` / `basis-combined` | **Combines the two engines into one book**: funding carry (levered) + the skew-priced condor, over a common window. Defaults to the **strongest config** — VOV-gated condor + funding-timed carry. Reports each leg vs combined (total/CAGR/Sharpe/maxDD) and the leg correlation. Flags: `--leverage`, `--risk`, `--vol-target`, `--no-vov`, `--no-timed`. |
| `basis.backfill` / `basis-backfill` | **Backfills historical IV-surface skew** from Tardis.dev free monthly Deribit option-chain snapshots (back to 2020) → `data/skew_history.csv`. Gives real historical RR/BF *now* instead of waiting on the logger. `--asset`, `--start`. |
| `basis.backtests.histskew` / `basis-histskew` · `basis.backtests.structures --histskew` | Condor backtest priced with **real per-roll historical skew** (from the Tardis backfill / our logged data) vs the static fit — answers whether the static-skew approximation was biased (issue #6). |
| `basis.backtests.structures` / `basis-condor-bt` | Backtests the **monthly defined-risk condor rule**: rolls a delta-based iron condor (synthetic credit @ historical DVOL, real price path for the payoff), compares sell-every-month vs a DVOL>RV filter, and shows the capped tail vs the naked book. Flags: `--delta`, `--wing-pct`, `--risk`. |
| `basis.structures` / `basis-structures` | Builds **defined-risk** short-vol structures (iron condor, put/call credit spreads) from the live Deribit chain. Prices legs conservatively (sell at bid, buy wings at ask) and reports max loss, breakevens, probability of profit (BS under implied), expected value under realized, and an ASCII payoff diagram. Flags: `--dte`, `--delta`, `--wing`. |
| `basis.skew` / `basis-skew` | Reads the live implied-vol **surface**: per-expiry ATM/25Δ vols, risk-reversal (RR25) and butterfly (BF25), the ATM term structure (contango/backwardation), an ASCII smile, and a fitted parametric skew shape that the condor backtest reuses. |
| `basis.monitor` / `basis-monitor` | Live perp funding across 4 venues, normalized to APR, plus the cross-venue spread / arb flag. |
| `basis.size` / `basis-size` | **Position sizer.** Vol-target scale (halve size when vol doubles) + fractional-Kelly stake from a win-rate/payoff. Flags: `--target-vol`, `--position-vol`, `--win-prob`, `--win-loss`. |
| `basis.backtests.rotation` / `basis-rotation` | **Backtests carry ROTATION vs fixed**, net of cost. Pulls HL hourly funding for the spot-able universe (BTC/ETH/SOL/HYPE), runs the *real* `select_asset` rule (trailing-avg rank + hysteresis), and compares rotating vs holding each fixed asset — APR, Sharpe, maxDD, switch count, cost drag, and a verdict. Validates whether `live-auto` is worth running. `--days`, `--window`, `--switch-margin`, `--cost-bps`, `--universe`. |
| `basis.backtests.regime` / `basis-regime` | **Regime study** (issue #17 Phase A): does allocating carry-vs-vol *by regime* beat always-carry? Builds per-block carry + defined-risk-condor return streams, classifies each block by VRP (DVOL−RV) and vol-of-vol (causally, expanding medians — no look-ahead), and compares **always-carry vs static-combined vs regime-weighted** net of cost, with a verdict. Research only — the vol leg is modelled, not live. `--leverage`, `--risk`, `--asset`. |
| `basis.carryscan` / `basis-carry-scan` | **Cross-asset/venue carry scanner.** Ranks **all** Hyperliquid perps (230, not just BTC) by **persistent** funding (multi-day average + % hours positive), surfacing structurally-hot, inefficiently-priced markets (e.g. XMR ~+32%, hard-to-short) vs one-hour spikes (PURR). Also pulls cross-venue funding from **Gate, KuCoin, dYdX** (+ Binance/Bybit where reachable) and lists the biggest **cross-venue funding spreads** — perp-vs-perp arb candidates (short the rich-funding venue, long the cheap one). `--min-oi`, `--top`, `--days`. |
| `basis.book` / `basis-book` | **Delta-neutral book monitor.** Reads a positions file (spot/perp/option legs), prices each leg's delta off the live chain, reports net delta (BTC + USD), and suggests the perp hedge to flatten. `--threshold`, `--strict` (exit nonzero on drift). See `examples/positions.example.json`. |
| `basis.analyze` / `basis-analyze` | Summarizes our **own captured** `data/timeseries.csv`: VRP, funding, skew (RR25/BF25/RR10), basis/OI distributions and exploratory correlations. Degrades gracefully with little history. |
| `basis.macro` / `basis-macro` | **Cross-asset VRP** for equities/commodities via Yahoo: implied (VIX-family `^VIX`/`^GVZ`/`^OVX`) vs realized for the S&P, gold, or oil. `--asset SPX\|GOLD\|OIL`. (Vol-selling ports; funding carry does not.) |
| `basis.logger` / `basis-log` | Appends one compact metrics row to `data/timeseries.csv` (spot, RV, DVOL, VRP, funding, basis, OI, and the IV-surface **ATM/RR25/BF25/term-slope** — skew has no public historical source, so we capture our own). Run on a schedule (Docker scheduler or launchd); migrates the CSV schema in place when columns are added. |

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
PYTHONPATH=src python3 -m basis.dashboard --asset ETH
PYTHONPATH=src python3 -m basis.skew --asset ETH
PYTHONPATH=src python3 -m basis.backtests.combined --asset ETH --vol-target 0.18
PYTHONPATH=src python3 -m basis.logger --asset ETH      # -> data/eth_timeseries.csv
```

The logger writes each asset to its own `data/<asset>_timeseries.csv` (BTC stays
`timeseries.csv`); backtests that need a volatility index require BTC or ETH.

---

## Live execution (paper-first) — see [README_live.md](README_live.md)

The research above feeds a safety-first execution layer (`basis.live`) that runs the
carry strategy in **paper mode by default** — live prices, simulated fills, full audit
trail, no API keys, no real money. Order placement is gated until you opt into live.

```bash
make live-paper      # one reconcile cycle (fixed asset)        [basis-live]
make live-auto       # auto-select best persistent-carry asset  [basis-live-auto]
make live-monitor    # CLI book status + carry opportunities    [basis-live-monitor]
make live-web        # web dashboard -> localhost:8787          [basis-live-web]
make carry-scan      # rank all perps by persistent funding     [basis-carry-scan]
make rotation        # backtest rotation vs fixed, net of cost  [basis-rotation]
make validate        # self-validation report -> research.db    [basis-validate]
make report-auto     # period P&L review of the auto book       [basis-report]
make preflight       # live-readiness go/no-go (no orders)      [basis-preflight]
```

Risk gate (USD limits + kill switch), SQLite audit store, read-only-first Hyperliquid
client, and an auto allocator with a liquidity floor + spot-able universe + hysteresis.
**How it decides what to trade** (scan → filter → hysteresis → funding-timing →
risk-gated reconcile), the phased path to live, and the API-key posture are all in
**[README_live.md](README_live.md#how-the-engine-decides-what-to-trade)**.

**Deploy on a home server (Docker):** a self-contained, power-loss- and network-blip-
resilient stack (scheduler + dashboard, SQLite-WAL on a named volume):
```bash
cp .env.example .env && docker compose up -d --build      # dashboard at :8787
```
See [README_live.md](README_live.md#deploy-on-a-home-server-docker--recommended) for the full guide.

---

## Project layout

```
quant/
├── pyproject.toml            packaging + console scripts + pytest config
├── Makefile                  convenience targets
├── README.md  README_live.md  GUIDE.md  LICENSE  .gitignore
├── src/basis/
│   ├── __init__.py
│   ├── dashboard.py          market snapshot + interpretation
│   ├── monitor.py            cross-venue funding monitor
│   ├── structures.py         defined-risk option structures vs live chain
│   ├── skew.py               live implied-vol surface / skew reader
│   ├── size.py               position sizer (vol-target + fractional Kelly)
│   ├── book.py               delta-neutral book monitor (net-delta drift)
│   ├── analyze.py            analyze our own captured timeseries.csv
│   ├── macro.py              cross-asset VRP (equities/commodities via Yahoo)
│   ├── backfill.py           historical skew from Tardis free monthly snapshots
│   ├── carryscan.py          cross-asset/venue carry scanner (persistent funding)
│   ├── logger.py             compact CSV time-series logger (scheduled target)
│   ├── backtests/
│   │   ├── carry.py          funding-carry backtest
│   │   ├── vrp.py            volatility-risk-premium backtest (naked)
│   │   ├── structures.py     monthly condor-rule backtest (flat or --skew)
│   │   ├── combined.py       carry + filtered-condor combined-book backtest
│   │   ├── robustness.py     param sweep / walk-forward / cost anti-overfit checks
│   │   ├── rotation.py       carry rotation vs fixed, net of cost (validates live-auto)
│   │   └── histskew.py       historical-skew condor backtest on our logged data (#6)
│   ├── core/                 shared layer (no presentation)
│       ├── http.py           keyless REST helpers
│       ├── stats.py          vol math: cc/parkinson vol, sharpe, drawdown
│       ├── blackscholes.py   BS pricing, delta, strike-from-delta, prob/EV
│       ├── surface.py        IV surface: smile metrics, interpolation, skew fit
│       ├── sizing.py         vol-target + fractional-Kelly sizing
│       ├── assets.py         per-asset venue symbols (BTC/ETH/SOL/PAXG)
│       ├── format.py         fmt_pct / fmt_vol / sparkline
│       ├── sources.py        all exchange data pulls (asset-parameterized)
│       └── paths.py          project-root-anchored data dir
│   └── live/                 EXECUTION layer (paper-first) — see README_live.md
│       ├── config.py         mode/venue/asset + USD risk limits (env-driven)
│       ├── store.py          SQLite audit store (events/orders/fills/positions/pnl/meta)
│       ├── risk.py           pre-trade gate + kill switch
│       ├── allocator.py      delta-neutral carry target
│       ├── selector.py       auto asset-selection (persistent funding + hysteresis)
│       ├── engine.py         fixed-asset reconcile engine
│       ├── auto.py           auto-rotating allocator
│       ├── validate.py       scheduled self-validation (re-check rule weekly, suggest)
│       ├── tune.py           guarded apply path for suggestions (bounded/audited/reversible)
│       ├── scheduler.py      supervisor loop (container) — runs cycles, self-heals
│       ├── healthcheck.py    container HEALTHCHECK (heartbeat freshness)
│       ├── status.py         shared status (CLI + web)
│       ├── monitor.py · web.py · dashboard.html   CLI + web tracker
│       └── exchanges/        base · paper (sim) · hyperliquid (read-only-first)
├── Dockerfile                stdlib-only image (non-root, healthcheck, data volume)
├── docker-compose.yml        home-server stack: scheduler + web, named volume
├── .env.example              deploy config template (copy to .env)
├── scripts/                  run_*.sh + install/uninstall_{launchd,live_paper,live_auto}.sh
├── deploy/                   launchd plist templates (com.vijit.basis.{logger,paper,auto})
├── tests/                    offline unit tests + opt-in integration smoke tests
└── data/                     SQLite books, timeseries.csv, logs (git-ignored)
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
| **Yahoo Finance** | Non-crypto (#10): equity/commodity ETFs + CBOE vol indices (`^VIX`/`^GVZ`/`^OVX`) for cross-asset VRP |
| **Tardis.dev** (free tier) | Historical Deribit option chain (mark IV) for the **1st of each month back to 2020** — the historical skew surface, no API key |

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
launchctl list | grep basis     # check it's loaded
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
make test              # offline unit suite (default, ~0.1s)
make test-integration  # opt-in: hit live venues and assert response shapes
```

**169 tests, fully offline** (no network — the suite runs in ~0.3s). Coverage spans the
pure logic: vol math / Sharpe / drawdown / Pearson, Black-Scholes + greeks + strike-from-
delta, the IV-surface smile/skew fit, position sizing, the asset registry, the backtest
factor math (incl. the rotation `compute`/curve/alignment helpers), the auto-selector
hysteresis, and the audit store (incl. the reports/metrics tables). The simulated
execution path (paper-exchange fills, funding accrual, the reconcile loop's delta-neutral
convergence, and the auto allocator's flatten) is tested via a fixed-mark exchange. The
**deployment/resilience layer** is covered too: the HTTP retry/backoff (retries transient
errors, fast-fails geo-blocks), SQLite WAL mode, the `BASIS_DATA_DIR` override, the
scheduler's per-cycle failure isolation, the container healthcheck's exit codes, the
**self-validation** (report shape, due/throttle, storage, and the **walk-forward** OOS
guard), the **fee model** (fees reduce equity + are tracked), the **regime study**
helpers, the **guarded tuner** (bounds, apply, rollback, reset), and **live-readiness**
(preflight checks + the live order **triple-gate**: blocked outside live, when unarmed,
and when the kill switch is on), the **cross-venue** funding spread logic, the **period
report** math, and **delta-neutral equity** (a price move leaves a hedged book's equity
unchanged) — all offline.

**Integration suite (opt-in, `-m integration`)** — 14 live-venue *smoke* tests that hit
the real endpoints (Hyperliquid, Coinbase, Deribit, OKX, Yahoo, Tardis, + the read-only
HL account client) and assert the **shape** of each response, so we catch upstream API
drift. A network/geo failure *skips* (so transient outages and geo-blocked venues like
Binance/Bybit don't fail the run); a wrong shape *fails*. Excluded from the default run
so `make test` stays offline and fast.

---

## Findings (≈3y of DVOL, ~33 condor rolls)

Backtests run on the full free history (DVOL backfills ~3y on Deribit; we use all of it).

- **Carry is the core edge.** Long spot / short perp earned **+24.5% CAGR at 3×**
  (Sharpe 3.3, −0.8% *modelled* drawdown) over 3 years — unlevered ~+5.6%, cyclical
  (+8.6% 2024 → +5.4% 2025 → +1.0% in the 2026 correction). Caveat: the real tail
  (exchange insolvency / short-leg liquidation) isn't in that curve, so the Sharpe is flattered.
  *Timing* the leg by a trailing-24h funding-sign forecast (Inan 2024) modestly helps — CAGR
  +5.8% vs +5.6% unlevered, higher Sharpe, only ~80% in-market (sidesteps the negative stretches).
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

- **Real historical skew** (33 monthly Tardis snapshots, `--histskew`): pricing each
  condor roll with the skew that *actually* prevailed gives CAGR **+4.9%** (Sharpe 0.32)
  vs the static-fit's **+3.5%** — close, so applying today's shape historically was an
  honest approximation (it mildly *understated* the edge). This validates the earlier
  static-skew results on real data, **without waiting months** for our own logger.
- **Vol-of-vol gate** (Du 2025, `--vov`): skipping rolls when vol-of-vol is above its
  expanding median (unstable-vol regimes) lifts the filtered condor to CAGR **+9.3%**,
  Sharpe **0.48**, maxDD **−20%** — a genuine improvement over the plain DVOL>RV filter.
- **Strongest combined book** (now the `combined` default — VOV-gated condor + funding-timed
  carry): **CAGR +23.3%, Sharpe 1.75, maxDD −11%** over 3y, vs the prior +21.0% / 1.53 — the
  timed carry leg sidesteps negative-funding stretches (≈0 modelled drawdown) and the VOV gate
  trims the condor's worst months. Legs stay negatively correlated (r≈−0.2), so the condor
  remains a hedge. This is the configuration the findings point to.

**Takeaway:** **carry is the workhorse; the condor is a marginal, parameter-sensitive
overlay that earns its place as a vol-targeted *hedge*, not a return source.** Sell
defined-risk and filtered (DVOL>RV), never naked, sized small. Even 33 rolls is short —
keep [#4](https://github.com/VijitSingh97/quant/issues/4) accumulating before sizing up.

---

## Roadmap

The roadmap is tracked in **[GitHub Issues](https://github.com/VijitSingh97/quant/issues)** —
completed work is closed there (each feature commit references its issue).

Data-gated (built, waiting on accumulated history):
- [#4](https://github.com/VijitSingh97/quant/issues/4) — data-accumulation tracker (always-on; do not close)
- [#6](https://github.com/VijitSingh97/quant/issues/6) — historical-skew condor backtest: the tool (`basis.backtests.histskew`) is **built and tested**; it degrades gracefully until the logger has a few months of skew history, then prints logged-skew vs static-skew side by side.

Researched / scoped (multi-exchange — after single-venue HL is proven live):
- [#19](https://github.com/VijitSingh97/quant/issues/19) — **cross-venue perp-vs-perp funding arbitrage** (delta-neutral across two venues, no spot leg). Discovery side is live in `carryscan`; execution/validation scoped.
- [#20](https://github.com/VijitSingh97/quant/issues/20) — **Hummingbot connectors as an optional execution backend** (keep our brain, borrow tested multi-venue hands) — evaluated vs CCXT / per-SDK.

Recently completed (both closed):
- [#18](https://github.com/VijitSingh97/quant/issues/18) — **guarded parameter tuner** ✅ done. Walk-forward out-of-sample scoring in the self-validation (suggestions only fire if they beat current OOS) **and** the bounded, audited, reversible `basis-tune` apply path. Suggests-only; you approve.
- [#17](https://github.com/VijitSingh97/quant/issues/17) — **regime-based strategy switch** ✅ researched & closed. The `basis.backtests.regime` study found regime-conditioning does **not** beat always-carry on risk-adjusted return (carry's the workhorse; the condor is a marginal hedge), so the heavy live-options-execution layer is **deferred** — revisit when `#4` has accumulated more history.
