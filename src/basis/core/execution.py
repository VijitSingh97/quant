"""Order-book execution-cost helpers (pure, no network).

Walk an L2 book to get the REAL fill price and slippage for a given size — so we can see
what a carry leg would actually cost at live depth, instead of a flat slippage assumption.
"""


def walk_book(levels, size):
    """levels: [(px, sz), ...] in execution order (asks ascending for a buy, bids
    descending for a sell). Returns (vwap_fill_px, filled_size, exhausted)."""
    remaining, cost, filled = size, 0.0, 0.0
    for px, sz in levels:
        take = sz if sz < remaining else remaining
        cost += take * px
        filled += take
        remaining -= take
        if remaining <= 1e-12:
            break
    if filled <= 0:
        return 0.0, 0.0, True
    return cost / filled, filled, remaining > 1e-9


def slippage_bps(vwap, mid, side):
    """Adverse fill vs mid, in bps (positive = worse than mid for you)."""
    if mid <= 0 or vwap <= 0:
        return 0.0
    return ((vwap / mid - 1) if side == "buy" else (mid / vwap - 1)) * 1e4


def quote(book, usd, side):
    """book = {bids, asks, mid}; walk `usd` notional through the right side.
    Returns fill stats (or None if the book is empty)."""
    mid = book.get("mid", 0.0)
    if mid <= 0:
        return None
    size = usd / mid
    levels = book["asks"] if side == "buy" else book["bids"]
    vwap, filled, exhausted = walk_book(levels, size)
    return {"mid": mid, "size": size, "vwap": vwap, "side": side,
            "slippage_bps": slippage_bps(vwap, mid, side),
            "filled_usd": filled * (vwap or mid), "exhausted": exhausted}
