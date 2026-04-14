import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from unittest.mock import MagicMock, patch
import pandas as pd
import pytest
from common.const import COL_CLOSE
from monitor.price_fetcher import fetch_current_price, fetch_history_df


def test_fetch_current_price_a_stock():
    """fetch_current_price calls EastMoney API for A-share."""
    with patch("monitor.price_fetcher.fetch_close_price", return_value=1800.5) as mock_fn:
        price = fetch_current_price("600519", "A")
    mock_fn.assert_called_once_with("600519")
    assert price == 1800.5


def test_fetch_current_price_etf():
    """fetch_current_price calls EastMoney API for ETF."""
    with patch("monitor.price_fetcher.fetch_close_price", return_value=3.25) as mock_fn:
        price = fetch_current_price("510300", "ETF")
    mock_fn.assert_called_once_with("510300")
    assert price == 3.25


def test_fetch_history_df_a_stock_returns_dataframe():
    """fetch_history_df loads A-stock history from storage."""
    mock_df = pd.DataFrame({COL_CLOSE: [100.0, 101.0, 102.0]})
    mock_storage = MagicMock()
    mock_storage.load_history_data_stock.return_value = mock_df

    with patch("monitor.price_fetcher.get_storage", return_value=mock_storage):
        result = fetch_history_df("600519", "A", min_periods=3)

    assert result is not None
    assert len(result) == 3
    assert COL_CLOSE in result.columns


def test_fetch_history_df_insufficient_returns_none():
    """fetch_history_df returns None when fewer rows than min_periods."""
    mock_df = pd.DataFrame({COL_CLOSE: [100.0, 101.0]})
    mock_storage = MagicMock()
    mock_storage.load_history_data_stock.return_value = mock_df

    with patch("monitor.price_fetcher.get_storage", return_value=mock_storage):
        result = fetch_history_df("600519", "A", min_periods=20)

    assert result is None


def test_fetch_history_df_etf():
    """fetch_history_df calls load_history_data_etf for ETF market."""
    mock_df = pd.DataFrame({COL_CLOSE: [3.0] * 25})
    mock_storage = MagicMock()
    mock_storage.load_history_data_etf.return_value = mock_df

    with patch("monitor.price_fetcher.get_storage", return_value=mock_storage):
        result = fetch_history_df("510300", "ETF", min_periods=20)

    assert result is not None
    mock_storage.load_history_data_etf.assert_called_once()
