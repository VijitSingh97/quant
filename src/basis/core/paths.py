"""Filesystem anchors, independent of the current working directory.

DATA_DIR defaults to <repo>/data for the src-layout dev checkout, but is overridable
via BASIS_DATA_DIR (legacy BTCVOL_DATA_DIR) — required when the package is pip-installed
outside the repo (e.g. in the Docker image, where it points at the /app/data volume),
because the parents[3] anchor only holds for the source tree.
"""

import os
from pathlib import Path

# src/basis/core/paths.py -> parents[3] is the project root (dev checkout only)
PROJECT_ROOT = Path(__file__).resolve().parents[3]

_data_env = os.environ.get("BASIS_DATA_DIR") or os.environ.get("BTCVOL_DATA_DIR")
DATA_DIR = Path(_data_env).expanduser() if _data_env else (PROJECT_ROOT / "data")
