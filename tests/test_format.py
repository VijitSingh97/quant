from btcvol.core import format as fmt


def test_fmt_pct_signed():
    assert fmt.fmt_pct(0.1234) == "+12.34%"
    assert fmt.fmt_pct(-0.05) == "-5.00%"
    assert fmt.fmt_pct(None) == "n/a"


def test_fmt_pct_precision():
    assert fmt.fmt_pct(0.123456, 1) == "+12.3%"


def test_fmt_vol():
    assert fmt.fmt_vol(0.5) == "50.0%"
    assert fmt.fmt_vol(None) == "n/a"


def test_sparkline_length_and_charset():
    s = fmt.sparkline([1, 2, 3, 4, 5])
    assert len(s) == 5
    assert all(c in "▁▂▃▄▅▆▇█" for c in s)


def test_sparkline_extremes():
    s = fmt.sparkline([0, 100])
    assert s[0] == "▁" and s[-1] == "█"


def test_sparkline_empty():
    assert fmt.sparkline([]) == ""


def test_sparkline_skips_none():
    assert len(fmt.sparkline([1, None, 3])) == 2
