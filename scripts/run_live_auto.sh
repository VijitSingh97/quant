#!/bin/zsh
# Cron/launchd wrapper: run one AUTO-ROTATING paper cycle — pick the best persistent
# carry (with hysteresis) and reconcile. Paper mode, no real orders. Own book:
# data/live_auto.db. Runs with a minimal environment, so paths are absolute.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
PYTHONPATH="$ROOT/src" BASIS_MODE=paper /usr/bin/python3 -m basis.live.auto
