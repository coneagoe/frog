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


def _expected_hk_history_dtypes(module):
    return {
        module.COL_DATE: "datetime64[ns]",
        module.COL_STOCK_ID: "object",
        module.COL_OPEN: "float64",
        module.COL_CLOSE: "float64",
        module.COL_HIGH: "float64",
        module.COL_LOW: "float64",
        module.COL_VOLUME: "float64",
        module.COL_AMOUNT: "float64",
        module.COL_CHANGE: "float64",
        module.COL_CHANGE_RATE: "float64",
        module.COL_TURNOVER_RATE: "float64",
    }


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

    pro_stub = types.SimpleNamespace()
    pro_stub.daily_basic = Mock()
    pro_stub.hk_daily_adj = Mock()

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
    # Verify pro_api was called with explicit token (no local token file write)
    ts_stub.pro_api.assert_called_once_with(token="test_token_123")

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


def test_download_stk_holdernumber_missing_token_raises(
    downloader_ts_module, monkeypatch
):
    """无 token 时应抛出 ConnectionError。"""
    module, ts_stub, _ = downloader_ts_module
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)

    with pytest.raises(ConnectionError, match="Tushare token is missing"):
        module.download_stk_holdernumber(ts_code="600600.SH")

    ts_stub.pro_api.assert_not_called()


def test_download_stk_holdernumber_success(downloader_ts_module, monkeypatch):
    """正常调用时验证参数传递和返回值。"""
    module, ts_stub, pro_stub = downloader_ts_module
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")

    mock_data = pd.DataFrame(
        {
            "ts_code": ["600600.SH"] * 3,
            "ann_date": ["20240101", "20230701", "20230101"],
            "end_date": ["20231231", "20230630", "20221231"],
            "holder_num": [120000, 118000, 115000],
        }
    )
    pro_stub.stk_holdernumber = Mock(return_value=mock_data)

    result = module.download_stk_holdernumber(
        ts_code="600600.SH",
        start_date="2023-01-01",
        end_date="2024-01-01",
    )

    ts_stub.pro_api.assert_called_once_with(token="test_token_123")
    pro_stub.stk_holdernumber.assert_called_once_with(
        ts_code="600600.SH",
        start_date="20230101",
        end_date="20240101",
        fields=module.stk_holdernumber_fields,
    )
    pd.testing.assert_frame_equal(result, mock_data)


def test_download_stk_holdernumber_all_data(downloader_ts_module, monkeypatch):
    """不传日期时 start_date/end_date 均为空字符串（获取全量历史）。"""
    module, ts_stub, pro_stub = downloader_ts_module
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")

    pro_stub.stk_holdernumber = Mock(return_value=pd.DataFrame())

    module.download_stk_holdernumber(ts_code="600600.SH")

    pro_stub.stk_holdernumber.assert_called_once_with(
        ts_code="600600.SH",
        start_date="",
        end_date="",
        fields=module.stk_holdernumber_fields,
    )


def test_download_history_data_stock_hk_ts_missing_token_raises(
    downloader_ts_module, monkeypatch
):
    module, ts_stub, _ = downloader_ts_module
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)

    with pytest.raises(ConnectionError, match="Tushare token is missing"):
        module.download_history_data_stock_hk_ts(
            stock_id="00700",
            start_date="2024-01-01",
            end_date="2024-01-05",
        )

    ts_stub.pro_api.assert_not_called()


def test_download_history_data_stock_hk_ts_success(downloader_ts_module, monkeypatch):
    module, ts_stub, pro_stub = downloader_ts_module
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")

    pro_stub.hk_daily_adj.return_value = pd.DataFrame(
        {
            "ts_code": ["00700.HK", "00700.HK"],
            "trade_date": ["20240105", "20240104"],
            "open": [391, 388],
            "high": [395, 390],
            "low": [389, 386],
            "close": [394, 389],
            "change": [5, 1],
            "pct_change": [1, 0],
            "vol": [1020300, 980000],
            "amount": [401020300, 398000000],
            "turnover_ratio": [1, 0],
        }
    )

    result = module.download_history_data_stock_hk_ts(
        stock_id="00700",
        start_date="2024-01-01",
        end_date="2024/01/05",
    )

    ts_stub.pro_api.assert_called_once_with(token="test_token_123")
    pro_stub.hk_daily_adj.assert_called_once_with(
        ts_code="00700.HK",
        trade_date="",
        start_date="20240101",
        end_date="20240105",
        fields=module.hk_daily_adj_fields,
    )
    assert list(result.columns) == module.hk_history_columns
    assert result.dtypes.apply(str).to_dict() == _expected_hk_history_dtypes(module)
    assert result[module.COL_STOCK_ID].tolist() == ["00700", "00700"]
    assert result[module.COL_CHANGE_RATE].tolist() == [1.0, 0.0]
    assert result[module.COL_TURNOVER_RATE].tolist() == [1.0, 0.0]
    assert result[module.COL_VOLUME].tolist() == [1020300.0, 980000.0]


def test_download_history_data_stock_hk_ts_unsupported_period_raises(
    downloader_ts_module, monkeypatch
):
    module, ts_stub, pro_stub = downloader_ts_module
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")

    with pytest.raises(ValueError, match="Only daily period is supported"):
        module.download_history_data_stock_hk_ts(
            stock_id="00700",
            start_date="20240101",
            end_date="20240105",
            period=module.PeriodType.WEEKLY,
        )

    ts_stub.pro_api.assert_not_called()
    pro_stub.hk_daily_adj.assert_not_called()


@pytest.mark.parametrize("adjust", [pytest.param(""), pytest.param("qfq")])
def test_download_history_data_stock_hk_ts_unsupported_adjust_raises(
    downloader_ts_module, monkeypatch, adjust
):
    module, ts_stub, pro_stub = downloader_ts_module
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")

    with pytest.raises(ValueError, match="Only HFQ adjust is supported"):
        module.download_history_data_stock_hk_ts(
            stock_id="00700",
            start_date="20240101",
            end_date="20240105",
            adjust=module.AdjustType(adjust),
        )

    ts_stub.pro_api.assert_not_called()
    pro_stub.hk_daily_adj.assert_not_called()


@pytest.mark.parametrize("stock_id", ["700", "0700", "00700.HK"])
def test_download_history_data_stock_hk_ts_invalid_stock_id_raises(
    downloader_ts_module, monkeypatch, stock_id
):
    module, ts_stub, pro_stub = downloader_ts_module
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")

    with pytest.raises(ValueError, match="Stock ID must be 5 digits."):
        module.download_history_data_stock_hk_ts(
            stock_id=stock_id,
            start_date="20240101",
            end_date="20240105",
        )

    ts_stub.pro_api.assert_not_called()
    pro_stub.hk_daily_adj.assert_not_called()


def test_download_history_data_stock_hk_ts_empty_result(
    downloader_ts_module, monkeypatch
):
    module, ts_stub, pro_stub = downloader_ts_module
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")

    pro_stub.hk_daily_adj.return_value = pd.DataFrame(
        columns=module.hk_daily_adj_fields
    )

    result = module.download_history_data_stock_hk_ts(
        stock_id="00700",
        start_date="20240101",
        end_date="20240105",
    )

    ts_stub.pro_api.assert_called_once_with(token="test_token_123")
    pro_stub.hk_daily_adj.assert_called_once_with(
        ts_code="00700.HK",
        trade_date="",
        start_date="20240101",
        end_date="20240105",
        fields=module.hk_daily_adj_fields,
    )
    assert list(result.columns) == module.hk_history_columns
    assert result.empty
    assert result.dtypes.apply(str).to_dict() == _expected_hk_history_dtypes(module)


def test_download_history_data_stock_hk_ts_single_day_uses_trade_date(
    downloader_ts_module, monkeypatch
):
    module, ts_stub, pro_stub = downloader_ts_module
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")
    monkeypatch.setenv("TUSHARE_HK_DAILY_ADJ_MIN_INTERVAL_SECONDS", "0")

    pro_stub.hk_daily_adj.return_value = pd.DataFrame(
        {
            "ts_code": ["00700.HK", "00005.HK"],
            "trade_date": ["20240105", "20240105"],
            "open": [391, 61],
            "high": [395, 62],
            "low": [389, 60],
            "close": [394, 61.5],
            "change": [5, 0.5],
            "pct_change": [1, 0.8],
            "vol": [1020300, 880000],
            "amount": [401020300, 53800000],
            "turnover_ratio": [1, 0.4],
        }
    )

    result = module.download_history_data_stock_hk_ts(
        stock_id="00700",
        start_date="2024/01/05",
        end_date="2024-01-05",
    )

    ts_stub.pro_api.assert_called_once_with(token="test_token_123")
    pro_stub.hk_daily_adj.assert_called_once_with(
        ts_code="",
        trade_date="20240105",
        start_date="",
        end_date="20240105",
        fields=module.hk_daily_adj_fields,
    )
    assert list(result.columns) == module.hk_history_columns
    assert result.dtypes.apply(str).to_dict() == _expected_hk_history_dtypes(module)
    assert result[module.COL_STOCK_ID].tolist() == ["00700"]


def test_download_history_data_stock_hk_ts_single_day_reuses_trade_date_cache(
    downloader_ts_module, monkeypatch
):
    module, ts_stub, pro_stub = downloader_ts_module
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")
    monkeypatch.setenv("TUSHARE_HK_DAILY_ADJ_MIN_INTERVAL_SECONDS", "0")

    pro_stub.hk_daily_adj.return_value = pd.DataFrame(
        {
            "ts_code": ["00700.HK", "00005.HK"],
            "trade_date": ["20240105", "20240105"],
            "open": [391, 61],
            "high": [395, 62],
            "low": [389, 60],
            "close": [394, 61.5],
            "change": [5, 0.5],
            "pct_change": [1, 0.8],
            "vol": [1020300, 880000],
            "amount": [401020300, 53800000],
            "turnover_ratio": [1, 0.4],
        }
    )

    first = module.download_history_data_stock_hk_ts(
        stock_id="00700",
        start_date="20240105",
        end_date="20240105",
    )
    second = module.download_history_data_stock_hk_ts(
        stock_id="00005",
        start_date="20240105",
        end_date="20240105",
    )

    ts_stub.pro_api.assert_called_once_with(token="test_token_123")
    pro_stub.hk_daily_adj.assert_called_once_with(
        ts_code="",
        trade_date="20240105",
        start_date="",
        end_date="20240105",
        fields=module.hk_daily_adj_fields,
    )
    assert first[module.COL_STOCK_ID].tolist() == ["00700"]
    assert second[module.COL_STOCK_ID].tolist() == ["00005"]


def test_download_history_data_stock_hk_ts_multi_day_uses_throttle(
    downloader_ts_module, monkeypatch
):
    """Multi-day path must go through the rate-limit throttle."""
    module, ts_stub, pro_stub = downloader_ts_module
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")
    monkeypatch.setenv("TUSHARE_HK_DAILY_ADJ_MIN_INTERVAL_SECONDS", "0")

    pro_stub.hk_daily_adj.return_value = pd.DataFrame(
        {
            "ts_code": ["00700.HK", "00700.HK"],
            "trade_date": ["20240101", "20240102"],
            "open": [380, 382],
            "high": [390, 391],
            "low": [378, 380],
            "close": [385, 388],
            "change": [5, 3],
            "pct_change": [1.3, 0.8],
            "vol": [1000000, 1100000],
            "amount": [385000000, 426800000],
            "turnover_ratio": [0.9, 1.0],
        }
    )

    result = module.download_history_data_stock_hk_ts(
        stock_id="00700",
        start_date="20240101",
        end_date="20240102",
    )

    # Multi-day path: ts_code=stock, trade_date="" — must go through throttled helper
    pro_stub.hk_daily_adj.assert_called_once_with(
        ts_code="00700.HK",
        trade_date="",
        start_date="20240101",
        end_date="20240102",
        fields=module.hk_daily_adj_fields,
    )
    assert list(result.columns) == module.hk_history_columns
    assert result[module.COL_STOCK_ID].tolist() == ["00700", "00700"]


def test_throttle_records_timestamp_even_on_failed_api_call(
    downloader_ts_module, monkeypatch, tmp_path
):
    """A failed API call must still update the state file so @retrying.retry respects the throttle."""
    module, ts_stub, pro_stub = downloader_ts_module
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")
    monkeypatch.setenv("TUSHARE_HK_DAILY_ADJ_MIN_INTERVAL_SECONDS", "0")

    state_path = str(tmp_path / "last_call")
    lock_path = str(tmp_path / "lock")
    monkeypatch.setattr(module, "_HK_DAILY_ADJ_RATE_LIMIT_STATE_PATH", state_path)
    monkeypatch.setattr(module, "_HK_DAILY_ADJ_RATE_LIMIT_LOCK_PATH", lock_path)

    pro_stub.hk_daily_adj.side_effect = RuntimeError("频率超限")

    with pytest.raises(RuntimeError, match="频率超限"):
        module._call_hk_daily_adj_throttled(
            pro_stub,
            ts_code="",
            trade_date="20240101",
            start_date="",
            end_date="20240101",
            fields=module.hk_daily_adj_fields,
        )

    # State file must be written even though the API call raised — so retries wait properly
    assert (
        tmp_path / "last_call"
    ).exists(), "State file must be written on failed call"
    recorded = float((tmp_path / "last_call").read_text())
    assert recorded > 0


if __name__ == "__main__":
    pytest.main([__file__])
