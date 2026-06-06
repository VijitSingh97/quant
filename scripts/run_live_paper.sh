#!/bin/zsh
# Cron/launchd wrapper: run one paper reconcile cycle of the carry engine.
# Paper mode — simulates fills, no real orders. Runs with a minimal environment.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
PYTHONPATH="$ROOT/src" BTCVOL_MODE=paper /usr/bin/python3 -m btcvol.live.engine
