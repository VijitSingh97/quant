import csv

from basis.logger import append_row


def _read(p):
    with open(p, newline="") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def test_append_row_creates_file_with_header(tmp_path):
    p = tmp_path / "ts.csv"
    append_row(p, ["a", "b", "c"], {"a": 1, "b": 2, "c": 3})
    fields, rows = _read(p)
    assert fields == ["a", "b", "c"]
    assert rows == [{"a": "1", "b": "2", "c": "3"}]


def test_append_row_same_schema_appends(tmp_path):
    p = tmp_path / "ts.csv"
    append_row(p, ["a", "b"], {"a": 1, "b": 2})
    append_row(p, ["a", "b"], {"a": 3, "b": 4})
    _, rows = _read(p)
    assert len(rows) == 2 and rows[1]["a"] == "3"


def test_append_row_migrates_old_schema_and_pads(tmp_path):
    p = tmp_path / "ts.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["a", "b"])
        w.writeheader()
        w.writerow({"a": 1, "b": 2})
    append_row(p, ["a", "b", "c"], {"a": 3, "b": 4, "c": 5})   # schema grows by 'c'
    fields, rows = _read(p)
    assert fields == ["a", "b", "c"]
    assert rows[0] == {"a": "1", "b": "2", "c": ""}            # old row padded
    assert rows[1] == {"a": "3", "b": "4", "c": "5"}
