# basis — User Guide

A practical guide to running **basis** to earn steady, market-neutral income from crypto
funding — and to tuning it for better risk-adjusted returns. New here? Read this top to
bottom once; it takes ~10 minutes.

> **What this is.** basis runs the **delta-neutral funding carry**: it holds an asset's
> spot *and* shorts an equal-sized perpetual, so it has **no price exposure** but collects
> the perp **funding** every hour. It auto-rotates to whichever liquid asset pays the best
> *persistent* funding, sits in cash when funding turns negative, and reports everything
> **net of fees**.
>
> **What it is NOT.** Not a directional bot, not a get-rich scheme, not advice. The income
> is a steady yield (think mid-teens % APR in good funding regimes, less otherwise), and
> the real risk is tail/exchange events, not day-to-day price moves.

---

## 0. Safety first (read this)

- **Paper by default.** Out of the box it simulates fills with live prices — **no API
  keys, no real money.** You opt into live deliberately, later.
- **It never withdraws.** When you do go live, you use a trade-enabled, **withdraw-disabled**
  key. The software cannot move your money out.
- **Kill switch.** One command halts all trading instantly (below).
- **You hold the keys and the decisions.** It *suggests* tuning changes; it never changes
  its own risk settings on live capital.

---

## 1. Quick start (Docker — recommended)

On any always-on machine (home server, mini-PC, cloud box) with Docker:

```bash
git clone https://github.com/VijitSingh97/quant.git && cd quant
cp .env.example .env        # optional — defaults are sensible (paper, 0.1 BTC, hourly)
docker compose up -d --build
```

Open the dashboard: **http://<server-ip>:8787**

That's it. The scheduler now runs hourly: it logs metrics, runs the carry on a fixed BTC
book *and* an auto-rotating book, and self-validates weekly. Everything persists in a
Docker volume and restarts on reboot/power loss.

```bash
docker compose logs -f basis     # watch it work
docker compose down              # stop (data is kept)
git pull && docker compose up -d --build   # update to a new version
```

**Prefer no Docker?** `pip install -e .` then use the `make` targets (`make live-web`,
`make live-auto`, …). See README_live.md.

---

## 2. Reading the dashboard

| Panel | What it tells you |
|---|---|
| **Position banner** | What you're in *right now*: the pair, DEPLOYED/FLAT/HALTED, the legs, **leverage**, net delta (green = neutral ✓). |
| **Net delta / Equity / Funding earned / Funding rate** | Delta should sit ~0. Equity is **net of fees**. Funding rate shows carry ON/OFF. |
| **Carry book — target vs actual** | The legs the engine wants vs holds, plus cash and **fees paid**. |
| **Carry opportunities** | All perps ranked by **persistent (14-day) funding**, with the deployed one highlighted and a plain-English line on what's being traded vs the best available. |
| **Self-validation** | The weekly check on whether your settings are still near-best (see §4). |
| **Audit trail** | Every signal, order intent, block, and fill — the full record. |

---

## 3. How it decides what to trade (the short version)

Each hour: **scan** all liquid perps → rank by *persistent* funding → **filter** (min
funding, liquidity floor, must have a co-located spot leg) → **hysteresis** (only switch
if a new asset beats the held one by a margin) → **funding-timing** (go to cash if funding
≤ 0) → **risk-gated reconcile**. Full explanation with the flow diagram and parameter
table is in [README_live.md → "How the engine decides"](README_live.md#how-the-engine-decides-what-to-trade).

The default deployable set is **BTC, ETH, SOL, HYPE** (they have both spot and perp on
Hyperliquid). Hotter-but-unshortable markets (e.g. XMR) are shown as *advisory* only.

---

## 4. Optimizing your returns

There are four levers, in order of impact and safety:

### a) Let it rotate (highest impact, zero effort)
The **auto book** already picks the best spot-able persistent carry and rotates with
hysteresis. Backtested, rotation beat a fixed BTC carry by **~+4% APR net of fees**. Just
watch the auto book — `BASIS_DB=live_auto.db` is what the dashboard shows by default.

### b) Tune the obvious knobs in `.env` (medium impact)
Edit `.env`, then `docker compose up -d` to apply:

| Knob | Default | Effect on returns |
|---|---|---|
| `BASIS_DEPLOY_FRACTION` | 0.85 | How much capital works. Higher = more carry **and** more leverage/risk. |
| `BASIS_AUTO_SPOT_UNIVERSE` | BTC,ETH,SOL,HYPE | Add assets you can source spot for (`=ANY` to allow all — only if you understand the spot-leg sourcing). |
| `BASIS_AUTO_MIN_FUNDING` | 0.05 | Floor APR to deploy. Lower = deploys more often (less idle cash, more cost). |
| `BASIS_AUTO_SWITCH_MARGIN` | 0.05 | Hysteresis. Lower = chases edges more (more switching cost); higher = stickier. |
| `BASIS_TAKER_FEE_BPS` / `BASIS_SLIPPAGE_BPS` | 4.5 / 5.0 | Your real cost assumption — set to your venue's actual fee tier so profitability is honest. |

### c) Use the self-validation → tune workflow (the smart way)
The system continuously checks whether your `switch_margin` / `min_funding` are still
best — **out-of-sample** (walk-forward), so it won't chase overfit noise.

```bash
make validate                 # run the check now (or it runs weekly on its own)
basis-tune --list             # see suggestions + report ids + current overrides
basis-tune --apply <id>       # apply a recommendation (only ones that beat current OOS)
docker compose restart basis  # take effect
basis-tune --rollback         # undo if you change your mind
```

`basis-tune` is **bounded, audited, and reversible**, and it **only suggests** — you
approve every change by running the command. If a suggestion looks great in-sample but
didn't hold up out-of-sample, the tool tells you to keep current.

### d) Know what doesn't help (so you don't over-engineer)
We backtested adding a **defined-risk volatility overlay** (selling option condors by
regime). Result: it raised total return but **worsened** risk-adjusted return — carry
alone had the best Sharpe. So basis stays carry-only on purpose. Re-check yourself:
`make regime`.

**Rule of thumb:** more deploy fraction and lower thresholds = more return *and* more
risk/cost. Optimize for **Sharpe and drawdown**, not just APR. Let the validator keep you
honest.

### e) Re-evaluating after a few months (the review)
Let the whole thing run on paper for **2–3 months**, then review how it actually did:

```bash
make report-auto      # period P&L of the auto book: total return (net of fees), APR,
                      # Sharpe, max drawdown, funding earned, fees, deployment %, rotations
```
The dashboard's **"Performance — since inception"** panel shows the same live. Equity is
**delta-neutral** (a hedged book's equity moves with funding and fees, *not* with price),
so what you're reading is the carry itself. Re-evaluate on **Sharpe + drawdown + whether
it survived an adverse funding regime**, not the headline APR (see GOING_LIVE.md timing).

---

## 5. Monitoring, kill switch, and exports

```bash
# halt everything instantly (paper or live):
docker compose exec basis touch /app/data/KILL_SWITCH
docker compose exec basis rm    /app/data/KILL_SWITCH      # resume

# read-only view of your REAL Hyperliquid account alongside the paper book:
#   set BASIS_HL_ADDRESS=0xYourPublicAddress in .env (public address, no secret)
```

**Export your data** (all in SQLite; download from the dashboard footer or):
```
http://<server>:8787/export/metrics.csv     # the logged timeseries
http://<server>:8787/export/reports.csv     # self-validation history
```

---

## 6. Going from paper to real money

Move one phase at a time; don't skip.

| Phase | What | Your money |
|---|---|---|
| **0. Paper** | the default — prove it runs and you trust the numbers | none |
| **1. Read-only live** | set `BASIS_HL_ADDRESS` to watch your real account | none |
| **2. Paper, scheduled** | already running in Docker — let it accrue for weeks | none |
| **3. Live, tiny** | `BASIS_MODE=live` + a trade-only (withdraw-disabled) Hyperliquid agent key, a *fraction* of your capital | a little |
| **4. Scale** | raise caps only as it proves out | grows slowly |

Live order signing is wired but **two-gated** (`BASIS_MODE=live` + `BASIS_LIVE_ARM=1`) and
untested against the venue, so the first live order must be checked by hand. The full
step-by-step — preflight, the agent key, the tiny-first rollout, and **how long to
validate before you trust it** — is in **[GOING_LIVE.md](GOING_LIVE.md)**. Run
`basis-preflight` for a go/no-go check anytime. Risk limits (`BASIS_MAX_NOTIONAL_USD`,
`MAX_LEVERAGE`, `MAX_ORDER_USD`, net-delta band) are hard ceilings enforced before every order.

---

## 7. The honest risks

- **Funding can go negative or thin out.** Funding-timing parks you in cash, so you earn
  less in bad regimes — that's expected, not a bug.
- **The tail is the real risk.** Exchange insolvency, a liquidation cascade, or losing
  your spot venue while short the perp. Keep leverage low, stay delta-neutral, use a
  withdraw-disabled key, and size so a venue blow-up is survivable.
- **Backtest Sharpes look high** because funding has low variance — they exclude the tail.
  Trust the *direction* of the findings, not the decimal.
- **This is educational tooling, not investment advice.** You own the decisions.

---

*Questions the docs answer next:* [README.md](README.md) (the research toolkit + all
commands), [README_live.md](README_live.md) (execution layer, decision logic, deploy,
risk limits). Roadmap and design discussions live in the GitHub issues.
