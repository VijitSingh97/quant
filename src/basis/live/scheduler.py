"""Long-running supervisor loop for container / home-server deployment.

Replaces per-OS schedulers (launchd/cron) with ONE self-healing process: each interval
it runs the configured cycles, isolates failures (a dead endpoint or transient network
blip is logged and skipped — it never crashes the loop), writes a heartbeat for the
container healthcheck, then sleeps. Power loss is handled by Docker `restart:
unless-stopped` (the loop just resumes on boot); crash durability by SQLite WAL.

Env (BASIS_* with legacy BTCVOL_* fallback):
  BASIS_CYCLE_SECONDS   seconds between cycles            (default 3600)
  BASIS_TASKS           comma list of cycles to run       (default "logger,paper,auto,validate")
                        valid: logger, paper, auto, validate
                        (validate self-throttles to BASIS_VALIDATE_INTERVAL_SECONDS, weekly)
Run:  python -m basis.live.scheduler
"""

import signal
import time
import traceback

from . import config
from ..core.paths import DATA_DIR

HEARTBEAT = DATA_DIR / "heartbeat"
_stop = False


def _handle_signal(signum, _frame):
    global _stop
    _stop = True
    print(f"[scheduler] signal {signum} received — stopping after the current cycle", flush=True)


def _load(name):
    """Resolve a task name to its cycle entry point (imported lazily)."""
    if name == "logger":
        from ..logger import main as fn
    elif name == "paper":
        from .engine import main as fn
    elif name == "auto":
        from .auto import main as fn
    elif name == "validate":
        from .validate import main as fn
    else:
        raise ValueError(f"unknown task '{name}' (valid: logger, paper, auto, validate)")
    return fn


def run_once(tasks, runner=None):
    """Run each task with per-task error isolation. `runner` is injectable for tests."""
    runner = runner or (lambda t: _load(t)())
    for t in tasks:
        try:
            print(f"\n[scheduler] === {t} cycle ===", flush=True)
            runner(t)
        except Exception:                       # noqa: BLE001 — one bad cycle must not stop the loop
            print(f"[scheduler] !! {t} cycle failed (continuing):", flush=True)
            traceback.print_exc()


def _heartbeat():
    try:
        HEARTBEAT.write_text(str(int(time.time())))
    except OSError as e:
        print(f"[scheduler] heartbeat write failed: {e}", flush=True)


def _sleep_until_next(seconds):
    """Sleep in short chunks so a SIGTERM/SIGINT is honoured within ~2s."""
    slept = 0.0
    while slept < seconds and not _stop:
        time.sleep(min(2.0, seconds - slept))
        slept += 2.0


def main():
    interval = int(config._env("CYCLE_SECONDS", "3600"))
    tasks = [t.strip() for t in config._env("TASKS", "logger,paper,auto,validate").split(",") if t.strip()]
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    print(f"[scheduler] starting — tasks={tasks} interval={interval}s\n  {config.summary()}", flush=True)

    while not _stop:
        start = time.time()
        run_once(tasks)
        _heartbeat()
        elapsed = time.time() - start
        rest = max(1.0, interval - elapsed)
        print(f"[scheduler] cycle finished in {elapsed:.0f}s; sleeping {rest:.0f}s", flush=True)
        _sleep_until_next(rest)
    print("[scheduler] stopped cleanly.", flush=True)


if __name__ == "__main__":
    main()
