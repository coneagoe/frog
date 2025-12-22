import os
import sys
from datetime import date
from unittest.mock import Mock, patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from common.const import (  # noqa: E402
    COL_AMOUNT,
    COL_CHANGE_RATE,
    COL_CLOSE,
    COL_DATE,
    COL_ETF_ID,
    COL_ETF_NAME,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    COL_STOCK_NAME,
    COL_TURNOVER_RATE,
    COL_VOLUME,
    AdjustType,
    PeriodType,
)
from storage.config import StorageConfig  # noqa: E402
from storage.model import (  # noqa: E402
    tb_name_history_data_daily_a_stock_qfq,
    tb_name_history_data_weekly_a_stock_qfq,
    tb_name_ingredient_300,
    tb_name_ingredient_500,
)
from storage.storage_db import (  # noqa: E402
    ConnectionError,
    connect_once,
    get_storage,
    reset_storage,
)


class TestStorageDb:
    @pytest.fixture
    def mock_config(self):
        config = Mock(spec=StorageConfig)
        config.get_db_host.return_value = "localhost"
        config.get_db_port.return_value = 5432
        config.get_db_name.return_value = "test_db"
        config.get_db_username.return_value = "test_user"
        config.get_db_password.return_value = "test_pass"
        return config

    @pytest.fixture
    def storage_db(self, mock_config, monkeypatch):
        """Create StorageDb instance with mocked dependencies"""
        # Reset storage instance to ensure we get a fresh one with mock config
        reset_storage()

        monkeypatch.setattr("storage.storage_db.create_engine", Mock())
        monkeypatch.setattr("storage.storage_db.sessionmaker", Mock())
        monkeypatch.setattr("storage.storage_db.Base.metadata.create_all", Mock())
        return get_storage(mock_config)

    def test_init(self, mock_config, monkeypatch):
        """Test StorageDb initialization"""
        mock_create_engine = Mock()
        monkeypatch.setattr("storage.storage_db.create_engine", mock_create_engine)
        monkeypatch.setattr("storage.storage_db.sessionmaker", Mock())
        monkeypatch.setattr("storage.storage_db.Base.metadata.create_all", Mock())

        storage = get_storage(mock_config)

        assert storage.config == mock_config
        assert storage.host == "localhost"
        assert storage.port == 5432
        assert storage.database == "test_db"
        assert storage.username == "test_user"
        assert storage.password == "test_pass"
        assert storage.connection is None
        assert storage.cursor is None
        mock_create_engine.assert_called_once()

    def test_save_history_data_stock_1d_success(self, storage_db):
        test_df = pd.DataFrame(
            {
                COL_DATE: [date(2023, 1, 1), date(2023, 1, 2)],
                COL_STOCK_ID: ["000001", "000002"],
                COL_OPEN: [10.5, 20.3],
                COL_CLOSE: [11.2, 21.1],
                COL_HIGH: [11.8, 21.5],
                COL_LOW: [10.1, 19.8],
                COL_VOLUME: [1000000, 2000000],
                COL_AMOUNT: [10500000, 40600000],
                COL_CHANGE_RATE: [6.67, 3.94],
                COL_TURNOVER_RATE: [1.5, 2.3],
            }
        )

        # Mock the to_sql method directly on the DataFrame
        with patch.object(test_df, "to_sql") as mock_to_sql:
            # Call the method
            storage_db.save_history_data_stock(
                test_df, PeriodType.DAILY, AdjustType.QFQ
            )

            # Assertions
            mock_to_sql.assert_called_once_with(
                tb_name_history_data_daily_a_stock_qfq,
                storage_db.engine,
                if_exists="append",
                index=False,
                method="multi",
            )

    def test_save_general_info_stock_success(self, storage_db):
        test_df = pd.DataFrame(
            {
                COL_STOCK_ID: ["000001", "000002"],
                COL_STOCK_NAME: ["平安银行", "万科A"],
                "所属行业": ["银行", "房地产"],
            }
        )

        with patch.object(test_df, "to_sql") as mock_to_sql:
            storage_db.save_general_info_stock(test_df)
            mock_to_sql.assert_called_once_with(
                "general_info_stock",
                storage_db.engine,
                if_exists="replace",
                index=False,
            )

    def test_load_general_info_stock_success(self, storage_db):
        """Test successful load_general_info_stock"""
        # 创建测试数据
        test_data = pd.DataFrame(
            {
                COL_STOCK_ID: ["000001", "000002", "600000"],
                COL_STOCK_NAME: ["平安银行", "万科A", "浦发银行"],
            }
        )

        # Mock pd.read_sql (now using read_sql instead of read_sql_table)
        with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
            mock_read_sql.return_value = test_data

            # 调用方法
            result = storage_db.load_general_info_stock()

            # 验证结果
            assert len(result) == 3
            assert result[COL_STOCK_ID].tolist() == ["000001", "000002", "600000"]
            assert result[COL_STOCK_NAME].tolist() == ["平安银行", "万科A", "浦发银行"]

            # 验证调用参数 - should be called with SQL query and engine
            mock_read_sql.assert_called_once()
            args, kwargs = mock_read_sql.call_args
            assert len(args) == 2
            assert (
                "general_info_stock" in args[0]
            )  # SQL query should contain table name
            assert args[1] == storage_db.engine

    def test_load_general_info_stock_empty_table(self, storage_db):
        """Test load_general_info_stock with empty table"""
        # 创建空DataFrame
        empty_data = pd.DataFrame(columns=[COL_STOCK_ID, COL_STOCK_NAME])

        # Mock pd.read_sql (now using read_sql instead of read_sql_table)
        with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
            mock_read_sql.return_value = empty_data

            # 调用方法
            result = storage_db.load_general_info_stock()

            # 验证结果
            assert len(result) == 0
            assert result.columns.tolist() == [COL_STOCK_ID, COL_STOCK_NAME]

            # 验证调用参数 - should be called with SQL query and engine
            mock_read_sql.assert_called_once()
            args, kwargs = mock_read_sql.call_args
            assert len(args) == 2
            assert (
                "general_info_stock" in args[0]
            )  # SQL query should contain table name
            assert args[1] == storage_db.engine

    def test_load_general_info_stock_table_not_exists(self, storage_db):
        """Test load_general_info_stock when table does not exist"""
        # Mock pd.read_sql to raise exception
        with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
            mock_read_sql.side_effect = Exception("Table does not exist")

            # 调用方法
            result = storage_db.load_general_info_stock()

            # 验证结果 - 应该返回空DataFrame
            assert len(result) == 0
            assert result.columns.tolist() == [COL_STOCK_ID, COL_STOCK_NAME]

            # 验证调用参数 - should be called with SQL query and engine
            mock_read_sql.assert_called_once()
            args, kwargs = mock_read_sql.call_args
            assert len(args) == 2
            assert (
                "general_info_stock" in args[0]
            )  # SQL query should contain table name
            assert args[1] == storage_db.engine

    def test_load_general_info_stock_database_error(self, storage_db):
        """Test load_general_info_stock with database error"""
        # Mock pd.read_sql to raise database exception
        with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
            mock_read_sql.side_effect = Exception("Database connection error")

            # 调用方法
            result = storage_db.load_general_info_stock()

            # 验证结果 - 应该返回空DataFrame
            assert len(result) == 0
            assert result.columns.tolist() == [COL_STOCK_ID, COL_STOCK_NAME]

            # 验证调用参数 - should be called with SQL query and engine
            mock_read_sql.assert_called_once()
            args, kwargs = mock_read_sql.call_args
            assert len(args) == 2
            assert (
                "general_info_stock" in args[0]
            )  # SQL query should contain table name
            assert args[1] == storage_db.engine

    def test_save_and_load_general_info_stock_integration(self, storage_db):
        """Test save_general_info_stock and load_general_info_stock work together"""
        # 创建测试数据
        test_data = pd.DataFrame(
            {
                COL_STOCK_ID: ["000001", "000002"],
                COL_STOCK_NAME: ["平安银行", "万科A"],
            }
        )

        # Mock save操作
        with patch.object(test_data, "to_sql") as mock_to_sql:
            # Mock load操作 (now using read_sql instead of read_sql_table)
            with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
                mock_read_sql.return_value = test_data

                # 先保存数据
                storage_db.save_general_info_stock(test_data)

                # 再加载数据
                result = storage_db.load_general_info_stock()

                # 验证保存操作
                mock_to_sql.assert_called_once_with(
                    "general_info_stock",
                    storage_db.engine,
                    if_exists="replace",
                    index=False,
                )

                # 验证加载操作 - should be called with SQL query and engine
                mock_read_sql.assert_called_once()
                args, kwargs = mock_read_sql.call_args
                assert len(args) == 2
                assert (
                    "general_info_stock" in args[0]
                )  # SQL query should contain table name
                assert args[1] == storage_db.engine

                # 验证数据一致性
                assert len(result) == 2
                assert result[COL_STOCK_ID].tolist() == ["000001", "000002"]
                assert result[COL_STOCK_NAME].tolist() == ["平安银行", "万科A"]

    def test_save_general_info_etf_success(self, storage_db):
        """Test successful save_general_info_etf"""
        # Create test dataframe
        test_df = pd.DataFrame(
            {
                COL_ETF_ID: ["510300", "510500"],
                COL_ETF_NAME: ["沪深300ETF", "中证500ETF"],
            }
        )

        # Mock the to_sql method directly on the DataFrame
        with patch.object(test_df, "to_sql") as mock_to_sql:
            result = storage_db.save_general_info_etf(test_df, "test_etf_table")

            assert result is True
            mock_to_sql.assert_called_once_with(
                "test_etf_table", storage_db.engine, if_exists="replace", index=False
            )

    def test_load_general_info_etf_success(self, storage_db):
        """Test successful load_general_info_etf"""
        # 创建测试数据
        test_data = pd.DataFrame(
            {
                COL_STOCK_ID: ["510300", "510500", "159915"],
                COL_STOCK_NAME: ["沪深300ETF", "中证500ETF", "创业板ETF"],
            }
        )

        # Mock pd.read_sql
        with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
            mock_read_sql.return_value = test_data

            # 调用方法
            result = storage_db.load_general_info_etf()

            # 验证结果
            assert len(result) == 3
            assert result[COL_STOCK_ID].tolist() == ["510300", "510500", "159915"]
            assert result[COL_STOCK_NAME].tolist() == [
                "沪深300ETF",
                "中证500ETF",
                "创业板ETF",
            ]

            # 验证调用参数
            mock_read_sql.assert_called_once()
            args, kwargs = mock_read_sql.call_args
            assert len(args) == 2
            assert "general_info_etf" in args[0]  # SQL query should contain table name
            assert args[1] == storage_db.engine  # engine parameter

    def test_load_general_info_etf_custom_table(self, storage_db):
        """Test load_general_info_etf with custom table name"""
        # 创建测试数据
        test_data = pd.DataFrame(
            {
                COL_STOCK_ID: ["510300", "510500"],
                COL_STOCK_NAME: ["沪深300ETF", "中证500ETF"],
            }
        )

        # Mock pd.read_sql
        with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
            mock_read_sql.return_value = test_data

            # 调用方法，使用自定义表名
            result = storage_db.load_general_info_etf("custom_etf_table")

            # 验证结果
            assert len(result) == 2
            assert result[COL_STOCK_ID].tolist() == ["510300", "510500"]
            assert result[COL_STOCK_NAME].tolist() == ["沪深300ETF", "中证500ETF"]

            # 验证调用参数
            mock_read_sql.assert_called_once()
            args, kwargs = mock_read_sql.call_args
            assert len(args) == 2
            assert (
                "custom_etf_table" in args[0]
            )  # SQL query should contain custom table name
            assert args[1] == storage_db.engine  # engine parameter

    def test_load_general_info_etf_empty_table(self, storage_db):
        """Test load_general_info_etf with empty table"""
        # 创建空DataFrame
        empty_data = pd.DataFrame(columns=[COL_STOCK_ID, COL_STOCK_NAME])

        # Mock pd.read_sql
        with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
            mock_read_sql.return_value = empty_data

            # 调用方法
            result = storage_db.load_general_info_etf()

            # 验证结果
            assert len(result) == 0
            assert result.columns.tolist() == [COL_STOCK_ID, COL_STOCK_NAME]

            # 验证调用参数
            mock_read_sql.assert_called_once()
            args, kwargs = mock_read_sql.call_args
            assert len(args) == 2
            assert "general_info_etf" in args[0]  # SQL query should contain table name
            assert args[1] == storage_db.engine  # engine parameter

    def test_load_general_info_etf_table_not_exists(self, storage_db):
        """Test load_general_info_etf when table does not exist"""
        # Mock pd.read_sql to raise exception
        with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
            mock_read_sql.side_effect = Exception("Table does not exist")

            # 调用方法
            result = storage_db.load_general_info_etf()

            # 验证结果 - 应该返回空DataFrame
            assert len(result) == 0
            assert result.columns.tolist() == [COL_STOCK_ID, COL_STOCK_NAME]

            # 验证调用参数
            mock_read_sql.assert_called_once()
            args, kwargs = mock_read_sql.call_args
            assert len(args) == 2
            assert "general_info_etf" in args[0]  # SQL query should contain table name
            assert args[1] == storage_db.engine  # engine parameter

    def test_load_general_info_etf_database_error(self, storage_db):
        """Test load_general_info_etf with database error"""
        # Mock pd.read_sql to raise database exception
        with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
            mock_read_sql.side_effect = Exception("Database connection error")

            # 调用方法
            result = storage_db.load_general_info_etf()

            # 验证结果 - 应该返回空DataFrame
            assert len(result) == 0
            assert result.columns.tolist() == [COL_STOCK_ID, COL_STOCK_NAME]

            # 验证调用参数
            mock_read_sql.assert_called_once()
            args, kwargs = mock_read_sql.call_args
            assert len(args) == 2
            assert "general_info_etf" in args[0]  # SQL query should contain table name
            assert args[1] == storage_db.engine  # engine parameter

    def test_save_and_load_general_info_etf_integration(self, storage_db):
        """Test save_general_info_etf and load_general_info_etf work together"""
        # 创建测试数据
        test_data = pd.DataFrame(
            {
                COL_STOCK_ID: ["510300", "510500"],
                COL_STOCK_NAME: ["沪深300ETF", "中证500ETF"],
            }
        )

        # Mock save操作
        with patch.object(test_data, "to_sql") as mock_to_sql:
            # Mock load操作
            with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
                mock_read_sql.return_value = test_data

                # 先保存数据
                storage_db.save_general_info_etf(test_data, "test_etf_table")

                # 再加载数据
                result = storage_db.load_general_info_etf("test_etf_table")

                # 验证保存操作
                mock_to_sql.assert_called_once_with(
                    "test_etf_table",
                    storage_db.engine,
                    if_exists="replace",
                    index=False,
                )

                # 验证加载操作
                mock_read_sql.assert_called_once()
                args, kwargs = mock_read_sql.call_args
                assert len(args) == 2
                assert (
                    "test_etf_table" in args[0]
                )  # SQL query should contain table name
                assert args[1] == storage_db.engine  # engine parameter

                # 验证数据一致性
                assert len(result) == 2
                assert result[COL_STOCK_ID].tolist() == ["510300", "510500"]
                assert result[COL_STOCK_NAME].tolist() == ["沪深300ETF", "中证500ETF"]

    def test_save_general_info_hk_ggt_success(self, storage_db):
        test_df = pd.DataFrame(
            {
                COL_STOCK_ID: ["00700", "09988"],
                COL_STOCK_NAME: ["腾讯控股", "阿里巴巴"],
                "港股通额度": [1000000, 2000000],
            }
        )

        with patch.object(test_df, "to_sql") as mock_to_sql:
            storage_db.save_general_info_hk_ggt(test_df)

            mock_to_sql.assert_called_once_with(
                "general_info_hk_ggt",
                storage_db.engine,
                if_exists="replace",
                index=False,
            )

    def test_dataframe_column_mapping(self, storage_db):
        """Test that DataFrame columns match expected database columns"""
        expected_columns = [
            COL_DATE,
            COL_STOCK_ID,
            COL_OPEN,
            COL_CLOSE,
            COL_HIGH,
            COL_LOW,
            COL_VOLUME,
            COL_AMOUNT,
            COL_CHANGE_RATE,
            COL_TURNOVER_RATE,
        ]

        test_df = pd.DataFrame({col: [None] for col in expected_columns})

        with patch.object(test_df, "to_sql") as mock_to_sql:
            storage_db.save_history_data_stock(
                test_df, PeriodType.DAILY, AdjustType.QFQ
            )
            mock_to_sql.assert_called_once_with(
                tb_name_history_data_daily_a_stock_qfq,
                storage_db.engine,
                if_exists="append",
                index=False,
                method="multi",
            )

    def test_save_history_data_stock_1w_success(self, storage_db):
        """Test save_history_data_stock_1w method"""
        test_df = pd.DataFrame(
            {
                COL_DATE: [date(2023, 1, 1), date(2023, 1, 8)],
                COL_STOCK_ID: ["000001", "000002"],
                COL_OPEN: [10.5, 20.3],
                COL_CLOSE: [11.2, 21.1],
                COL_HIGH: [11.8, 21.5],
                COL_LOW: [10.1, 19.8],
                COL_VOLUME: [1000000, 2000000],
                COL_AMOUNT: [10500000, 40600000],
                COL_CHANGE_RATE: [6.67, 3.94],
                COL_TURNOVER_RATE: [1.5, 2.3],
            }
        )

        with patch.object(test_df, "to_sql") as mock_to_sql:
            storage_db.save_history_data_stock(
                test_df, PeriodType.WEEKLY, AdjustType.QFQ
            )
            mock_to_sql.assert_called_once_with(
                tb_name_history_data_weekly_a_stock_qfq,
                storage_db.engine,
                if_exists="append",
                index=False,
                method="multi",
            )

    def test_connect_success(self, mock_config, monkeypatch):
        """Test successful database connection"""
        monkeypatch.setattr("storage.storage_db.create_engine", Mock())
        monkeypatch.setattr("storage.storage_db.sessionmaker", Mock())
        monkeypatch.setattr("storage.storage_db.Base.metadata.create_all", Mock())

        # Mock psycopg2.connect
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_connection.cursor.return_value = mock_cursor

        with patch("psycopg2.connect", return_value=mock_connection) as mock_connect:
            storage = get_storage(mock_config)
            result = storage.connect()

            assert result is True
            assert storage.connection == mock_connection
            assert storage.cursor == mock_cursor
            mock_connect.assert_called_once()

    def test_connect_failure(self, mock_config, monkeypatch):
        """Test failed database connection"""
        monkeypatch.setattr("storage.storage_db.create_engine", Mock())
        monkeypatch.setattr("storage.storage_db.sessionmaker", Mock())
        monkeypatch.setattr("storage.storage_db.Base.metadata.create_all", Mock())

        with patch("psycopg2.connect", side_effect=Exception("Connection failed")):
            storage = get_storage(mock_config)
            result = storage.connect()

            assert result is False
            assert storage.connection is None
            assert storage.cursor is None

    def test_disconnect_success(self, mock_config, monkeypatch):
        """Test successful database disconnection"""
        # Reset storage instance to ensure we get a fresh one with mock config
        from storage.storage_db import reset_storage

        reset_storage()

        monkeypatch.setattr("storage.storage_db.create_engine", Mock())
        monkeypatch.setattr("storage.storage_db.sessionmaker", Mock())
        monkeypatch.setattr("storage.storage_db.Base.metadata.create_all", Mock())

        storage = get_storage(mock_config)
        mock_connection = Mock()
        mock_cursor = Mock()
        storage.connection = mock_connection
        storage.cursor = mock_cursor

        result = storage.disconnect()

        assert result is True
        assert storage.connection is None
        assert storage.cursor is None
        mock_cursor.close.assert_called_once()
        mock_connection.close.assert_called_once()

    def test_disconnect_failure(self, mock_config, monkeypatch):
        """Test failed database disconnection"""
        from storage.storage_db import reset_storage

        reset_storage()

        monkeypatch.setattr("storage.storage_db.create_engine", Mock())
        monkeypatch.setattr("storage.storage_db.sessionmaker", Mock())
        monkeypatch.setattr("storage.storage_db.Base.metadata.create_all", Mock())

        storage = get_storage(mock_config)
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_cursor.close.side_effect = Exception("Close failed")
        storage.connection = mock_connection
        storage.cursor = mock_cursor

        result = storage.disconnect()

        assert result is False
        assert storage.connection == mock_connection
        assert storage.cursor == mock_cursor

    def test_connect_once_decorator_creates_connection(self, storage_db):
        """Test that connect_once decorator creates and cleans up connection"""
        storage_db.connect = Mock(return_value=True)
        storage_db.disconnect = Mock(return_value=True)

        @connect_once
        def mock_method(self):
            return "success"

        result = mock_method(storage_db)

        assert result == "success"
        storage_db.connect.assert_called_once()
        storage_db.disconnect.assert_called_once()

    def test_connect_once_decorator_preserves_existing_connection(self, storage_db):
        """Test that connect_once decorator doesn't interfere with existing connection"""
        mock_connection = Mock()
        mock_cursor = Mock()
        storage_db.connection = mock_connection
        storage_db.cursor = mock_cursor
        storage_db.connect = Mock()
        storage_db.disconnect = Mock()

        @connect_once
        def mock_method(self):
            return "success"

        result = mock_method(storage_db)

        assert result == "success"
        storage_db.connect.assert_not_called()
        storage_db.disconnect.assert_not_called()
        assert storage_db.connection == mock_connection
        assert storage_db.cursor == mock_cursor

    def test_connect_once_decorator_connect_failure(self, storage_db):
        """Test connect_once decorator when connection fails"""
        storage_db.connect = Mock(return_value=False)

        @connect_once
        def mock_method(self):
            return "should not reach here"

        with pytest.raises(ConnectionError, match="无法建立数据库连接"):
            mock_method(storage_db)

        storage_db.connect.assert_called_once()

    def test_drop_table_success(self, storage_db):
        """Test successful drop_table operation"""
        # Mock the connection and cursor
        mock_connection = Mock()
        mock_cursor = Mock()
        storage_db.connection = mock_connection
        storage_db.cursor = mock_cursor

        # Call drop_table
        storage_db.drop_table("test_table")

        # Verify the SQL was executed correctly
        mock_cursor.execute.assert_called_once_with("DELETE FROM test_table")
        mock_connection.commit.assert_called_once()

    def test_drop_table_with_connect_once_decorator(self, storage_db):
        """Test drop_table uses connect_once decorator properly"""
        storage_db.connect = Mock(return_value=True)
        storage_db.disconnect = Mock(return_value=True)

        # Call drop_table (should auto-connect and disconnect)
        storage_db.drop_table("test_table")

        # Verify connection management
        storage_db.connect.assert_called_once()
        storage_db.disconnect.assert_called_once()

    def test_drop_table_preserves_existing_connection(self, storage_db):
        """Test drop_table doesn't interfere with existing connection"""
        mock_connection = Mock()
        mock_cursor = Mock()
        storage_db.connection = mock_connection
        storage_db.cursor = mock_cursor
        storage_db.connect = Mock()
        storage_db.disconnect = Mock()

        # Call drop_table
        storage_db.drop_table("test_table")

        # Verify no connection management when already connected
        storage_db.connect.assert_not_called()
        storage_db.disconnect.assert_not_called()
        assert storage_db.connection == mock_connection
        assert storage_db.cursor == mock_cursor

    def test_drop_table_failure_with_rollback(self, storage_db):
        """Test drop_table handles database errors and rolls back"""
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_cursor.execute.side_effect = Exception("Database error")
        storage_db.connection = mock_connection
        storage_db.cursor = mock_cursor

        # Call drop_table - should not raise exception, just log error
        storage_db.drop_table("test_table")

        # Verify rollback was called on failure
        mock_cursor.execute.assert_called_once_with("DELETE FROM test_table")
        mock_connection.rollback.assert_called_once()
        mock_connection.commit.assert_not_called()

    def test_drop_table_failure_without_connection(self, storage_db):
        """Test drop_table handles case where connection is None"""
        storage_db.connection = None
        storage_db.cursor = None

        # Mock the connect method to return False (simulating connection failure)
        storage_db.connect = Mock(return_value=False)

        # Call drop_table - should raise ConnectionError due to connect_once decorator
        with pytest.raises(ConnectionError, match="无法建立数据库连接"):
            storage_db.drop_table("test_table")

        # Verify connect was called
        storage_db.connect.assert_called_once()

    def test_drop_table_with_special_table_names(self, storage_db):
        """Test drop_table with various table name formats"""
        mock_connection = Mock()
        mock_cursor = Mock()
        storage_db.connection = mock_connection
        storage_db.cursor = mock_cursor

        # Test with different table names
        test_cases = [
            "simple_table",
            "table_with_123",
            "UPPERCASE_TABLE",
            "table_with_underscores_and_numbers_123",
        ]

        for table_name in test_cases:
            mock_cursor.reset_mock()
            storage_db.drop_table(table_name)
            mock_cursor.execute.assert_called_once_with(f"DELETE FROM {table_name}")

    def test_get_last_record_success(self, storage_db):
        """Test successful get_last_record operation"""
        # Mock the connection and cursor
        mock_connection = Mock()
        mock_cursor = Mock()
        storage_db.connection = mock_connection
        storage_db.cursor = mock_cursor

        # Mock the expected record data
        expected_record = {
            COL_DATE: "2024-01-15",
            COL_STOCK_ID: "000001",
            COL_OPEN: 10.5,
            COL_CLOSE: 11.2,
            COL_HIGH: 11.8,
            COL_LOW: 10.1,
            COL_VOLUME: 1000000,
            COL_AMOUNT: 10500000,
            COL_CHANGE_RATE: 6.67,
            COL_TURNOVER_RATE: 1.5,
        }

        # Mock fetchone to return the expected record
        mock_cursor.fetchone.return_value = expected_record

        # Call get_last_record
        result = storage_db.get_last_record("test_table", "000001")

        # Verify the result
        assert result == expected_record

        # Verify the SQL was executed correctly
        expected_sql = f"""
            SELECT * FROM test_table
            WHERE "{COL_STOCK_ID}" = %s
            ORDER BY "{COL_DATE}" DESC
            LIMIT 1
            """
        mock_cursor.execute.assert_called_once_with(expected_sql, ("000001",))

    def test_get_last_record_no_data(self, storage_db):
        """Test get_last_record when no data exists"""
        # Mock the connection and cursor
        mock_connection = Mock()
        mock_cursor = Mock()
        storage_db.connection = mock_connection
        storage_db.cursor = mock_cursor

        # Mock fetchone to return None (no data)
        mock_cursor.fetchone.return_value = None

        # Call get_last_record
        result = storage_db.get_last_record("test_table", "000001")

        # Verify the result is None
        assert result is None

        # Verify the SQL was executed correctly
        expected_sql = f"""
            SELECT * FROM test_table
            WHERE "{COL_STOCK_ID}" = %s
            ORDER BY "{COL_DATE}" DESC
            LIMIT 1
            """
        mock_cursor.execute.assert_called_once_with(expected_sql, ("000001",))

    def test_get_last_record_with_connect_once_decorator(self, storage_db):
        """Test that get_last_record uses connect_once decorator properly"""
        storage_db.connect = Mock(return_value=True)
        storage_db.disconnect = Mock(return_value=True)

        # Mock the cursor after connection is established
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = None

        # Mock the connection to return our mock cursor
        mock_connection = Mock()
        mock_connection.cursor.return_value = mock_cursor

        # Patch psycopg2.connect to return our mock connection
        with patch("psycopg2.connect", return_value=mock_connection):
            # Call get_last_record (should auto-connect and disconnect)
            result = storage_db.get_last_record("test_table", "000001")

            # Verify connection management
            storage_db.connect.assert_called_once()
            storage_db.disconnect.assert_called_once()
            assert result is None

    def test_get_last_record_preserves_existing_connection(self, storage_db):
        """Test get_last_record doesn't interfere with existing connection"""
        mock_connection = Mock()
        mock_cursor = Mock()
        expected_record = {
            COL_DATE: "2024-01-15",
            COL_STOCK_ID: "000001",
            COL_CLOSE: 11.2,
        }
        mock_cursor.fetchone.return_value = expected_record

        storage_db.connection = mock_connection
        storage_db.cursor = mock_cursor
        storage_db.connect = Mock()
        storage_db.disconnect = Mock()

        # Call get_last_record
        result = storage_db.get_last_record("test_table", "000001")

        # Verify no connection management when already connected
        storage_db.connect.assert_not_called()
        storage_db.disconnect.assert_not_called()
        assert result == expected_record
        assert storage_db.connection == mock_connection
        assert storage_db.cursor == mock_cursor

    def test_get_last_record_database_error(self, storage_db):
        """Test get_last_record handles database errors gracefully"""
        # Mock the connection and cursor
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_cursor.execute.side_effect = Exception("Database error")
        storage_db.connection = mock_connection
        storage_db.cursor = mock_cursor

        # Call get_last_record - should not raise exception, just log error and return None
        result = storage_db.get_last_record("test_table", "000001")

        # Verify error handling
        assert result is None

    def test_get_last_record_with_different_table_names(self, storage_db):
        """Test get_last_record with various table name formats"""
        mock_connection = Mock()
        mock_cursor = Mock()
        expected_record = {
            COL_DATE: "2024-01-15",
            COL_STOCK_ID: "000001",
            COL_CLOSE: 11.2,
        }
        mock_cursor.fetchone.return_value = expected_record
        storage_db.connection = mock_connection
        storage_db.cursor = mock_cursor

        # Test with different table names
        test_cases = [
            "simple_table",
            "table_with_123",
            "UPPERCASE_TABLE",
            "table_with_underscores_and_numbers_123",
            "history_data_daily_a_stock_qfq",
        ]

        for table_name in test_cases:
            mock_cursor.reset_mock()
            result = storage_db.get_last_record(table_name, "000001")

            assert result == expected_record
            expected_sql = f"""
            SELECT * FROM {table_name}
            WHERE "{COL_STOCK_ID}" = %s
            ORDER BY "{COL_DATE}" DESC
            LIMIT 1
            """
            mock_cursor.execute.assert_called_once_with(expected_sql, ("000001",))

    def test_get_last_record_with_different_stock_ids(self, storage_db):
        """Test get_last_record with various stock ID formats"""
        mock_connection = Mock()
        mock_cursor = Mock()
        storage_db.connection = mock_connection
        storage_db.cursor = mock_cursor

        # Test with different stock IDs
        test_cases = [
            "000001",
            "600000",
            "300001",
            "688001",
            "00700",
        ]

        for stock_id in test_cases:
            mock_cursor.reset_mock()
            expected_record = {
                COL_DATE: "2024-01-15",
                COL_STOCK_ID: stock_id,
                COL_CLOSE: 11.2,
            }
            mock_cursor.fetchone.return_value = expected_record

            result = storage_db.get_last_record("test_table", stock_id)

            assert result == expected_record
            expected_sql = f"""
            SELECT * FROM test_table
            WHERE "{COL_STOCK_ID}" = %s
            ORDER BY "{COL_DATE}" DESC
            LIMIT 1
            """
            mock_cursor.execute.assert_called_once_with(expected_sql, (stock_id,))

    def test_get_last_record_connect_once_failure(self, storage_db):
        """Test get_last_record when connection fails"""
        storage_db.connect = Mock(return_value=False)

        # Call get_last_record - should raise ConnectionError due to connect_once decorator
        with pytest.raises(ConnectionError, match="无法建立数据库连接"):
            storage_db.get_last_record("test_table", "000001")

        storage_db.connect.assert_called_once()

    def test_load_history_data_stock_daily_qfq_success(self, storage_db, monkeypatch):
        """Test successful load_history_data_stock for daily QFQ data"""
        test_data = pd.DataFrame(
            {
                COL_DATE: ["2023-01-01", "2023-01-02", "2023-01-03"],
                COL_STOCK_ID: ["000001", "000001", "000001"],
                COL_OPEN: [10.5, 10.8, 11.2],
                COL_CLOSE: [11.2, 11.5, 11.8],
                COL_HIGH: [11.8, 12.1, 12.5],
                COL_LOW: [10.1, 10.4, 10.8],
                COL_VOLUME: [1000000, 1200000, 1500000],
                COL_AMOUNT: [10500000, 12600000, 15750000],
                COL_CHANGE_RATE: [6.67, 2.68, 2.61],
                COL_TURNOVER_RATE: [1.5, 1.8, 2.25],
            }
        )

        mock_read_sql = Mock(return_value=test_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        result = storage_db.load_history_data_stock(
            "000001", PeriodType.DAILY, AdjustType.QFQ
        )

        # 验证结果
        assert len(result) == 3
        assert result[COL_STOCK_ID].tolist() == ["000001", "000001", "000001"]
        assert result[COL_DATE].tolist() == ["2023-01-01", "2023-01-02", "2023-01-03"]
        assert result[COL_CLOSE].tolist() == [11.2, 11.5, 11.8]

        # 验证SQL查询参数
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        sql_query = args[0]
        assert "history_data_daily_a_stock_qfq" in sql_query
        assert 'WHERE "股票代码" = %s' in sql_query  # 使用实际的列名
        assert 'ORDER BY "日期" ASC' in sql_query  # 使用实际的列名
        assert args[1] == storage_db.engine  # engine参数
        assert kwargs["params"] == ("000001",)  # stock_id参数

    def test_load_history_data_stock_weekly_hfq_success(self, storage_db, monkeypatch):
        """Test successful load_history_data_stock for weekly HFQ data"""
        # 创建测试数据
        test_data = pd.DataFrame(
            {
                COL_DATE: ["2023-01-01", "2023-01-08", "2023-01-15"],
                COL_STOCK_ID: ["000002", "000002", "000002"],
                COL_OPEN: [20.3, 21.1, 22.5],
                COL_CLOSE: [21.1, 22.3, 23.8],
                COL_HIGH: [21.5, 22.8, 24.2],
                COL_LOW: [19.8, 20.5, 21.9],
                COL_VOLUME: [2000000, 2200000, 2500000],
                COL_AMOUNT: [40600000, 44660000, 50750000],
                COL_CHANGE_RATE: [3.94, 5.69, 6.73],
                COL_TURNOVER_RATE: [2.3, 2.53, 2.88],
            }
        )

        # 使用monkeypatch替代patch
        mock_read_sql = Mock(return_value=test_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        # 调用方法
        result = storage_db.load_history_data_stock(
            "000002", PeriodType.WEEKLY, AdjustType.HFQ
        )

        # 验证结果
        assert len(result) == 3
        assert result[COL_STOCK_ID].tolist() == ["000002", "000002", "000002"]
        assert result[COL_DATE].tolist() == ["2023-01-01", "2023-01-08", "2023-01-15"]
        assert result[COL_CLOSE].tolist() == [21.1, 22.3, 23.8]

        # 验证SQL查询参数
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        sql_query = args[0]
        assert "history_data_weekly_a_stock_hfq" in sql_query
        assert kwargs["params"] == ("000002",)

    def test_load_history_data_stock_with_date_range(self, storage_db, monkeypatch):
        """Test load_history_data_stock with date range filter"""
        # 创建测试数据
        test_data = pd.DataFrame(
            {
                COL_DATE: ["2023-01-15", "2023-01-16", "2023-01-17"],
                COL_STOCK_ID: ["000001", "000001", "000001"],
                COL_OPEN: [11.0, 11.2, 11.5],
                COL_CLOSE: [11.8, 12.1, 12.4],
                COL_HIGH: [12.2, 12.5, 12.8],
                COL_LOW: [10.8, 11.0, 11.3],
                COL_VOLUME: [1300000, 1400000, 1600000],
                COL_AMOUNT: [13650000, 14700000, 16800000],
                COL_CHANGE_RATE: [7.27, 2.54, 2.48],
                COL_TURNOVER_RATE: [1.95, 2.1, 2.4],
            }
        )

        # 使用monkeypatch替代patch
        mock_read_sql = Mock(return_value=test_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        # 调用方法，带日期范围
        result = storage_db.load_history_data_stock(
            "000001",
            PeriodType.DAILY,
            AdjustType.QFQ,
            start_date="2023-01-15",
            end_date="2023-01-17",
        )

        # 验证结果
        assert len(result) == 3
        assert result[COL_DATE].tolist() == ["2023-01-15", "2023-01-16", "2023-01-17"]

        # 验证SQL查询参数
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        sql_query = args[0]
        assert "history_data_daily_a_stock_qfq" in sql_query
        assert 'AND "日期" >= %s' in sql_query  # 使用实际的列名
        assert 'AND "日期" <= %s' in sql_query  # 使用实际的列名
        assert kwargs["params"] == ("000001", "2023-01-15", "2023-01-17")

    def test_load_history_data_stock_empty_result(self, storage_db, monkeypatch):
        """Test load_history_data_stock returns empty DataFrame when no data found"""
        # 创建空DataFrame
        empty_data = pd.DataFrame(
            columns=[
                COL_DATE,
                COL_STOCK_ID,
                COL_OPEN,
                COL_CLOSE,
                COL_HIGH,
                COL_LOW,
                COL_VOLUME,
                COL_AMOUNT,
                COL_CHANGE_RATE,
                COL_TURNOVER_RATE,
            ]
        )

        # 使用monkeypatch替代patch
        mock_read_sql = Mock(return_value=empty_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        # 调用方法
        result = storage_db.load_history_data_stock(
            "000003", PeriodType.DAILY, AdjustType.QFQ
        )

        # 验证结果
        assert len(result) == 0
        assert list(result.columns) == [
            COL_DATE,
            COL_STOCK_ID,
            COL_OPEN,
            COL_CLOSE,
            COL_HIGH,
            COL_LOW,
            COL_VOLUME,
            COL_AMOUNT,
            COL_CHANGE_RATE,
            COL_TURNOVER_RATE,
        ]

        # 验证SQL查询被调用
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        assert kwargs["params"] == ("000003",)

    def test_load_history_data_stock_database_error(self, storage_db, monkeypatch):
        """Test load_history_data_stock handles database errors gracefully"""
        # 使用monkeypatch替代patch
        mock_read_sql = Mock(side_effect=Exception("Database connection error"))
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        # 调用方法
        result = storage_db.load_history_data_stock(
            "000001", PeriodType.DAILY, AdjustType.QFQ
        )

        # 验证结果 - 应该返回空DataFrame
        assert len(result) == 0
        assert list(result.columns) == []  # 空DataFrame

        # 验证SQL查询被调用
        mock_read_sql.assert_called_once()

    def test_load_history_data_stock_unsupported_period(self, storage_db):
        """Test load_history_data_stock with unsupported period type"""
        # 调用方法，使用不支持的周期类型
        result = storage_db.load_history_data_stock(
            "000001", "MONTHLY", AdjustType.QFQ  # 使用字符串代替枚举，模拟不支持的情况
        )

        # 验证结果 - 应该返回空DataFrame
        assert len(result) == 0
        assert list(result.columns) == []  # 空DataFrame

    def test_load_history_data_stock_unsupported_adjust(self, storage_db):
        """Test load_history_data_stock with unsupported adjust type"""
        # 调用方法，使用不支持的复权类型
        result = storage_db.load_history_data_stock(
            "000001",
            PeriodType.DAILY,
            "INVALID_ADJUST",  # 使用字符串代替枚举，模拟不支持的情况
        )

        # 验证结果 - 应该返回空DataFrame
        assert len(result) == 0
        assert list(result.columns) == []  # 空DataFrame

    def test_load_history_data_stock_with_only_start_date(
        self, storage_db, monkeypatch
    ):
        """Test load_history_data_stock with only start date filter"""
        # 创建测试数据
        test_data = pd.DataFrame(
            {
                COL_DATE: ["2023-01-10", "2023-01-11", "2023-01-12"],
                COL_STOCK_ID: ["000001", "000001", "000001"],
                COL_OPEN: [10.0, 10.2, 10.5],
                COL_CLOSE: [10.8, 11.1, 11.4],
                COL_HIGH: [11.2, 11.5, 11.8],
                COL_LOW: [9.8, 10.0, 10.3],
                COL_VOLUME: [1000000, 1100000, 1300000],
                COL_AMOUNT: [10500000, 11550000, 13650000],
                COL_CHANGE_RATE: [8.0, 2.78, 2.7],
                COL_TURNOVER_RATE: [1.5, 1.65, 1.95],
            }
        )

        # 使用monkeypatch替代patch
        mock_read_sql = Mock(return_value=test_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        # 调用方法，只带开始日期
        result = storage_db.load_history_data_stock(
            "000001", PeriodType.DAILY, AdjustType.QFQ, start_date="2023-01-10"
        )

        # 验证结果
        assert len(result) == 3
        assert result[COL_DATE].tolist() == ["2023-01-10", "2023-01-11", "2023-01-12"]

        # 验证SQL查询参数
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        sql_query = args[0]
        assert 'AND "日期" >= %s' in sql_query  # 使用实际的列名
        assert 'AND "日期" <= %s' not in sql_query  # 不应该有结束日期条件
        assert kwargs["params"] == ("000001", "2023-01-10")

    def test_load_history_data_stock_with_only_end_date(self, storage_db, monkeypatch):
        """Test load_history_data_stock with only end date filter"""
        # 创建测试数据
        test_data = pd.DataFrame(
            {
                COL_DATE: ["2023-01-05", "2023-01-06", "2023-01-07"],
                COL_STOCK_ID: ["000001", "000001", "000001"],
                COL_OPEN: [9.5, 9.7, 10.0],
                COL_CLOSE: [10.3, 10.6, 10.9],
                COL_HIGH: [10.7, 11.0, 11.3],
                COL_LOW: [9.3, 9.5, 9.8],
                COL_VOLUME: [900000, 950000, 1100000],
                COL_AMOUNT: [9450000, 9975000, 11550000],
                COL_CHANGE_RATE: [8.42, 2.91, 2.83],
                COL_TURNOVER_RATE: [1.35, 1.43, 1.65],
            }
        )

        # 使用monkeypatch替代patch
        mock_read_sql = Mock(return_value=test_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        # 调用方法，只带结束日期
        result = storage_db.load_history_data_stock(
            "000001", PeriodType.DAILY, AdjustType.QFQ, end_date="2023-01-07"
        )

        # 验证结果
        assert len(result) == 3
        assert result[COL_DATE].tolist() == ["2023-01-05", "2023-01-06", "2023-01-07"]

        # 验证SQL查询参数
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        sql_query = args[0]
        assert 'AND "日期" >= %s' not in sql_query  # 不应该有开始日期条件
        assert 'AND "日期" <= %s' in sql_query  # 使用实际的列名
        assert kwargs["params"] == ("000001", "2023-01-07")

    def test_load_history_data_etf_daily_qfq_success(self, storage_db, monkeypatch):
        """Test successful load_history_data_etf for daily QFQ data"""
        test_data = pd.DataFrame(
            {
                COL_DATE: ["2023-01-01", "2023-01-02", "2023-01-03"],
                COL_STOCK_ID: ["510300", "510300", "510300"],  # ETF代码
                COL_OPEN: [4.5, 4.6, 4.7],
                COL_CLOSE: [4.6, 4.7, 4.8],
                COL_HIGH: [4.7, 4.8, 4.9],
                COL_LOW: [4.4, 4.5, 4.6],
                COL_VOLUME: [5000000, 5200000, 5500000],
                COL_AMOUNT: [23000000, 23920000, 26400000],
                COL_CHANGE_RATE: [2.22, 2.17, 2.13],
                COL_TURNOVER_RATE: [0.5, 0.52, 0.55],
            }
        )

        mock_read_sql = Mock(return_value=test_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        result = storage_db.load_history_data_etf(
            "510300", PeriodType.DAILY, AdjustType.QFQ
        )

        # 验证结果
        assert len(result) == 3
        assert result[COL_STOCK_ID].tolist() == ["510300", "510300", "510300"]
        assert result[COL_DATE].tolist() == ["2023-01-01", "2023-01-02", "2023-01-03"]
        assert result[COL_CLOSE].tolist() == [4.6, 4.7, 4.8]

        # 验证SQL查询参数
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        sql_query = args[0]
        assert "history_data_daily_etf_qfq" in sql_query
        assert 'WHERE "股票代码" = %s' in sql_query  # 使用实际的列名
        assert 'ORDER BY "日期" ASC' in sql_query  # 使用实际的列名
        assert args[1] == storage_db.engine  # engine参数
        assert kwargs["params"] == ("510300",)  # etf_id参数

    def test_load_history_data_etf_weekly_hfq_success(self, storage_db, monkeypatch):
        """Test successful load_history_data_etf for weekly HFQ data"""
        # 创建测试数据
        test_data = pd.DataFrame(
            {
                COL_DATE: ["2023-01-01", "2023-01-08", "2023-01-15"],
                COL_STOCK_ID: ["510500", "510500", "510500"],  # ETF代码
                COL_OPEN: [6.3, 6.4, 6.6],
                COL_CLOSE: [6.4, 6.6, 6.8],
                COL_HIGH: [6.6, 6.7, 6.9],
                COL_LOW: [6.2, 6.3, 6.5],
                COL_VOLUME: [3000000, 3200000, 3500000],
                COL_AMOUNT: [19200000, 20480000, 22400000],
                COL_CHANGE_RATE: [1.59, 3.13, 3.03],
                COL_TURNOVER_RATE: [0.3, 0.32, 0.35],
            }
        )

        # 使用monkeypatch替代patch
        mock_read_sql = Mock(return_value=test_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        # 调用方法
        result = storage_db.load_history_data_etf(
            "510500", PeriodType.WEEKLY, AdjustType.HFQ
        )

        # 验证结果
        assert len(result) == 3
        assert result[COL_STOCK_ID].tolist() == ["510500", "510500", "510500"]
        assert result[COL_DATE].tolist() == ["2023-01-01", "2023-01-08", "2023-01-15"]
        assert result[COL_CLOSE].tolist() == [6.4, 6.6, 6.8]

        # 验证SQL查询参数
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        sql_query = args[0]
        assert "history_data_weekly_etf_hfq" in sql_query
        assert kwargs["params"] == ("510500",)

    def test_load_history_data_etf_with_date_range(self, storage_db, monkeypatch):
        """Test load_history_data_etf with date range filter"""
        # 创建测试数据
        test_data = pd.DataFrame(
            {
                COL_DATE: ["2023-01-15", "2023-01-16", "2023-01-17"],
                COL_STOCK_ID: ["510300", "510300", "510300"],  # ETF代码
                COL_OPEN: [4.8, 4.9, 5.0],
                COL_CLOSE: [4.9, 5.0, 5.1],
                COL_HIGH: [5.0, 5.1, 5.2],
                COL_LOW: [4.7, 4.8, 4.9],
                COL_VOLUME: [6000000, 6200000, 6500000],
                COL_AMOUNT: [29400000, 30380000, 31850000],
                COL_CHANGE_RATE: [2.08, 2.04, 2.0],
                COL_TURNOVER_RATE: [0.6, 0.62, 0.65],
            }
        )

        # 使用monkeypatch替代patch
        mock_read_sql = Mock(return_value=test_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        # 调用方法，带日期范围
        result = storage_db.load_history_data_etf(
            "510300",
            PeriodType.DAILY,
            AdjustType.QFQ,
            start_date="2023-01-15",
            end_date="2023-01-17",
        )

        # 验证结果
        assert len(result) == 3
        assert result[COL_DATE].tolist() == ["2023-01-15", "2023-01-16", "2023-01-17"]

        # 验证SQL查询参数
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        sql_query = args[0]
        assert "history_data_daily_etf_qfq" in sql_query
        assert 'AND "日期" >= %s' in sql_query  # 使用实际的列名
        assert 'AND "日期" <= %s' in sql_query  # 使用实际的列名
        assert kwargs["params"] == ("510300", "2023-01-15", "2023-01-17")

    def test_load_history_data_etf_empty_result(self, storage_db, monkeypatch):
        """Test load_history_data_etf returns empty DataFrame when no data found"""
        # 创建空DataFrame
        empty_data = pd.DataFrame(
            columns=[
                COL_DATE,
                COL_STOCK_ID,
                COL_OPEN,
                COL_CLOSE,
                COL_HIGH,
                COL_LOW,
                COL_VOLUME,
                COL_AMOUNT,
                COL_CHANGE_RATE,
                COL_TURNOVER_RATE,
            ]
        )

        # 使用monkeypatch替代patch
        mock_read_sql = Mock(return_value=empty_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        # 调用方法
        result = storage_db.load_history_data_etf(
            "510300", PeriodType.DAILY, AdjustType.QFQ
        )

        # 验证结果
        assert len(result) == 0
        assert list(result.columns) == [
            COL_DATE,
            COL_STOCK_ID,
            COL_OPEN,
            COL_CLOSE,
            COL_HIGH,
            COL_LOW,
            COL_VOLUME,
            COL_AMOUNT,
            COL_CHANGE_RATE,
            COL_TURNOVER_RATE,
        ]

        # 验证SQL查询被调用
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        assert kwargs["params"] == ("510300",)

    def test_load_history_data_etf_database_error(self, storage_db, monkeypatch):
        """Test load_history_data_etf handles database errors gracefully"""
        # 使用monkeypatch替代patch
        mock_read_sql = Mock(side_effect=Exception("Database connection error"))
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        # 调用方法
        result = storage_db.load_history_data_etf(
            "510300", PeriodType.DAILY, AdjustType.QFQ
        )

        # 验证结果 - 应该返回空DataFrame
        assert len(result) == 0
        assert list(result.columns) == []  # 空DataFrame

        # 验证SQL查询被调用
        mock_read_sql.assert_called_once()

    def test_load_history_data_etf_unsupported_period(self, storage_db):
        """Test load_history_data_etf with unsupported period type"""
        # 调用方法，使用不支持的周期类型
        result = storage_db.load_history_data_etf(
            "510300", "MONTHLY", AdjustType.QFQ  # 使用字符串代替枚举，模拟不支持的情况
        )

        # 验证结果 - 应该返回空DataFrame
        assert len(result) == 0
        assert list(result.columns) == []  # 空DataFrame

    def test_load_history_data_etf_unsupported_adjust(self, storage_db):
        """Test load_history_data_etf with unsupported adjust type"""
        # 调用方法，使用不支持的复权类型
        result = storage_db.load_history_data_etf(
            "510300",
            PeriodType.DAILY,
            "INVALID_ADJUST",  # 使用字符串代替枚举，模拟不支持的情况
        )

        # 验证结果 - 应该返回空DataFrame
        assert len(result) == 0
        assert list(result.columns) == []  # 空DataFrame

    def test_load_history_data_etf_with_only_start_date(self, storage_db, monkeypatch):
        """Test load_history_data_etf with only start date filter"""
        # 创建测试数据
        test_data = pd.DataFrame(
            {
                COL_DATE: ["2023-01-10", "2023-01-11", "2023-01-12"],
                COL_STOCK_ID: ["510300", "510300", "510300"],  # ETF代码
                COL_OPEN: [4.9, 5.0, 5.1],
                COL_CLOSE: [5.0, 5.1, 5.2],
                COL_HIGH: [5.2, 5.3, 5.4],
                COL_LOW: [4.8, 4.9, 5.0],
                COL_VOLUME: [7000000, 7200000, 7500000],
                COL_AMOUNT: [34300000, 35280000, 36750000],
                COL_CHANGE_RATE: [2.04, 2.0, 1.96],
                COL_TURNOVER_RATE: [0.7, 0.72, 0.75],
            }
        )

        # 使用monkeypatch替代patch
        mock_read_sql = Mock(return_value=test_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        # 调用方法，只带开始日期
        result = storage_db.load_history_data_etf(
            "510300", PeriodType.DAILY, AdjustType.QFQ, start_date="2023-01-10"
        )

        # 验证结果
        assert len(result) == 3
        assert result[COL_DATE].tolist() == ["2023-01-10", "2023-01-11", "2023-01-12"]

        # 验证SQL查询参数
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        sql_query = args[0]
        assert 'AND "日期" >= %s' in sql_query  # 使用实际的列名
        assert 'AND "日期" <= %s' not in sql_query  # 不应该有结束日期条件
        assert kwargs["params"] == ("510300", "2023-01-10")

    def test_load_history_data_etf_with_only_end_date(self, storage_db, monkeypatch):
        """Test load_history_data_etf with only end date filter"""
        # 创建测试数据
        test_data = pd.DataFrame(
            {
                COL_DATE: ["2023-01-05", "2023-01-06", "2023-01-07"],
                COL_STOCK_ID: ["510300", "510300", "510300"],  # ETF代码
                COL_OPEN: [4.6, 4.7, 4.8],
                COL_CLOSE: [4.7, 4.8, 4.9],
                COL_HIGH: [4.9, 5.0, 5.1],
                COL_LOW: [4.5, 4.6, 4.7],
                COL_VOLUME: [5500000, 5700000, 6000000],
                COL_AMOUNT: [25850000, 26790000, 28200000],
                COL_CHANGE_RATE: [2.17, 2.13, 2.08],
                COL_TURNOVER_RATE: [0.55, 0.57, 0.6],
            }
        )

        # 使用monkeypatch替代patch
        mock_read_sql = Mock(return_value=test_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        # 调用方法，只带结束日期
        result = storage_db.load_history_data_etf(
            "510300", PeriodType.DAILY, AdjustType.QFQ, end_date="2023-01-07"
        )

        # 验证结果
        assert len(result) == 3
        assert result[COL_DATE].tolist() == ["2023-01-05", "2023-01-06", "2023-01-07"]

        # 验证SQL查询参数
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        sql_query = args[0]
        assert 'AND "日期" >= %s' not in sql_query  # 不应该有开始日期条件
        assert 'AND "日期" <= %s' in sql_query  # 使用实际的列名
        assert kwargs["params"] == ("510300", "2023-01-07")

    def test_save_ingredient_300_success(self, storage_db):
        """Test successful save_ingredient_300"""
        # 创建测试数据
        test_df = pd.DataFrame(
            {
                COL_STOCK_ID: ["000001", "000002", "600000"],
                COL_STOCK_NAME: ["平安银行", "万科A", "浦发银行"],
            }
        )

        # Mock the to_sql method directly on the DataFrame
        with patch.object(test_df, "to_sql") as mock_to_sql:
            result = storage_db.save_ingredient_300(test_df)

            assert result is True
            mock_to_sql.assert_called_once_with(
                tb_name_ingredient_300,
                storage_db.engine,
                if_exists="replace",
                index=False,
            )

    def test_save_ingredient_300_failure(self, storage_db):
        """Test save_ingredient_300 when database operation fails"""
        # 创建测试数据
        test_df = pd.DataFrame(
            {
                COL_STOCK_ID: ["000001", "000002"],
                COL_STOCK_NAME: ["平安银行", "万科A"],
            }
        )

        # Mock the to_sql method to raise an exception
        with patch.object(test_df, "to_sql") as mock_to_sql:
            mock_to_sql.side_effect = Exception("Database error")

            result = storage_db.save_ingredient_300(test_df)

            assert result is False
            mock_to_sql.assert_called_once_with(
                tb_name_ingredient_300,
                storage_db.engine,
                if_exists="replace",
                index=False,
            )

    def test_save_ingredient_500_success(self, storage_db):
        """Test successful save_ingredient_500"""
        # 创建测试数据
        test_df = pd.DataFrame(
            {
                COL_STOCK_ID: ["000001", "000002", "600000"],
                COL_STOCK_NAME: ["平安银行", "万科A", "浦发银行"],
            }
        )

        # Mock the to_sql method directly on the DataFrame
        with patch.object(test_df, "to_sql") as mock_to_sql:
            result = storage_db.save_ingredient_500(test_df)

            assert result is True
            mock_to_sql.assert_called_once_with(
                tb_name_ingredient_500,
                storage_db.engine,
                if_exists="replace",
                index=False,
            )

    def test_save_ingredient_500_failure(self, storage_db):
        """Test save_ingredient_500 when database operation fails"""
        # 创建测试数据
        test_df = pd.DataFrame(
            {
                COL_STOCK_ID: ["000001", "000002"],
                COL_STOCK_NAME: ["平安银行", "万科A"],
            }
        )

        # Mock the to_sql method to raise an exception
        with patch.object(test_df, "to_sql") as mock_to_sql:
            mock_to_sql.side_effect = Exception("Database error")

            result = storage_db.save_ingredient_500(test_df)

            assert result is False
            mock_to_sql.assert_called_once_with(
                tb_name_ingredient_500,
                storage_db.engine,
                if_exists="replace",
                index=False,
            )

    def test_save_ingredient_300_empty_dataframe(self, storage_db):
        """Test save_ingredient_300 with empty DataFrame"""
        # 创建空DataFrame
        test_df = pd.DataFrame(columns=[COL_STOCK_ID, COL_STOCK_NAME])

        # Mock the to_sql method directly on the DataFrame
        with patch.object(test_df, "to_sql") as mock_to_sql:
            result = storage_db.save_ingredient_300(test_df)

            assert result is True
            mock_to_sql.assert_called_once_with(
                tb_name_ingredient_300,
                storage_db.engine,
                if_exists="replace",
                index=False,
            )

    def test_save_ingredient_500_empty_dataframe(self, storage_db):
        """Test save_ingredient_500 with empty DataFrame"""
        # 创建空DataFrame
        test_df = pd.DataFrame(columns=[COL_STOCK_ID, COL_STOCK_NAME])

        # Mock the to_sql method directly on the DataFrame
        with patch.object(test_df, "to_sql") as mock_to_sql:
            result = storage_db.save_ingredient_500(test_df)

            assert result is True
            mock_to_sql.assert_called_once_with(
                tb_name_ingredient_500,
                storage_db.engine,
                if_exists="replace",
                index=False,
            )

    def test_load_ingredient_300_success(self, storage_db, monkeypatch):
        """Test successful load_ingredient_300"""
        # 创建测试数据
        test_data = pd.DataFrame(
            {
                COL_STOCK_ID: ["000001", "000002", "600000"],
                COL_STOCK_NAME: ["平安银行", "万科A", "浦发银行"],
            }
        )

        # Mock pd.read_sql using monkeypatch
        mock_read_sql = Mock(return_value=test_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        # 调用方法
        result = storage_db.load_ingredient_300()

        # 验证结果
        assert len(result) == 3
        assert result[COL_STOCK_ID].tolist() == ["000001", "000002", "600000"]
        assert result[COL_STOCK_NAME].tolist() == ["平安银行", "万科A", "浦发银行"]

        # 验证调用参数
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        assert len(args) == 2
        assert tb_name_ingredient_300 in args[0]  # SQL query should contain table name
        assert args[1] == storage_db.engine  # engine parameter

    def test_load_ingredient_300_empty_table(self, storage_db, monkeypatch):
        """Test load_ingredient_300 with empty table"""
        # 创建空DataFrame
        empty_data = pd.DataFrame(columns=[COL_STOCK_ID, COL_STOCK_NAME])

        # Mock pd.read_sql using monkeypatch
        mock_read_sql = Mock(return_value=empty_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        # 调用方法
        result = storage_db.load_ingredient_300()

        # 验证结果
        assert len(result) == 0
        assert result.columns.tolist() == [COL_STOCK_ID, COL_STOCK_NAME]

        # 验证调用参数
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        assert len(args) == 2
        assert tb_name_ingredient_300 in args[0]  # SQL query should contain table name
        assert args[1] == storage_db.engine  # engine parameter

    def test_load_ingredient_300_table_not_exists(self, storage_db):
        """Test load_ingredient_300 when table does not exist"""
        # Mock pd.read_sql to raise exception
        with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
            mock_read_sql.side_effect = Exception("Table does not exist")

            # 调用方法
            result = storage_db.load_ingredient_300()

            # 验证结果 - 应该返回空DataFrame
            assert len(result) == 0
            assert result.columns.tolist() == [COL_STOCK_ID, COL_STOCK_NAME]

            # 验证调用参数
            mock_read_sql.assert_called_once()
            args, kwargs = mock_read_sql.call_args
            assert len(args) == 2
            assert (
                tb_name_ingredient_300 in args[0]
            )  # SQL query should contain table name
            assert args[1] == storage_db.engine  # engine parameter

    def test_load_ingredient_300_database_error(self, storage_db):
        """Test load_ingredient_300 with database error"""
        # Mock pd.read_sql to raise database exception
        with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
            mock_read_sql.side_effect = Exception("Database connection error")

            # 调用方法
            result = storage_db.load_ingredient_300()

            # 验证结果 - 应该返回空DataFrame
            assert len(result) == 0
            assert result.columns.tolist() == [COL_STOCK_ID, COL_STOCK_NAME]

            # 验证调用参数
            mock_read_sql.assert_called_once()
            args, kwargs = mock_read_sql.call_args
            assert len(args) == 2
            assert (
                tb_name_ingredient_300 in args[0]
            )  # SQL query should contain table name
            assert args[1] == storage_db.engine  # engine parameter

    def test_load_ingredient_500_success(self, storage_db):
        """Test successful load_ingredient_500"""
        # 创建测试数据
        test_data = pd.DataFrame(
            {
                COL_STOCK_ID: ["000001", "000002", "600000"],
                COL_STOCK_NAME: ["平安银行", "万科A", "浦发银行"],
            }
        )

        # Mock pd.read_sql
        with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
            mock_read_sql.return_value = test_data

            # 调用方法
            result = storage_db.load_ingredient_500()

            # 验证结果
            assert len(result) == 3
            assert result[COL_STOCK_ID].tolist() == ["000001", "000002", "600000"]
            assert result[COL_STOCK_NAME].tolist() == ["平安银行", "万科A", "浦发银行"]

            # 验证调用参数
            mock_read_sql.assert_called_once()
            args, kwargs = mock_read_sql.call_args
            assert len(args) == 2
            assert (
                tb_name_ingredient_500 in args[0]
            )  # SQL query should contain table name
            assert args[1] == storage_db.engine  # engine parameter

    def test_load_ingredient_500_empty_table(self, storage_db):
        """Test load_ingredient_500 with empty table"""
        # 创建空DataFrame
        empty_data = pd.DataFrame(columns=[COL_STOCK_ID, COL_STOCK_NAME])

        # Mock pd.read_sql
        with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
            mock_read_sql.return_value = empty_data

            # 调用方法
            result = storage_db.load_ingredient_500()

            # 验证结果
            assert len(result) == 0
            assert result.columns.tolist() == [COL_STOCK_ID, COL_STOCK_NAME]

            # 验证调用参数
            mock_read_sql.assert_called_once()
            args, kwargs = mock_read_sql.call_args
            assert len(args) == 2
            assert (
                tb_name_ingredient_500 in args[0]
            )  # SQL query should contain table name
            assert args[1] == storage_db.engine  # engine parameter

    def test_load_ingredient_500_table_not_exists(self, storage_db):
        """Test load_ingredient_500 when table does not exist"""
        # Mock pd.read_sql to raise exception
        with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
            mock_read_sql.side_effect = Exception("Table does not exist")

            # 调用方法
            result = storage_db.load_ingredient_500()

            # 验证结果 - 应该返回空DataFrame
            assert len(result) == 0
            assert result.columns.tolist() == [COL_STOCK_ID, COL_STOCK_NAME]

            # 验证调用参数
            mock_read_sql.assert_called_once()
            args, kwargs = mock_read_sql.call_args
            assert len(args) == 2
            assert (
                tb_name_ingredient_500 in args[0]
            )  # SQL query should contain table name
            assert args[1] == storage_db.engine  # engine parameter

    def test_load_ingredient_500_database_error(self, storage_db):
        """Test load_ingredient_500 with database error"""
        # Mock pd.read_sql to raise database exception
        with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
            mock_read_sql.side_effect = Exception("Database connection error")

            # 调用方法
            result = storage_db.load_ingredient_500()

            # 验证结果 - 应该返回空DataFrame
            assert len(result) == 0
            assert result.columns.tolist() == [COL_STOCK_ID, COL_STOCK_NAME]

            # 验证调用参数
            mock_read_sql.assert_called_once()
            args, kwargs = mock_read_sql.call_args
            assert len(args) == 2
            assert (
                tb_name_ingredient_500 in args[0]
            )  # SQL query should contain table name
            assert args[1] == storage_db.engine  # engine parameter

    def test_save_and_load_ingredient_300_integration(self, storage_db):
        """Test save_ingredient_300 and load_ingredient_300 work together"""
        # 创建测试数据
        test_data = pd.DataFrame(
            {
                COL_STOCK_ID: ["000001", "000002"],
                COL_STOCK_NAME: ["平安银行", "万科A"],
            }
        )

        # Mock save操作
        with patch.object(test_data, "to_sql") as mock_to_sql:
            # Mock load操作
            with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
                mock_read_sql.return_value = test_data

                # 先保存数据
                storage_db.save_ingredient_300(test_data)

                # 再加载数据
                result = storage_db.load_ingredient_300()

                # 验证保存操作
                mock_to_sql.assert_called_once_with(
                    tb_name_ingredient_300,
                    storage_db.engine,
                    if_exists="replace",
                    index=False,
                )

                # 验证加载操作
                mock_read_sql.assert_called_once()
                args, kwargs = mock_read_sql.call_args
                assert len(args) == 2
                assert (
                    tb_name_ingredient_300 in args[0]
                )  # SQL query should contain table name
                assert args[1] == storage_db.engine  # engine parameter

                # 验证数据一致性
                assert len(result) == 2
                assert result[COL_STOCK_ID].tolist() == ["000001", "000002"]
                assert result[COL_STOCK_NAME].tolist() == ["平安银行", "万科A"]

    def test_save_and_load_ingredient_500_integration(self, storage_db):
        """Test save_ingredient_500 and load_ingredient_500 work together"""
        # 创建测试数据
        test_data = pd.DataFrame(
            {
                COL_STOCK_ID: ["000001", "000002"],
                COL_STOCK_NAME: ["平安银行", "万科A"],
            }
        )

        # Mock save操作
        with patch.object(test_data, "to_sql") as mock_to_sql:
            # Mock load操作
            with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
                mock_read_sql.return_value = test_data

                # 先保存数据
                storage_db.save_ingredient_500(test_data)

                # 再加载数据
                result = storage_db.load_ingredient_500()

                # 验证保存操作
                mock_to_sql.assert_called_once_with(
                    tb_name_ingredient_500,
                    storage_db.engine,
                    if_exists="replace",
                    index=False,
                )

                # 验证加载操作
                mock_read_sql.assert_called_once()
                args, kwargs = mock_read_sql.call_args
                assert len(args) == 2
                assert (
                    tb_name_ingredient_500 in args[0]
                )  # SQL query should contain table name
                assert args[1] == storage_db.engine  # engine parameter

                # 验证数据一致性
                assert len(result) == 2
                assert result[COL_STOCK_ID].tolist() == ["000001", "000002"]
                assert result[COL_STOCK_NAME].tolist() == ["平安银行", "万科A"]

    def test_load_history_data_stock_hk_ggt_daily_success(
        self, storage_db, monkeypatch
    ):
        """Test successful load_history_data_stock_hk_ggt for daily data"""
        test_data = pd.DataFrame(
            {
                COL_DATE: ["2023-01-01", "2023-01-02", "2023-01-03"],
                COL_STOCK_ID: ["00700", "00700", "00700"],  # 港股通股票代码
                COL_OPEN: [380.5, 385.2, 390.1],
                COL_CLOSE: [385.2, 390.1, 395.8],
                COL_HIGH: [388.0, 392.5, 398.2],
                COL_LOW: [378.0, 383.5, 389.0],
                COL_VOLUME: [1500000, 1600000, 1700000],
                COL_AMOUNT: [577500000, 616160000, 672860000],
                COL_CHANGE_RATE: [1.23, 1.27, 1.46],
                COL_TURNOVER_RATE: [0.15, 0.16, 0.17],
            }
        )

        mock_read_sql = Mock(return_value=test_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        result = storage_db.load_history_data_stock_hk_ggt(
            "00700", PeriodType.DAILY, AdjustType.HFQ
        )

        # 验证结果
        assert len(result) == 3
        assert result[COL_STOCK_ID].tolist() == ["00700", "00700", "00700"]
        assert result[COL_DATE].tolist() == ["2023-01-01", "2023-01-02", "2023-01-03"]
        assert result[COL_CLOSE].tolist() == [385.2, 390.1, 395.8]

        # 验证SQL查询参数
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        sql_query = args[0]
        assert "history_data_daily_hk_stock_hfq" in sql_query
        assert 'WHERE "股票代码" = %s' in sql_query  # 使用实际的列名
        assert 'ORDER BY "日期" ASC' in sql_query  # 使用实际的列名
        assert args[1] == storage_db.engine  # engine参数
        assert kwargs["params"] == ("00700",)  # stock_id参数

    def test_load_history_data_stock_hk_ggt_weekly_success(
        self, storage_db, monkeypatch
    ):
        """Test successful load_history_data_stock_hk_ggt for weekly data"""
        test_data = pd.DataFrame(
            {
                COL_DATE: ["2023-01-01", "2023-01-08", "2023-01-15"],
                COL_STOCK_ID: ["09988", "09988", "09988"],  # 港股通股票代码
                COL_OPEN: [85.5, 87.2, 89.1],
                COL_CLOSE: [87.2, 89.1, 91.5],
                COL_HIGH: [88.0, 90.5, 92.8],
                COL_LOW: [84.0, 86.5, 88.2],
                COL_VOLUME: [2500000, 2600000, 2800000],
                COL_AMOUNT: [217500000, 226760000, 246400000],
                COL_CHANGE_RATE: [1.99, 2.18, 2.69],
                COL_TURNOVER_RATE: [0.25, 0.26, 0.28],
            }
        )

        mock_read_sql = Mock(return_value=test_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        result = storage_db.load_history_data_stock_hk_ggt(
            "09988", PeriodType.WEEKLY, AdjustType.HFQ
        )

        # 验证结果
        assert len(result) == 3
        assert result[COL_STOCK_ID].tolist() == ["09988", "09988", "09988"]
        assert result[COL_DATE].tolist() == ["2023-01-01", "2023-01-08", "2023-01-15"]
        assert result[COL_CLOSE].tolist() == [87.2, 89.1, 91.5]

        # 验证SQL查询参数
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        sql_query = args[0]
        assert "history_data_weekly_hk_stock_hfq" in sql_query
        assert kwargs["params"] == ("09988",)

    def test_load_history_data_stock_hk_ggt_monthly_success(
        self, storage_db, monkeypatch
    ):
        """Test successful load_history_data_stock_hk_ggt for monthly data"""
        test_data = pd.DataFrame(
            {
                COL_DATE: ["2023-01-31", "2023-02-28", "2023-03-31"],
                COL_STOCK_ID: ["02318", "02318", "02318"],  # 港股通股票代码
                COL_OPEN: [45.5, 47.2, 49.1],
                COL_CLOSE: [47.2, 49.1, 51.5],
                COL_HIGH: [48.0, 50.5, 52.8],
                COL_LOW: [44.0, 46.5, 48.2],
                COL_VOLUME: [3500000, 3600000, 3800000],
                COL_AMOUNT: [158750000, 181080000, 197600000],
                COL_CHANGE_RATE: [3.74, 4.03, 4.89],
                COL_TURNOVER_RATE: [0.35, 0.36, 0.38],
            }
        )

        mock_read_sql = Mock(return_value=test_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        result = storage_db.load_history_data_stock_hk_ggt(
            "02318", PeriodType.MONTHLY, AdjustType.HFQ
        )

        # 验证结果
        assert len(result) == 3
        assert result[COL_STOCK_ID].tolist() == ["02318", "02318", "02318"]
        assert result[COL_DATE].tolist() == ["2023-01-31", "2023-02-28", "2023-03-31"]
        assert result[COL_CLOSE].tolist() == [47.2, 49.1, 51.5]

        # 验证SQL查询参数
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        sql_query = args[0]
        assert "history_data_monthly_hk_stock_hfq" in sql_query
        assert kwargs["params"] == ("02318",)

    def test_load_history_data_stock_hk_ggt_with_date_range(
        self, storage_db, monkeypatch
    ):
        """Test load_history_data_stock_hk_ggt with date range filter"""
        test_data = pd.DataFrame(
            {
                COL_DATE: ["2023-01-15", "2023-01-16", "2023-01-17"],
                COL_STOCK_ID: ["00700", "00700", "00700"],  # 港股通股票代码
                COL_OPEN: [382.0, 385.5, 389.2],
                COL_CLOSE: [387.5, 391.2, 395.8],
                COL_HIGH: [390.0, 394.5, 398.8],
                COL_LOW: [380.5, 384.0, 388.5],
                COL_VOLUME: [1400000, 1450000, 1500000],
                COL_AMOUNT: [542500000, 567225000, 593700000],
                COL_CHANGE_RATE: [1.44, 0.95, 1.18],
                COL_TURNOVER_RATE: [0.14, 0.145, 0.15],
            }
        )

        mock_read_sql = Mock(return_value=test_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        result = storage_db.load_history_data_stock_hk_ggt(
            "00700",
            PeriodType.DAILY,
            AdjustType.HFQ,
            start_date="2023-01-15",
            end_date="2023-01-17",
        )

        # 验证结果
        assert len(result) == 3
        assert result[COL_DATE].tolist() == ["2023-01-15", "2023-01-16", "2023-01-17"]

        # 验证SQL查询参数
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        sql_query = args[0]
        assert "history_data_daily_hk_stock_hfq" in sql_query
        assert 'AND "日期" >= %s' in sql_query  # 使用实际的列名
        assert 'AND "日期" <= %s' in sql_query  # 使用实际的列名
        assert kwargs["params"] == ("00700", "2023-01-15", "2023-01-17")

    def test_load_history_data_stock_hk_ggt_unsupported_adjust_type(self, storage_db):
        """Test load_history_data_stock_hk_ggt with unsupported adjust type (should only support HFQ)"""
        # 调用方法，使用不支持的复权类型（港股通只支持后复权）
        result = storage_db.load_history_data_stock_hk_ggt(
            "00700", PeriodType.DAILY, AdjustType.QFQ  # QFQ 不被支持
        )

        # 验证结果 - 应该返回空DataFrame
        assert len(result) == 0
        assert list(result.columns) == []  # 空DataFrame

    def test_load_history_data_stock_hk_ggt_unsupported_period(self, storage_db):
        """Test load_history_data_stock_hk_ggt with unsupported period type"""
        # 调用方法，使用不支持的周期类型
        result = storage_db.load_history_data_stock_hk_ggt(
            "00700", "INVALID_PERIOD", AdjustType.HFQ  # 使用无效周期
        )

        # 验证结果 - 应该返回空DataFrame
        assert len(result) == 0
        assert list(result.columns) == []  # 空DataFrame

    def test_load_history_data_stock_hk_ggt_database_error(
        self, storage_db, monkeypatch
    ):
        """Test load_history_data_stock_hk_ggt handles database errors gracefully"""
        # Mock pd.read_sql to raise database exception
        mock_read_sql = Mock(side_effect=Exception("Database connection error"))
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        # 调用方法
        result = storage_db.load_history_data_stock_hk_ggt(
            "00700", PeriodType.DAILY, AdjustType.HFQ
        )

        # 验证结果 - 应该返回空DataFrame
        assert len(result) == 0
        assert list(result.columns) == []  # 空DataFrame

        # 验证SQL查询被调用
        mock_read_sql.assert_called_once()

    def test_load_history_data_stock_hk_ggt_empty_result(self, storage_db, monkeypatch):
        """Test load_history_data_stock_hk_ggt returns empty DataFrame when no data found"""
        # 创建空DataFrame
        empty_data = pd.DataFrame(
            columns=[
                COL_DATE,
                COL_STOCK_ID,
                COL_OPEN,
                COL_CLOSE,
                COL_HIGH,
                COL_LOW,
                COL_VOLUME,
                COL_AMOUNT,
                COL_CHANGE_RATE,
                COL_TURNOVER_RATE,
            ]
        )

        mock_read_sql = Mock(return_value=empty_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        # 调用方法
        result = storage_db.load_history_data_stock_hk_ggt(
            "00700", PeriodType.DAILY, AdjustType.HFQ
        )

        # 验证结果
        assert len(result) == 0
        assert list(result.columns) == [
            COL_DATE,
            COL_STOCK_ID,
            COL_OPEN,
            COL_CLOSE,
            COL_HIGH,
            COL_LOW,
            COL_VOLUME,
            COL_AMOUNT,
            COL_CHANGE_RATE,
            COL_TURNOVER_RATE,
        ]

        # 验证SQL查询被调用
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        assert kwargs["params"] == ("00700",)

    def test_load_history_data_stock_hk_ggt_with_only_start_date(
        self, storage_db, monkeypatch
    ):
        """Test load_history_data_stock_hk_ggt with only start date filter"""
        test_data = pd.DataFrame(
            {
                COL_DATE: ["2023-01-10", "2023-01-11", "2023-01-12"],
                COL_STOCK_ID: ["00700", "00700", "00700"],  # 港股通股票代码
                COL_OPEN: [383.0, 386.5, 390.2],
                COL_CLOSE: [388.5, 392.2, 396.8],
                COL_HIGH: [391.0, 395.5, 399.8],
                COL_LOW: [381.5, 385.0, 389.5],
                COL_VOLUME: [1350000, 1400000, 1450000],
                COL_AMOUNT: [519750000, 549150000, 575350000],
                COL_CHANGE_RATE: [1.44, 0.95, 1.17],
                COL_TURNOVER_RATE: [0.135, 0.14, 0.145],
            }
        )

        mock_read_sql = Mock(return_value=test_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        result = storage_db.load_history_data_stock_hk_ggt(
            "00700", PeriodType.DAILY, AdjustType.HFQ, start_date="2023-01-10"
        )

        # 验证结果
        assert len(result) == 3
        assert result[COL_DATE].tolist() == ["2023-01-10", "2023-01-11", "2023-01-12"]

        # 验证SQL查询参数
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        sql_query = args[0]
        assert 'AND "日期" >= %s' in sql_query  # 使用实际的列名
        assert 'AND "日期" <= %s' not in sql_query  # 不应该有结束日期条件
        assert kwargs["params"] == ("00700", "2023-01-10")

    def test_load_history_data_stock_hk_ggt_with_only_end_date(
        self, storage_db, monkeypatch
    ):
        """Test load_history_data_stock_hk_ggt with only end date filter"""
        test_data = pd.DataFrame(
            {
                COL_DATE: ["2023-01-05", "2023-01-06", "2023-01-07"],
                COL_STOCK_ID: ["00700", "00700", "00700"],  # 港股通股票代码
                COL_OPEN: [378.0, 381.5, 385.2],
                COL_CLOSE: [383.5, 387.2, 391.8],
                COL_HIGH: [386.0, 390.5, 394.8],
                COL_LOW: [376.5, 380.0, 384.5],
                COL_VOLUME: [1300000, 1350000, 1400000],
                COL_AMOUNT: [498550000, 523525000, 548520000],
                COL_CHANGE_RATE: [1.46, 0.96, 1.19],
                COL_TURNOVER_RATE: [0.13, 0.135, 0.14],
            }
        )

        mock_read_sql = Mock(return_value=test_data)
        monkeypatch.setattr("storage.storage_db.pd.read_sql", mock_read_sql)

        result = storage_db.load_history_data_stock_hk_ggt(
            "00700", PeriodType.DAILY, AdjustType.HFQ, end_date="2023-01-07"
        )

        # 验证结果
        assert len(result) == 3
        assert result[COL_DATE].tolist() == ["2023-01-05", "2023-01-06", "2023-01-07"]

        # 验证SQL查询参数
        mock_read_sql.assert_called_once()
        args, kwargs = mock_read_sql.call_args
        sql_query = args[0]
        assert 'AND "日期" >= %s' not in sql_query  # 不应该有开始日期条件
        assert 'AND "日期" <= %s' in sql_query  # 使用实际的列名
        assert kwargs["params"] == ("00700", "2023-01-07")


if __name__ == "__main__":
    pytest.main([__file__])
