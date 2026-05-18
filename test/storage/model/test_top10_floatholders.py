import os
import sys

import pytest
from sqlalchemy import create_engine, inspect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from storage.model.top10_floatholders import (  # noqa: E402
    Base,
    Top10Floatholders,
    tb_name_top10_floatholders,
)


class TestTop10FloatholdersModel:
    @pytest.fixture
    def sqlite_engine(self, tmp_path):
        db_path = tmp_path / "test.db"
        engine = create_engine(f"sqlite:///{db_path}")
        yield engine
        engine.dispose()

    def test_table_name(self):
        assert tb_name_top10_floatholders == "top10_floatholders"

    def test_table_creation(self, sqlite_engine):
        Base.metadata.create_all(sqlite_engine)
        inspector = inspect(sqlite_engine)
        assert tb_name_top10_floatholders in inspector.get_table_names()

    def test_columns_exist(self, sqlite_engine):
        Base.metadata.create_all(sqlite_engine)
        inspector = inspect(sqlite_engine)
        columns = [
            col["name"] for col in inspector.get_columns(tb_name_top10_floatholders)
        ]
        for expected in [
            "股票代码",
            "公告日期",
            "截止日期",
            "股东名称",
            "持有数量（万股）",
            "占总流通股本持股比例",
            "占流通股本比例",
            "持股变动",
            "股东类型",
        ]:
            assert expected in columns, f"列 '{expected}' 不存在"

    def test_model_class(self):
        assert Top10Floatholders.__tablename__ == "top10_floatholders"
