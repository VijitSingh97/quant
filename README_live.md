# btcvol.live — execution layer (paper-first)

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
make live-monitor    # book status (positions, net delta, equity, funding) + audit trail
```

Run `live-paper` repeatedly (or on a schedule) — it converges to the delta-neutral
carry (long spot / short perp), stays funding-timed (flat when funding < 0), and
accrues simulated funding so you can watch the strategy earn.

## Architecture (`src/btcvol/live/`)

```
config.py        mode (PAPER default), venue, capital, hard risk limits — all via env
store.py         SQLite audit store: events · orders · fills · positions · pnl  (the audit trail)
risk.py          pre-trade gate every order must pass + the kill switch
allocator.py     delta-neutral carry target (funding-timed)
engine.py        reconcile target vs actual -> risk-gated orders -> (paper) fills -> audit
monitor.py       read-only book status + recent audit trail
exchanges/
  base.py        ExchangeClient interface + Order
  paper.py       simulates fills at the live mark (default)
  hyperliquid.py read-only first (public data + account-by-address); live orders gated
```

**Safety invariants:** paper unless `BTCVOL_MODE=live`; every order passes `risk.py`
(max notional / leverage / order size / net-delta band); a `data/KILL_SWITCH` file
halts all trading instantly; every signal, intent, block, and fill is logged
append-only to `data/live.db`.

## Risk limits (env-overridable)

| Limit | Default | Env |
|---|---|---|
| Max notional | $10,000 | `BTCVOL_MAX_NOTIONAL_USD` |
| Max leverage | 2.0× | `BTCVOL_MAX_LEVERAGE` |
| Max order | 0.05 BTC | `BTCVOL_MAX_ORDER_BTC` |
| Net-delta band | ±0.02 BTC | `BTCVOL_MAX_ABS_DELTA_BTC` |
| Capital / deploy | 0.1 BTC / 85% | `BTCVOL_CAPITAL_BTC`, `BTCVOL_DEPLOY_FRACTION` |
| Kill switch | `data/KILL_SWITCH` | — |

## The phased path to real money

| Phase | Command | Needs | Your money |
|---|---|---|---|
| **0. Paper** (here) | `make live-paper` | nothing | none |
| **1. Read-only live** | `BTCVOL_HL_ADDRESS=0x… make live-monitor` | HL wallet *address* (no secret) | none |
| **2. Paper, scheduled** | launchd/cron `live-paper` hourly | nothing | none |
| **3. Live, tiny** | `BTCVOL_MODE=live` + agent key | HL **agent wallet** (cannot withdraw) | a fraction of 0.1 BTC |
| **4. Scaled** | same, caps raised | — | scales as it proves out |

**Funding:** you deposit USDC/BTC into your own Hyperliquid account; the system
trades within it and has no withdrawal rights. Live order signing (Phase 3) is
deliberately not wired yet — `hyperliquid.place_order` raises until it is.

*(Educational tooling, not investment advice. Crypto leverage and exchange failure
are the real risks — the kill switch and trade-not-withdraw keys are there for a reason.)*
