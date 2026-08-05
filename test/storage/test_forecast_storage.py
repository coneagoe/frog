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
