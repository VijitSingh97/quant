"""btcvol.live — execution layer (PAPER by default).

A safety-first, phased path from the research toolkit to real automated trading:
config (paper unless explicitly LIVE), an append-only SQLite audit store, a
pre-trade risk gate with a kill switch, pluggable exchange clients (a paper
simulator + a read-only-first Hyperliquid client), a delta-neutral carry
allocator, and a reconcile engine that never sends live orders unless mode=live.

Nothing here moves real money on its own: paper mode simulates fills against live
marks; live mode requires explicit opt-in + trade-not-withdraw API keys.
"""
