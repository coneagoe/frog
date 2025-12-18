import os
import sys

import pytest
from sqlalchemy import create_engine, inspect

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
)
from storage.model.history_data_a_stock import (  # noqa: E402
    Base,
    HistoryDataDailyAStockQFQ,
    HistoryDataWeeklyAStockQFQ,
    tb_name_history_data_daily_a_stock_qfq,
    tb_name_history_data_weekly_a_stock_qfq,
)


class TestHistoryDataDailyAStockTableCreation:
    @pytest.fixture
    def sqlite_engine(self, tmp_path):
        db_path = tmp_path / "test.db"
        engine = create_engine(f"sqlite:///{db_path}")
        yield engine
        engine.dispose()

    def test_table_creation_with_file_db(self, sqlite_engine):
        Base.metadata.create_all(sqlite_engine)

        inspector = inspect(sqlite_engine)
        tables = inspector.get_table_names()

        assert (
            tb_name_history_data_daily_a_stock_qfq in tables
        ), f"数据表 '{tb_name_history_data_daily_a_stock_qfq}' 未成功创建"

        columns = inspector.get_columns(tb_name_history_data_daily_a_stock_qfq)
        column_names = [col["name"] for col in columns]

        expected_columns = [
            "日期",
            "股票代码",
            "开盘",
            "收盘",
            "最高",
            "最低",
            "成交量",
            "成交额",
            "换手率(%)",
            "涨跌幅(%)",
            "市盈率(TTM)",
            "市净率(MRQ)",
            "市销率(TTM)",
            "市现率(TTM)",
            "是否ST",
        ]

        for expected_col in expected_columns:
            assert expected_col in column_names, f"列 '{expected_col}' 不存在"

    def test_table_creation_weekly_a_stock(self, sqlite_engine):
        Base.metadata.create_all(sqlite_engine)

        inspector = inspect(sqlite_engine)
        tables = inspector.get_table_names()

        assert (
            tb_name_history_data_weekly_a_stock_qfq in tables
        ), f"数据表 '{tb_name_history_data_weekly_a_stock_qfq}' 未成功创建"

        columns = inspector.get_columns(tb_name_history_data_weekly_a_stock_qfq)
        column_names = [col["name"] for col in columns]

        expected_columns = [
            "日期",
            "股票代码",
            "开盘",
            "收盘",
            "最高",
            "最低",
            "成交量",
            "成交额",
            "换手率(%)",
            "涨跌幅(%)",
        ]

        for expected_col in expected_columns:
            assert expected_col in column_names, f"列 '{expected_col}' 不存在"

    def test_model_attributes(self):
        """测试模型的属性设置和获取"""
        daily_stock = HistoryDataDailyAStockQFQ()
        daily_stock.日期 = "2023-01-01"
        daily_stock.股票代码 = "000001"
        daily_stock.开盘 = 10.5
        daily_stock.收盘 = 11.2

        # 验证属性设置正确
        assert daily_stock.日期 == "2023-01-01"
        assert daily_stock.股票代码 == "000001"
        assert daily_stock.开盘 == 10.5
        assert daily_stock.收盘 == 11.2

        weekly_stock = HistoryDataWeeklyAStockQFQ()
        weekly_stock.日期 = "2023-01-01"
        weekly_stock.股票代码 = "000001"
        weekly_stock.最高 = 12.0
        weekly_stock.最低 = 9.8

        # 验证属性设置正确
        assert weekly_stock.日期 == "2023-01-01"
        assert weekly_stock.股票代码 == "000001"
        assert weekly_stock.最高 == 12.0
        assert weekly_stock.最低 == 9.8


if __name__ == "__main__":
    pytest.main([__file__])
