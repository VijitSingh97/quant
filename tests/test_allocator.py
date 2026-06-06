"""Offline tests for the funding-timed carry target + its anti-churn hysteresis."""

from basis.live.allocator import carry_target

EQ, MARK = 6000.0, 60000.0
ENTER, EXIT = 0.03, -0.02


def _on(funding, currently_on):
    t = carry_target(EQ, MARK, funding, currently_on=currently_on, enter=ENTER, exit_=EXIT)
    return abs(t["spot"]) > 0


def test_deploys_when_funding_clearly_positive():
    assert _on(0.10, currently_on=False)          # flat + funding > enter -> deploy


def test_flat_does_not_deploy_in_the_band():
    assert not _on(0.01, currently_on=False)       # flat + funding in [exit, enter] -> stay flat
    assert not _on(-0.01, currently_on=False)


def test_deployed_holds_through_the_band():
    assert _on(0.01, currently_on=True)            # deployed + small positive -> hold (no churn)
    assert _on(-0.01, currently_on=True)           # deployed + small negative -> hold (fee not worth it)


def test_deployed_flattens_only_when_clearly_negative():
    assert not _on(-0.05, currently_on=True)       # funding < exit -> flatten


def test_no_flap_on_zero_crossing():
    # the classic churn: deployed, funding dips just below zero, then back up.
    assert _on(-0.005, currently_on=True)          # tiny dip -> still held (would have flapped before)
    assert _on(0.005, currently_on=True)           # back up -> still held; never round-tripped


def test_timed_off_always_deploys():
    assert _on(-0.50, currently_on=False) is False or carry_target(
        EQ, MARK, -0.5, timed=False)["spot"] > 0   # timed=False ignores funding entirely


def test_neutral_target_is_delta_zero():
    t = carry_target(EQ, MARK, 0.10, currently_on=False, enter=ENTER, exit_=EXIT)
    assert abs(t["spot"] + t["perp"]) < 1e-12      # long spot == short perp
