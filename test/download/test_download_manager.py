import importlib
import os
import sys
from unittest.mock import MagicMock

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from common.const import (
    COL_AMOUNT,
    COL_CLOSE,
    COL_DATE,
    COL_ETF_ID,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    COL_VOLUME,
    AdjustType,
    PeriodType,
)  # noqa: E402


def _make_manager(monkeypatch):
    dm = importlib.import_module("download.download_manager")

    mock_storage_instance = MagicMock()
    mock_downloader_instance = MagicMock()

    monkeypatch.setattr(dm, "get_storage", lambda: mock_storage_instance)
    monkeypatch.setattr(dm, "Downloader", lambda: mock_downloader_instance)

    manager = dm.DownloadManager()
    return manager, mock_storage_instance, mock_downloader_instance


class TestDownloadManager:
    def test_download_etf_history_success_daily_qfq(self, monkeypatch):
        """测试ETF历史数据下载成功 - 日频前复权"""
        manager, storage, downloader = _make_manager(monkeypatch)

        mock_etf_data = pd.DataFrame(
            {
                COL_DATE: ["2024-01-01", "2024-01-02"],
                COL_ETF_ID: ["510300", "510300"],
                "开盘": [4.5, 4.6],
                "收盘": [4.6, 4.7],
                "最高": [4.7, 4.8],
                "最低": [4.4, 4.5],
                "成交量": [1000000, 1200000],
            }
        )

        downloader.dl_etf_daily.return_value = mock_etf_data
        storage.get_last_record.return_value = None
        storage.save_etf_daily.return_value = True

        result = manager.download_etf_history(
            etf_id="510300",
            period=PeriodType.DAILY,
            start_date="20240101",
            end_date="20240102",
            adjust=AdjustType.QFQ,
        )

        assert result is True
        storage.get_last_record.assert_called_once_with("etf_daily", "510300")
        downloader.dl_etf_daily.assert_called_once_with(
            etf_id="510300",
            start_date="20240101",
            end_date="20240102",
        )
        storage.save_etf_daily.assert_called_once_with(mock_etf_data)

    def test_download_etf_history_success_weekly_hfq(self, monkeypatch):
        """测试ETF历史数据下载成功 - 周频后复权"""
        manager, storage, downloader = _make_manager(monkeypatch)

        mock_etf_data = pd.DataFrame(
            {
                COL_DATE: ["2024-01-01", "2024-01-08"],
                COL_ETF_ID: ["510500", "510500"],
                "开盘": [5.5, 5.6],
                "收盘": [5.6, 5.7],
                "最高": [5.7, 5.8],
                "最低": [5.4, 5.5],
                "成交量": [800000, 900000],
            }
        )

        downloader.dl_etf_daily.return_value = mock_etf_data
        storage.get_last_record.return_value = None
        storage.save_etf_daily.return_value = True

        result = manager.download_etf_history(
            etf_id="510500",
            period=PeriodType.WEEKLY,
            start_date="20240101",
            end_date="20240108",
            adjust=AdjustType.HFQ,
        )

        assert result is True
        storage.get_last_record.assert_called_once_with("etf_daily", "510500")
        downloader.dl_etf_daily.assert_called_once_with(
            etf_id="510500",
            start_date="20240101",
            end_date="20240108",
        )
        storage.save_etf_daily.assert_called_once_with(mock_etf_data)

    def test_download_etf_history_incremental_update(self, monkeypatch):
        """测试ETF历史数据增量更新"""
        manager, storage, downloader = _make_manager(monkeypatch)

        storage.get_last_record.return_value = {COL_DATE: "2024-01-15"}

        mock_etf_data = pd.DataFrame(
            {
                COL_DATE: ["2024-01-16", "2024-01-17"],
                COL_ETF_ID: ["510300", "510300"],
                "开盘": [4.7, 4.8],
                "收盘": [4.8, 4.9],
                "最高": [4.9, 5.0],
                "最低": [4.6, 4.7],
                "成交量": [1300000, 1400000],
            }
        )

        downloader.dl_etf_daily.return_value = mock_etf_data
        storage.save_etf_daily.return_value = True

        result = manager.download_etf_history(
            etf_id="510300",
            period=PeriodType.DAILY,
            start_date="20240101",
            end_date="20240117",
            adjust=AdjustType.QFQ,
        )

        assert result is True
        downloader.dl_etf_daily.assert_called_once_with(
            etf_id="510300",
            start_date="20240116",
            end_date="20240117",
        )
        storage.save_etf_daily.assert_called_once_with(mock_etf_data)

    def test_download_etf_history_data_up_to_date(self, monkeypatch):
        """测试ETF数据已是最新，无需下载"""
        manager, storage, downloader = _make_manager(monkeypatch)

        storage.get_last_record.return_value = {COL_DATE: "2024-01-20"}

        result = manager.download_etf_history(
            etf_id="510300",
            period=PeriodType.DAILY,
            start_date="20240101",
            end_date="20240115",
            adjust=AdjustType.QFQ,
        )

        assert result is True
        downloader.dl_etf_daily.assert_not_called()
        storage.save_etf_daily.assert_not_called()

    def test_download_etf_history_no_new_data(self, monkeypatch):
        """测试ETF无新数据可下载"""
        manager, storage, _downloader = _make_manager(monkeypatch)

        storage.get_last_record.return_value = None
        _downloader.dl_etf_daily.return_value = pd.DataFrame()

        result = manager.download_etf_history(
            etf_id="510300",
            period=PeriodType.DAILY,
            start_date="20240101",
            end_date="20240102",
            adjust=AdjustType.QFQ,
        )

        assert result is True
        storage.save_etf_daily.assert_not_called()

    def test_download_etf_history_download_failure(self, monkeypatch):
        """测试ETF下载失败"""
        manager, storage, downloader = _make_manager(monkeypatch)

        storage.get_last_record.return_value = None
        downloader.dl_etf_daily.return_value = None

        result = manager.download_etf_history(
            etf_id="510300",
            period=PeriodType.DAILY,
            start_date="20240101",
            end_date="20240102",
            adjust=AdjustType.QFQ,
        )

        assert result is False
        storage.save_etf_daily.assert_not_called()

    def test_download_etf_history_save_failure(self, monkeypatch):
        """测试ETF保存失败"""
        manager, storage, downloader = _make_manager(monkeypatch)

        mock_etf_data = pd.DataFrame(
            {
                COL_DATE: ["2024-01-01", "2024-01-02"],
                COL_ETF_ID: ["510300", "510300"],
                "开盘": [4.5, 4.6],
                "收盘": [4.6, 4.7],
                "最高": [4.7, 4.8],
                "最低": [4.4, 4.5],
                "成交量": [1000000, 1200000],
            }
        )

        downloader.dl_etf_daily.return_value = mock_etf_data
        storage.get_last_record.return_value = None
        storage.save_etf_daily.return_value = False

        result = manager.download_etf_history(
            etf_id="510300",
            period=PeriodType.DAILY,
            start_date="20240101",
            end_date="20240102",
            adjust=AdjustType.QFQ,
        )

        assert result is False
        storage.save_etf_daily.assert_called_once_with(mock_etf_data)

    def test_download_etf_history_exception_handling(self, monkeypatch):
        """测试ETF下载异常处理"""
        manager, storage, downloader = _make_manager(monkeypatch)

        storage.get_last_record.side_effect = Exception("Database error")

        result = manager.download_etf_history(
            etf_id="510300",
            period=PeriodType.DAILY,
            start_date="20240101",
            end_date="20240102",
            adjust=AdjustType.QFQ,
        )

        assert result is False
        downloader.dl_etf_daily.assert_not_called()
        storage.save_etf_daily.assert_not_called()


class TestDownloadStkHoldernumberAStock:
    def test_download_success_no_prior_data(self, monkeypatch):
        """无历史记录时，从 default_start_date 开始下载并保存"""
        manager, storage, downloader = _make_manager(monkeypatch)

        mock_df = pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "ann_date": ["20240315"],
                "end_date": ["20231231"],
                "holder_num": [450000],
            }
        )
        storage.get_last_stk_holdernumber_ann_date.return_value = None
        downloader.dl_stk_holdernumber.return_value = mock_df
        storage.save_stk_holdernumber.return_value = True

        result = manager.download_stk_holdernumber_a_stock(
            "000001", default_start_date="2020-01-01", end_date="2024-03-20"
        )

        assert result is True
        downloader.dl_stk_holdernumber.assert_called_once_with(
            ts_code="000001.SZ", start_date="2020-01-01", end_date="2024-03-20"
        )
        storage.save_stk_holdernumber.assert_called_once_with(mock_df)

    def test_download_incremental_from_last_ann_date(self, monkeypatch):
        """有历史记录时，从 last_ann_date + 1 天开始下载"""
        manager, storage, downloader = _make_manager(monkeypatch)

        storage.get_last_stk_holdernumber_ann_date.return_value = "2024-03-10"
        downloader.dl_stk_holdernumber.return_value = pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "ann_date": ["20240315"],
                "end_date": ["20231231"],
                "holder_num": [460000],
            }
        )
        storage.save_stk_holdernumber.return_value = True

        manager.download_stk_holdernumber_a_stock("000001", end_date="2024-03-20")

        downloader.dl_stk_holdernumber.assert_called_once_with(
            ts_code="000001.SZ", start_date="2024-03-11", end_date="2024-03-20"
        )

    def test_download_already_latest(self, monkeypatch):
        """last_ann_date + 1 > end_date 时跳过下载"""
        manager, storage, downloader = _make_manager(monkeypatch)

        storage.get_last_stk_holdernumber_ann_date.return_value = "2024-03-20"

        result = manager.download_stk_holdernumber_a_stock("000001", end_date="2024-03-20")

        assert result is True
        downloader.dl_stk_holdernumber.assert_not_called()
        storage.save_stk_holdernumber.assert_not_called()

    def test_download_empty_result_skipped(self, monkeypatch):
        """下载返回空 DataFrame 时跳过，不调用 save"""
        manager, storage, downloader = _make_manager(monkeypatch)

        storage.get_last_stk_holdernumber_ann_date.return_value = None
        downloader.dl_stk_holdernumber.return_value = pd.DataFrame()

        result = manager.download_stk_holdernumber_a_stock("000001", end_date="2024-03-20")

        assert result is True
        storage.save_stk_holdernumber.assert_not_called()

    def test_ts_code_sh_for_6_prefix(self, monkeypatch):
        """以 6 开头的股票代码应使用 .SH 后缀"""
        manager, storage, downloader = _make_manager(monkeypatch)

        storage.get_last_stk_holdernumber_ann_date.return_value = None
        downloader.dl_stk_holdernumber.return_value = pd.DataFrame()

        manager.download_stk_holdernumber_a_stock("600000", end_date="2024-03-20")

        call_kwargs = downloader.dl_stk_holdernumber.call_args[1]
        assert call_kwargs["ts_code"] == "600000.SH"

    def test_ts_code_sz_for_0_prefix(self, monkeypatch):
        """以 0 开头的股票代码应使用 .SZ 后缀"""
        manager, storage, downloader = _make_manager(monkeypatch)

        storage.get_last_stk_holdernumber_ann_date.return_value = None
        downloader.dl_stk_holdernumber.return_value = pd.DataFrame()

        manager.download_stk_holdernumber_a_stock("000001", end_date="2024-03-20")

        call_kwargs = downloader.dl_stk_holdernumber.call_args[1]
        assert call_kwargs["ts_code"] == "000001.SZ"


class TestDownloadTop10FloatholdersAStock:
    def test_download_success_no_prior_data(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)

        mock_df = pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "ann_date": ["20240315"],
                "end_date": ["20231231"],
                "holder_name": ["股东A"],
                "hold_amount": [12345.0],
                "hold_ratio": [2.34],
            }
        )
        storage.get_last_top10_floatholders_ann_date.return_value = None
        downloader.dl_top10_floatholders.return_value = mock_df
        storage.save_top10_floatholders.return_value = True

        result = manager.download_top10_floatholders_a_stock(
            "000001", default_start_date="2020-01-01", end_date="2024-03-20"
        )

        assert result is True
        downloader.dl_top10_floatholders.assert_called_once_with(
            ts_code="000001.SZ", start_date="2020-01-01", end_date="2024-03-20"
        )
        storage.save_top10_floatholders.assert_called_once_with(mock_df)

    def test_download_incremental_from_last_ann_date(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)

        storage.get_last_top10_floatholders_ann_date.return_value = "2024-03-10"
        downloader.dl_top10_floatholders.return_value = pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "ann_date": ["20240315"],
                "end_date": ["20231231"],
                "holder_name": ["股东A"],
                "hold_amount": [12345.0],
                "hold_ratio": [2.34],
            }
        )
        storage.save_top10_floatholders.return_value = True

        manager.download_top10_floatholders_a_stock("000001", end_date="2024-03-20")

        downloader.dl_top10_floatholders.assert_called_once_with(
            ts_code="000001.SZ", start_date="2024-03-10", end_date="2024-03-20"
        )

    def test_download_already_latest(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)

        storage.get_last_top10_floatholders_ann_date.return_value = "2024-03-20"
        downloader.dl_top10_floatholders.return_value = pd.DataFrame()

        result = manager.download_top10_floatholders_a_stock("000001", end_date="2024-03-20")

        assert result is True
        downloader.dl_top10_floatholders.assert_called_once_with(
            ts_code="000001.SZ", start_date="2024-03-20", end_date="2024-03-20"
        )
        storage.save_top10_floatholders.assert_not_called()

    def test_download_empty_result_skipped(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)

        storage.get_last_top10_floatholders_ann_date.return_value = None
        downloader.dl_top10_floatholders.return_value = pd.DataFrame()

        result = manager.download_top10_floatholders_a_stock("000001", end_date="2024-03-20")

        assert result is True
        storage.save_top10_floatholders.assert_not_called()


class TestDownloadStockHistoryProviderFallback:
    def test_download_stock_history_falls_back_after_provider_exception(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        monkeypatch.setattr(dm, "parse_stock_history_provider_order", lambda: ["baostock", "tushare"])
        storage.get_last_record.return_value = None
        fallback_df = _stock_history_df()

        def fake_provider(provider, stock_id, start_date, end_date, period, adjust):
            if provider == "baostock":
                raise RuntimeError("baostock unavailable")
            return fallback_df

        downloader.dl_history_data_stock_by_provider.side_effect = fake_provider
        storage.save_history_data_stock.return_value = True

        result = manager.download_stock_history("000001", PeriodType.DAILY, "20240101", "20240102", AdjustType.QFQ)

        assert result is True
        assert [call.args[0] for call in downloader.dl_history_data_stock_by_provider.call_args_list] == [
            "baostock",
            "tushare",
        ]
        storage.save_history_data_stock.assert_called_once()
        saved_df = storage.save_history_data_stock.call_args[0][0]
        pd.testing.assert_frame_equal(saved_df, fallback_df)
        assert storage.save_history_data_stock.call_args[0][1:] == (PeriodType.DAILY, AdjustType.QFQ)

    def test_download_stock_history_falls_back_after_empty_dataframe(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        monkeypatch.setattr(dm, "parse_stock_history_provider_order", lambda: ["baostock", "tushare"])
        storage.get_last_record.return_value = None
        fallback_df = _stock_history_df()
        downloader.dl_history_data_stock_by_provider.side_effect = [pd.DataFrame(), fallback_df]
        storage.save_history_data_stock.return_value = True

        result = manager.download_stock_history("000001", PeriodType.DAILY, "20240101", "20240102", AdjustType.QFQ)

        assert result is True
        storage.save_history_data_stock.assert_called_once()
        saved_df = storage.save_history_data_stock.call_args[0][0]
        pd.testing.assert_frame_equal(saved_df, fallback_df)
        assert storage.save_history_data_stock.call_args[0][1:] == (PeriodType.DAILY, AdjustType.QFQ)

    def test_download_stock_history_falls_back_after_missing_required_field(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        monkeypatch.setattr(dm, "parse_stock_history_provider_order", lambda: ["baostock", "tushare"])
        storage.get_last_record.return_value = None
        invalid_df = _stock_history_df().drop(columns=[COL_CLOSE])
        fallback_df = _stock_history_df()
        downloader.dl_history_data_stock_by_provider.side_effect = [invalid_df, fallback_df]
        storage.save_history_data_stock.return_value = True

        result = manager.download_stock_history("000001", PeriodType.DAILY, "20240101", "20240102", AdjustType.QFQ)

        assert result is True
        storage.save_history_data_stock.assert_called_once()
        saved_df = storage.save_history_data_stock.call_args[0][0]
        pd.testing.assert_frame_equal(saved_df, fallback_df)
        assert storage.save_history_data_stock.call_args[0][1:] == (PeriodType.DAILY, AdjustType.QFQ)

    def test_download_stock_history_short_circuits_after_first_success(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        monkeypatch.setattr(dm, "parse_stock_history_provider_order", lambda: ["baostock", "tushare", "akshare"])
        storage.get_last_record.return_value = None
        first_df = _stock_history_df()
        downloader.dl_history_data_stock_by_provider.return_value = first_df
        storage.save_history_data_stock.return_value = True

        result = manager.download_stock_history("000001", PeriodType.DAILY, "20240101", "20240102", AdjustType.QFQ)

        assert result is True
        downloader.dl_history_data_stock_by_provider.assert_called_once()

    def test_download_stock_history_save_failure_does_not_try_next_provider(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        monkeypatch.setattr(dm, "parse_stock_history_provider_order", lambda: ["baostock", "tushare"])
        storage.get_last_record.return_value = None
        downloader.dl_history_data_stock_by_provider.return_value = _stock_history_df()
        storage.save_history_data_stock.return_value = False

        result = manager.download_stock_history("000001", PeriodType.DAILY, "20240101", "20240102", AdjustType.QFQ)

        assert result is False
        downloader.dl_history_data_stock_by_provider.assert_called_once()

    def test_download_stock_history_all_providers_fail_returns_false(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        monkeypatch.setattr(dm, "parse_stock_history_provider_order", lambda: ["baostock", "tushare"])
        storage.get_last_record.return_value = None
        downloader.dl_history_data_stock_by_provider.side_effect = RuntimeError("provider failed")

        result = manager.download_stock_history("000001", PeriodType.DAILY, "20240101", "20240102", AdjustType.QFQ)

        assert result is False
        storage.save_history_data_stock.assert_not_called()

    def test_download_stock_history_up_to_date_does_not_download(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        monkeypatch.setattr(dm, "parse_stock_history_provider_order", lambda: ["baostock", "tushare"])
        storage.get_last_record.return_value = {COL_DATE: "2024-01-03"}

        result = manager.download_stock_history("000001", PeriodType.DAILY, "20240101", "20240102", AdjustType.QFQ)

        assert result is True
        downloader.dl_history_data_stock_by_provider.assert_not_called()
        storage.save_history_data_stock.assert_not_called()

    def test_download_stock_history_skips_when_no_trading_days_in_incremental_window(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        storage.get_last_record.return_value = {COL_DATE: "2026-07-10"}
        monkeypatch.setattr(dm, "get_a_stock_trading_window", lambda start_date, end_date: None)

        result = manager.download_stock_history("000026", PeriodType.DAILY, "20200101", "2026-07-12", AdjustType.HFQ)

        assert result is True
        downloader.dl_history_data_stock_by_provider.assert_not_called()
        storage.save_history_data_stock.assert_not_called()

    def test_download_stock_history_uses_trading_day_window_for_provider_calls(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        monkeypatch.setattr(dm, "parse_stock_history_provider_order", lambda: ["baostock"])
        call_args = []
        monkeypatch.setattr(
            dm, "get_a_stock_trading_window",
            lambda start_date, end_date: call_args.append((start_date, end_date)) or ("20260713", "20260714"),
        )
        storage.get_last_record.return_value = {COL_DATE: "2026-07-10"}
        fallback_df = _stock_history_df()
        downloader.dl_history_data_stock_by_provider.return_value = fallback_df
        storage.save_history_data_stock.return_value = True

        result = manager.download_stock_history("000026", PeriodType.DAILY, "20200101", "2026-07-14", AdjustType.HFQ)

        assert result is True
        assert call_args == [("20260711", "2026-07-14")]
        downloader.dl_history_data_stock_by_provider.assert_called_once_with(
            "baostock", "000026", "20260713", "20260714", PeriodType.DAILY, AdjustType.HFQ
        )

    def test_download_stock_history_non_daily_skips_trading_window(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        monkeypatch.setattr(dm, "parse_stock_history_provider_order", lambda: ["baostock"])
        call_args = []
        monkeypatch.setattr(
            dm, "get_a_stock_trading_window",
            lambda start_date, end_date: call_args.append((start_date, end_date)) or ("20260713", "20260714"),
        )
        storage.get_last_record.return_value = {COL_DATE: "2026-07-10"}
        fallback_df = _stock_history_df()
        downloader.dl_history_data_stock_by_provider.return_value = fallback_df
        storage.save_history_data_stock.return_value = True

        result = manager.download_stock_history("000026", PeriodType.WEEKLY, "20200101", "2026-07-14", AdjustType.HFQ)

        assert result is True
        assert call_args == []  # get_a_stock_trading_window was NOT called
        downloader.dl_history_data_stock_by_provider.assert_called_once_with(
            "baostock", "000026", "20260711", "2026-07-14", PeriodType.WEEKLY, AdjustType.HFQ
        )


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
