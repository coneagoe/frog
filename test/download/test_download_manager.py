import os
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from common.const import COL_DATE, COL_STOCK_ID, AdjustType, PeriodType  # noqa: E402
from download.download_manager import DownloadManager  # noqa: E402


class TestDownloadManager:
    def test_init_with_db_storage(self, monkeypatch):
        # Create mock instances
        mock_storage_instance = MagicMock()
        mock_downloader_instance = MagicMock()

        # Mock the get_storage function
        def mock_get_storage():
            return mock_storage_instance

        # Mock the Downloader class
        def mock_downloader_class():
            return mock_downloader_instance

        # Apply monkeypatches
        monkeypatch.setattr("download.download_manager.get_storage", mock_get_storage)
        monkeypatch.setattr(
            "download.download_manager.Downloader", mock_downloader_class
        )

        # Create manager instance
        manager = DownloadManager()

        # Assert that the mocks were used correctly
        assert manager.storage == mock_storage_instance
        assert manager.downloader == mock_downloader_instance

    def test_download_etf_history_success_daily_qfq(self, monkeypatch):
        """测试ETF历史数据下载成功 - 日频前复权"""
        # Create mock instances
        mock_storage_instance = MagicMock()
        mock_downloader_instance = MagicMock()

        # Mock the get_storage function
        def mock_get_storage():
            return mock_storage_instance

        # Mock the Downloader class
        def mock_downloader_class():
            return mock_downloader_instance

        # Apply monkeypatches
        monkeypatch.setattr("download.download_manager.get_storage", mock_get_storage)
        monkeypatch.setattr(
            "download.download_manager.Downloader", mock_downloader_class
        )

        # Create manager instance
        manager = DownloadManager()

        # Mock ETF data
        mock_etf_data = pd.DataFrame(
            {
                COL_DATE: ["2024-01-01", "2024-01-02"],
                COL_STOCK_ID: ["510300", "510300"],
                "开盘": [4.5, 4.6],
                "收盘": [4.6, 4.7],
                "最高": [4.7, 4.8],
                "最低": [4.4, 4.5],
                "成交量": [1000000, 1200000],
            }
        )

        # Mock downloader to return ETF data
        mock_downloader_instance.dl_history_data_etf.return_value = mock_etf_data

        # Mock storage methods
        mock_storage_instance.get_last_record.return_value = None  # No existing data
        mock_storage_instance.save_history_data_etf.return_value = True

        # Test the function
        result = manager.download_etf_history(
            etf_id="510300",
            period=PeriodType.DAILY,
            start_date="20240101",
            end_date="20240102",
            adjust=AdjustType.QFQ,
        )

        # Assertions
        assert result is True
        mock_storage_instance.get_last_record.assert_called_once_with(
            "history_data_daily_etf_qfq", "510300"
        )
        mock_downloader_instance.dl_history_data_etf.assert_called_once_with(
            "510300", "20240101", "20240102", PeriodType.DAILY, AdjustType.QFQ
        )
        mock_storage_instance.save_history_data_etf.assert_called_once_with(
            mock_etf_data, PeriodType.DAILY, AdjustType.QFQ
        )

    def test_download_etf_history_success_weekly_hfq(self, monkeypatch):
        """测试ETF历史数据下载成功 - 周频后复权"""
        # Create mock instances
        mock_storage_instance = MagicMock()
        mock_downloader_instance = MagicMock()

        # Mock the get_storage function
        def mock_get_storage():
            return mock_storage_instance

        # Mock the Downloader class
        def mock_downloader_class():
            return mock_downloader_instance

        # Apply monkeypatches
        monkeypatch.setattr("download.download_manager.get_storage", mock_get_storage)
        monkeypatch.setattr(
            "download.download_manager.Downloader", mock_downloader_class
        )

        # Create manager instance
        manager = DownloadManager()

        # Mock ETF data
        mock_etf_data = pd.DataFrame(
            {
                COL_DATE: ["2024-01-01", "2024-01-08"],
                COL_STOCK_ID: ["510500", "510500"],
                "开盘": [5.5, 5.6],
                "收盘": [5.6, 5.7],
                "最高": [5.7, 5.8],
                "最低": [5.4, 5.5],
                "成交量": [800000, 900000],
            }
        )

        # Mock downloader to return ETF data
        mock_downloader_instance.dl_history_data_etf.return_value = mock_etf_data

        # Mock storage methods
        mock_storage_instance.get_last_record.return_value = None  # No existing data
        mock_storage_instance.save_history_data_etf.return_value = True

        # Test the function
        result = manager.download_etf_history(
            etf_id="510500",
            period=PeriodType.WEEKLY,
            start_date="20240101",
            end_date="20240108",
            adjust=AdjustType.HFQ,
        )

        # Assertions
        assert result is True
        mock_storage_instance.get_last_record.assert_called_once_with(
            "history_data_weekly_etf_hfq", "510500"
        )
        mock_downloader_instance.dl_history_data_etf.assert_called_once_with(
            "510500", "20240101", "20240108", PeriodType.WEEKLY, AdjustType.HFQ
        )
        mock_storage_instance.save_history_data_etf.assert_called_once_with(
            mock_etf_data, PeriodType.WEEKLY, AdjustType.HFQ
        )

    def test_download_etf_history_incremental_update(self, monkeypatch):
        """测试ETF历史数据增量更新"""
        # Create mock instances
        mock_storage_instance = MagicMock()
        mock_downloader_instance = MagicMock()

        # Mock the get_storage function
        def mock_get_storage():
            return mock_storage_instance

        # Mock the Downloader class
        def mock_downloader_class():
            return mock_downloader_instance

        # Apply monkeypatches
        monkeypatch.setattr("download.download_manager.get_storage", mock_get_storage)
        monkeypatch.setattr(
            "download.download_manager.Downloader", mock_downloader_class
        )

        # Create manager instance
        manager = DownloadManager()

        # Mock existing data with latest date
        mock_last_record = {COL_DATE: "2024-01-15"}
        mock_storage_instance.get_last_record.return_value = mock_last_record

        # Mock ETF data for incremental update
        mock_etf_data = pd.DataFrame(
            {
                COL_DATE: ["2024-01-16", "2024-01-17"],
                COL_STOCK_ID: ["510300", "510300"],
                "开盘": [4.7, 4.8],
                "收盘": [4.8, 4.9],
                "最高": [4.9, 5.0],
                "最低": [4.6, 4.7],
                "成交量": [1300000, 1400000],
            }
        )

        # Mock downloader to return ETF data
        mock_downloader_instance.dl_history_data_etf.return_value = mock_etf_data

        # Mock storage methods
        mock_storage_instance.save_history_data_etf.return_value = True

        # Test the function
        result = manager.download_etf_history(
            etf_id="510300",
            period=PeriodType.DAILY,
            start_date="20240101",
            end_date="20240117",
            adjust=AdjustType.QFQ,
        )

        # Assertions
        assert result is True
        # Should start from day after last record
        mock_downloader_instance.dl_history_data_etf.assert_called_once_with(
            "510300", "20240116", "20240117", PeriodType.DAILY, AdjustType.QFQ
        )
        mock_storage_instance.save_history_data_etf.assert_called_once_with(
            mock_etf_data, PeriodType.DAILY, AdjustType.QFQ
        )

    def test_download_etf_history_data_up_to_date(self, monkeypatch):
        """测试ETF数据已是最新，无需下载"""
        # Create mock instances
        mock_storage_instance = MagicMock()
        mock_downloader_instance = MagicMock()

        # Mock the get_storage function
        def mock_get_storage():
            return mock_storage_instance

        # Mock the Downloader class
        def mock_downloader_class():
            return mock_downloader_instance

        # Apply monkeypatches
        monkeypatch.setattr("download.download_manager.get_storage", mock_get_storage)
        monkeypatch.setattr(
            "download.download_manager.Downloader", mock_downloader_class
        )

        # Create manager instance
        manager = DownloadManager()

        # Mock existing data with latest date beyond end_date
        mock_last_record = {COL_DATE: "2024-01-20"}
        mock_storage_instance.get_last_record.return_value = mock_last_record

        # Test the function
        result = manager.download_etf_history(
            etf_id="510300",
            period=PeriodType.DAILY,
            start_date="20240101",
            end_date="20240115",
            adjust=AdjustType.QFQ,
        )

        # Assertions
        assert result is True
        # Should not call downloader since data is up to date
        mock_downloader_instance.dl_history_data_etf.assert_not_called()
        mock_storage_instance.save_history_data_etf.assert_not_called()

    def test_download_etf_history_no_new_data(self, monkeypatch):
        """测试ETF无新数据可下载"""
        # Create mock instances
        mock_storage_instance = MagicMock()
        mock_downloader_instance = MagicMock()

        # Mock the get_storage function
        def mock_get_storage():
            return mock_storage_instance

        # Mock the Downloader class
        def mock_downloader_class():
            return mock_downloader_instance

        # Apply monkeypatches
        monkeypatch.setattr("download.download_manager.get_storage", mock_get_storage)
        monkeypatch.setattr(
            "download.download_manager.Downloader", mock_downloader_class
        )

        # Create manager instance
        manager = DownloadManager()

        # Mock no existing data
        mock_storage_instance.get_last_record.return_value = None

        # Mock downloader to return empty DataFrame
        mock_downloader_instance.dl_history_data_etf.return_value = pd.DataFrame()

        # Test the function
        result = manager.download_etf_history(
            etf_id="510300",
            period=PeriodType.DAILY,
            start_date="20240101",
            end_date="20240102",
            adjust=AdjustType.QFQ,
        )

        # Assertions
        assert result is True
        # Should not call save since no new data
        mock_storage_instance.save_history_data_etf.assert_not_called()

    def test_download_etf_history_download_failure(self, monkeypatch):
        """测试ETF下载失败"""
        # Create mock instances
        mock_storage_instance = MagicMock()
        mock_downloader_instance = MagicMock()

        # Mock the get_storage function
        def mock_get_storage():
            return mock_storage_instance

        # Mock the Downloader class
        def mock_downloader_class():
            return mock_downloader_instance

        # Apply monkeypatches
        monkeypatch.setattr("download.download_manager.get_storage", mock_get_storage)
        monkeypatch.setattr(
            "download.download_manager.Downloader", mock_downloader_class
        )

        # Create manager instance
        manager = DownloadManager()

        # Mock no existing data
        mock_storage_instance.get_last_record.return_value = None

        # Mock downloader to return None (download failure)
        mock_downloader_instance.dl_history_data_etf.return_value = None

        # Test the function
        result = manager.download_etf_history(
            etf_id="510300",
            period=PeriodType.DAILY,
            start_date="20240101",
            end_date="20240102",
            adjust=AdjustType.QFQ,
        )

        # Assertions
        assert result is True
        # Should not call save since download failed
        mock_storage_instance.save_history_data_etf.assert_not_called()

    def test_download_etf_history_save_failure(self, monkeypatch):
        """测试ETF保存失败"""
        # Create mock instances
        mock_storage_instance = MagicMock()
        mock_downloader_instance = MagicMock()

        # Mock the get_storage function
        def mock_get_storage():
            return mock_storage_instance

        # Mock the Downloader class
        def mock_downloader_class():
            return mock_downloader_instance

        # Apply monkeypatches
        monkeypatch.setattr("download.download_manager.get_storage", mock_get_storage)
        monkeypatch.setattr(
            "download.download_manager.Downloader", mock_downloader_class
        )

        # Create manager instance
        manager = DownloadManager()

        # Mock ETF data
        mock_etf_data = pd.DataFrame(
            {
                COL_DATE: ["2024-01-01", "2024-01-02"],
                COL_STOCK_ID: ["510300", "510300"],
                "开盘": [4.5, 4.6],
                "收盘": [4.6, 4.7],
                "最高": [4.7, 4.8],
                "最低": [4.4, 4.5],
                "成交量": [1000000, 1200000],
            }
        )

        # Mock downloader to return ETF data
        mock_downloader_instance.dl_history_data_etf.return_value = mock_etf_data

        # Mock storage methods
        mock_storage_instance.get_last_record.return_value = None  # No existing data
        mock_storage_instance.save_history_data_etf.return_value = False  # Save fails

        # Test the function
        result = manager.download_etf_history(
            etf_id="510300",
            period=PeriodType.DAILY,
            start_date="20240101",
            end_date="20240102",
            adjust=AdjustType.QFQ,
        )

        # Assertions
        assert result is False
        mock_storage_instance.save_history_data_etf.assert_called_once_with(
            mock_etf_data, PeriodType.DAILY, AdjustType.QFQ
        )

    def test_download_etf_history_exception_handling(self, monkeypatch):
        """测试ETF下载异常处理"""
        # Create mock instances
        mock_storage_instance = MagicMock()
        mock_downloader_instance = MagicMock()

        # Mock the get_storage function
        def mock_get_storage():
            return mock_storage_instance

        # Mock the Downloader class
        def mock_downloader_class():
            return mock_downloader_instance

        # Apply monkeypatches
        monkeypatch.setattr("download.download_manager.get_storage", mock_get_storage)
        monkeypatch.setattr(
            "download.download_manager.Downloader", mock_downloader_class
        )

        # Create manager instance
        manager = DownloadManager()

        # Mock storage to raise exception
        mock_storage_instance.get_last_record.side_effect = Exception("Database error")

        # Test the function
        result = manager.download_etf_history(
            etf_id="510300",
            period=PeriodType.DAILY,
            start_date="20240101",
            end_date="20240102",
            adjust=AdjustType.QFQ,
        )

        # Assertions
        assert result is False
        # Should not call downloader or save due to exception
        mock_downloader_instance.dl_history_data_etf.assert_not_called()
        mock_storage_instance.save_history_data_etf.assert_not_called()


if __name__ == "__main__":
    # Run tests with verbose output and coverage if available
    pytest.main([__file__, "-v", "--tb=short"])
