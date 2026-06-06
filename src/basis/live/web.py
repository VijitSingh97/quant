"""Web dashboard — stdlib http.server, no dependencies.

Serves a single-page UI (dashboard.html) + a /api/status JSON endpoint backed by the
shared status assembler. Market/live data is cached ~30s so the 5s UI refresh doesn't
hammer the exchanges; store reads are fresh each call.

Run:  python3 -m basis.live.web   ->  http://localhost:8787
"""

import csv
import http.server
import io
import json
import os
import socketserver
import time
from pathlib import Path

from . import config
from .status import build_status, market_snapshot, live_account, opportunities
from .store import Store

HTML = (Path(__file__).parent / "dashboard.html").read_bytes()
_cache = {"market": None, "live": None, "opps": None, "mts": 0.0, "ots": 0.0}


def _research(fn):
    s = Store(config.RESEARCH_DB)
    try:
        return fn(s)
    finally:
        s.close()


def _reports_csv(rows):
    cols = ["ts", "iso", "summary", "cur_switch_margin", "cur_min_funding", "cur_apr",
            "cur_sharpe", "cur_switches", "vs_btc_apr", "best_switch_margin",
            "best_min_funding", "best_apr", "at_optimum"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        d = r.get("data") or {}
        cur, best = d.get("current") or {}, d.get("best_in_sweep") or {}
        w.writerow([r["ts"], time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r["ts"])),
                    r.get("summary", ""), cur.get("switch_margin"), cur.get("min_funding"),
                    cur.get("apr"), cur.get("sharpe"), cur.get("switches"), cur.get("vs_btc_apr"),
                    best.get("switch_margin"), best.get("min_funding"), best.get("apr"),
                    d.get("at_optimum")])
    return buf.getvalue().encode()


def _metrics_csv(rows):
    from ..logger import FIELDS
    cols = ["ts", "asset"] + FIELDS
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        d = r.get("data") or {}
        w.writerow([r["ts"], r.get("asset")] + [d.get(k) for k in FIELDS])
    return buf.getvalue().encode()


def _refresh(market_ttl=30, opps_ttl=300):
    now = time.time()
    if now - _cache["mts"] > market_ttl:            # market + live: cheap, refresh often
        try:
            _cache["market"] = market_snapshot()
            if config.HL_ADDRESS:
                from .exchanges.hyperliquid import HyperliquidClient
                _cache["live"] = live_account(HyperliquidClient())
            _cache["mts"] = now
        except Exception:       # noqa: BLE001 — keep serving stale on a transient error
            pass
    if now - _cache["ots"] > opps_ttl:              # opportunities: ~9 calls, refresh slowly
        try:
            _cache["opps"] = opportunities(top=8)
            _cache["ots"] = now
        except Exception:       # noqa: BLE001
            pass
    return _cache


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _download(self, body, ctype, filename):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, HTML, "text/html; charset=utf-8")
        elif self.path.startswith("/api/status"):
            c = _refresh()
            store = Store(config.DB_PATH)
            try:
                s = build_status(store, market=c["market"] or market_snapshot(),
                                 include_live=False, opps=c["opps"])
            finally:
                store.close()
            s["live"] = c["live"]
            s["validation"] = _research(lambda st: st.latest_report("validation"))
            self._send(200, json.dumps(s, default=str).encode(), "application/json")
        elif self.path.startswith("/api/reports"):
            data = _research(lambda st: st.recent_reports("validation", 50))
            self._send(200, json.dumps(data, default=str).encode(), "application/json")
        elif self.path.startswith("/export/"):
            self._export()
        else:
            self._send(404, b"not found", "text/plain")

    def _export(self):
        p = self.path
        if p.startswith("/export/reports.csv"):
            self._download(_reports_csv(_research(lambda s: s.recent_reports("validation", 500))),
                           "text/csv", "basis_reports.csv")
        elif p.startswith("/export/reports.json"):
            data = _research(lambda s: s.recent_reports("validation", 500))
            self._download(json.dumps(data, default=str, indent=2).encode(),
                           "application/json", "basis_reports.json")
        elif p.startswith("/export/metrics.csv"):
            self._download(_metrics_csv(_research(lambda s: s.metrics_rows(n=100000))),
                           "text/csv", "basis_metrics.csv")
        elif p.startswith("/export/metrics.json"):
            data = _research(lambda s: s.metrics_rows(n=100000))
            self._download(json.dumps(data, default=str, indent=2).encode(),
                           "application/json", "basis_metrics.json")
        else:
            self._send(404, b"not found", "text/plain")

    def log_message(self, *a):
        pass


def main():
    port = int(os.environ.get("BASIS_WEB_PORT", "8787"))
    # Default to loopback for safe local/CLI use; containers set 0.0.0.0 to be reachable.
    host = os.environ.get("BASIS_WEB_HOST", "127.0.0.1")
    print(f"basis.live dashboard -> http://{host}:{port}   (Ctrl-C to stop)")
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((host, port), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped.")


if __name__ == "__main__":
    main()
