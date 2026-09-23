import pytest

from common.market_code import to_tushare_code


@pytest.mark.parametrize(
    ("code", "market", "expected"),
    [
        ("600000", "A", "600000.SH"),
        ("430001", "A", "430001.BJ"),
        ("830001", "A", "830001.BJ"),
        ("000001", "A", "000001.SZ"),
        ("002001", "A", "002001.SZ"),
        ("300001", "A", "300001.SZ"),
        ("510300", "ETF", "510300.SH"),
        ("159915", "ETF", "159915.SZ"),
        ("164999", "ETF", "164999.SZ"),
        ("12345", "HK", "12345.HK"),
    ],
)
def test_to_tushare_code(code: str, market: str, expected: str) -> None:
    assert to_tushare_code(code, market) == expected


@pytest.mark.parametrize(
    ("code", "market"),
    [
        ("60000", "A"),
        ("6000000", "A"),
        ("60000a", "A"),
        ("100000", "A"),
        ("100000", "ETF"),
        ("600000", "ETF"),
        ("165000", "ETF"),
        ("1234", "HK"),
        ("123456", "HK"),
        ("1234a", "HK"),
        ("１２３４５", "HK"),
        ("123456", "UNKNOWN"),
    ],
)
def test_to_tushare_code_rejects_invalid_codes(code: str, market: str) -> None:
    with pytest.raises(ValueError):
        to_tushare_code(code, market)  # type: ignore[arg-type]
