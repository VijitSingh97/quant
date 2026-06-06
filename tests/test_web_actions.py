"""Offline tests for the dashboard action layer (kill switch, registry, unknowns)."""

import importlib

from basis.live import config, web


def test_kill_toggle(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "KILL_FILE", tmp_path / "KILL_SWITCH")
    assert web.do_action("kill_on", {})["ok"] and config.KILL_FILE.exists()
    assert web.do_action("kill_off", {})["ok"] and not config.KILL_FILE.exists()


def test_unknown_tool_and_action():
    assert "unknown tool" in web.run_tool("nope")
    assert web.do_action("bogus", {})["ok"] is False


def test_every_registered_tool_module_imports():
    for name, (group, modpath) in web.TOOLS.items():
        mod = importlib.import_module(modpath)
        assert hasattr(mod, "main"), f"{name} ({modpath}) has no main()"
