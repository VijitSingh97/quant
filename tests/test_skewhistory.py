import csv

from basis.backtests.structures import load_skew_history, _nearest_coeffs, _date_ms


def _write(path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "asset", "index", "atm_iv", "rr25", "bf25", "rr10", "bf10",
                    "pc_oi_ratio", "n_options"])
        w.writerow(["2024-01-01", "BTC", "42000", "0.55", "-0.05", "0.01", "-0.10", "0.03", "0.5", "800"])
        w.writerow(["2024-02-01", "BTC", "60000", "0.50", "0.02", "0.01", "0.04", "0.02", "0.4", "900"])


def test_date_ms_epoch():
    assert _date_ms("1970-01-01") == 0
    assert _date_ms("1970-01-02") == 86400 * 1000


def test_load_skew_history(tmp_path):
    p = tmp_path / "skew_history.csv"
    _write(p)
    series = load_skew_history(p)
    assert len(series) == 2
    assert series[0][0] < series[1][0]                     # sorted by date
    assert len(series[0][1]) == 3                          # (a0, a1, a2) coeffs


def test_load_skew_history_skips_bad_rows(tmp_path):
    p = tmp_path / "sh.csv"
    with open(p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "atm_iv", "rr25", "bf25", "rr10", "bf10"])
        w.writerow(["2024-01-01", "", "-0.05", "0.01", "", ""])     # bad atm -> skipped
        w.writerow(["2024-02-01", "0.5", "-0.05", "0.01", "-0.1", "0.03"])
    assert len(load_skew_history(p)) == 1


def test_nearest_coeffs_picks_closest():
    series = [(_date_ms("2024-01-01"), (1.0, -0.1, 0.05)),
              (_date_ms("2024-06-01"), (1.0, 0.02, 0.04))]
    assert _nearest_coeffs(series, _date_ms("2024-05-20")) == (1.0, 0.02, 0.04)
    assert _nearest_coeffs([], 0) == (1.0, 0.0, 0.0)
