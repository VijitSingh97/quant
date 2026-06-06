"""Offline tests for the guarded parameter apply path (#18 Phase B)."""

from basis.live import config, tune
from basis.live.store import Store


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RESEARCH_DB", tmp_path / "research.db")
    monkeypatch.setattr(config, "OVERRIDES_PATH", tmp_path / "overrides.json")
    return Store(config.RESEARCH_DB)


def _report(store, *, at_optimum, sm=0.10, mf=0.03):
    return store.add_report("validation", "test", {
        "ok": True, "at_optimum": at_optimum,
        "best_in_sweep": {"switch_margin": sm, "min_funding": mf, "apr": 0.2}})


def test_bounds_reject_out_of_range():
    ok, _ = tune._bounds_ok({"AUTO_SWITCH_MARGIN": 0.99})     # > 0.20 cap
    assert not ok
    ok, _ = tune._bounds_ok({"AUTO_SWITCH_MARGIN": 0.10, "AUTO_MIN_FUNDING": 0.03})
    assert ok


def test_apply_writes_overrides_and_logs(tmp_path, monkeypatch):
    store = _setup(tmp_path, monkeypatch)
    rid = _report(store, at_optimum=False, sm=0.10, mf=0.03)
    rc = tune.apply_cmd(store, rid)
    assert rc == 0
    assert config.load_overrides() == {"AUTO_SWITCH_MARGIN": 0.10, "AUTO_MIN_FUNDING": 0.03}
    assert store.recent_reports("config_change", 1)[0]["data"]["report_id"] == rid
    store.close()


def test_apply_refuses_when_no_change_recommended(tmp_path, monkeypatch):
    store = _setup(tmp_path, monkeypatch)
    rid = _report(store, at_optimum=True)                     # "keep current"
    assert tune.apply_cmd(store, rid) == 1                    # refused
    assert config.load_overrides() == {}                      # nothing written
    assert tune.apply_cmd(store, rid, force=True) == 0        # --force overrides
    store.close()


def test_rollback_restores_previous(tmp_path, monkeypatch):
    store = _setup(tmp_path, monkeypatch)
    tune.apply_cmd(store, _report(store, at_optimum=False, sm=0.10, mf=0.03))
    tune.apply_cmd(store, _report(store, at_optimum=False, sm=0.02, mf=0.08))
    assert config.load_overrides()["AUTO_SWITCH_MARGIN"] == 0.02
    tune.rollback_cmd(store)
    assert config.load_overrides()["AUTO_SWITCH_MARGIN"] == 0.10   # back to the prior change
    store.close()


def test_reset_clears(tmp_path, monkeypatch):
    store = _setup(tmp_path, monkeypatch)
    tune.apply_cmd(store, _report(store, at_optimum=False))
    assert config.load_overrides()
    tune.reset_cmd(store)
    assert config.load_overrides() == {}
    store.close()
