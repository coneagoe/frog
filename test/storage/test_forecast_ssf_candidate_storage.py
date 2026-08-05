from datetime import date

import pandas as pd
import pytest
from sqlalchemy import create_engine

from common.const import COL_ANN_DATE, COL_FLOAT_HOLDER_NAME
from storage.model import Base, ForecastSSFCandidate
from storage.storage_db import StorageDb


def _sqlite_storage(tmp_path):
    db = StorageDb.__new__(StorageDb)
    db.engine = create_engine(f"sqlite:///{tmp_path}/forecast_ssf_candidates.db")
    from sqlalchemy.orm import sessionmaker

    db.Session = sessionmaker(bind=db.engine)
    Base.metadata.create_all(db.engine)
    return db


def test_candidate_upsert_preserves_one_auditable_record(tmp_path):
    db = _sqlite_storage(tmp_path)
    first = db.upsert_forecast_ssf_candidate(
        stock_code="600001",
        market="A",
        report_end_date=date(2025, 12, 31),
        state="eligible",
        state_reason="ssf_holder_match",
        evidence={
            "forecast": {"ann_date": "2026-01-15"},
            "holder": {"name": "全国社保基金一一八组合"},
        },
        monitor_target_id=7,
    )
    second = db.upsert_forecast_ssf_candidate(
        stock_code="600001",
        market="A",
        report_end_date=date(2025, 12, 31),
        state="blackroom",
        state_reason="active_blackroom",
        evidence={"blackroom": {"banned": True}},
        monitor_target_id=7,
    )

    rows = db.list_forecast_ssf_candidates()

    assert first.stock_code == second.stock_code == "600001"
    assert list(ForecastSSFCandidate.__table__.primary_key.columns.keys()) == ["stock_code"]
    assert [(row.stock_code, row.state, row.monitor_target_id) for row in rows] == [("600001", "blackroom", 7)]
    assert rows[0].evidence == {"blackroom": {"banned": True}}


def test_load_latest_top10_floatholders_returns_all_holders_for_latest_announcement(tmp_path):
    db = _sqlite_storage(tmp_path)
    older_date = date(2025, 10, 30)
    latest_date = date(2026, 1, 31)
    pd.DataFrame(
        {
            "股票代码": ["600001", "600001", "600001"],
            "公告日期": [older_date, latest_date, latest_date],
            "股东名称": ["旧股东", "最新股东甲", "最新股东乙"],
        }
    ).to_sql("top10_floatholders", db.engine, if_exists="append", index=False)

    result = db.load_latest_top10_floatholders("600001")

    assert {
        (row[COL_ANN_DATE], row[COL_FLOAT_HOLDER_NAME])
        for row in result[[COL_ANN_DATE, COL_FLOAT_HOLDER_NAME]].to_dict("records")
    } == {
        (pd.Timestamp(latest_date), "最新股东甲"),
        (pd.Timestamp(latest_date), "最新股东乙"),
    }


def test_workflow_monitor_target_uses_only_matching_marker_and_preserves_id(tmp_path):
    db = _sqlite_storage(tmp_path)
    db.create_monitor_target("600001", "A", {"price": {"above": 10}}, note="manual one")
    db.create_monitor_target("600001", "A", {"price": {"below": 8}}, note="manual two")
    workflow_target = db.create_monitor_target(
        "600001",
        "A",
        {"workflow": "forecast_ssf", "price": {"above": 11}},
        note="workflow",
        last_state=True,
    )

    found = db.find_workflow_monitor_target("600001", "A", "forecast_ssf")
    updated = db.upsert_workflow_monitor_target(
        "600001",
        "A",
        "forecast_ssf",
        {"workflow": "forecast_ssf", "price": {"above": 12}},
        "updated workflow",
        enabled=False,
        reset_last_state=True,
    )

    assert found.id == workflow_target.id
    assert updated.id == workflow_target.id
    assert updated.condition == {"workflow": "forecast_ssf", "price": {"above": 12}}
    assert updated.note == "updated workflow"
    assert not updated.enabled
    assert not updated.last_state
    assert len(db.list_monitor_targets()) == 3


def test_workflow_monitor_target_rejects_duplicate_markers(tmp_path):
    db = _sqlite_storage(tmp_path)
    for note in ["first", "second"]:
        db.create_monitor_target(
            "600001",
            "A",
            {"workflow": "forecast_ssf", "price": {"above": 10}},
            note=note,
        )

    with pytest.raises(ValueError, match="多个 workflow='forecast_ssf' 的监控目标"):
        db.find_workflow_monitor_target("600001", "A", "forecast_ssf")


@pytest.mark.parametrize(
    "condition",
    [
        {"price": {"above": 10}},
        {"workflow": "other_workflow", "price": {"above": 10}},
    ],
)
def test_workflow_monitor_target_rejects_missing_or_conflicting_marker(tmp_path, condition):
    db = _sqlite_storage(tmp_path)

    with pytest.raises(ValueError, match="workflow marker"):
        db.upsert_workflow_monitor_target(
            "600001",
            "A",
            "forecast_ssf_ma20",
            condition,
            "workflow",
            enabled=True,
            reset_last_state=False,
        )

    assert db.list_monitor_targets() == []
