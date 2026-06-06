"""Asset selector for the auto allocator — pick the deploy asset from the funding scan.

Pure decision logic (testable): rank qualifying markets by PERSISTENT (14d-avg) funding,
subject to a liquidity floor and a spot-availability universe, then apply HYSTERESIS so
we don't churn — only rotate off the held asset if a candidate beats it by a margin, or
the held asset stops qualifying. Returns (chosen_symbol_or_None, reason).
"""

from . import config


def select_asset(opps, held, held_avg, *, spot_universe=None, spot_any=None,
                 min_funding=None, oi_floor=None, switch_margin=None, exit_funding=None):
    spot_universe = config.AUTO_SPOT_UNIVERSE if spot_universe is None else spot_universe
    spot_any = config.AUTO_SPOT_ANY if spot_any is None else spot_any
    min_funding = config.AUTO_MIN_FUNDING if min_funding is None else min_funding
    oi_floor = config.AUTO_OI_FLOOR_USD if oi_floor is None else oi_floor
    switch_margin = config.AUTO_SWITCH_MARGIN if switch_margin is None else switch_margin
    exit_funding = config.AUTO_EXIT_FUNDING if exit_funding is None else exit_funding

    def spot_ok(coin):
        return spot_any or coin in spot_universe

    cands = sorted((o for o in opps
                    if o.get("avg_apr", -9) >= min_funding
                    and o.get("oi_usd", 0) >= oi_floor
                    and spot_ok(o["coin"])),
                   key=lambda o: o["avg_apr"], reverse=True)
    best = cands[0] if cands else None

    if best is None:
        return None, f"no carry above {min_funding*100:.0f}% (liquid + spot-able) — flat to cash"
    if not held:
        return best["coin"], f"deploy {best['coin']} ({best['avg_apr']*100:+.1f}% 14d-avg)"

    held_ok = (held_avg is not None and held_avg >= exit_funding and spot_ok(held))
    if not held_ok:
        return best["coin"], f"{held} no longer qualifies -> rotate to {best['coin']}"
    if best["coin"] != held and best["avg_apr"] > held_avg + switch_margin:
        edge = (best["avg_apr"] - held_avg) * 100
        return best["coin"], f"rotate {held}->{best['coin']} (+{edge:.1f}% > {switch_margin*100:.0f}% margin)"
    return held, f"hold {held} ({held_avg*100:+.1f}% 14d-avg; best {best['coin']} not worth switching)"
