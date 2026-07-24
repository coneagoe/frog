import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from download.provider_order import parse_stock_history_provider_order  # noqa: E402


def test_parse_stock_history_provider_order_uses_default_when_unset(monkeypatch):
    monkeypatch.delenv("DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER", raising=False)

    assert parse_stock_history_provider_order() == ["baostock", "tushare", "akshare"]


def test_parse_stock_history_provider_order_strips_empty_items_and_deduplicates():
    assert parse_stock_history_provider_order(" tushare, baostock, tushare, , akshare ") == [
        "tushare",
        "baostock",
        "akshare",
    ]


def test_parse_stock_history_provider_order_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unsupported stock history provider: yahoo"):
        parse_stock_history_provider_order("baostock,yahoo")


def test_parse_stock_history_provider_order_rejects_empty_provider_order():
    with pytest.raises(ValueError, match="stock history provider order is empty"):
        parse_stock_history_provider_order(" , , ")


from download.provider_order import parse_hk_stock_history_provider_order  # noqa: E402


def test_parse_hk_stock_history_provider_order_defaults(monkeypatch):
    monkeypatch.delenv("DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER", raising=False)

    assert parse_hk_stock_history_provider_order() == ["yfinance", "tushare", "akshare"]


def test_parse_hk_stock_history_provider_order_accepts_yfinance():
    assert parse_hk_stock_history_provider_order(" yfinance, akshare, yfinance ") == ["yfinance", "akshare"]


def test_parse_hk_stock_history_provider_order_normalizes_and_dedupes():
    assert parse_hk_stock_history_provider_order(" akshare, tushare, AKSHARE ,, ") == [
        "akshare",
        "tushare",
    ]


def test_parse_hk_stock_history_provider_order_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unsupported HK stock history provider: yahoo"):
        parse_hk_stock_history_provider_order("tushare,yahoo")


def test_parse_hk_stock_history_provider_order_rejects_empty_order():
    with pytest.raises(ValueError, match="HK stock history provider order is empty"):
        parse_hk_stock_history_provider_order(" , , ")
