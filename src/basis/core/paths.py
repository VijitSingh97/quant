"""Filesystem anchors, independent of the current working directory."""

from pathlib import Path

# src/basis/core/paths.py -> parents[3] is the project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
