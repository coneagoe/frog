from datetime import date

import pandas as pd
from sqlalchemy import create_engine, text

from storage.model import Base
from storage.storage_db import StorageDb


def test_load_active_forecast_candidates_keeps_latest_announcement(tmp_path):
    db = StorageDb.__new__(StorageDb)
    db.engine = create_engine(f"sqlite:///{tmp_path}/forecast.db")
    db.Session = None
    Base.metadata.create_all(db.engine)
    with db.engine.begin() as conn:
        conn.execute(
            text(
                'INSERT INTO a_stock_basic ("股票代码", "股票名称", "上市状态") '
                "VALUES ('600001', '正常公司', 'L'), ('000001', '*ST 风险公司', 'L')"
            )
        )
    db.ensure_forecasts_table()
    db.save_forecasts(
        pd.DataFrame(
            {
                "股票代码": ["600001", "600001", "000001"],
                "公告日期": [date(2025, 1, 1), date(2025, 1, 5), date(2025, 1, 2)],
                "截止日期": [date(2024, 12, 31)] * 3,
                "预告类型": ["预增", "预增", "预增"],
                "增长下限": [60.0, 50.0, 100.0],
                "增长上限": [80.0, 70.0, 120.0],
            }
        )
    )

    result = db.load_active_forecast_candidates(as_of_date=date(2025, 1, 10))

    assert result[["股票代码", "公告日期", "增长下限"]].to_dict("records") == [
        {"股票代码": "600001", "公告日期": date(2025, 1, 5), "增长下限": 50.0}
    ]


def test_save_forecasts_is_idempotent_for_repeated_normalized_rows(tmp_path):
    db = StorageDb.__new__(StorageDb)
    db.engine = create_engine(f"sqlite:///{tmp_path}/forecast.db")
    db.Session = None
    Base.metadata.create_all(db.engine)
    db.ensure_forecasts_table()
    forecast = pd.DataFrame(
        {
            "股票代码": ["600001.SH"],
            "公告日期": ["2025-01-05"],
            "截止日期": ["2024-12-31"],
            "预告类型": ["预增"],
            "增长下限": [50.0],
            "增长上限": [70.0],
        }
    )

    assert db.save_forecasts(forecast) is True
    assert db.save_forecasts(forecast) is True

    with db.engine.connect() as conn:
        rows = (
            conn.execute(text('SELECT "股票代码", "公告日期", "截止日期", "增长下限" FROM forecasts')).mappings().all()
        )

    assert len(rows) == 1
    assert rows[0]["股票代码"] == "600001"
    assert rows[0]["增长下限"] == 50.0
