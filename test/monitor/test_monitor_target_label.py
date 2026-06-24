from unittest.mock import patch

from monitor.monitor_target_service import format_monitor_target_label, resolve_stock_name


def test_format_monitor_target_label_prefers_note_text():
    label = format_monitor_target_label(
        stock_code="600519",
        stock_name="贵州茅台",
        condition={"type": "price_threshold", "direction": "below", "value": 1500},
        note="抄底提醒",
    )

    assert label == "600519 贵州茅台 抄底提醒"


def test_format_monitor_target_label_falls_back_to_readable_condition_when_note_missing():
    label = format_monitor_target_label(
        stock_code="600519",
        stock_name="贵州茅台",
        condition={"type": "price_threshold", "direction": "below", "value": 1500},
        note=None,
    )

    assert label == "600519 贵州茅台 价格低于1500"


def test_format_monitor_target_label_treats_blank_note_as_missing():
    label = format_monitor_target_label(
        stock_code="600519",
        stock_name="贵州茅台",
        condition={"type": "price_threshold", "direction": "below", "value": 1500},
        note="   ",
    )

    assert label == "600519 贵州茅台 价格低于1500"


def test_format_monitor_target_label_price_threshold_above():
    label = format_monitor_target_label(
        stock_code="000001",
        stock_name="平安银行",
        condition={"type": "price_threshold", "direction": "above", "value": 12.5},
        note=None,
    )

    assert label == "000001 平安银行 价格高于12.5"


def test_format_monitor_target_label_change_pct():
    label = format_monitor_target_label(
        stock_code="600519",
        stock_name="贵州茅台",
        condition={"type": "change_pct", "direction": "above", "value": 5},
        note=None,
    )

    assert label == "600519 贵州茅台 涨幅超过5%"


def test_format_monitor_target_label_change_pct_below():
    label = format_monitor_target_label(
        stock_code="600519",
        stock_name="贵州茅台",
        condition={"type": "change_pct", "direction": "below", "value": 3},
        note=None,
    )

    assert label == "600519 贵州茅台 跌幅超过3%"


def test_format_monitor_target_label_price_cross_ma():
    label = format_monitor_target_label(
        stock_code="600519",
        stock_name="贵州茅台",
        condition={"type": "price_cross_ma", "direction": "above", "period": 5},
        note=None,
    )

    assert label == "600519 贵州茅台 价格上穿5日均线"


def test_format_monitor_target_label_price_cross_ma_below():
    label = format_monitor_target_label(
        stock_code="600519",
        stock_name="贵州茅台",
        condition={"type": "price_cross_ma", "direction": "below", "period": 20},
        note=None,
    )

    assert label == "600519 贵州茅台 价格下穿20日均线"


def test_format_monitor_target_label_ma_cross_golden():
    label = format_monitor_target_label(
        stock_code="600519",
        stock_name="贵州茅台",
        condition={"type": "ma_cross", "direction": "golden", "fast": 5, "slow": 10},
        note=None,
    )

    assert label == "600519 贵州茅台 5日均线上穿10日均线"


def test_format_monitor_target_label_ma_cross_death():
    label = format_monitor_target_label(
        stock_code="600519",
        stock_name="贵州茅台",
        condition={"type": "ma_cross", "direction": "death", "fast": 10, "slow": 30},
        note=None,
    )

    assert label == "600519 贵州茅台 10日均线下穿30日均线"


def test_format_monitor_target_label_rsi():
    label = format_monitor_target_label(
        stock_code="600519",
        stock_name="贵州茅台",
        condition={"type": "rsi", "direction": "below", "value": 30},
        note=None,
    )

    assert label == "600519 贵州茅台 RSI低于30"


def test_format_monitor_target_label_rsi_above():
    label = format_monitor_target_label(
        stock_code="600519",
        stock_name="贵州茅台",
        condition={"type": "rsi", "direction": "above", "value": 70},
        note=None,
    )

    assert label == "600519 贵州茅台 RSI高于70"


def test_format_monitor_target_label_condition_is_none():
    label = format_monitor_target_label(
        stock_code="600519",
        stock_name="贵州茅台",
        condition=None,
        note=None,
    )

    assert label == "600519 贵州茅台 未知条件"


def test_format_monitor_target_label_empty_code_and_name():
    label = format_monitor_target_label(
        stock_code="",
        stock_name="",
        condition={"type": "price_threshold", "direction": "below", "value": 100},
        note="提醒",
    )

    assert label == "提醒"


# ---------------------------------------------------------------------------
# resolve_stock_name tests
# ---------------------------------------------------------------------------


def test_resolve_stock_name_returns_provided_name():
    """When stock_name is truthy, return it as-is regardless of stock_code."""
    assert resolve_stock_name("600519", "贵州茅台") == "贵州茅台"


def test_resolve_stock_name_skips_empty_string_name():
    """When stock_name is empty string, resolve from stock_code via get_security_name."""
    with patch("stock.data.access_data.get_security_name", return_value="贵州茅台") as mock_gsn:
        result = resolve_stock_name("600519", "")
    assert result == "贵州茅台"
    mock_gsn.assert_called_once_with("600519")


def test_resolve_stock_name_resolves_from_code_when_name_none():
    """When stock_name is None, call get_security_name to resolve."""
    with patch("stock.data.access_data.get_security_name", return_value="贵州茅台") as mock_gsn:
        result = resolve_stock_name("600519", None)
    assert result == "贵州茅台"
    mock_gsn.assert_called_once_with("600519")


def test_resolve_stock_name_graceful_fallback_on_exception():
    """When get_security_name raises, return None gracefully."""
    with patch("stock.data.access_data.get_security_name", side_effect=RuntimeError("API down")):
        result = resolve_stock_name("600519", None)
    assert result is None


def test_resolve_stock_name_graceful_fallback_on_empty_result():
    """When get_security_name returns empty string, return None gracefully."""
    with patch("stock.data.access_data.get_security_name", return_value=""):
        result = resolve_stock_name("600519", None)
    assert result is None
