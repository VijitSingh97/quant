"""Web dashboard — stdlib http.server, no dependencies. The single control surface.

Serves a single-page UI (dashboard.html) + a /api/status JSON endpoint, AND interactive
POST actions so everything is on the dashboard (no CLI required): run any tool/backtest,
run the self-validation, apply/rollback tuning, and toggle the kill switch. Threaded so a
slow action (a backtest that hits exchanges) doesn't block the 5s refresh; a lock
serializes actions. Read-mostly + bounded actions — run it on a trusted LAN.

Run:  python3 -m basis.live.web   ->  http://localhost:8787
"""

import contextlib
import csv
import http.server
import importlib
import io
import json
import os
import sys
import threading
import time
from pathlib import Path

from . import config
from .status import build_status, market_snapshot, live_account, opportunities, reconcile
from .store import Store

HTML = (Path(__file__).parent / "dashboard.html").read_bytes()
_cache = {"market": None, "live": None, "opps": None, "mts": 0.0, "ots": 0.0}
_LOCK = threading.Lock()      # serialize actions (avoid sys.argv races + hammering exchanges)

# Every CLI tool, runnable from the dashboard. name -> (group, module). The module's main()
# is called with default args (argv reset), stdout captured and returned to the UI.
TOOLS = {
    "preflight":  ("decision", "basis.live.preflight"),
    "carry-scan": ("decision", "basis.carryscan"),
    "execost":    ("decision", "basis.execost"),
    "rotation":   ("backtest", "basis.backtests.rotation"),
    "regime":     ("backtest", "basis.backtests.regime"),
    "carry":      ("backtest", "basis.backtests.carry"),
    "vrp":        ("backtest", "basis.backtests.vrp"),
    "combined":   ("backtest", "basis.backtests.combined"),
    "robust":     ("backtest", "basis.backtests.robustness"),
    "condor-bt":  ("backtest", "basis.backtests.structures"),
    "skew":       ("analysis", "basis.skew"),
    "structures": ("analysis", "basis.structures"),
    "macro":      ("analysis", "basis.macro"),
    "analyze":    ("analysis", "basis.analyze"),
    "snapshot":   ("analysis", "basis.dashboard"),
}


def _capture(fn, argv=("basis",)):
    """Run fn() with a clean argv (so argparse uses defaults), capturing stdout -> str."""
    with _LOCK:
        old = sys.argv
        sys.argv = list(argv)
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                fn()
        except SystemExit:
            pass
        except Exception as e:      # noqa: BLE001 — surface tool errors to the UI, don't crash the server
            buf.write(f"\n[error] {type(e).__name__}: {e}")
        finally:
            sys.argv = old
        return buf.getvalue()


def run_tool(name):
    if name not in TOOLS:
        return f"unknown tool: {name}"
    mod = importlib.import_module(TOOLS[name][1])
    return _capture(mod.main, argv=[name])


def do_action(do, params):
    """Mutating dashboard actions (bounded): kill switch, validation, tuning."""
    if do == "kill_on":
        config.KILL_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.KILL_FILE.write_text("dashboard")
        return {"ok": True, "msg": "KILL SWITCH ON — all trading halted"}
    if do == "kill_off":
        try:
            config.KILL_FILE.unlink()
        except FileNotFoundError:
            pass
        return {"ok": True, "msg": "kill switch cleared — trading can resume"}
    if do == "validate":
        from .validate import main as vmain
        return {"ok": True, "output": _capture(lambda: vmain(force=True))}
    if do in ("tune_apply", "tune_rollback", "tune_reset"):
        from . import tune
        st = Store(config.RESEARCH_DB)

        def _do():
            if do == "tune_apply":
                tune.apply_cmd(st, int((params.get("id") or ["0"])[0]))
            elif do == "tune_rollback":
                tune.rollback_cmd(st)
            else:
                tune.reset_cmd(st)
        try:
            out = _capture(_do)
        finally:
            st.close()
        return {"ok": True, "output": out}
    return {"ok": False, "msg": f"unknown action: {do}"}


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
            s["reconcile"] = reconcile(s["equity"], s["paper"], c["live"])   # our book vs exchange
            s["validation"] = _research(lambda st: st.latest_report("validation"))
            s["overrides"] = config.load_overrides()      # tuner-applied params (#18)
            s["limits"] = {                                # system / risk config for the dashboard
                "cost_bps": config.COST_PER_LEG_BPS, "max_notional_usd": config.MAX_NOTIONAL_USD,
                "max_leverage": config.MAX_LEVERAGE, "max_order_usd": config.MAX_ORDER_USD,
                "deploy_fraction": config.DEPLOY_FRACTION, "funding_timed": config.FUNDING_TIMED,
                "armed": config.LIVE_ARM,
            }
            store2 = Store(config.DB_PATH)
            try:
                from .report import compute as _perf
                s["performance"] = _perf(store2)          # since-inception summary
            finally:
                store2.close()
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

    def do_POST(self):
        from urllib.parse import urlparse, parse_qs
        u = urlparse(self.path)
        q = parse_qs(u.query)
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n:
            self.rfile.read(n)                      # drain any body
        if u.path == "/run":
            out = run_tool((q.get("tool") or [""])[0])
            self._send(200, json.dumps({"output": out}).encode(), "application/json")
        elif u.path == "/action":
            res = do_action((q.get("do") or [""])[0], q)
            self._send(200, json.dumps(res, default=str).encode(), "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def log_message(self, *a):
        pass


def main():
    port = int(os.environ.get("BASIS_WEB_PORT", "8787"))
    # Default to loopback for safe local/CLI use; containers set 0.0.0.0 to be reachable.
    host = os.environ.get("BASIS_WEB_HOST", "127.0.0.1")
    print(f"basis.live dashboard -> http://{host}:{port}   (Ctrl-C to stop)")
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    with http.server.ThreadingHTTPServer((host, port), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped.")


if __name__ == "__main__":
    main()
