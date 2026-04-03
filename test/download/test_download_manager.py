import importlib
import os
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from common.const import COL_DATE, COL_ETF_ID, AdjustType, PeriodType  # noqa: E402


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

        result = manager.download_stk_holdernumber_a_stock(
            "000001", end_date="2024-03-20"
        )

        assert result is True
        downloader.dl_stk_holdernumber.assert_not_called()
        storage.save_stk_holdernumber.assert_not_called()

    def test_download_empty_result_skipped(self, monkeypatch):
        """下载返回空 DataFrame 时跳过，不调用 save"""
        manager, storage, downloader = _make_manager(monkeypatch)

        storage.get_last_stk_holdernumber_ann_date.return_value = None
        downloader.dl_stk_holdernumber.return_value = pd.DataFrame()

        result = manager.download_stk_holdernumber_a_stock(
            "000001", end_date="2024-03-20"
        )

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


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
