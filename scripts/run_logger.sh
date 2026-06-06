#!/bin/zsh
# Append one metrics row to data/timeseries.csv (no LLM tokens).
# Invoked by the launchd agent; runs with a minimal environment, so paths are absolute.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
PYTHONPATH="$ROOT/src" /usr/bin/python3 -m basis.logger
