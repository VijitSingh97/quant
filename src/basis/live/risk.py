"""Pre-trade risk gate. EVERY order must pass check_order() before it can be sent.

Hard ceilings (config) + a kill switch: if the KILL_SWITCH file exists, nothing trades.
Returns (ok, reason); the engine logs both the pass and the block to the audit trail.
"""

from . import config


def kill_active():
    return config.KILL_FILE.exists()


def check_order(order, ctx):
    """ctx (all USD): order_notional_usd, notional_usd_after, leverage_after, net_delta_usd_after."""
    if kill_active():
        return False, "KILL_SWITCH active — trading halted"
    on = ctx.get("order_notional_usd", 0)
    if on < config.MIN_ORDER_USD:
        return False, f"order ${on:,.0f} < min ${config.MIN_ORDER_USD:,.0f}"
    if on > config.MAX_ORDER_USD:
        return False, f"order ${on:,.0f} > max ${config.MAX_ORDER_USD:,.0f}"
    if ctx.get("notional_usd_after", 0) > config.MAX_NOTIONAL_USD:
        return False, f"notional ${ctx['notional_usd_after']:,.0f} > cap ${config.MAX_NOTIONAL_USD:,.0f}"
    if ctx.get("leverage_after", 0) > config.MAX_LEVERAGE:
        return False, f"leverage {ctx['leverage_after']:.2f} > cap {config.MAX_LEVERAGE}"
    if abs(ctx.get("net_delta_usd_after", 0)) > config.MAX_ABS_DELTA_USD + 1e-6:
        return False, f"net delta ${ctx['net_delta_usd_after']:+,.0f} outside band ±${config.MAX_ABS_DELTA_USD:,.0f}"
    return True, "ok"
