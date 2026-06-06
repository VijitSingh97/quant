"""Offline tests for the order-book execution-cost helpers."""

from basis.core.execution import quote, slippage_bps, walk_book


def test_walk_book_full_fill_within_one_level():
    vwap, filled, exhausted = walk_book([(100.0, 10.0)], 4.0)
    assert vwap == 100.0 and filled == 4.0 and not exhausted


def test_walk_book_spans_levels_vwap():
    # buy 3 units: 1 @100, 2 @101 -> vwap (100 + 202)/3
    vwap, filled, exhausted = walk_book([(100.0, 1.0), (101.0, 5.0)], 3.0)
    assert abs(vwap - (100 + 202) / 3) < 1e-9 and filled == 3.0 and not exhausted


def test_walk_book_exhausted_when_too_thin():
    vwap, filled, exhausted = walk_book([(100.0, 1.0)], 5.0)
    assert filled == 1.0 and exhausted is True


def test_slippage_bps_sign():
    assert slippage_bps(101.0, 100.0, "buy") > 0       # paid above mid
    assert slippage_bps(99.0, 100.0, "sell") > 0       # sold below mid
    assert abs(slippage_bps(100.0, 100.0, "buy")) < 1e-9


def test_quote_walks_correct_side():
    book = {"mid": 100.0, "asks": [(100.5, 100.0)], "bids": [(99.5, 100.0)]}
    b = quote(book, usd=1000.0, side="buy")
    assert b["vwap"] == 100.5 and b["slippage_bps"] > 0 and not b["exhausted"]
    s = quote(book, usd=1000.0, side="sell")
    assert s["vwap"] == 99.5 and s["slippage_bps"] > 0


def test_quote_empty_book():
    assert quote({"mid": 0.0, "asks": [], "bids": []}, 1000.0, "buy") is None
