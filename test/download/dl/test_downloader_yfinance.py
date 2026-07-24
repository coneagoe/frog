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
def downloader_yf_module(monkeypatch):
    module_name = "download.dl.downloader_yfinance"
    sys.modules.pop(module_name, None)

    ticker = Mock()
    yf_stub = types.SimpleNamespace(Ticker=ticker)
    monkeypatch.setitem(sys.modules, "yfinance", yf_stub)

    module = importlib.import_module(module_name)
    module = importlib.reload(module)

    return module, ticker


def test_download_history_data_stock_hk_yf_normalizes_raw_daily_history(downloader_yf_module):
    module, ticker = downloader_yf_module
    ticker.return_value.history.return_value = pd.DataFrame(
        {
            "Open": [10.0],
            "High": [12.0],
            "Low": [9.0],
            "Close": [11.0],
            "Adj Close": [10.5],
            "Volume": [1000],
        },
        index=pd.DatetimeIndex(["2026-01-02"], tz="Asia/Hong_Kong"),
    )

    result = module.download_history_data_stock_hk_yf("03738", "2026-01-01", "2026-01-02")

    ticker.assert_called_once_with("3738.HK")
    ticker.return_value.history.assert_called_once_with(
        start="2026-01-01",
        end="2026-01-03",
        interval="1d",
        auto_adjust=False,
        actions=False,
        back_adjust=False,
        repair=False,
        prepost=False,
        raise_errors=True,
    )
    assert list(result.columns) == module.hk_history_columns
    assert result[module.COL_STOCK_ID].tolist() == ["03738"]
    assert result[module.COL_CLOSE].tolist() == [11.0]
    assert result[module.COL_AMOUNT].tolist() == [11000.0]
    assert result[module.COL_CHANGE].tolist() == [0.0]

    ticker.reset_mock()
    ticker.return_value.history.reset_mock()
    ticker.return_value.history.return_value = pd.DataFrame(
        {
            "Open": [10.0],
            "High": [12.0],
            "Low": [9.0],
            "Close": [11.0],
            "Adj Close": [10.5],
            "Volume": [1000],
        },
        index=pd.DatetimeIndex(["2026-01-02"], tz="Asia/Hong_Kong"),
    )

    module.download_history_data_stock_hk_yf("03738", "2026/01/01", "2026/01/02")

    ticker.return_value.history.assert_called_once_with(
        start="2026-01-01",
        end="2026-01-03",
        interval="1d",
        auto_adjust=False,
        actions=False,
        back_adjust=False,
        repair=False,
        prepost=False,
        raise_errors=True,
    )


@pytest.mark.parametrize("stock_id", ["700", "0700", "03738.HK", "ABCDE"])
def test_download_history_data_stock_hk_yf_rejects_invalid_ids_without_client_call(
    downloader_yf_module, stock_id
):
    module, ticker = downloader_yf_module

    with pytest.raises(ValueError, match="Stock ID must be 5 digits"):
        module.download_history_data_stock_hk_yf(stock_id, "20260101", "20260102")

    ticker.assert_not_called()


@pytest.mark.parametrize("period, adjust", [("weekly", None), (None, "qfq")])
def test_download_history_data_stock_hk_yf_rejects_unsupported_options_without_client_call(
    downloader_yf_module, period, adjust
):
    module, ticker = downloader_yf_module
    kwargs = {}
    if period is not None:
        kwargs["period"] = module.PeriodType.WEEKLY
    if adjust is not None:
        kwargs["adjust"] = module.AdjustType.QFQ

    with pytest.raises(ValueError):
        module.download_history_data_stock_hk_yf("00700", "20260101", "20260102", **kwargs)

    ticker.assert_not_called()


def test_download_history_data_stock_hk_yf_empty_result_uses_canonical_schema(downloader_yf_module):
    module, ticker = downloader_yf_module
    ticker.return_value.history.return_value = pd.DataFrame()

    result = module.download_history_data_stock_hk_yf("00700", "20260101", "20260102")

    assert result.empty
    assert list(result.columns) == module.hk_history_columns


def test_download_history_data_stock_hk_yf_missing_required_column_raises(downloader_yf_module):
    module, ticker = downloader_yf_module
    ticker.return_value.history.return_value = pd.DataFrame(
        {"Open": [1.0], "High": [2.0], "Low": [1.0], "Close": [2.0]}
    )

    with pytest.raises(ValueError, match="Missing required column 'Volume'"):
        module.download_history_data_stock_hk_yf("00700", "20260101", "20260102")


def test_download_history_data_stock_hk_yf_propagates_history_exception(downloader_yf_module):
    module, ticker = downloader_yf_module
    ticker.return_value.history.side_effect = RuntimeError("Yahoo unavailable")

    with pytest.raises(RuntimeError, match="Yahoo unavailable"):
        module.download_history_data_stock_hk_yf("00700", "20260101", "20260102")
