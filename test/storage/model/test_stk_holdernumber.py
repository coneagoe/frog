import os
import sys

import pytest
from sqlalchemy import create_engine, inspect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from storage.model.stk_holdernumber import (  # noqa: E402
    Base,
    StkHoldernumber,
    tb_name_stk_holdernumber,
)


class TestStkHoldernumberModel:
    @pytest.fixture
    def sqlite_engine(self, tmp_path):
        db_path = tmp_path / "test.db"
        engine = create_engine(f"sqlite:///{db_path}")
        yield engine
        engine.dispose()

    def test_table_name(self):
        assert tb_name_stk_holdernumber == "stk_holdernumber"

    def test_table_creation(self, sqlite_engine):
        Base.metadata.create_all(sqlite_engine)
        inspector = inspect(sqlite_engine)
        assert tb_name_stk_holdernumber in inspector.get_table_names()

    def test_columns_exist(self, sqlite_engine):
        Base.metadata.create_all(sqlite_engine)
        inspector = inspect(sqlite_engine)
        columns = [col["name"] for col in inspector.get_columns(tb_name_stk_holdernumber)]
        for expected in ["股票代码", "公告日期", "截止日期", "股东人数"]:
            assert expected in columns, f"列 '{expected}' 不存在"

    def test_primary_keys(self, sqlite_engine):
        Base.metadata.create_all(sqlite_engine)
        inspector = inspect(sqlite_engine)
        pk_cols = inspector.get_pk_constraint(tb_name_stk_holdernumber)["constrained_columns"]
        assert "股票代码" in pk_cols
        assert "公告日期" in pk_cols

    def test_model_class(self):
        assert StkHoldernumber.__tablename__ == "stk_holdernumber"
