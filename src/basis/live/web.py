"""Web dashboard — stdlib http.server, no dependencies.

Serves a single-page UI (dashboard.html) + a /api/status JSON endpoint backed by the
shared status assembler. Market/live data is cached ~30s so the 5s UI refresh doesn't
hammer the exchanges; store reads are fresh each call.

Run:  python3 -m basis.live.web   ->  http://localhost:8787
"""

import http.server
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
            self._send(200, json.dumps(s, default=str).encode(), "application/json")
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
