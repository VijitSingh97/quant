"""Offline tests for the supervisor loop's failure isolation (the resilience core)."""

import pytest

from basis.live import scheduler


def test_run_once_isolates_failures():
    calls = []

    def runner(t):
        calls.append(t)
        if t == "boom":
            raise RuntimeError("network down")

    scheduler.run_once(["a", "boom", "b"], runner=runner)   # must NOT raise
    assert calls == ["a", "boom", "b"]                      # all attempted, failure swallowed


def test_run_once_empty_is_noop():
    scheduler.run_once([], runner=lambda t: None)


def test_load_resolves_known_tasks():
    for name in ("logger", "paper", "auto"):
        assert callable(scheduler._load(name))


def test_load_unknown_task_raises():
    with pytest.raises(ValueError):
        scheduler._load("nope")
