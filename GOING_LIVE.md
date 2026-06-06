# Going Live — a careful, staged guide

This is the checklist for moving **basis** from paper to real money on Hyperliquid. Read
all of it before you flip anything. The whole design assumes you go **slowly** and prove
each step.

> **Boundary (important).** This software *computes and submits* orders when **you** arm
> it; it never withdraws funds and never decides to go live on its own. The live order
> path is **structurally complete but UNTESTED against the live venue** (it can't be
> tested without placing real orders). So **you must verify your first live order by hand**
> (below). Treat the first live week as testing the *plumbing*, not making money.

---

## What's wired (and what isn't)

| Piece | State |
|---|---|
| Decision logic, risk gate, kill switch, reconcile, audit store | ✅ wired + tested |
| Read-only live account (positions/equity by address) | ✅ wired + tested |
| Paper execution (sim fills, net of fees) | ✅ wired + tested |
| **Live order signing/submission** (Hyperliquid SDK) | ⚠️ wired, **gated**, **not tested against the venue** |

Two independent gates must BOTH be on to place a real order — `BASIS_MODE=live` **and**
`BASIS_LIVE_ARM=1` — plus the kill switch must be off and every order still passes the
USD risk gate. You can't trade by accident.

---

## Prerequisites

1. **Hyperliquid account**, funded with the capital you intend to use (start tiny).
2. **An agent / API wallet that CANNOT withdraw.** On Hyperliquid, create an *API wallet*
   (agent) — it can trade but not move funds out. Never use your main wallet's seed.
3. **The signer dependencies** (the only third-party deps in the whole project; live-only):
   ```bash
   pip install -e ".[live]"      # eth-account + hyperliquid-python-sdk
   ```
   (In Docker, add these to the image or a `live` build — they are not in the default
   image, which stays stdlib-only.)
4. **Env** (put in `.env`, which is gitignored):
   ```bash
   BASIS_HL_ADDRESS=0xYourMainAccountAddress      # the account being traded (public)
   BASIS_HL_API_SECRET=0xYourAgentWalletKey       # withdraw-disabled agent key
   BASIS_MAX_ORDER_USD=50                          # TINY for the first live run
   BASIS_MAX_NOTIONAL_USD=300                      # cap total exposure small at first
   BASIS_MAX_LEVERAGE=1.5
   # leave BASIS_MODE=paper and DO NOT set BASIS_LIVE_ARM yet
   ```

---

## Step 1 — Preflight (places no orders)

```bash
basis-preflight        # or: python -m basis.live.preflight
```
Fix everything until it prints **GO**. It checks: signer deps, the agent key (valid +
derives an address), the account address, venue connectivity, the read-only account is
readable and funded, risk caps are sane, the kill switch is off, and whether you're armed.

## Step 2 — Read-only live, alongside paper (no money at risk)

With `BASIS_HL_ADDRESS` set, the monitor/dashboard show your **real** account read-only.
Confirm the engine's view of your positions/equity matches the Hyperliquid UI exactly.

```bash
make live-monitor      # your real account appears next to the paper book
```

## Step 2.5 — Testnet: a real API that tracks balances (no real money) ★ recommended

Before risking a cent, run the **whole thing against Hyperliquid testnet** — a real API
with a faucet that signs orders, fills them, and **tracks your balances/positions/funding
server-side**. This is the safe way to **(a) test the live signing path** and **(b)
reconcile the exchange's numbers against ours**.

```bash
# 1. create a testnet account + agent key at https://app.hyperliquid-testnet.xyz, fund via the faucet
# 2. point EVERYTHING at testnet and arm:
BASIS_HL_TESTNET=1 BASIS_MODE=live BASIS_LIVE_ARM=1 \
  BASIS_HL_ADDRESS=0xYourTestnetAddr BASIS_HL_API_SECRET=0xTestnetAgentKey \
  BASIS_MAX_ORDER_USD=50 python -m basis.live.engine        # one cycle
# 3. check it in the testnet UI; then run it scheduled for a few days.
```
`BASIS_HL_TESTNET=1` routes market data, account state, **and** the signer to
`hyperliquid-testnet.xyz` so the run is self-consistent. Caveat: testnet **funding and
liquidity ≠ mainnet**, so the *economics* won't match real carry — but the **accounting
does**, which is the point: do orders sign + fill, are balances/positions/funding tracked,
and does our `basis-report` (reading the testnet account) line up with the testnet UI.

**Reconciling their numbers vs ours:** run a paper book and a testnet book over the same
period, then `make report-auto` / `basis-report` on each — the equity, fills, and funding
should agree (within testnet's different funding). Discrepancies = an accounting bug to fix
*before* mainnet.

## Step 3 — Verify ONE live order by hand (the critical step)

Because the submission path is untested against the *mainnet* venue, prove it with a single tiny
order before you trust the loop:

```bash
# arm + live, run ONE reconcile cycle, then immediately check the HL UI:
BASIS_MODE=live BASIS_LIVE_ARM=1 BASIS_MAX_ORDER_USD=20 python -m basis.live.engine
```
Then in the Hyperliquid UI confirm: the order(s) appeared, the **size and side were
correct**, it filled near mark, and (for the carry) the spot and perp legs are roughly
equal and opposite. If anything looks wrong — wrong size, wrong asset, rejected for
tick/lot rounding, or the spot leg named wrong — **stop and fix** before continuing.
(Tick/lot rounding and the spot-pair name are the most likely first-order issues.)

## Step 4 — Tiny live, scheduled (validate the plumbing)

Once a manual order verified cleanly, let it run small and watch it for a couple of weeks:

```bash
# in .env:  BASIS_MODE=live  BASIS_LIVE_ARM=1  BASIS_MAX_ORDER_USD=50  BASIS_MAX_NOTIONAL_USD=300
docker compose up -d        # (with the [live] deps in the image)
```
Watch daily: net delta stays ~0, funding is actually being credited, the engine's equity
tracks the HL UI, reconcile converges, no repeated order rejections.

## Step 5 — Scale gradually

Only after the tiny-live period **executed cleanly AND realized funding ≈ what paper
predicted** (net of fees), raise `BASIS_MAX_NOTIONAL_USD` / `BASIS_MAX_ORDER_USD` in
steps. Never jump from tiny to full size.

---

## How long before you should trust it?

Short answer: **plan ~3 months before any meaningful live size**, and gate "confident to
scale" on *events survived*, not a calendar date. Why:

- **Funding cycles, so you must see more than one regime.** A few good weeks of positive
  funding prove nothing about a negative-funding or risk-off stretch. You want to have
  watched the strategy **deploy in good funding, sit out (go to cash) in negative funding,
  and survive at least one vol spike** — that typically spans a **full quarter**.
- **Paper validates the *logic*; tiny-live validates the *execution*.** They answer
  different questions, so do both:
  - **Paper: ~6–8 weeks minimum.** Long enough for the weekly self-validation to stop
    saying *"history too short for out-of-sample"* and render a walk-forward verdict, and
    to see ≥1 funding flip handled. Confirm carry is positive **net of fees** over the run.
  - **Tiny live: ~2–4 weeks.** Purely to prove fills happen, funding is credited, and the
    engine's book matches the venue. Profit is not the goal here.
- **Rotations are rare** (~1 per ~2 months in backtest), so seeing the auto-rotation
  actually fire live also argues for a couple of months.

**Validating your *own* results** (not vendor backtests) needs three things to line up —
treat scaling as blocked until all three are true:
1. The **self-validation has an out-of-sample verdict** (≈2–3 months of the weekly cycle).
2. You've **observed and survived one adverse regime** (negative funding and/or a vol spike).
3. Over the tiny-live window, **live realized funding ≈ paper-predicted funding** within
   fees+slippage. If live materially underperforms paper, your cost model is wrong — fix
   it (raise `BASIS_TAKER_FEE_BPS`/`SLIPPAGE_BPS` to reality) before scaling.

A caution on the numbers: the backtest Sharpe looks very high because funding has low
day-to-day variance — it **excludes the tail** (liquidation / exchange failure). So weight
*calendar time + adverse-event survival* more than the headline APR/Sharpe. Steady and
small beats fast.

---

## Abort / monitor

```bash
docker compose exec basis touch /app/data/KILL_SWITCH    # halt ALL trading instantly
docker compose logs -f basis                              # watch
basis-preflight                                           # re-check readiness any time
```
To stand down from live entirely: set `BASIS_LIVE_ARM=0` (or `BASIS_MODE=paper`) and
restart. Your audit trail and books persist.

*Educational tooling, not investment advice. You own every decision and every order.*
