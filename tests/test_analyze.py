import csv

from btcvol.analyze import column_stats, pearson, pct_true, load_series


def test_column_stats_basic():
    s = column_stats([1, 2, 3, 4])
    assert s["n"] == 4 and s["min"] == 1 and s["max"] == 4
    assert abs(s["mean"] - 2.5) < 1e-12 and abs(s["median"] - 2.5) < 1e-12


def test_column_stats_empty_is_none():
    assert column_stats([]) is None


def test_pearson_perfect_positive_and_negative():
    xs = [1, 2, 3, 4, 5]
    assert abs(pearson(xs, [2, 4, 6, 8, 10]) - 1.0) < 1e-9
    assert abs(pearson(xs, [10, 8, 6, 4, 2]) + 1.0) < 1e-9


def test_pearson_degenerate_is_none():
    assert pearson([1, 1, 1], [1, 2, 3]) is None       # zero variance
    assert pearson([1, 2], [3, 4]) is None             # too few points


def test_pct_true_ignores_none():
    # None is dropped from the denominator: 2 positive of 4 non-null = 50%
    assert pct_true([1, -1, 2, None, -3], lambda x: x > 0) == 50.0


def test_load_series_parses_and_nulls(tmp_path):
    p = tmp_path / "ts.csv"
    with open(p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["iso_time", "unix", "spot", "vrp", "rr25"])
        w.writerow(["2026-06-06T00:00:00Z", "1780000000", "60000", "0.12", ""])
    rows = load_series(p)
    assert len(rows) == 1
    assert rows[0]["spot"] == 60000.0 and rows[0]["vrp"] == 0.12
    assert rows[0]["rr25"] is None                     # empty -> None
