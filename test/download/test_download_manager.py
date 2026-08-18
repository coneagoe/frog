import importlib
import os
import sys
from unittest.mock import MagicMock

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import download.download_manager as dm  # noqa: E402
from common.const import (
    COL_AMOUNT,
    COL_CLOSE,
    COL_DATE,
    COL_ETF_ID,
    COL_HIGH,
    COL_INDEX_CODE,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    COL_VOLUME,
    AdjustType,
    PeriodType,
)  # noqa: E402
from download.core_indexes import CORE_INDEX_TS_CODES  # noqa: E402


def _make_manager(monkeypatch):
    dm = importlib.import_module("download.download_manager")

    mock_storage_instance = MagicMock()
    mock_downloader_instance = MagicMock()

    monkeypatch.setattr(dm, "get_storage", lambda: mock_storage_instance)
    monkeypatch.setattr(dm, "Downloader", lambda: mock_downloader_instance)

    manager = dm.DownloadManager()
    return manager, mock_storage_instance, mock_downloader_instance


class TestDownloadManager:
    def test_prepare_etf_flow_index_context_exposes_manager_seam_for_mapped_etf(self):
        from download.download_manager import prepare_etf_flow_index_context
        from download.etf_index_mapping import ETFIndexMappingStatus

        context = prepare_etf_flow_index_context("159915.SZ")

        assert context.should_calculate is True
        assert context.normalized_etf_code == "159915"
        assert context.index_ts_code == "399006.SZ"
        assert context.diagnostic.status == ETFIndexMappingStatus.MAPPED

    def test_prepare_etf_flow_index_context_exposes_manager_seam_for_missing_mapping(self):
        from download.download_manager import prepare_etf_flow_index_context
        from download.etf_index_mapping import ETFIndexMappingStatus

        context = prepare_etf_flow_index_context("560000.SH")

        assert context.should_calculate is False
        assert context.normalized_etf_code == "560000"
        assert context.index_ts_code is None
        assert context.diagnostic.status == ETFIndexMappingStatus.MISSING_MAPPING

    def test_download_etf_basic_refreshes_and_reconciles_saved_snapshot_atomically(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        etf_basic = pd.DataFrame({"ts_code": ["510300.SH"]})
        downloader.dl_etf_basic.return_value = etf_basic
        storage.refresh_etf_basic_and_reconcile.return_value = True

        result = manager.download_etf_basic()

        assert result is True
        storage.refresh_etf_basic_and_reconcile.assert_called_once_with(etf_basic)

    def test_download_etf_basic_does_not_reconcile_failed_or_empty_refreshes(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        etf_basic = pd.DataFrame({"ts_code": ["510300.SH"]})

        downloader.dl_etf_basic.return_value = pd.DataFrame()
        assert manager.download_etf_basic() is False
        storage.refresh_etf_basic_and_reconcile.assert_not_called()

        downloader.dl_etf_basic.return_value = etf_basic
        storage.refresh_etf_basic_and_reconcile.return_value = False
        assert manager.download_etf_basic() is False
        storage.refresh_etf_basic_and_reconcile.assert_called_once_with(etf_basic)

    def test_download_etf_basic_returns_false_when_reconciliation_fails(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        etf_basic = pd.DataFrame({"ts_code": ["510300.SH"]})
        downloader.dl_etf_basic.return_value = etf_basic
        storage.refresh_etf_basic_and_reconcile.return_value = False

        result = manager.download_etf_basic()

        assert result is False
        storage.refresh_etf_basic_and_reconcile.assert_called_once_with(etf_basic)

    def test_download_etf_basic_download_error_does_not_save_or_reconcile(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        downloader.dl_etf_basic.side_effect = RuntimeError("provider unavailable")

        result = manager.download_etf_basic()

        assert result is False
        storage.refresh_etf_basic_and_reconcile.assert_not_called()

    def test_download_etf_share_size_saves_rows(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        df = pd.DataFrame(
            [
                {
                    "基金代码": "510300",
                    "日期": "2024-01-05",
                    "收盘": 3.5,
                    "单位净值": 3.48,
                    "总份额": 123.4,
                    "总规模": 432.1,
                }
            ]
        )
        downloader.dl_etf_share_size.return_value = df
        storage.save_etf_share_size.return_value = True

        result = manager.download_etf_share_size(ts_code="510300", start_date="20240101", end_date="20240105")

        assert result is True
        downloader.dl_etf_share_size.assert_called_once_with(
            ts_code="510300",
            trade_date="",
            start_date="20240101",
            end_date="20240105",
        )
        storage.save_etf_share_size.assert_called_once_with(df)

    def test_download_etf_share_size_empty_response_is_successful_noop(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        downloader.dl_etf_share_size.return_value = pd.DataFrame(
            columns=["基金代码", "日期", "收盘", "单位净值", "总份额", "总规模"]
        )

        result = manager.download_etf_share_size(trade_date="20240105")

        assert result is True
        storage.save_etf_share_size.assert_not_called()

    def test_download_index_daily_turnover_saves_rows(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        df = pd.DataFrame(
            [
                {
                    COL_INDEX_CODE: "000300.SH",
                    COL_DATE: "2024-01-05",
                    COL_CLOSE: 3350.5,
                    COL_AMOUNT: 123456789.0,
                }
            ]
        )
        downloader.dl_index_daily_turnover.return_value = df
        storage.save_index_daily_turnover.return_value = True

        result = manager.download_index_daily_turnover(
            ts_code="000300.SH",
            start_date="20240101",
            end_date="20240105",
        )

        assert result is True
        downloader.dl_index_daily_turnover.assert_called_once_with(
            ts_code="000300.SH",
            trade_date="",
            start_date="20240101",
            end_date="20240105",
        )
        storage.save_index_daily_turnover.assert_called_once_with(df)

    def test_download_index_daily_turnover_empty_response_is_successful_noop(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        downloader.dl_index_daily_turnover.return_value = pd.DataFrame(
            columns=[COL_INDEX_CODE, COL_DATE, COL_CLOSE, COL_AMOUNT]
        )

        result = manager.download_index_daily_turnover(trade_date="20240105")

        assert result is True
        storage.save_index_daily_turnover.assert_not_called()

    def test_download_core_index_daily_turnover_requests_pinned_indexes(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        df = pd.DataFrame(
            [
                {
                    COL_INDEX_CODE: "000300.SH",
                    COL_DATE: "2024-01-05",
                    COL_CLOSE: 3350.5,
                    COL_AMOUNT: 123456789.0,
                }
            ]
        )
        downloader.dl_index_daily_turnover.return_value = df
        storage.save_index_daily_turnover.return_value = True

        result = manager.download_core_index_daily_turnover(start_date="20240101", end_date="20240105")

        assert result is True
        assert downloader.dl_index_daily_turnover.call_count == len(CORE_INDEX_TS_CODES)
        assert storage.save_index_daily_turnover.call_count == len(CORE_INDEX_TS_CODES)
        requested_codes = [call.kwargs["ts_code"] for call in downloader.dl_index_daily_turnover.call_args_list]
        assert requested_codes == list(CORE_INDEX_TS_CODES.values())

    def test_download_forecast_reports_saved_rows(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        forecast = pd.DataFrame({"股票代码": ["600001", "000001"]})
        forecast.attrs["source_rows"] = 3
        downloader.dl_forecast.return_value = forecast
        storage.save_forecasts.return_value = True

        result = manager.download_forecast(ann_date="2025-01-01")

        assert result.announcement_date == "2025-01-01"
        assert result.source_rows == 3
        assert result.a_share_rows == 2
        assert result.saved is True
        downloader.dl_forecast.assert_called_once_with(ann_date="2025-01-01")
        storage.save_forecasts.assert_called_once_with(forecast)

    def test_download_forecast_reports_saved_empty_result(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        forecast = pd.DataFrame()
        downloader.dl_forecast.return_value = forecast
        storage.save_forecasts.return_value = True

        result = manager.download_forecast(ann_date="2025-01-01")

        assert result.announcement_date == "2025-01-01"
        assert result.source_rows == 0
        assert result.a_share_rows == 0
        assert result.saved is True
        storage.save_forecasts.assert_called_once_with(forecast)

    def test_download_forecast_reports_source_rows_when_normalization_excludes_all_records(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        forecast = pd.DataFrame()
        forecast.attrs["source_rows"] = 3
        downloader.dl_forecast.return_value = forecast
        storage.save_forecasts.return_value = True

        result = manager.download_forecast(ann_date="2025-01-01")

        assert result == dm.ForecastDownloadResult("2025-01-01", 3, 0, True)
        storage.save_forecasts.assert_called_once_with(forecast)

    def test_download_forecast_reports_unsaved_provider_none(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        downloader.dl_forecast.return_value = None

        result = manager.download_forecast(ann_date="2025-01-01")

        assert result.announcement_date == "2025-01-01"
        assert result.source_rows == 0
        assert result.a_share_rows == 0
        assert result.saved is False
        storage.save_forecasts.assert_not_called()

    def test_download_forecast_reports_unsaved_provider_error(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        downloader.dl_forecast.side_effect = RuntimeError("provider unavailable")

        result = manager.download_forecast(ann_date="2025-01-01")

        assert result.announcement_date == "2025-01-01"
        assert result.source_rows == 0
        assert result.a_share_rows == 0
        assert result.saved is False
        storage.save_forecasts.assert_not_called()

    def test_download_forecast_reports_unsaved_persistence_result(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        forecast = pd.DataFrame({"股票代码": ["600001"]})
        downloader.dl_forecast.return_value = forecast
        storage.save_forecasts.return_value = False

        result = manager.download_forecast(ann_date="2025-01-01")

        assert result.announcement_date == "2025-01-01"
        assert result.source_rows == 1
        assert result.a_share_rows == 1
        assert result.saved is False
        storage.save_forecasts.assert_called_once_with(forecast)

    def test_download_forecast_reports_unsaved_persistence_error(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        downloader.dl_forecast.return_value = pd.DataFrame({"股票代码": ["600001"]})
        storage.save_forecasts.side_effect = RuntimeError("database unavailable")

        result = manager.download_forecast(ann_date="2025-01-01")

        assert result.announcement_date == "2025-01-01"
        assert result.source_rows == 0
        assert result.a_share_rows == 0
        assert result.saved is False

    def test_all_empty_providers_create_missing_market_data_outcome(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        storage.get_last_record.return_value = None
        monkeypatch.setattr(dm, "get_a_stock_trading_window", lambda *_: ("20260728", "20260728"))
        downloader.dl_history_data_stock_by_provider.return_value = pd.DataFrame()
        outcome = manager.download_stock_history_outcome(
            "300996", PeriodType.DAILY, "20260728", "20260728", AdjustType.BFQ
        )
        assert outcome.classification == "missing_market_data"
        assert {item.status for item in outcome.provider_outcomes} == {"empty"}

    def test_provider_error_without_fallback_is_warning(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        storage.get_last_record.return_value = None
        monkeypatch.setattr(dm, "get_a_stock_trading_window", lambda *_: ("20260728", "20260728"))
        downloader.dl_history_data_stock_by_provider.side_effect = RuntimeError("provider down")
        outcome = manager.download_stock_history_outcome(
            "300996", PeriodType.DAILY, "20260728", "20260728", AdjustType.BFQ
        )
        assert outcome.classification == "provider_error"
        assert any(item.detail == "provider down" for item in outcome.provider_outcomes)

    def test_provider_none_is_recorded_as_error_not_empty(self, monkeypatch):
        manager, storage, downloader = _make_manager(monkeypatch)
        storage.get_last_record.return_value = None
        monkeypatch.setattr(dm, "get_a_stock_trading_window", lambda *_: ("20260728", "20260728"))
        downloader.dl_history_data_stock_by_provider.return_value = None

        outcome = manager.download_stock_history_outcome(
            "300996", PeriodType.DAILY, "20260728", "20260728", AdjustType.BFQ
        )

        assert outcome.classification == "provider_error"
        assert {item.status for item in outcome.provider_outcomes} == {"error"}
        assert all(item.detail == "provider returned None" for item in outcome.provider_outcomes)

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

        def fake_get_a_stock_trading_window(start_date, end_date):
            call_args.append((start_date, end_date))
            return "20260713", "20260714"

        monkeypatch.setattr(
            dm,
            "get_a_stock_trading_window",
            fake_get_a_stock_trading_window,
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

        def fake_get_a_stock_trading_window(start_date, end_date):
            call_args.append((start_date, end_date))
            return "20260713", "20260714"

        monkeypatch.setattr(
            dm,
            "get_a_stock_trading_window",
            fake_get_a_stock_trading_window,
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


def _hk_stock_history_df(stock_id="00700"):
    return pd.DataFrame(
        {
            COL_DATE: [pd.Timestamp("2026-01-02")],
            COL_STOCK_ID: [stock_id],
            COL_OPEN: [300.0],
            COL_HIGH: [302.0],
            COL_LOW: [299.0],
            COL_CLOSE: [301.0],
            COL_VOLUME: [1000],
            COL_AMOUNT: [300000.0],
        }
    )


class TestDownloadHkGgtHistoryFallback:
    def test_download_hk_ggt_history_uses_yfinance_then_falls_back(self, monkeypatch):
        import download.download_manager as dm
        from download.download_manager import DownloadManager

        monkeypatch.delenv("DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER", raising=False)
        storage = MagicMock()
        storage.get_last_record.return_value = None
        storage.save_history_data_hk_stock.return_value = True
        monkeypatch.setattr(dm, "get_storage", lambda: storage)
        manager = DownloadManager()
        download_mock = MagicMock(
            side_effect=[RuntimeError("Yahoo unavailable"), RuntimeError("rate limited"), _hk_stock_history_df()]
        )
        monkeypatch.setattr(manager.downloader, "dl_history_data_stock_hk_by_provider", download_mock)

        assert manager.download_hk_ggt_history("00700", PeriodType.DAILY, "2026-01-01", "2026-01-03", AdjustType.BFQ)
        assert [call.args[0] for call in download_mock.call_args_list] == ["akshare", "yfinance", "tushare"]
        storage.save_history_data_hk_stock.assert_called_once()

    def test_download_hk_ggt_history_falls_back_to_akshare_on_tushare_exception(self, monkeypatch):
        from unittest.mock import MagicMock

        import download.download_manager as dm
        from download.download_manager import DownloadManager

        storage = MagicMock()
        storage.get_last_record.return_value = None
        storage.save_history_data_hk_stock.return_value = True
        monkeypatch.setattr(dm, "get_storage", lambda: storage)
        monkeypatch.setattr(dm, "parse_hk_stock_history_provider_order", lambda: ["tushare", "akshare"])

        hk_df = _hk_stock_history_df()
        manager = DownloadManager()
        download_mock = MagicMock(side_effect=[RuntimeError("unsupported adjust"), hk_df])
        monkeypatch.setattr(manager.downloader, "dl_history_data_stock_hk_by_provider", download_mock)

        assert (
            manager.download_hk_ggt_history("00700", PeriodType.DAILY, "2026-01-01", "2026-01-03", AdjustType.BFQ)
            is True
        )

        assert [call.args[0] for call in download_mock.call_args_list] == ["tushare", "akshare"]
        storage.save_history_data_hk_stock.assert_called_once()

    def test_download_hk_ggt_history_falls_back_on_empty_dataframe(self, monkeypatch):
        from unittest.mock import MagicMock

        import download.download_manager as dm
        from download.download_manager import DownloadManager

        storage = MagicMock()
        storage.get_last_record.return_value = None
        storage.save_history_data_hk_stock.return_value = True
        monkeypatch.setattr(dm, "get_storage", lambda: storage)
        monkeypatch.setattr(dm, "parse_hk_stock_history_provider_order", lambda: ["tushare", "akshare"])

        fallback_df = _hk_stock_history_df()
        manager = DownloadManager()
        download_mock = MagicMock(side_effect=[pd.DataFrame(), fallback_df])
        monkeypatch.setattr(manager.downloader, "dl_history_data_stock_hk_by_provider", download_mock)

        assert (
            manager.download_hk_ggt_history("00700", PeriodType.DAILY, "2026-01-01", "2026-01-03", AdjustType.BFQ)
            is True
        )
        storage.save_history_data_hk_stock.assert_called_once()

    def test_download_hk_ggt_history_falls_back_on_missing_column(self, monkeypatch):
        from unittest.mock import MagicMock

        import download.download_manager as dm
        from download.download_manager import DownloadManager

        storage = MagicMock()
        storage.get_last_record.return_value = None
        storage.save_history_data_hk_stock.return_value = True
        monkeypatch.setattr(dm, "get_storage", lambda: storage)
        monkeypatch.setattr(dm, "parse_hk_stock_history_provider_order", lambda: ["tushare", "akshare"])

        invalid_df = _hk_stock_history_df().drop(columns=[COL_CLOSE])
        fallback_df = _hk_stock_history_df()
        manager = DownloadManager()
        download_mock = MagicMock(side_effect=[invalid_df, fallback_df])
        monkeypatch.setattr(manager.downloader, "dl_history_data_stock_hk_by_provider", download_mock)

        assert (
            manager.download_hk_ggt_history("00700", PeriodType.DAILY, "2026-01-01", "2026-01-03", AdjustType.BFQ)
            is True
        )
        storage.save_history_data_hk_stock.assert_called_once()

    def test_download_hk_ggt_history_falls_back_on_bad_numeric(self, monkeypatch):
        from unittest.mock import MagicMock

        import download.download_manager as dm
        from download.download_manager import DownloadManager

        storage = MagicMock()
        storage.get_last_record.return_value = None
        storage.save_history_data_hk_stock.return_value = True
        monkeypatch.setattr(dm, "get_storage", lambda: storage)
        monkeypatch.setattr(dm, "parse_hk_stock_history_provider_order", lambda: ["tushare", "akshare"])

        invalid_df = _hk_stock_history_df()
        invalid_df[COL_CLOSE] = "bad_value"
        fallback_df = _hk_stock_history_df()
        manager = DownloadManager()
        download_mock = MagicMock(side_effect=[invalid_df, fallback_df])
        monkeypatch.setattr(manager.downloader, "dl_history_data_stock_hk_by_provider", download_mock)

        assert (
            manager.download_hk_ggt_history("00700", PeriodType.DAILY, "2026-01-01", "2026-01-03", AdjustType.BFQ)
            is True
        )
        storage.save_history_data_hk_stock.assert_called_once()

    def test_download_hk_ggt_history_short_circuits_after_first_success(self, monkeypatch):
        from unittest.mock import MagicMock

        import download.download_manager as dm
        from download.download_manager import DownloadManager

        storage = MagicMock()
        storage.get_last_record.return_value = None
        storage.save_history_data_hk_stock.return_value = True
        monkeypatch.setattr(dm, "get_storage", lambda: storage)
        monkeypatch.setattr(dm, "parse_hk_stock_history_provider_order", lambda: ["tushare", "akshare"])

        first_df = _hk_stock_history_df()
        manager = DownloadManager()
        download_mock = MagicMock(return_value=first_df)
        monkeypatch.setattr(manager.downloader, "dl_history_data_stock_hk_by_provider", download_mock)

        assert (
            manager.download_hk_ggt_history("00700", PeriodType.DAILY, "2026-01-01", "2026-01-03", AdjustType.BFQ)
            is True
        )
        download_mock.assert_called_once()

    def test_download_hk_ggt_history_all_providers_fail_returns_false(self, monkeypatch):
        from unittest.mock import MagicMock

        import download.download_manager as dm
        from download.download_manager import DownloadManager

        storage = MagicMock()
        storage.get_last_record.return_value = None
        storage.save_history_data_hk_stock.return_value = True
        monkeypatch.setattr(dm, "get_storage", lambda: storage)
        monkeypatch.setattr(dm, "parse_hk_stock_history_provider_order", lambda: ["tushare", "akshare"])

        manager = DownloadManager()
        download_mock = MagicMock(side_effect=RuntimeError("provider failed"))
        monkeypatch.setattr(manager.downloader, "dl_history_data_stock_hk_by_provider", download_mock)

        assert (
            manager.download_hk_ggt_history("00700", PeriodType.DAILY, "2026-01-01", "2026-01-03", AdjustType.BFQ)
            is False
        )
        storage.save_history_data_hk_stock.assert_not_called()

    def test_download_hk_ggt_history_save_failure_does_not_try_next_provider(self, monkeypatch):
        from unittest.mock import MagicMock

        import download.download_manager as dm
        from download.download_manager import DownloadManager

        storage = MagicMock()
        storage.get_last_record.return_value = None
        storage.save_history_data_hk_stock.return_value = False
        monkeypatch.setattr(dm, "get_storage", lambda: storage)
        monkeypatch.setattr(dm, "parse_hk_stock_history_provider_order", lambda: ["tushare", "akshare"])

        first_df = _hk_stock_history_df()
        manager = DownloadManager()
        download_mock = MagicMock(return_value=first_df)
        monkeypatch.setattr(manager.downloader, "dl_history_data_stock_hk_by_provider", download_mock)

        assert (
            manager.download_hk_ggt_history("00700", PeriodType.DAILY, "2026-01-01", "2026-01-03", AdjustType.BFQ)
            is False
        )
        download_mock.assert_called_once()
        storage.save_history_data_hk_stock.assert_called_once()
