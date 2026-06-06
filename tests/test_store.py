"""Offline tests for the SQLite store: WAL durability mode + a basic round-trip."""

from basis.live.store import Store


def test_wal_mode_enabled(tmp_path):
    s = Store(tmp_path / "s.db")
    assert s.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"   # crash-safe
    assert s.db.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
    s.close()


def test_round_trip(tmp_path):
    s = Store(tmp_path / "s.db")
    s.set_position("spot", 1.5, 100.0)
    assert s.positions()["spot"]["qty"] == 1.5
    s.set_meta("held_symbol", "HYPE")
    assert s.get_meta("held_symbol") == "HYPE"
    assert s.get_meta("missing", "def") == "def"
    s.log("test_event", {"a": 1})
    assert s.recent_events(1)[0]["kind"] == "test_event"
    s.snapshot_pnl(6000.0, 0.0, "t")
    assert s.latest_pnl()["equity_usd"] == 6000.0
    s.close()


def test_reports_and_metrics(tmp_path):
    s = Store(tmp_path / "research.db")
    assert s.latest_report("validation") is None
    s.add_report("validation", "near-optimal", {"ok": True, "current": {"apr": 0.12}})
    lr = s.latest_report("validation")
    assert lr["summary"] == "near-optimal" and lr["data"]["current"]["apr"] == 0.12
    assert len(s.recent_reports("validation")) == 1
    s.add_metric("BTC", {"spot": 60000, "hl_funding_apr": 0.1})
    rows = s.metrics_rows()
    assert rows[-1]["asset"] == "BTC" and rows[-1]["data"]["spot"] == 60000
    s.close()
