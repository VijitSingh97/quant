"""Offline tests for the scheduled self-validation (mocked funding, tmp research DB)."""

import basis.live.validate as validate
from basis.live import config
from basis.live.store import Store


def _series(n=400, step=3600000):
    return {"BTC": [(i * step, 0.00001) for i in range(n)],
            "ALT": [(i * step, 0.00005) for i in range(n)]}


def test_compute_report_shape(monkeypatch):
    monkeypatch.setattr(validate.rotation, "pull_series", lambda u, d, **k: _series())
    monkeypatch.setattr(config, "AUTO_SPOT_UNIVERSE", {"BTC", "ALT"})
    rep = validate.compute_report()
    assert rep["ok"]
    assert "current" in rep and "best_in_sweep" in rep and rep["sweep"]
    assert isinstance(rep["suggestion"], str)
    assert rep["current"]["vs_btc_apr"] is not None


def test_due_logic(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RESEARCH_DB", tmp_path / "r.db")
    s = Store(config.RESEARCH_DB)
    try:
        assert validate._due(s, 100)                 # no report yet -> due
        s.add_report("validation", "x", {"ok": True})
        assert not validate._due(s, 100)             # just ran -> not due
    finally:
        s.close()


def test_main_force_stores_report(tmp_path, monkeypatch):
    monkeypatch.setattr(validate.rotation, "pull_series", lambda u, d, **k: _series())
    monkeypatch.setattr(config, "AUTO_SPOT_UNIVERSE", {"BTC", "ALT"})
    monkeypatch.setattr(config, "RESEARCH_DB", tmp_path / "r.db")
    rep = validate.main(force=True)
    assert rep and rep["ok"]
    s = Store(config.RESEARCH_DB)
    try:
        assert s.latest_report("validation") is not None
    finally:
        s.close()
