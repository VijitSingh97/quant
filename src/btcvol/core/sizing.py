"""Position sizing — volatility targeting and fractional Kelly. Pure functions.

'Consistent' comes from sizing, not from picking the right trade. Two levers:
  - vol targeting: scale a position so its vol hits a target (halve size when vol doubles)
  - fractional Kelly: bet a capped fraction of the Kelly-optimal stake (full Kelly is
    far too wild for crypto's fat tails)
"""


def vol_target_scale(target_vol, position_vol, max_scale=3.0):
    """Scale factor to bring a position's annualized vol to `target_vol`.

    Halves when position vol doubles. Capped at `max_scale` so a near-zero vol
    estimate doesn't imply absurd leverage.
    """
    if position_vol <= 0:
        return max_scale
    return min(max_scale, target_vol / position_vol)


def kelly_fraction(win_prob, win_loss_ratio):
    """Full-Kelly stake fraction for a binary bet: f* = p - (1-p)/b,
    where p = win probability and b = win/loss payoff ratio. Can be negative
    (no edge -> don't bet)."""
    if win_loss_ratio <= 0:
        return 0.0
    return win_prob - (1 - win_prob) / win_loss_ratio


def fractional_kelly(win_prob, win_loss_ratio, fraction=0.25, cap=0.5):
    """A capped fraction of Kelly. Defaults to quarter-Kelly, hard-capped at 50%
    of capital. Never returns negative (returns 0 when there's no edge)."""
    f = fraction * kelly_fraction(win_prob, win_loss_ratio)
    return max(0.0, min(cap, f))
