import importlib
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="function")
def downloader_ts_module(monkeypatch):
    module_name = "download.dl.downloader_tushare"

    for mod in [
        module_name,
        "download.dl.downloader",
        "download.dl",
        "download",
    ]:
        sys.modules.pop(mod, None)

    ts_stub = types.SimpleNamespace()
    ts_stub.set_token = Mock()

    pro_stub = types.SimpleNamespace()
    pro_stub.daily_basic = Mock()

    ts_stub.pro_api = Mock(return_value=pro_stub)

    monkeypatch.setitem(sys.modules, "tushare", ts_stub)

    module = importlib.import_module(module_name)
    module = importlib.reload(module)

    return module, ts_stub, pro_stub


def test_download_daily_basic_missing_token_raises(downloader_ts_module, monkeypatch):
    module, ts_stub, _ = downloader_ts_module
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)

    with pytest.raises(ConnectionError, match="Tushare token is missing"):
        module.download_daily_basic_a_stock_ts("2024-01-05")

    ts_stub.pro_api.assert_not_called()


def test_download_daily_basic_a_stock_ts_success(downloader_ts_module, monkeypatch):
    """Test successful download of daily basic A-stock data."""
    module, ts_stub, pro_stub = downloader_ts_module

    # Set up environment with token
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")

    # Mock return data
    mock_data = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000002.SZ"],
            "trade_date": ["20240105", "20240105"],
            "close": [10.5, 20.3],
            "turnover_rate": [1.2, 0.8],
            "turnover_rate_f": [1.1, 0.7],
            "volume_ratio": [1.5, 2.1],
            "pe": [15.2, 18.5],
            "pe_ttm": [14.8, 17.9],
            "pb": [2.1, 3.2],
            "ps": [1.8, 2.5],
            "ps_ttm": [1.7, 2.4],
            "dv_ratio": [2.5, 1.8],
            "dv_ttm": [2.3, 1.6],
            "total_share": [1000000, 2000000],
            "float_share": [800000, 1600000],
            "free_share": [750000, 1500000],
            "total_mv": [10500000, 40600000],
            "circ_mv": [8400000, 32480000],
            "limit_status": ["N", "N"],
        }
    )

    pro_stub.daily_basic.return_value = mock_data

    # Test with different date formats
    test_date = "2024-01-05"
    result = module.download_daily_basic_a_stock_ts(test_date)

    # Verify token was set
    ts_stub.set_token.assert_called_once_with("test_token_123")

    # Verify pro_api was called
    ts_stub.pro_api.assert_called_once()

    # Verify daily_basic was called with correct parameters
    expected_params = {
        "ts_code": "",
        "trade_date": "20240105",  # Date should be converted to YYYYMMDD format
        "start_date": "",
        "end_date": "",
        "limit": "",
        "offset": "",
    }
    pro_stub.daily_basic.assert_called_once_with(
        **expected_params, fields=module.daily_basic_fields
    )

    # Verify return value
    pd.testing.assert_frame_equal(result, mock_data)


def test_download_daily_basic_a_stock_ts_different_date_formats(
    downloader_ts_module, monkeypatch
):
    """Test date format conversion in download_daily_basic_a_stock_ts."""
    module, ts_stub, pro_stub = downloader_ts_module

    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")

    # Mock empty DataFrame return
    pro_stub.daily_basic.return_value = pd.DataFrame()

    # Test different date formats
    date_formats = [
        "2024-01-05",  # YYYY-MM-DD
        "2024/01/05",  # YYYY/MM/DD
        "2024.01.05",  # YYYY.MM.DD
        "20240105",  # YYYYMMDD
    ]

    for date_str in date_formats:
        # Reset mocks
        pro_stub.daily_basic.reset_mock()

        module.download_daily_basic_a_stock_ts(date_str)

        # All formats should be converted to YYYYMMDD
        expected_params = {
            "ts_code": "",
            "trade_date": "20240105",
            "start_date": "",
            "end_date": "",
            "limit": "",
            "offset": "",
        }
        pro_stub.daily_basic.assert_called_once_with(
            **expected_params, fields=module.daily_basic_fields
        )


def test_download_daily_basic_a_stock_ts_invalid_date_format(
    downloader_ts_module, monkeypatch
):
    """Test invalid date format raises ValueError."""
    module, ts_stub, pro_stub = downloader_ts_module

    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")

    with pytest.raises(ValueError, match="Invalid date format: invalid_date"):
        module.download_daily_basic_a_stock_ts("invalid_date")

    # Verify no API calls were made
    pro_stub.daily_basic.assert_not_called()


def test_download_daily_basic_a_stock_ts_empty_result(
    downloader_ts_module, monkeypatch
):
    """Test handling of empty result from API."""
    module, ts_stub, pro_stub = downloader_ts_module

    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")

    # Mock empty DataFrame
    empty_df = pd.DataFrame(columns=module.daily_basic_fields)
    pro_stub.daily_basic.return_value = empty_df

    result = module.download_daily_basic_a_stock_ts("2024-01-05")

    # Verify the function returns the empty DataFrame
    pd.testing.assert_frame_equal(result, empty_df)
    assert len(result) == 0


if __name__ == "__main__":
    pytest.main([__file__])
