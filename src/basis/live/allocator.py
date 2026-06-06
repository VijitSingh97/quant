"""Strategy allocator — the delta-neutral funding carry as a target position.

Long X BTC spot + short X BTC perp (net delta 0), where X is the deployed notional
/ mark. Funding-timed: when funding is negative, target flat (cash) to avoid paying
funding — staying delta-neutral either way (neutral pair, or flat).
"""

from . import config


def carry_target(equity_usd, mark, funding_apr, deploy=None, timed=None):
    deploy = config.DEPLOY_FRACTION if deploy is None else deploy
    timed = config.FUNDING_TIMED if timed is None else timed
    if equity_usd <= 0 or mark <= 0:
        return {"spot": 0.0, "perp": 0.0}
    x = (equity_usd * deploy) / mark
    on = (not timed) or (funding_apr > 0)
    return {"spot": x, "perp": -x} if on else {"spot": 0.0, "perp": 0.0}
