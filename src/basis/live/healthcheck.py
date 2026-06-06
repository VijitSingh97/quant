"""Container healthcheck — exit 0 if the scheduler heartbeat is fresh, else 1.

Docker uses this to mark the container healthy/unhealthy. "Fresh" = the scheduler
wrote its heartbeat within ~2 cycles (plus a grace margin), so a single slow/failed
cycle doesn't flap the status. Run:  python -m basis.live.healthcheck
"""

import sys
import time

from . import config
from ..core.paths import DATA_DIR

HEARTBEAT = DATA_DIR / "heartbeat"


def main():
    interval = int(config._env("CYCLE_SECONDS", "3600"))
    if not HEARTBEAT.exists():
        print("no heartbeat yet")
        sys.exit(1)
    age = time.time() - HEARTBEAT.stat().st_mtime
    limit = 2 * interval + 300                     # tolerate one missed cycle + margin
    if age > limit:
        print(f"stale heartbeat: {age:.0f}s old (limit {limit}s)")
        sys.exit(1)
    print(f"ok: heartbeat {age:.0f}s old")
    sys.exit(0)


if __name__ == "__main__":
    main()
