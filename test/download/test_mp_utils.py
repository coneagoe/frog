import os
import sys
from unittest.mock import MagicMock

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import download.provider_order  # noqa: E402
from common.const import (
    COL_AMOUNT,
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    COL_VOLUME,
    AdjustType,
    PeriodType,
    SecurityType,
)  # noqa: E402
from download import mp_utils  # noqa: E402


def _stock_history_df(stock_id="000001"):
    return pd.DataFrame(
        {
            COL_DATE: [pd.Timestamp("2024-01-01")],
            COL_STOCK_ID: [stock_id],
            COL_OPEN: [10.0],
            COL_HIGH: [11.0],
            COL_LOW: [9.0],
            COL_CLOSE: [10.5],
            COL_VOLUME: [1000.0],
            COL_AMOUNT: [10000.0],
        }
    )


def test_history_batch_worker_falls_back_for_stock_download(monkeypatch):
    storage = MagicMock()
    storage.get_last_record.return_value = None
    storage.save_history_data_stock.return_value = True
    monkeypatch.setattr(mp_utils, "get_storage", lambda: storage)
    monkeypatch.setattr(download.provider_order, "parse_stock_history_provider_order", lambda: ["baostock", "tushare"])

    downloader = MagicMock()
    fallback_df = _stock_history_df()

    def fake_provider(provider, security_id, start_date, end_date, period, adjust):
        if provider == "baostock":
            raise RuntimeError("baostock unavailable")
        return fallback_df

    downloader.dl_history_data_stock_by_provider.side_effect = fake_provider
    monkeypatch.setattr(mp_utils, "Downloader", lambda: downloader)

    result = mp_utils._history_batch_worker(
        SecurityType.STOCK,
        ["000001"],
        PeriodType.DAILY.value,
        AdjustType.QFQ.value,
        "20240101",
        "20240102",
    )

    assert result.success == 1
    assert result.failed == 0
    assert [call.args[0] for call in downloader.dl_history_data_stock_by_provider.call_args_list] == [
        "baostock",
        "tushare",
    ]
    storage.save_history_data_stock.assert_called_once()
    saved_df = storage.save_history_data_stock.call_args[0][0]
    pd.testing.assert_frame_equal(saved_df, fallback_df)
    assert storage.save_history_data_stock.call_args[0][1:] == (PeriodType.DAILY, AdjustType.QFQ)


def test_history_batch_worker_save_failure_does_not_try_next_stock_provider(monkeypatch):
    storage = MagicMock()
    storage.get_last_record.return_value = None
    storage.save_history_data_stock.return_value = False
    monkeypatch.setattr(mp_utils, "get_storage", lambda: storage)
    monkeypatch.setattr(download.provider_order, "parse_stock_history_provider_order", lambda: ["baostock", "tushare"])

    downloader = MagicMock()
    downloader.dl_history_data_stock_by_provider.return_value = _stock_history_df()
    monkeypatch.setattr(mp_utils, "Downloader", lambda: downloader)

    result = mp_utils._history_batch_worker(
        SecurityType.STOCK,
        ["000001"],
        PeriodType.DAILY.value,
        AdjustType.QFQ.value,
        "20240101",
        "20240102",
    )

    assert result.success == 0
    assert result.failed == 1
    downloader.dl_history_data_stock_by_provider.assert_called_once()


def test_history_batch_worker_keeps_etf_single_provider_path(monkeypatch):
    storage = MagicMock()
    storage.get_last_record.return_value = None
    storage.save_history_data_etf.return_value = True
    monkeypatch.setattr(mp_utils, "get_storage", lambda: storage)

    downloader = MagicMock()
    downloader.dl_history_data_etf.return_value = pd.DataFrame({COL_DATE: [pd.Timestamp("2024-01-01")]})
    monkeypatch.setattr(mp_utils, "Downloader", lambda: downloader)

    result = mp_utils._history_batch_worker(
        SecurityType.ETF,
        ["510300"],
        PeriodType.DAILY.value,
        AdjustType.QFQ.value,
        "20240101",
        "20240102",
    )

    assert result.success == 1
    assert result.failed == 0
    downloader.dl_history_data_stock_by_provider.assert_not_called()
    downloader.dl_history_data_etf.assert_called_once()


def test_history_batch_worker_skips_stock_provider_when_no_trading_days(monkeypatch):
    storage = MagicMock()
    storage.get_last_record.return_value = {COL_DATE: "2026-07-10"}
    monkeypatch.setattr(mp_utils, "get_storage", lambda: storage)
    monkeypatch.setattr(mp_utils, "get_a_stock_trading_window", lambda start_date, end_date: None)

    downloader = MagicMock()
    monkeypatch.setattr(mp_utils, "Downloader", lambda: downloader)

    result = mp_utils._history_batch_worker(
        SecurityType.STOCK,
        ["000026"],
        PeriodType.DAILY.value,
        AdjustType.HFQ.value,
        "20200101",
        "2026-07-12",
    )

    assert result.success == 1
    assert result.failed == 0
    downloader.dl_history_data_stock_by_provider.assert_not_called()
    storage.save_history_data_stock.assert_not_called()


def test_history_batch_worker_uses_trading_day_window_for_stock_provider(monkeypatch):
    storage = MagicMock()
    storage.get_last_record.return_value = {COL_DATE: "2026-07-10"}
    storage.save_history_data_stock.return_value = True
    monkeypatch.setattr(mp_utils, "get_storage", lambda: storage)
    monkeypatch.setattr(download.provider_order, "parse_stock_history_provider_order", lambda: ["baostock"])
    monkeypatch.setattr(mp_utils, "get_a_stock_trading_window", lambda start_date, end_date: ("20260713", "20260714"))

    downloader = MagicMock()
    fallback_df = _stock_history_df("000026")
    downloader.dl_history_data_stock_by_provider.return_value = fallback_df
    monkeypatch.setattr(mp_utils, "Downloader", lambda: downloader)

    result = mp_utils._history_batch_worker(
        SecurityType.STOCK,
        ["000026"],
        PeriodType.DAILY.value,
        AdjustType.HFQ.value,
        "20200101",
        "2026-07-14",
    )

    assert result.success == 1
    assert result.failed == 0
    downloader.dl_history_data_stock_by_provider.assert_called_once_with(
        "baostock", "000026", "20260713", "20260714", PeriodType.DAILY, AdjustType.HFQ
    )


def test_history_batch_worker_does_not_use_a_stock_window_for_etf(monkeypatch):
    storage = MagicMock()
    storage.get_last_record.return_value = None
    storage.save_history_data_etf.return_value = True
    monkeypatch.setattr(mp_utils, "get_storage", lambda: storage)

    get_window = MagicMock(return_value=None)
    monkeypatch.setattr(mp_utils, "get_a_stock_trading_window", get_window)

    downloader = MagicMock()
    downloader.dl_history_data_etf.return_value = pd.DataFrame({COL_DATE: [pd.Timestamp("2026-07-13")]})
    monkeypatch.setattr(mp_utils, "Downloader", lambda: downloader)

    result = mp_utils._history_batch_worker(
        SecurityType.ETF,
        ["510300"],
        PeriodType.DAILY.value,
        AdjustType.QFQ.value,
        "20260711",
        "2026-07-14",
    )

    assert result.success == 1
    assert result.failed == 0
    get_window.assert_not_called()
