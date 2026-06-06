"""SQLite audit store — the immutable record of everything the system does.

Append-only `events` (the audit trail) + `orders` / `fills` / `pnl` history, plus a
current `positions` snapshot. Every decision, intent, block, and fill is logged, so
the book can be fully reconstructed and reconciled.
"""

import json
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL, kind TEXT NOT NULL, data TEXT
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL, client_id TEXT, venue TEXT, symbol TEXT, side TEXT,
    qty REAL, price REAL, kind TEXT, status TEXT, reason TEXT
);
CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL, order_id INTEGER, symbol TEXT, qty REAL, price REAL
);
CREATE TABLE IF NOT EXISTS positions (
    leg TEXT PRIMARY KEY, qty REAL, avg_price REAL, ts REAL
);
CREATE TABLE IF NOT EXISTS pnl (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL, equity_usd REAL, net_delta_btc REAL, note TEXT
);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL, kind TEXT NOT NULL, summary TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL, asset TEXT, data TEXT
);
"""


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), timeout=30)
        self.db.row_factory = sqlite3.Row
        # Crash/power-loss durability + safe concurrent reader (the web GUI) alongside
        # the writer (the scheduler): WAL survives an abrupt kill without corruption,
        # synchronous=NORMAL flushes the WAL at each checkpoint, busy_timeout waits out
        # a brief lock instead of erroring.
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("PRAGMA busy_timeout=30000")
        self.db.executescript(SCHEMA)
        self.db.commit()

    # --- audit ---
    def log(self, kind, data=None):
        self.db.execute("INSERT INTO events(ts, kind, data) VALUES (?,?,?)",
                        (time.time(), kind, json.dumps(data, default=str) if data is not None else None))
        self.db.commit()

    def recent_events(self, n=20):
        cur = self.db.execute("SELECT ts, kind, data FROM events ORDER BY id DESC LIMIT ?", (n,))
        return [dict(r) for r in cur.fetchall()]

    # --- orders / fills ---
    def add_order(self, o, status, reason=""):
        cur = self.db.execute(
            "INSERT INTO orders(ts, client_id, venue, symbol, side, qty, price, kind, status, reason) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (time.time(), o.client_id, o.venue, o.symbol, o.side, o.qty, o.price, o.kind, status, reason))
        self.db.commit()
        return cur.lastrowid

    def add_fill(self, order_id, symbol, qty, price):
        self.db.execute("INSERT INTO fills(ts, order_id, symbol, qty, price) VALUES (?,?,?,?,?)",
                        (time.time(), order_id, symbol, qty, price))
        self.db.commit()

    # --- positions (current snapshot) ---
    def set_position(self, leg, qty, avg_price):
        self.db.execute(
            "INSERT INTO positions(leg, qty, avg_price, ts) VALUES (?,?,?,?) "
            "ON CONFLICT(leg) DO UPDATE SET qty=?, avg_price=?, ts=?",
            (leg, qty, avg_price, time.time(), qty, avg_price, time.time()))
        self.db.commit()

    def positions(self):
        return {r["leg"]: {"qty": r["qty"], "avg_price": r["avg_price"]}
                for r in self.db.execute("SELECT leg, qty, avg_price FROM positions").fetchall()}

    # --- pnl ---
    def snapshot_pnl(self, equity_usd, net_delta_btc, note=""):
        self.db.execute("INSERT INTO pnl(ts, equity_usd, net_delta_btc, note) VALUES (?,?,?,?)",
                        (time.time(), equity_usd, net_delta_btc, note))
        self.db.commit()

    def latest_pnl(self):
        r = self.db.execute("SELECT * FROM pnl ORDER BY id DESC LIMIT 1").fetchone()
        return dict(r) if r else None

    def pnl_history(self, n=300):
        cur = self.db.execute("SELECT ts, equity_usd, net_delta_btc FROM pnl ORDER BY id DESC LIMIT ?", (n,))
        return list(reversed([dict(r) for r in cur.fetchall()]))

    # --- key-value meta (e.g. currently held asset for the auto allocator) ---
    def set_meta(self, k, v):
        self.db.execute("INSERT INTO meta(k, v) VALUES (?,?) ON CONFLICT(k) DO UPDATE SET v=?",
                        (k, str(v), str(v)))
        self.db.commit()

    def get_meta(self, k, default=None):
        r = self.db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r["v"] if r else default

    # --- research: validation reports + metrics timeseries (research.db) ---
    def add_report(self, kind, summary, data):
        cur = self.db.execute("INSERT INTO reports(ts, kind, summary, data) VALUES (?,?,?,?)",
                              (time.time(), kind, summary, json.dumps(data, default=str)))
        self.db.commit()
        return cur.lastrowid

    def latest_report(self, kind):
        r = self.db.execute("SELECT id, ts, kind, summary, data FROM reports WHERE kind=? "
                            "ORDER BY id DESC LIMIT 1", (kind,)).fetchone()
        return self._report_row(r) if r else None

    def get_report(self, report_id):
        r = self.db.execute("SELECT id, ts, kind, summary, data FROM reports WHERE id=?",
                            (report_id,)).fetchone()
        return self._report_row(r) if r else None

    def recent_reports(self, kind=None, n=20):
        if kind:
            cur = self.db.execute("SELECT id, ts, kind, summary, data FROM reports WHERE kind=? "
                                  "ORDER BY id DESC LIMIT ?", (kind, n))
        else:
            cur = self.db.execute("SELECT id, ts, kind, summary, data FROM reports ORDER BY id DESC LIMIT ?", (n,))
        return [self._report_row(r) for r in cur.fetchall()]

    @staticmethod
    def _report_row(r):
        d = dict(r)
        d["data"] = json.loads(d["data"]) if d["data"] else None
        return d

    def add_metric(self, asset, data):
        self.db.execute("INSERT INTO metrics(ts, asset, data) VALUES (?,?,?)",
                        (time.time(), asset, json.dumps(data, default=str)))
        self.db.commit()

    def metrics_rows(self, asset=None, n=2000):
        if asset:
            cur = self.db.execute("SELECT ts, asset, data FROM metrics WHERE asset=? "
                                  "ORDER BY id DESC LIMIT ?", (asset, n))
        else:
            cur = self.db.execute("SELECT ts, asset, data FROM metrics ORDER BY id DESC LIMIT ?", (n,))
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            d["data"] = json.loads(d["data"]) if d["data"] else None
            rows.append(d)
        return list(reversed(rows))

    def close(self):
        self.db.close()
