# basis.live — execution layer (paper-first)

The bridge from the research toolkit to real, automated, monitored trading of the
**delta-neutral funding carry** — built safety-first. It runs in **paper mode by
default**: it reads live Hyperliquid prices/funding, computes the carry target,
reconciles to orders, and simulates fills with a full audit trail — **no real money
and no API keys required** to start.

> **Boundary:** this software places orders only when *you* set it to live mode with
> trade-not-withdraw API keys. It can never withdraw funds. Paper mode never sends
> a real order. You hold the kill switch.

## Run it now (paper, zero risk)

```bash
make live-paper      # one reconcile cycle: read market -> target -> simulate fills -> audit
make live-auto       # auto-select the best persistent-carry asset and rotate (paper)
make live-monitor    # CLI status (positions, net delta, equity, funding) + audit trail
make live-web        # web dashboard -> http://localhost:8787
```

Each `make X` == `PYTHONPATH=src python3 -m basis.live.X` == the console script
`basis-live[-X]` after `pip install -e .` (e.g. `basis-live-auto`, `basis-live-web`).

Run `live-paper` repeatedly (or scheduled) — it converges to the delta-neutral carry
(long spot / short perp), stays funding-timed (flat when funding < 0), and accrues
simulated funding so you can watch the strategy earn.

## How the engine decides what to trade

**The edge.** A perpetual swap pays *funding* periodically between longs and shorts.
When funding is positive, longs pay shorts. So if you hold the asset's **spot** (long)
and **short an equal-sized perp**, you have **zero price exposure** (delta-neutral) but
you **receive funding every hour**. That funding stream is the income. The job of the
engine is to (a) find where that stream is richest *and durable*, (b) hold it neutral,
and (c) stop when it isn't worth it — all within hard risk caps.

Each cycle runs this pipeline:

```
              ┌─ 1. SCAN ─────────────────────────────────┐
  every       │ funding for every liquid perp, summarised  │
  cycle  ───▶ │ as PERSISTENT funding: 14d-avg APR + %hrs+ │   (a 1h spike isn't
  (hourly)    │ (carryscan / status.opportunities)         │    harvestable; a
              └───────────────────┬───────────────────────┘    structurally-hot
                                  ▼                              market is)
              ┌─ 2. FILTER (selector.select_asset) ───────┐
              │ keep candidates where:                     │
              │   avg APR ≥ min_funding   (5%)             │
              │   open interest ≥ liquidity floor ($20M)   │
              │   asset ∈ spot-able universe (BTC/ETH/     │
              │     SOL/HYPE) — need a co-located spot leg  │
              │ rank survivors by persistent APR           │
              └───────────────────┬───────────────────────┘
                                  ▼
              ┌─ 3. HYSTERESIS (don't churn) ─────────────┐
              │ no position  → deploy the best             │
              │ holding X    → rotate ONLY if a candidate  │
              │   beats X by switch_margin (5% APR), or X  │
              │   stops qualifying / drops below exit      │
              │ else         → hold X                      │
              └───────────────────┬───────────────────────┘
                                  ▼ chosen asset (or cash)
              ┌─ 4. FUNDING-TIMING (allocator.carry_target) ┐
              │ HYSTERESIS (anti-fee-churn):                 │
              │  flat     → deploy only if funding > +enter  │
              │  deployed → hold until funding < −exit       │
              │  (band in between = no-trade hold zone)      │
              │ deploy size = deploy_fraction (85%) of equity│
              └───────────────────┬───────────────────────┘
                                  ▼ target legs
              ┌─ 5. RECONCILE + RISK GATE (engine/auto) ──┐
              │ diff target vs current → orders, each      │
              │ CLAMPED to max_order ($3k) so it converges │
              │ over cycles; every order must pass         │
              │ risk.check_order (caps + kill switch);     │
              │ then fill (paper sim / live) → audit DB    │
              └────────────────────────────────────────────┘
```

**Why each step exists**
- **Persistence, not spot rate** — funding is noisy hour-to-hour. Ranking on a 14-day
  average (plus % of hours positive) finds markets that are *structurally* hard to short
  (so longs persistently overpay), not a one-hour blip you'd miss anyway.
- **Spot-able universe** — to be delta-neutral you must actually hold spot against the
  short perp. XMR can print +32% but there's no co-located spot to pair it with, so it's
  shown as *advisory* and never deployed. The default deployable set is BTC/ETH/SOL/HYPE
  (spot **and** perp on Hyperliquid); `BASIS_AUTO_SPOT_UNIVERSE=ANY` opts into others you
  can source spot for.
- **Hysteresis** — a small, persistent edge isn't worth paying 4 legs of fees to chase.
  Requiring a candidate to beat the held asset by a margin keeps turnover low (the
  backtest rotated 7× in 400 days). See `make rotation` for the evidence it pays.
- **Funding-timing (with hysteresis)** — the carry earns when funding is positive, but
  flattening costs a round-trip fee, so we use a deadband: **deploy only when funding
  clears `+FUNDING_ENTER_APR` (3%), flatten only when it drops below `−FUNDING_EXIT_APR`
  (−2%), hold in between**. This stops fee-churn near zero — flattening to dodge a brief,
  mildly-negative funding dip costs far more than the funding it saves (a flatten+redeploy
  is ~0.32% of equity; dodging −2% APR only pays off if it stays negative ~70 days).
- **Clamp + risk gate** — orders are capped per cycle (so a big rebalance walks in over a
  few cycles instead of one fat fill) and every single order is checked against the USD
  risk limits and the kill switch before it can touch the book.

**Two ways to run it**
| Mode | Command | Asset choice |
|---|---|---|
| **Fixed** | `make live-paper` (`BASIS_SYMBOL=ETH …`) | you pick; engine holds it, funding-timed |
| **Auto** | `make live-auto` | the selector picks + rotates with hysteresis |

**The parameters that drive the decision** (env-overridable, `BASIS_*`):

| Parameter | Env | Default | What it controls |
|---|---|---|---|
| Min funding | `BASIS_AUTO_MIN_FUNDING` | 0.05 | floor APR to deploy at all |
| Liquidity floor | `BASIS_AUTO_OI_FLOOR_USD` | 20,000,000 | skip thin markets |
| Spot universe | `BASIS_AUTO_SPOT_UNIVERSE` | BTC,ETH,SOL,HYPE | deployable set (`ANY` = all) |
| Switch margin | `BASIS_AUTO_SWITCH_MARGIN` | 0.05 | hysteresis: edge needed to rotate |
| Exit funding | `BASIS_AUTO_EXIT_FUNDING` | 0.0 | drop the held asset below this avg |
| Deploy fraction | `BASIS_DEPLOY_FRACTION` | 0.85 | how much equity to put to work |
| Funding-timed | `BASIS_FUNDING_TIMED` | 1 | hysteretic on/off (anti-churn) |
| Funding enter / exit | `BASIS_FUNDING_ENTER_APR` / `_EXIT_APR` | +3% / −2% | deploy / flatten thresholds (deadband stops fee-churn) |
| Funding enter / exit | `BASIS_FUNDING_ENTER_APR` / `_EXIT_APR` | +3% / −2% | deploy / flatten thresholds |

**Worked example (live, right now).** BTC perp funding is *negative* (≈ −2.5% APR), so a
fixed-BTC carry sits **FLAT** (funding-timed). The auto allocator scans, sees **HYPE** at
≈ +14% persistent (spot-able, ~$1.2B OI) as the best qualifying market, and deploys it
delta-neutral at 0.85× — while reporting that XMR (≈ +32%) is hotter but **excluded** for
lack of co-located spot. Hysteresis then *holds* HYPE until something beats it by 5% APR.

## Web dashboard (`make live-web` → http://localhost:8787)

A dependency-free single-page dashboard (stdlib `http.server`), organised top-to-bottom
from *your book* to generic *market/system* data, auto-refreshing every 5s:

- **Position banner** (top) — what we're in right now: the **pair**, **state** (DEPLOYED /
  FLAT / WINDING DOWN / HALTED), the **legs**, **leverage** + gross notional, net delta —
  colour-coded (green deployed-neutral, amber flat, red halted). A red **ARMED** badge
  shows in the header when live trading is armed.
- **Your book** — a 6-card stat row (equity net-of-fees, total return, APR, funding
  earned, fees paid, net delta), the **target-vs-actual carry book** (legs/cash/funding/
  fees), an **equity curve** (lo/hi/now), a **performance** table (return/APR/Sharpe/maxDD/
  period/deployment/rotations), and the read-only **live account** (if configured).
- **Strategy** — the **deployment** line (held asset, funding now vs 14d-avg, what's
  deployed vs the best available), the **self-validation** panel (current vs best-in-sweep
  + walk-forward verdict + suggestion, tuned-overrides note, CSV/JSON export), and the
  **audit trail**.
- **Market & system** — mark, funding rate, DVOL, cost/leg; the **carry-opportunities**
  table (all perps by persistent funding); and a **system & risk-limits** table.

Every section header and metric has a hoverable **?** with a plain-English explanation,
so the dashboard is self-documenting. The CLI (`make live-monitor`) shows the same
POSITION block in text; `make report` / `make report-auto` print the period scorecard.

## Deploy on a home server (Docker) — recommended

A self-contained stack for an always-on box. One `restart: unless-stopped` scheduler
runs the cycles hourly; a web service serves the dashboard; both share a named volume
so the SQLite books + CSV survive container recreation. Built to ride out the two
things that actually happen at home — **power loss** and **flaky network**.

```bash
git clone https://github.com/VijitSingh97/quant.git && cd quant
cp .env.example .env        # optional: tweak capital / interval / HL address
docker compose up -d --build
# dashboard: http://<server-ip>:8787   ·   logs: docker compose logs -f basis
```

Update / restart / stop:
```bash
git pull && docker compose up -d --build      # roll forward to a new version
docker compose restart basis                  # restart just the scheduler
docker compose down                           # stop (named volume basis-data is kept)
```

Kill switch (halts ALL trading instantly, paper or live):
```bash
docker compose exec basis touch  /app/data/KILL_SWITCH    # stop
docker compose exec basis rm     /app/data/KILL_SWITCH    # resume
```

**Resilience built in**
- **Power loss** → `restart: unless-stopped` brings both services back on boot; the
  scheduler just resumes its loop, and SQLite **WAL mode** (`synchronous=NORMAL`) means
  an abrupt kill mid-write doesn't corrupt the book.
- **Network blips** → every HTTP call retries with backoff (DNS hiccup / timeout / 429 /
  5xx); a cycle that still fails is logged and **skipped — the loop never dies**. A
  Docker `HEALTHCHECK` watches a heartbeat the scheduler writes each cycle.
- **Self-contained** → stdlib-only, so the image is just Python + the package (no DB
  server, no third-party deps). Runs as a non-root user. `BASIS_MODE=paper` by default;
  live order signing stays gated regardless.
- **Config** → all via `.env` (`BASIS_*`, legacy `BTCVOL_*` honoured). `BASIS_TASKS`
  selects which cycles run (`logger,paper,auto`); `BASIS_CYCLE_SECONDS` the interval;
  the data volume lives at `/app/data` (`BASIS_DATA_DIR`).

## Scheduled paper trading on macOS (launchd)

For a Mac you leave running (instead of Docker), the same cycles install as launchd
agents:
```bash
./scripts/install_live_paper.sh     # hourly fixed-asset paper reconcile (data/live.db)
./scripts/install_live_auto.sh      # hourly auto-rotating paper allocator (data/live_auto.db)
./scripts/uninstall_live_paper.sh   # remove
```

Runs the carry engine hourly like the data logger; accrues funding and builds the
audit trail in `data/live.db`. Logs to `data/paper.{out,err}.log`.

## Which asset to deploy (carry scanner + multi-asset engine)

Funding (the carry yield) varies hugely by asset — in a correction the majors' perps
can go *negative* (longs paid) while liquid alts sit at Hyperliquid's ~+11% baseline.
Find the best:

```bash
make carry-scan      # ranks all HL perps by funding APR (liquid only) + caveats
```

The monitor and web dashboard now show a live **carry-opportunities** panel — all perps
ranked by persistent (14d-avg) funding — and a **TRADING** line that states plainly what
the engine is actually deploying vs the best market (e.g. "deploys BTC at −5% now; best
persistent carry is XMR +32% — NOT traded, auto-rotate OFF"). The engine does **not**
auto-rotate yet; it deploys a fixed asset you choose:

Two ways to deploy:

**Fixed asset** — you choose, engine holds it (own book per asset; USD-based limits):
```bash
BASIS_SYMBOL=ETH make live-paper      # deploy the carry on ETH instead of BTC
```

**Auto-select (rotating carry)** — the engine picks the best asset from the scan itself:
```bash
make live-auto                          # one paper cycle; own book data/live_auto.db
BASIS_DB=live_auto.db make live-web      # view the auto book in the dashboard
make live-auto-install                   # run it hourly under launchd (paper)
make live-auto-uninstall                 # stop it
```
The auto allocator (`basis.live.auto` → `selector.py`) ranks markets by **persistent**
(14d-avg) funding, requires a **liquidity floor** and a **spot-able universe**
(`BASIS_AUTO_SPOT_UNIVERSE`, default BTC/ETH/SOL/HYPE — `=ANY` to allow alts you can
source spot for), and applies **hysteresis** (`BASIS_AUTO_SWITCH_MARGIN`, default 5%):
it only rotates off the held asset when a candidate beats it by the margin, or the held
asset stops qualifying — so it doesn't churn on hourly funding noise. Every rotation and
order is risk-gated and audited. Example: it deploys **HYPE** (~+14% persistent, has HL
spot) and reports that XMR (~+32%) is hotter but excluded for lack of co-located spot.

**Does rotating actually pay?** Backtested (`make rotation`, 400d HL funding for
BTC/ETH/SOL/HYPE, the real `select_asset` rule, **9.5 bps/leg = taker 4.5 + slippage 5**,
the same cost the live book pays): rotation returned **+11.6% APR net of cost vs a fixed
BTC carry's +7.8% (+3.8%)**, with only **7 switches in 400 days** (hysteresis ⇒ low churn)
and ~1.6% cost drag. It can't beat HYPE-with-hindsight (−2.2%), but that's the point — it
*robustly captures* the best carry without having to guess the ex-ante winner. (Caveat:
the high Sharpe reflects funding's low variance; the real risk is tail/liquidation/
exchange events, which the curve excludes.)

The funding-timed allocator stays flat (cash) on any asset whose funding is negative,
so pointing it at a negative-funding asset correctly does nothing. Notes: you need a
**spot leg** to be delta-neutral — trivial for BTC/ETH/SOL/HYPE (spot + perp on HL),
needs cross-venue spot for other alts; and very high funding is usually thin/transient,
not a gift.

## Scheduled self-validation (does the rule still hold?)

The engine doesn't blindly trust its own settings. A **weekly** self-validation cycle
re-runs the rotation backtest on the latest funding history for the *current* config,
then sweeps the two key knobs (`switch_margin`, `min_funding`) over a small grid and
records whether the live settings are still near-best — or whether something would have
done materially better.

```bash
make validate     # run one report now (-> research.db)   [basis-validate --force]
```

**Walk-forward guard against overfitting (issue #18, Phase A — done).** A bigger
in-sample number is usually just curve-fitting. So before suggesting any change, the
validator runs a **walk-forward** check: on each fold it picks the best params *in-sample*
on a train slice, then scores them *out-of-sample* on the next slice against the current
config. It only recommends a change if re-tuning beats current **out-of-sample** too;
otherwise it explicitly says *"in-sample sweep prefers X, but it does NOT generalise —
keep current."* The report carries both the in-sample sweep and the walk-forward verdict.

**Applying a suggestion — guarded (`basis-tune`, issue #18 Phase B — done).** It still
**never auto-applies**; you apply by hand, and the path is guarded:

```bash
make tune                       # or: basis-tune --list   — suggestions + report ids + current overrides
basis-tune --apply <report_id>  # apply a recommendation (bounded; only ones that beat current OOS)
docker compose restart basis    # take effect
basis-tune --rollback           # undo the last change   ·   basis-tune --reset  (back to defaults)
```

Every apply is **bounded** (out-of-range values rejected), **out-of-sample-gated** (refuses
a report that didn't beat current out-of-sample, unless `--force`), **audited** (logged to
`research.db` with from→to + the report id), and **reversible**. It writes
`data/overrides.json` (env vars still win over it); the dashboard shows when tuned
overrides are active. The scheduler never tunes — you are the approval.

(A regime-based carry-vs-vol
switch is [issue #17](https://github.com/VijitSingh97/quant/issues/17).)

In the container the `validate` task is in the scheduler's task list and **self-throttles**
to `BASIS_VALIDATE_INTERVAL_SECONDS` (default weekly), so it runs without a separate cron.
Each report shows on the dashboard (current vs best-in-sweep + a verdict) and is exportable.

## Data & export — everything in the database

All runtime data lives in **SQLite** (WAL-mode, on the Docker volume):

| DB | Contents |
|---|---|
| `data/live.db` | fixed-asset paper carry book (events · orders · fills · positions · pnl) |
| `data/live_auto.db` | auto-rotating book (same schema + held-asset meta) |
| `data/research.db` | `metrics` (the logged timeseries) + `reports` (self-validation) |

The metrics logger writes each row to `research.db` **and** keeps `timeseries.csv` (the
existing backtests still read the CSV). Everything is exportable from the dashboard or
directly:

```
GET /export/reports.csv   /export/reports.json     # self-validation history
GET /export/metrics.csv   /export/metrics.json     # the logged timeseries
GET /api/reports                                    # recent reports as JSON
```

## Read-only live account (Phase 1 — done)

Set your Hyperliquid wallet **address** (public, no secret) to see your real account
read-only in the monitor and the web dashboard:

```bash
export BASIS_HL_ADDRESS=0xYourHyperliquidAddress
make live-monitor      # now shows your real positions/equity alongside the paper book
```

## Architecture (`src/basis/live/`)

```
config.py        mode (PAPER default), venue, capital, hard risk limits — all via env
store.py         SQLite audit store: events · orders · fills · positions · pnl  (the audit trail)
risk.py          pre-trade gate every order must pass + the kill switch
allocator.py     delta-neutral carry target (funding-timed)
engine.py        reconcile target vs actual -> risk-gated orders -> (paper) fills -> audit
status.py        shared status assembler (one source of truth for CLI + web)
selector.py      auto asset-selection (persistent funding + hysteresis)
auto.py          auto-rotating allocator (own book)
validate.py      scheduled self-validation — re-check the rule weekly, suggest (never apply)
tune.py          guarded apply path for suggestions (bounded/audited/reversible)
preflight.py     live-readiness go/no-go check (places NO orders)
scheduler.py     supervisor loop (container): run cycles, isolate failures, heartbeat
healthcheck.py   container HEALTHCHECK — heartbeat freshness
monitor.py · web.py · dashboard.html   CLI + web tracker
exchanges/
  base.py        ExchangeClient interface + Order
  paper.py       simulates fills at the live mark (default)
  hyperliquid.py read-only first; live orders behind a two-gate (live + armed) signer
```

**Safety invariants:** paper unless `BASIS_MODE=live` **and** `BASIS_LIVE_ARM=1` (two
gates — you can't trade by accident); every order passes `risk.py` (max notional /
leverage / order size / net-delta band); a `data/KILL_SWITCH` file halts all trading
instantly; the agent key cannot withdraw; every signal, intent, block, and fill is logged
append-only. **Going live:** run `basis-preflight` then follow **[GOING_LIVE.md](GOING_LIVE.md)**.

## Risk limits (env-overridable)

Limits are **USD-denominated** so they're asset-agnostic (the engine rotates across
assets). Env vars are read as `BASIS_*` and fall back to the legacy `BTCVOL_*` names,
so an existing `.env` keeps working after the rename.

| Limit | Default | Env |
|---|---|---|
| Max notional | $10,000 | `BASIS_MAX_NOTIONAL_USD` |
| Max leverage | 2.0× | `BASIS_MAX_LEVERAGE` |
| Max order | $3,000 | `BASIS_MAX_ORDER_USD` |
| Min order | $10 | `BASIS_MIN_ORDER_USD` |
| Net-delta band | ±$1,200 | `BASIS_MAX_ABS_DELTA_USD` |
| Capital / deploy | 0.1 BTC / 85% | `BASIS_CAPITAL_BTC`, `BASIS_DEPLOY_FRACTION` |
| Kill switch | `data/KILL_SWITCH` | — |

## The phased path to real money

| Phase | Command | Needs | Your money | Status |
|---|---|---|---|---|
| **0. Paper** | `make live-paper` / `live-web` | nothing | none | ✅ done |
| **1. Read-only live** | `BASIS_HL_ADDRESS=0x… make live-monitor` | HL wallet *address* (no secret) | none | ✅ done |
| **2. Paper, scheduled** | `./scripts/install_live_paper.sh` | nothing | none | ✅ done |
| **3. Live, tiny** | `pip install -e ".[live]"`, `basis-preflight`, then `BASIS_MODE=live BASIS_LIVE_ARM=1` | HL **agent wallet** (cannot withdraw) + tiny deposit | a fraction of 0.1 BTC | 🔌 wired, gated — **needs your key + first-order check** |
| **4. Scaled** | same, caps raised | — | scales as it proves out | — |

**Testnet first (`BASIS_HL_TESTNET=1`):** routes the whole HL surface — market data,
account, and the order signer — to Hyperliquid testnet, a **real API with a faucet that
tracks balances server-side**. It's the safe way to exercise the live signing path and
reconcile the exchange's numbers against ours with **no real money** (testnet economics ≠
mainnet, but the accounting matches). See GOING_LIVE.md Step 2.5.

**Funding:** you deposit USDC/BTC into your own Hyperliquid account; the system
trades within it and has no withdrawal rights. Live order signing **is wired** (official
HL SDK, behind the live+armed two-gate) but is **untested against the venue** — so the
first live order must be verified by hand. The full staged procedure, the preflight, and
**how long to validate before trusting it** are in **[GOING_LIVE.md](GOING_LIVE.md)**.

*(Educational tooling, not investment advice. Crypto leverage and exchange failure
are the real risks — the kill switch and trade-not-withdraw keys are there for a reason.)*
