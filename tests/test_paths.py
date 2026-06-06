"""Offline test for the DATA_DIR env override (the fix for pip-installed deploys)."""

import importlib

import basis.core.paths as paths


def test_data_dir_env_override(monkeypatch):
    monkeypatch.setenv("BASIS_DATA_DIR", "/tmp/basis_test_data")
    importlib.reload(paths)
    try:
        assert str(paths.DATA_DIR) == "/tmp/basis_test_data"
    finally:
        monkeypatch.delenv("BASIS_DATA_DIR", raising=False)
        importlib.reload(paths)            # restore default for other tests
    assert paths.DATA_DIR.name == "data"   # back to <repo>/data
