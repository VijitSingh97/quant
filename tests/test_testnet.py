"""Offline test: BASIS_HL_TESTNET routes the whole HL surface to testnet."""

import importlib

import basis.core.sources as sources


def test_hl_base_routes_to_testnet(monkeypatch):
    monkeypatch.setenv("BASIS_HL_TESTNET", "1")
    importlib.reload(sources)
    try:
        assert "hyperliquid-testnet" in sources.HL_INFO and sources.HL_INFO.endswith("/info")
    finally:
        monkeypatch.delenv("BASIS_HL_TESTNET", raising=False)
        importlib.reload(sources)            # restore mainnet for the rest of the suite
    assert sources.HL_INFO == "https://api.hyperliquid.xyz/info"
