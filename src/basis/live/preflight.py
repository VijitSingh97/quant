"""basis-preflight — go/no-go readiness check for LIVE trading. Places NO orders.

Verifies everything that can be verified without trading: config + risk caps, the signer
deps, the agent key, connectivity, the read-only account, balance, kill switch, and the
arm flag. Prints each check PASS / WARN / FAIL and an overall verdict.

  GO     = no FAILs (safe to proceed to the staged go-live in GOING_LIVE.md)
  NO-GO  = at least one FAIL (fix it first)

Run:  python3 -m basis.live.preflight   (or  basis-preflight)
"""

from . import config

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def _r(name, level, detail):
    return {"name": name, "level": level, "detail": detail}


def check_caps(max_order, max_notional, max_lev, deploy, first_order_warn=500.0):
    """Pure: risk-limit sanity (no network)."""
    out = []
    out.append(_r("max order > 0", PASS if max_order > 0 else FAIL, f"${max_order:,.0f}"))
    out.append(_r("max notional > 0", PASS if max_notional > 0 else FAIL, f"${max_notional:,.0f}"))
    out.append(_r("leverage sane", PASS if 1 <= max_lev <= 5 else WARN,
                  f"{max_lev}x" + ("" if 1 <= max_lev <= 5 else " (high — keep low live)")))
    out.append(_r("deploy fraction < 1", PASS if deploy < 1.0 else FAIL, f"{deploy:.0%}"))
    out.append(_r("first-order size is tiny", PASS if max_order <= first_order_warn else WARN,
                  f"${max_order:,.0f}" + ("" if max_order <= first_order_warn else
                  f" — set BASIS_MAX_ORDER_USD small (≤${first_order_warn:,.0f}) for the first live run")))
    return out


def check_deps():
    try:
        import eth_account  # noqa: F401
        from hyperliquid.exchange import Exchange  # noqa: F401
        return _r("signer deps installed", PASS, 'eth-account + hyperliquid-python-sdk')
    except ImportError:
        return _r("signer deps installed", FAIL, 'missing — run: pip install -e ".[live]"')


def check_key():
    if not config.HL_API_SECRET:
        return _r("agent key present", FAIL, "set BASIS_HL_API_SECRET (withdraw-disabled agent key)")
    try:
        from eth_account import Account
        addr = Account.from_key(config.HL_API_SECRET).address
        return _r("agent key valid", PASS, f"agent {addr[:10]}…")
    except ImportError:
        return _r("agent key valid", WARN, "can't verify without [live] deps")
    except Exception as e:  # noqa: BLE001
        return _r("agent key valid", FAIL, f"invalid key: {str(e)[:50]}")


def verdict(results):
    fails = [r for r in results if r["level"] == FAIL]
    return ("NO-GO", fails) if fails else ("GO", [])


def _gather():
    results = []
    # mode / arm
    results.append(_r("mode = live", PASS if config.LIVE else WARN,
                     config.MODE + ("" if config.LIVE else " (set BASIS_MODE=live when ready)")))
    results.append(_r("armed", WARN if config.LIVE_ARM else PASS,
                     "ARMED — real orders WILL be sent" if config.LIVE_ARM
                     else "not armed (safe) — set BASIS_LIVE_ARM=1 to actually trade"))
    results.append(_r("kill switch off", FAIL if config.KILL_FILE.exists() else PASS,
                     "ACTIVE — remove data/KILL_SWITCH" if config.KILL_FILE.exists() else "off"))
    results.append(_r("network", PASS,
                     "TESTNET (faucet funds, no real money)" if config.HL_TESTNET else "MAINNET (real money)"))
    # deps + key + account address
    results.append(check_deps())
    results.append(check_key())
    results.append(_r("account address set", PASS if config.HL_ADDRESS else FAIL,
                     (config.HL_ADDRESS[:10] + "…") if config.HL_ADDRESS else "set BASIS_HL_ADDRESS"))
    # connectivity + read-only account
    try:
        from ..core.sources import hyperliquid_perp
        mark = hyperliquid_perp(config.SYMBOL)["mark"]
        results.append(_r("venue reachable", PASS if mark > 0 else FAIL, f"{config.SYMBOL} ${mark:,.0f}"))
    except Exception as e:  # noqa: BLE001
        results.append(_r("venue reachable", FAIL, str(e)[:60]))
    if config.HL_ADDRESS:
        try:
            from .exchanges.hyperliquid import HyperliquidClient
            eq = HyperliquidClient().equity_usd()
            results.append(_r("account readable", PASS, f"equity ${eq:,.2f}"))
            results.append(_r("funded", PASS if eq > config.MIN_ORDER_USD else WARN,
                             f"${eq:,.2f}" + ("" if eq > config.MIN_ORDER_USD else " — deposit before trading")))
        except Exception as e:  # noqa: BLE001
            results.append(_r("account readable", FAIL, str(e)[:60]))
    # risk caps
    results += check_caps(config.MAX_ORDER_USD, config.MAX_NOTIONAL_USD,
                          config.MAX_LEVERAGE, config.DEPLOY_FRACTION)
    return results


def main():
    print("\n" + "=" * 60 + "\nbasis-preflight — LIVE readiness (places NO orders)\n" + "=" * 60)
    results = _gather()
    for r in results:
        mark = {"PASS": "✓", "WARN": "!", "FAIL": "✗"}[r["level"]]
        print(f"  [{mark}] {r['name']:24} {r['detail']}")
    v, fails = verdict(results)
    print("=" * 60)
    if v == "GO":
        armed = config.LIVE_ARM
        print("  VERDICT: GO" + ("  — ARMED: live orders WILL be sent on the next cycle."
              if armed else "  — not armed (safe). Set BASIS_LIVE_ARM=1 to actually trade."))
        print("  Next: follow GOING_LIVE.md (start tiny, verify the first order in the HL UI).")
    else:
        print(f"  VERDICT: NO-GO — fix {len(fails)} item(s): " + ", ".join(f["name"] for f in fails))
    print("=" * 60)
    return 0 if v == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
