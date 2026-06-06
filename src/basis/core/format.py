"""Terminal formatting helpers."""

_SPARK = "▁▂▃▄▅▆▇█"


def fmt_pct(x, d=2):
    return f"{x*100:+.{d}f}%" if x is not None else "n/a"


def fmt_vol(x):
    return f"{x*100:.1f}%" if x is not None else "n/a"


def sparkline(values):
    """Unicode block sparkline; None values are skipped."""
    vals = [v for v in values if v is not None]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    rng = hi - lo or 1.0
    return "".join(_SPARK[min(7, int((v - lo) / rng * 7))] for v in values if v is not None)
