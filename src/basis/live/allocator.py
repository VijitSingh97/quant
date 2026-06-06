"""Strategy allocator — the delta-neutral funding carry as a target position.

Long X spot + short X perp (net delta 0), X = deployed notional / mark. Funding-timed
with HYSTERESIS: deploy only when funding is clearly positive, flatten only when clearly
negative, hold in between — so we don't pay a round-trip fee flapping on zero-crossings.
"""

from . import config


def carry_target(equity_usd, mark, funding_apr, deploy=None, timed=None,
                 currently_on=False, enter=None, exit_=None):
    """If flat, deploy only when funding clears +enter; if already deployed, hold until
    funding drops below -exit. The [exit, enter] band is a no-trade hold zone that stops
    fee-churn. `currently_on` = whether the book is already deployed (caller passes it)."""
    deploy = config.DEPLOY_FRACTION if deploy is None else deploy
    timed = config.FUNDING_TIMED if timed is None else timed
    enter = config.FUNDING_ENTER_APR if enter is None else enter
    exit_ = config.FUNDING_EXIT_APR if exit_ is None else exit_
    if equity_usd <= 0 or mark <= 0:
        return {"spot": 0.0, "perp": 0.0}
    if not timed:
        on = True
    elif currently_on:
        on = funding_apr > exit_           # hold until funding clearly turns negative
    else:
        on = funding_apr > enter           # only (re)deploy when funding is clearly positive
    x = (equity_usd * deploy) / mark
    return {"spot": x, "perp": -x} if on else {"spot": 0.0, "perp": 0.0}
