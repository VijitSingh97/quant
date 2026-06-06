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

## Web dashboard (`make live-web` → http://localhost:8787)

A dependency-free single-page dashboard (stdlib `http.server`). Up top, a **position
banner** states plainly what we're in right now — the **pair** (`BTC-SPOT / BTC-PERP`),
the **state** (DEPLOYED / FLAT / HALTED), the **legs**, the **leverage** and gross
notional, and net delta — colour-coded (green deployed-neutral, amber flat, red halted).
Below it: mode/venue badge, net-delta indicator, equity, funding earned, live funding
rate (carry ON/OFF), target-vs-actual book, an equity sparkline, the cross-asset
carry-opportunities panel, the read-only live account (if configured), and the live
**audit trail** — auto-refreshing every 5s. The CLI (`make live-monitor`) shows the
same POSITION block in text.

## Scheduled paper trading (Phase 2 — done)

```bash
./scripts/install_live_paper.sh     # launchd agent: hourly paper reconcile (no real money)
./scripts/uninstall_live_paper.sh   # remove it
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
make live-auto                          # paper; own book data/live_auto.db
BASIS_DB=live_auto.db make live-web    # view the auto book in the dashboard
```
The auto allocator (`basis.live.auto` → `selector.py`) ranks markets by **persistent**
(14d-avg) funding, requires a **liquidity floor** and a **spot-able universe**
(`BASIS_AUTO_SPOT_UNIVERSE`, default BTC/ETH/SOL/HYPE — `=ANY` to allow alts you can
source spot for), and applies **hysteresis** (`BASIS_AUTO_SWITCH_MARGIN`, default 5%):
it only rotates off the held asset when a candidate beats it by the margin, or the held
asset stops qualifying — so it doesn't churn on hourly funding noise. Every rotation and
order is risk-gated and audited. Example: it deploys **HYPE** (~+14% persistent, has HL
spot) and reports that XMR (~+32%) is hotter but excluded for lack of co-located spot.

The funding-timed allocator stays flat (cash) on any asset whose funding is negative,
so pointing it at a negative-funding asset correctly does nothing. Notes: you need a
**spot leg** to be delta-neutral — trivial for BTC/ETH/SOL/HYPE (spot + perp on HL),
needs cross-venue spot for other alts; and very high funding is usually thin/transient,
not a gift. Auto-rotation to the best asset is a deliberate *future* step (with a
liquidity floor + hysteresis so it doesn't churn on noise) — not on by default.

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
monitor.py · web.py · dashboard.html   CLI + web tracker
exchanges/
  base.py        ExchangeClient interface + Order
  paper.py       simulates fills at the live mark (default)
  hyperliquid.py read-only first (public data + account-by-address); live orders gated
```

**Safety invariants:** paper unless `BASIS_MODE=live`; every order passes `risk.py`
(max notional / leverage / order size / net-delta band); a `data/KILL_SWITCH` file
halts all trading instantly; every signal, intent, block, and fill is logged
append-only to `data/live.db`.

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
| **3. Live, tiny** | `BASIS_MODE=live` + agent key | HL **agent wallet** (cannot withdraw) | a fraction of 0.1 BTC | ⏳ needs your key |
| **4. Scaled** | same, caps raised | — | scales as it proves out | — |

**Funding:** you deposit USDC/BTC into your own Hyperliquid account; the system
trades within it and has no withdrawal rights. Live order signing (Phase 3) is
deliberately not wired yet — `hyperliquid.place_order` raises until it is.

*(Educational tooling, not investment advice. Crypto leverage and exchange failure
are the real risks — the kill switch and trade-not-withdraw keys are there for a reason.)*
