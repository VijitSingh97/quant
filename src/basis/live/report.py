"""basis-report — period performance review of a paper (or live) book.

This is the tool to run after the strategy has accrued for a while (e.g. a 2–3 month
paper run) to decide whether it's working. It reads the book's pnl history + positions +
audit trail and reports the realized return NET OF FEES, APR, Sharpe, max drawdown,
funding earned, fees paid, deployment %, and rotation count over the whole period.

  basis-report                         # the default book (data/live.db)
  BASIS_DB=live_auto.db basis-report   # the auto-rotating book (usually the interesting one)
"""

import argparse
import time

from . import config
from .store import Store
from ..core import fmt_pct, max_drawdown, sharpe


def compute(store):
    """Pure-ish (DB read only): period performance of a book. No network."""
    hist = store.pnl_history(1_000_000)
    pos = store.positions()
    if len(hist) < 2:
        return {"ok": False, "error": "not enough history yet (let it run longer)"}

    eq = [h["equity_usd"] for h in hist]
    t0, t1 = hist[0]["ts"], hist[-1]["ts"]
    days = max((t1 - t0) / 86400.0, 1e-9)
    start, cur = eq[0], eq[-1]
    total = (cur / start - 1) if start else 0.0
    apr = ((cur / start) ** (365.0 / days) - 1) if (start > 0 and days > 0) else 0.0

    # daily-bucketed equity -> daily returns -> annualized Sharpe
    byday = {}
    for h in hist:
        byday[int(h["ts"] // 86400)] = h["equity_usd"]      # last equity each day
    de = [byday[d] for d in sorted(byday)]
    daily = [de[i] / de[i - 1] - 1 for i in range(1, len(de)) if de[i - 1]]
    shp = sharpe(daily, 365)

    funding = pos.get("funding_usd", {}).get("qty", 0.0)
    fees = pos.get("fees_usd", {}).get("qty", 0.0)
    rotations = sum(1 for e in store.recent_events(1_000_000) if e["kind"] == "rotate_in")
    noted = [h for h in hist if h.get("note")]
    deployed = (sum(1 for h in noted if "cash" not in (h["note"] or "")) / len(noted)) if noted else None

    return {
        "ok": True, "started": t0, "as_of": t1, "period_days": days, "cycles": len(hist),
        "start_equity": start, "current_equity": cur, "total_return": total, "apr": apr,
        "sharpe": shp, "max_drawdown": max_drawdown(eq),
        "funding_earned": funding, "fees_paid": fees, "rotations": rotations,
        "deployed_frac": deployed, "net_delta": hist[-1]["net_delta_btc"],
        "last_note": hist[-1].get("note"),
    }


def _verdict(r):
    if r["apr"] <= 0:
        return "FLAT/NEGATIVE so far — too early, or funding regime has been poor. Keep accruing."
    if r["period_days"] < 30:
        return "POSITIVE but < 1 month — not yet a meaningful sample. Keep running."
    if r["sharpe"] and r["sharpe"] > 1.5:
        return "Positive with a healthy Sharpe over a real window — tracking as designed (paper)."
    return "Positive but watch the Sharpe/drawdown; let it run through more regimes."


def main():
    ap = argparse.ArgumentParser(description="Period performance review of a book (paper or live)")
    ap.add_argument("--db", default=None, help="db filename under data/ (else BASIS_DB / default)")
    a = ap.parse_args()
    path = (config.DATA_DIR / a.db) if a.db else config.DB_PATH
    store = Store(path)
    try:
        r = compute(store)
    finally:
        store.close()
    bar = "=" * 60
    print(f"\n{bar}\nPERFORMANCE — {path.name} ({config.MODE})\n{bar}")
    if not r["ok"]:
        print(f"  {r['error']}")
        return
    started = time.strftime("%Y-%m-%d", time.gmtime(r["started"]))
    print(f"  period        {started} → now   ({r['period_days']:.1f} days, {r['cycles']} cycles)")
    print(f"  equity        ${r['start_equity']:,.2f} → ${r['current_equity']:,.2f}")
    print(f"  total return  {fmt_pct(r['total_return'])}   (net of fees)")
    print(f"  APR           {fmt_pct(r['apr'])}   (annualized from the period)")
    shp = f"{r['sharpe']:.2f}" if r["sharpe"] is not None else "n/a"
    print(f"  Sharpe        {shp}        max drawdown {fmt_pct(r['max_drawdown'])}")
    print(f"  funding       +${r['funding_earned']:,.2f} earned     fees −${abs(r['fees_paid']):,.2f} paid")
    if r["deployed_frac"] is not None:
        print(f"  deployed      {r['deployed_frac']*100:.0f}% of the time     rotations {r['rotations']}")
    print(f"  now           net delta {r['net_delta']:+.4f}   {r['last_note'] or ''}")
    print(f"\n  {_verdict(r)}")
    print(bar)


if __name__ == "__main__":
    main()
