import os
import sys
from unittest.mock import Mock, patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from common.const import (  # noqa: E402
    COL_CLOSE,
    COL_DATE,
    COL_ETF_ID,
    COL_ETF_NAME,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    COL_STOCK_NAME,
    COL_VOLUME,
)
from stock.data import access_data  # noqa: E402


class TestAccessData:
    """Test class for stock/data/access_data.py functions"""

    @pytest.fixture
    def mock_storage_db(self):
        """Mock storage instance returned by get_storage"""
        storage = Mock()
        storage.config = Mock()
        storage.config.get_db_host.return_value = "localhost"
        storage.config.get_db_port.return_value = 5432
        storage.config.get_db_name.return_value = "test_db"
        storage.config.get_db_username.return_value = "test_user"
        storage.config.get_db_password.return_value = "test_pass"
        return storage

    @pytest.fixture
    def sample_stock_data(self):
        """Sample stock data for testing"""
        return pd.DataFrame(
            {
                COL_DATE: ["2024-01-01", "2024-01-02", "2024-01-03"],
                COL_STOCK_ID: ["000001", "000002", "000003"],
                COL_STOCK_NAME: ["平安银行", "万科A", "国农科技"],
                COL_OPEN: [10.5, 20.3, 15.2],
                COL_CLOSE: [11.2, 21.1, 16.8],
                COL_HIGH: [11.8, 21.5, 17.2],
                COL_LOW: [10.1, 19.8, 14.9],
                COL_VOLUME: [1000000, 2000000, 1500000],
            }
        )

    @pytest.fixture
    def sample_etf_data(self):
        """Sample ETF data for testing"""
        return pd.DataFrame(
            {
                COL_ETF_ID: ["510300", "510500", "159915"],
                COL_ETF_NAME: ["沪深300ETF", "中证500ETF", "创业板ETF"],
            }
        )

    def test_load_general_info_stock_caching(
        self, mock_storage_db, sample_stock_data, monkeypatch
    ):
        """Test that load_general_info_stock uses caching properly"""
        # Reset global variable
        access_data.g_df_stocks = None

        # Mock the load_general_info_stock method
        mock_storage_db.load_general_info_stock.return_value = sample_stock_data

        # Use monkeypatch to mock get_storage - get_storage is a singleton function that takes no parameters
        monkeypatch.setattr(
            "stock.data.access_data.get_storage", lambda: mock_storage_db
        )

        # First call - should load from database
        result1 = access_data.load_general_info_stock()

        # Second call - should use cached data
        result2 = access_data.load_general_info_stock()

        # Verify caching behavior
        assert mock_storage_db.load_general_info_stock.call_count == 1
        assert result1.equals(result2)
        assert access_data.g_df_stocks is not None

        # Verify stock ID formatting
        assert result1[COL_STOCK_ID].dtype == "object"  # string type
        assert all(len(str(stock_id)) == 6 for stock_id in result1[COL_STOCK_ID])

    def test_load_general_info_stock_database_error(self, mock_storage_db, monkeypatch):
        """Test load_general_info_stock handles database errors"""
        # Reset global variable
        access_data.g_df_stocks = None

        # Mock database error
        mock_storage_db.load_general_info_stock.side_effect = Exception(
            "Database error"
        )

        # Use monkeypatch to mock get_storage - get_storage is a singleton function that takes no parameters
        monkeypatch.setattr(
            "stock.data.access_data.get_storage", lambda: mock_storage_db
        )

        # Should handle error gracefully and return empty DataFrame
        result = access_data.load_general_info_stock()

        # Should return empty DataFrame with expected columns
        assert len(result) == 0
        assert COL_STOCK_ID in result.columns
        assert COL_STOCK_NAME in result.columns

    def test_load_general_info_stock_empty_database(self, mock_storage_db):
        """Test load_general_info_stock with empty database result"""
        # Reset global variable
        access_data.g_df_stocks = None

        # Mock empty DataFrame from database
        empty_data = pd.DataFrame(columns=[COL_STOCK_ID, COL_STOCK_NAME])
        mock_storage_db.load_general_info_stock.return_value = empty_data

        with patch("stock.data.access_data.get_storage", return_value=mock_storage_db):
            result = access_data.load_general_info_stock()

            assert len(result) == 0
            assert COL_STOCK_ID in result.columns
            assert COL_STOCK_NAME in result.columns


if __name__ == "__main__":
    pytest.main([__file__])
