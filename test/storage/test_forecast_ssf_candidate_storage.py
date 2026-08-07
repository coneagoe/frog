from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from common.const import COL_ANN_DATE, COL_DELISTING_DATE, COL_FLOAT_HOLDER_NAME, COL_LIST_STATUS, COL_STOCK_ID
from storage import storage_db as storage_db_module
from storage.model import AStockBasic, Base, ForecastSSFCandidate
from storage.storage_db import StorageDb


def _sqlite_storage(tmp_path):
    db = StorageDb.__new__(StorageDb)
    db.engine = create_engine(f"sqlite:///{tmp_path}/forecast_ssf_candidates.db")
    db.Session = sessionmaker(bind=db.engine)
    Base.metadata.create_all(db.engine)
    return db


def _legacy_monitor_target_storage(tmp_path):
    db = StorageDb.__new__(StorageDb)
    db.engine = create_engine(f"sqlite:///{tmp_path}/legacy_monitor_targets.db")
    db.Session = sessionmaker(bind=db.engine)
    with db.engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE stock_monitor_targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code VARCHAR(10) NOT NULL,
                    market VARCHAR(5) NOT NULL DEFAULT 'A',
                    condition JSON NOT NULL,
                    note TEXT,
                    frequency VARCHAR(10) NOT NULL DEFAULT 'daily',
                    reset_mode VARCHAR(10) NOT NULL DEFAULT 'auto',
                    enabled BOOLEAN NOT NULL DEFAULT true,
                    last_state BOOLEAN NOT NULL DEFAULT false,
                    triggered_at DATETIME,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
    return db


def _typed_condition(**extra: Any) -> dict[str, Any]:
    return {"type": "price_threshold", "direction": "above", "value": 10} | extra


def _create_target(db, *, workflow: str | None, enabled: bool = True):
    condition = _typed_condition()
    if workflow is not None:
        condition["workflow"] = workflow
    return db.create_monitor_target("600001", "A", condition, workflow or "manual", enabled=enabled)


def _create_linked_forecast_ssf_target(db, *, enabled: bool, state: str):
    target = _create_target(db, workflow="forecast_ssf_ma20", enabled=enabled)
    candidate = db.upsert_forecast_ssf_candidate(
        stock_code="600001",
        market="A",
        report_end_date=date(2025, 12, 31),
        state=state,
        state_reason="ssf_holder_match",
        evidence={"forecast": {"ann_date": "2026-01-15"}},
        monitor_target_id=target.id,
    )
    return target, candidate


def test_direct_storage_create_rejects_invalid_condition_before_commit(tmp_path):
    db = _sqlite_storage(tmp_path)

    with pytest.raises(ValueError, match="condition.type"):
        db.create_monitor_target("600001", "A", {"workflow": "forecast_ssf_ma20"})


@pytest.mark.parametrize("field,value", [("market", "US"), ("frequency", "weekly"), ("reset_mode", "never")])
def test_direct_monitor_storage_rejects_unknown_finite_values(tmp_path, field, value):
    db = _sqlite_storage(tmp_path)
    kwargs = {"market": "A", "frequency": "daily", "reset_mode": "auto"}
    kwargs[field] = value

    with pytest.raises(ValueError):
        db.create_monitor_target("600001", condition=_typed_condition(), **kwargs)


def test_forecast_candidate_storage_rejects_unknown_state(tmp_path):
    db = _sqlite_storage(tmp_path)

    with pytest.raises(ValueError, match="state"):
        db.upsert_forecast_ssf_candidate("600001", "A", date(2025, 12, 31), "unknown", "reason", {}, None)


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


def test_load_monitor_targets_filters_enabled_targets_by_workflow(tmp_path):
    db = _sqlite_storage(tmp_path)
    workflow_target = _create_target(db, workflow="forecast_ssf_ma20")
    _create_target(db, workflow=None)
    _create_target(db, workflow="other_workflow", enabled=False)

    assert [target.id for target in db.load_monitor_targets("daily", "forecast_ssf_ma20")] == [workflow_target.id]


def test_get_forecast_ssf_candidate_for_target_returns_linked_candidate(tmp_path):
    db = _sqlite_storage(tmp_path)
    target, candidate = _create_linked_forecast_ssf_target(db, enabled=True, state="eligible")

    saved = db.get_forecast_ssf_candidate_for_target(target.id)

    assert saved.stock_code == candidate.stock_code
    assert db.get_forecast_ssf_candidate_for_target(target.id + 1) is None


def test_delete_transition_removes_owned_target_and_retains_candidate(tmp_path):
    db = _sqlite_storage(tmp_path)
    target, _ = _create_linked_forecast_ssf_target(db, enabled=True, state="eligible")
    evidence = {"lifecycle": {"state": "ineligible", "reason": "ssf_holder_not_found"}}

    assert (
        db.delete_forecast_ssf_target_with_candidate_transition(
            target.id, "ineligible", "ssf_holder_not_found", evidence
        )
        is True
    )

    assert db.get_monitor_target(target.id) is None
    assert db.get_forecast_ssf_candidate_for_target(target.id) is None
    saved = db.list_forecast_ssf_candidates()[0]
    assert (saved.state, saved.state_reason, saved.monitor_target_id) == (
        "ineligible",
        "ssf_holder_not_found",
        None,
    )
    assert saved.evidence == evidence


def test_disable_blackroom_wrapper_deletes_target_and_retains_candidate(tmp_path):
    db = _sqlite_storage(tmp_path)
    target, _ = _create_linked_forecast_ssf_target(db, enabled=True, state="eligible")

    assert db.disable_forecast_ssf_target_for_blackroom(target.id, "active_blackroom") is True

    assert db.get_monitor_target(target.id) is None
    saved = db.list_forecast_ssf_candidates()[0]
    assert (saved.state, saved.state_reason, saved.monitor_target_id) == ("blackroom", "active_blackroom", None)


def test_blackroom_delete_builds_lifecycle_evidence_with_previous_state(tmp_path, monkeypatch):
    db = _sqlite_storage(tmp_path)
    target, _ = _create_linked_forecast_ssf_target(db, enabled=True, state="eligible")
    fixed_date = date(2026, 8, 6)

    class FrozenDate(date):
        @classmethod
        def today(cls):
            return fixed_date

    monkeypatch.setattr(storage_db_module, "date", FrozenDate)

    assert db.delete_forecast_ssf_target_for_blackroom(target.id, "active_blackroom") is True
    assert db.get_monitor_target(target.id) is None
    saved = db.list_forecast_ssf_candidates()[0]
    assert saved.state == "blackroom"
    assert saved.state_reason == "active_blackroom"
    assert saved.monitor_target_id is None
    assert saved.evidence == {
        "forecast": {"ann_date": "2026-01-15"},
        "lifecycle": {
            "as_of_date": fixed_date.isoformat(),
            "state": "blackroom",
            "reason": "active_blackroom",
            "previous_state": "eligible",
        },
    }


def test_blackroom_delete_uses_current_candidate_without_detached_pre_read(tmp_path, monkeypatch):
    db = _sqlite_storage(tmp_path)
    target, _ = _create_linked_forecast_ssf_target(db, enabled=True, state="eligible")
    db.upsert_forecast_ssf_candidate(
        stock_code="600001",
        market="A",
        report_end_date=date(2025, 12, 31),
        state="paused",
        state_reason="sync_paused",
        evidence={"forecast": {"ann_date": "2026-02-01"}, "sync": {"version": 2}},
        monitor_target_id=target.id,
    )
    monkeypatch.setattr(
        db,
        "get_forecast_ssf_candidate_for_target",
        MagicMock(side_effect=AssertionError("blackroom transition must not pre-read candidate")),
    )

    assert db.delete_forecast_ssf_target_for_blackroom(target.id, "active_blackroom") is True

    saved = db.list_forecast_ssf_candidates()[0]
    assert saved.evidence == {
        "forecast": {"ann_date": "2026-02-01"},
        "sync": {"version": 2},
        "lifecycle": {
            "as_of_date": date.today().isoformat(),
            "state": "blackroom",
            "reason": "active_blackroom",
            "previous_state": "paused",
        },
    }


def test_blackroom_delete_rolls_back_candidate_when_target_delete_fails(tmp_path, monkeypatch):
    db = _sqlite_storage(tmp_path)
    target, _ = _create_linked_forecast_ssf_target(db, enabled=True, state="eligible")
    monkeypatch.setattr(
        db,
        "_delete_workflow_target_in_transaction",
        MagicMock(side_effect=RuntimeError("delete failed")),
    )

    with pytest.raises(RuntimeError, match="delete failed"):
        db.delete_forecast_ssf_target_for_blackroom(target.id, "active_blackroom")

    assert db.get_monitor_target(target.id) is not None
    saved = db.list_forecast_ssf_candidates()[0]
    assert (saved.state, saved.monitor_target_id) == ("eligible", target.id)
    assert saved.evidence == {"forecast": {"ann_date": "2026-01-15"}}


def test_delete_transition_rejects_duplicate_candidates_before_mutation(tmp_path):
    db = _sqlite_storage(tmp_path)
    target, _ = _create_linked_forecast_ssf_target(db, enabled=True, state="eligible")
    db.upsert_forecast_ssf_candidate(
        stock_code="600002",
        market="A",
        report_end_date=date(2025, 12, 31),
        state="eligible",
        state_reason="ssf_holder_match",
        evidence={"before": True},
        monitor_target_id=target.id,
    )

    with pytest.raises(ValueError, match=r"multiple candidates.*monitor_target_id"):
        db.get_forecast_ssf_candidate_for_target(target.id)

    with pytest.raises(ValueError, match=r"multiple candidates.*monitor_target_id"):
        db.delete_forecast_ssf_target_with_candidate_transition(
            target.id, "blackroom", "active_blackroom", {"after": True}
        )

    assert db.get_monitor_target(target.id) is not None
    assert {candidate.state for candidate in db.list_forecast_ssf_candidates()} == {"eligible"}


@pytest.mark.parametrize("workflow, linked", [(None, True), ("other_workflow", True), ("forecast_ssf_ma20", False)])
def test_delete_transition_leaves_unowned_or_unlinked_target_unchanged(tmp_path, workflow, linked):
    db = _sqlite_storage(tmp_path)
    target = _create_target(db, workflow=workflow)
    if linked:
        db.upsert_forecast_ssf_candidate(
            stock_code="600001",
            market="A",
            report_end_date=date(2025, 12, 31),
            state="eligible",
            state_reason="ssf_holder_match",
            evidence={"before": True},
            monitor_target_id=target.id,
        )

    assert (
        db.delete_forecast_ssf_target_with_candidate_transition(
            target.id, "blackroom", "active_blackroom", {"after": True}
        )
        is False
    )
    assert db.get_monitor_target(target.id) is not None
    saved = db.get_forecast_ssf_candidate_for_target(target.id)
    if linked:
        assert saved.state == "eligible"
        assert saved.evidence == {"before": True}
    else:
        assert saved is None


def test_delete_transition_leaves_owned_non_daily_target_unchanged(tmp_path):
    db = _sqlite_storage(tmp_path)
    target = db.create_monitor_target(
        "600001",
        "A",
        _typed_condition(workflow="forecast_ssf_ma20"),
        frequency="intraday",
    )
    db.upsert_forecast_ssf_candidate(
        stock_code="600001",
        market="A",
        report_end_date=date(2025, 12, 31),
        state="eligible",
        state_reason="ssf_holder_match",
        evidence={"before": True},
        monitor_target_id=target.id,
    )

    assert (
        db.delete_forecast_ssf_target_with_candidate_transition(
            target.id, "blackroom", "active_blackroom", {"after": True}
        )
        is False
    )

    assert db.get_monitor_target(target.id) is not None
    saved = db.get_forecast_ssf_candidate_for_target(target.id)
    assert saved.state == "eligible"
    assert saved.monitor_target_id == target.id
    assert saved.evidence == {"before": True}


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


def test_load_a_stock_listing_status_returns_requested_rows_and_omits_absent_codes(tmp_path):
    db = _sqlite_storage(tmp_path)
    session = db.Session()
    try:
        session.add_all(
            [
                AStockBasic(**{COL_STOCK_ID: "600001", "股票名称": "active", COL_LIST_STATUS: "L"}),
                AStockBasic(
                    **{
                        COL_STOCK_ID: "600002",
                        "股票名称": "delisted",
                        COL_LIST_STATUS: "D",
                        COL_DELISTING_DATE: date(2026, 1, 1),
                    }
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    result = db.load_a_stock_listing_status(["600001", "600002", "600003"])

    assert list(result.columns) == [COL_STOCK_ID, COL_LIST_STATUS, COL_DELISTING_DATE]
    assert result[COL_STOCK_ID].tolist() == ["600001", "600002"]
    assert result.loc[result[COL_STOCK_ID] == "600001", COL_LIST_STATUS].item() == "L"
    assert str(result.loc[result[COL_STOCK_ID] == "600002", COL_DELISTING_DATE].item()) == "2026-01-01"


def test_load_a_stock_listing_status_empty_input_returns_schema_only(tmp_path):
    db = _sqlite_storage(tmp_path)

    result = db.load_a_stock_listing_status([])

    assert list(result.columns) == [COL_STOCK_ID, COL_LIST_STATUS, COL_DELISTING_DATE]
    assert result.empty


def test_workflow_monitor_target_uses_only_matching_marker_and_preserves_id(tmp_path):
    db = _sqlite_storage(tmp_path)
    db.create_monitor_target("600001", "A", _typed_condition(), note="manual one")
    db.create_monitor_target("600001", "A", _typed_condition(direction="below", value=8), note="manual two")
    workflow_target = db.create_monitor_target(
        "600001",
        "A",
        _typed_condition(workflow="forecast_ssf", value=11),
        note="workflow",
        last_state=True,
    )

    found = db.find_workflow_monitor_target("600001", "A", "daily", "forecast_ssf")
    updated = db.upsert_workflow_monitor_target(
        "600001",
        "A",
        "daily",
        "forecast_ssf",
        _typed_condition(workflow="forecast_ssf", value=12),
        "updated workflow",
        enabled=False,
        reset_last_state=True,
    )

    assert found.id == workflow_target.id
    assert updated.id == workflow_target.id
    assert updated.condition == _typed_condition(workflow="forecast_ssf", value=12)
    assert updated.note == "updated workflow"
    assert not updated.enabled
    assert not updated.last_state
    assert len(db.list_monitor_targets()) == 3


def test_pause_resume_migrates_legacy_targets_and_preserves_disabled_resume(tmp_path):
    db = _legacy_monitor_target_storage(tmp_path)
    with db.engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO stock_monitor_targets (stock_code, market, condition, note)
                VALUES ('600001', 'A', :condition, 'workflow target')
                """
            ),
            {"condition": '{"workflow": "forecast_ssf"}'},
        )

    db.ensure_monitor_targets_table()

    target = db.get_monitor_target(1)
    assert target.paused is False
    paused = db.set_workflow_monitor_target_paused(target.id, paused=True)
    resumed = db.set_workflow_monitor_target_paused(target.id, paused=False)

    assert (paused.paused, paused.enabled) == (True, False)
    assert (resumed.paused, resumed.enabled) == (False, False)


def test_pause_rejects_manual_target_without_mutation(tmp_path):
    db = _sqlite_storage(tmp_path)
    manual = db.create_monitor_target("600001", "A", _typed_condition())

    with pytest.raises(ValueError, match="workflow"):
        db.set_workflow_monitor_target_paused(manual.id, paused=True)

    assert db.get_monitor_target(manual.id).enabled is True


def test_pause_returns_none_for_missing_target(tmp_path):
    db = _sqlite_storage(tmp_path)

    assert db.set_workflow_monitor_target_paused(1, paused=True) is None


def test_paused_workflow_target_stays_disabled_on_automatic_upsert(tmp_path):
    db = _sqlite_storage(tmp_path)
    target = db.upsert_workflow_monitor_target(
        "600001",
        "A",
        "daily",
        "forecast_ssf",
        _typed_condition(workflow="forecast_ssf"),
        "workflow",
        enabled=True,
        reset_last_state=False,
    )
    db.set_workflow_monitor_target_paused(target.id, paused=True)

    updated = db.upsert_workflow_monitor_target(
        "600001",
        "A",
        "daily",
        "forecast_ssf",
        _typed_condition(workflow="forecast_ssf", version=2),
        "updated workflow",
        enabled=True,
        reset_last_state=False,
    )

    assert updated.paused is True
    assert updated.enabled is False


def test_legacy_monitor_target_migration_backfills_empty_workflow_before_orm_access(tmp_path):
    db = _legacy_monitor_target_storage(tmp_path)
    with db.engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO stock_monitor_targets (stock_code, market, condition, note)
                VALUES
                    ('600001', 'A', :workflow_condition, 'workflow target'),
                    ('600002', 'A', :manual_condition, 'manual target')
                """
            ),
            {
                "workflow_condition": '{"workflow": "", "price": {"above": 10}}',
                "manual_condition": '{"price": {"below": 8}}',
            },
        )

    db.ensure_monitor_targets_table()
    targets = db.list_monitor_targets()
    created = db.create_monitor_target("600003", "A", _typed_condition(value=11), note="new manual target")

    assert [(target.stock_code, target.workflow) for target in targets] == [("600001", ""), ("600002", None)]
    assert created.stock_code == "600003"


@pytest.mark.parametrize(
    "operation",
    ["list", "get", "create", "update", "delete", "state"],
)
def test_generic_monitor_target_operations_migrate_legacy_schema_before_orm_access(tmp_path, operation):
    db = _legacy_monitor_target_storage(tmp_path)
    with db.engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO stock_monitor_targets (stock_code, market, condition, note)
                VALUES ('600001', 'A', :condition, 'legacy manual target')
                """
            ),
            {"condition": '{"price": {"above": 10}}'},
        )

    if operation == "list":
        assert [target.id for target in db.list_monitor_targets()] == [1]
    elif operation == "get":
        assert db.get_monitor_target(1).stock_code == "600001"
    elif operation == "create":
        assert db.create_monitor_target("600002", "A", _typed_condition(direction="below", value=8)).id == 2
    elif operation == "update":
        assert db.update_monitor_target(1, note="updated legacy target").note == "updated legacy target"
    elif operation == "delete":
        assert db.delete_monitor_target(1) is True
    else:
        db.update_monitor_target_state(1, True)
        assert db.get_monitor_target(1).last_state is True


def test_legacy_monitor_target_migration_reports_duplicate_workflow_owners_before_index_creation(tmp_path):
    db = _legacy_monitor_target_storage(tmp_path)
    with db.engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO stock_monitor_targets (stock_code, market, condition, note)
                VALUES
                    ('600001', 'A', :first_condition, 'first workflow target'),
                    ('600001', 'A', :second_condition, 'second workflow target')
                """
            ),
            {
                "first_condition": '{"workflow": "forecast_ssf_ma20"}',
                "second_condition": '{"workflow": "forecast_ssf_ma20"}',
            },
        )

    with pytest.raises(
        ValueError,
        match=r"600001/A/daily/'forecast_ssf_ma20'.*ids: \[1, 2\]",
    ):
        db.ensure_monitor_targets_table()

    index_names = {index["name"] for index in inspect(db.engine).get_indexes("stock_monitor_targets")}
    assert "uq_stock_monitor_targets_workflow_owner" not in index_names


def test_empty_workflow_marker_enforces_unique_owner_and_manual_targets_remain_unrestricted(tmp_path):
    db = _sqlite_storage(tmp_path)

    db.create_monitor_target("600001", "A", _typed_condition(workflow=""), note="empty workflow target")

    with pytest.raises(IntegrityError):
        db.create_monitor_target("600001", "A", _typed_condition(workflow=""), note="duplicate empty workflow target")

    manual = db.create_monitor_target("600001", "A", _typed_condition(), note="manual target")

    assert manual.workflow is None


def test_workflow_monitor_target_rejects_duplicate_markers(tmp_path):
    db = _sqlite_storage(tmp_path)
    db.create_monitor_target("600001", "A", _typed_condition(workflow="forecast_ssf"), note="first")

    with pytest.raises(IntegrityError):
        db.create_monitor_target("600001", "A", _typed_condition(workflow="forecast_ssf"), note="second")


@pytest.mark.parametrize(
    "condition",
    [
        _typed_condition(),
        _typed_condition(workflow="other_workflow"),
    ],
)
def test_workflow_monitor_target_rejects_missing_or_conflicting_marker(tmp_path, condition):
    db = _sqlite_storage(tmp_path)

    with pytest.raises(ValueError, match="workflow marker"):
        db.upsert_workflow_monitor_target(
            "600001",
            "A",
            "daily",
            "forecast_ssf_ma20",
            condition,
            "workflow",
            enabled=True,
            reset_last_state=False,
        )

    assert db.list_monitor_targets() == []


def test_workflow_owned_monitor_target_rejects_condition_marker_replacement(tmp_path):
    db = _sqlite_storage(tmp_path)
    target = db.create_monitor_target(
        "600001",
        "A",
        _typed_condition(workflow="forecast_ssf"),
        note="workflow",
    )

    for condition in (_typed_condition(value=11), _typed_condition(workflow="other_workflow", value=11)):
        with pytest.raises(ValueError, match="workflow marker"):
            db.update_monitor_target(target.id, condition=condition)

        persisted = db.get_monitor_target(target.id)
        assert persisted.condition == _typed_condition(workflow="forecast_ssf")
        assert persisted.workflow == "forecast_ssf"


def test_empty_workflow_owned_monitor_target_rejects_unmarked_condition_replacement(tmp_path):
    db = _sqlite_storage(tmp_path)
    target = db.create_monitor_target(
        "600001",
        "A",
        _typed_condition(workflow=""),
        note="empty workflow",
    )

    with pytest.raises(ValueError, match="workflow marker"):
        db.update_monitor_target(target.id, condition=_typed_condition(value=11))

    persisted = db.get_monitor_target(target.id)
    assert persisted.condition == _typed_condition(workflow="")
    assert persisted.workflow == ""


def test_workflow_owned_monitor_target_accepts_matching_condition_marker(tmp_path):
    db = _sqlite_storage(tmp_path)
    target = db.create_monitor_target(
        "600001",
        "A",
        _typed_condition(workflow="forecast_ssf"),
        note="workflow",
    )

    updated = db.update_monitor_target(
        target.id,
        condition=_typed_condition(workflow="forecast_ssf", value=11),
    )

    assert updated.condition == _typed_condition(workflow="forecast_ssf", value=11)
    assert updated.workflow == "forecast_ssf"


def test_manual_monitor_target_accepts_unmarked_condition_replacement(tmp_path):
    db = _sqlite_storage(tmp_path)
    target = db.create_monitor_target("600001", "A", _typed_condition(), note="manual")

    updated = db.update_monitor_target(target.id, condition=_typed_condition(value=11))

    assert updated.condition == _typed_condition(value=11)
    assert updated.workflow is None


def test_manual_monitor_target_rejects_condition_workflow_marker(tmp_path):
    db = _sqlite_storage(tmp_path)
    target = db.create_monitor_target("600001", "A", _typed_condition(), note="manual")

    with pytest.raises(ValueError, match="manual.*workflow marker"):
        db.update_monitor_target(target.id, condition=_typed_condition(workflow="forecast_ssf", value=11))

    persisted = db.get_monitor_target(target.id)
    assert persisted.condition == _typed_condition()
    assert persisted.workflow is None


def test_workflow_monitor_target_scope_does_not_mutate_intraday_target(tmp_path):
    db = _sqlite_storage(tmp_path)
    intraday = db.create_monitor_target(
        "600001",
        "A",
        _typed_condition(workflow="forecast_ssf", value=11),
        note="intraday workflow",
        frequency="intraday",
        last_state=True,
    )

    assert db.find_workflow_monitor_target("600001", "A", "daily", "forecast_ssf") is None
    daily = db.upsert_workflow_monitor_target(
        "600001",
        "A",
        "daily",
        "forecast_ssf",
        _typed_condition(workflow="forecast_ssf", value=12),
        "daily workflow",
        enabled=True,
        reset_last_state=True,
    )

    targets = db.list_monitor_targets()
    unchanged_intraday = next(target for target in targets if target.id == intraday.id)
    assert daily.frequency == "daily"
    assert len(targets) == 2
    assert unchanged_intraday.frequency == "intraday"
    assert unchanged_intraday.enabled is True
    assert unchanged_intraday.last_state is True


@pytest.mark.parametrize(
    ("existing_target", "enabled"),
    [(False, True), (True, False)],
    ids=["eligible_create", "disable"],
)
def test_atomic_workflow_target_transition_rolls_back_when_candidate_persistence_fails(
    tmp_path, monkeypatch, existing_target, enabled
):
    db = _sqlite_storage(tmp_path)
    if existing_target:
        original = db.upsert_workflow_monitor_target(
            "600001",
            "A",
            "daily",
            "forecast_ssf_ma20",
            _typed_condition(workflow="forecast_ssf_ma20"),
            "workflow",
            enabled=True,
            reset_last_state=False,
        )

    def fail_candidate(*args, **kwargs):
        raise RuntimeError("candidate persistence failed")

    monkeypatch.setattr(db, "_upsert_forecast_ssf_candidate_in_transaction", fail_candidate)

    with pytest.raises(RuntimeError, match="candidate persistence failed"):
        db.upsert_forecast_ssf_candidate_with_workflow_target(
            stock_code="600001",
            market="A",
            report_end_date=date(2025, 12, 31),
            state="eligible" if enabled else "ineligible",
            state_reason="test",
            evidence={"test": True},
            workflow="forecast_ssf_ma20",
            frequency="daily",
            condition=_typed_condition(workflow="forecast_ssf_ma20"),
            note="workflow",
            target_enabled=enabled,
            reset_last_state=enabled,
        )

    target = db.find_workflow_monitor_target("600001", "A", "daily", "forecast_ssf_ma20")
    assert db.list_forecast_ssf_candidates() == []
    if existing_target:
        assert target.id == original.id
        assert target.enabled is True
    else:
        assert target is None


def test_atomic_paused_workflow_transition_rolls_back_candidate_and_target_on_failure(tmp_path, monkeypatch):
    db = _sqlite_storage(tmp_path)
    original_target = db.upsert_workflow_monitor_target(
        "600001",
        "A",
        "daily",
        "forecast_ssf_ma20",
        _typed_condition(workflow="forecast_ssf_ma20"),
        "workflow",
        enabled=True,
        reset_last_state=False,
    )
    db.set_workflow_monitor_target_paused(original_target.id, paused=True)
    original_candidate = db.upsert_forecast_ssf_candidate(
        "600001",
        "A",
        date(2025, 12, 31),
        "eligible",
        "ssf_holder_match",
        {"before": True},
        original_target.id,
    )

    def fail_candidate(*args, **kwargs):
        raise RuntimeError("candidate persistence failed")

    monkeypatch.setattr(db, "_upsert_forecast_ssf_candidate_in_transaction", fail_candidate)

    with pytest.raises(RuntimeError, match="candidate persistence failed"):
        db.upsert_forecast_ssf_candidate_with_workflow_target(
            stock_code="600001",
            market="A",
            report_end_date=date(2025, 12, 31),
            state="paused",
            state_reason="manual_pause",
            evidence={"after": True},
            workflow="forecast_ssf_ma20",
            frequency="daily",
            condition=_typed_condition(workflow="forecast_ssf_ma20", version=2),
            note="updated workflow",
            target_enabled=False,
            reset_last_state=False,
        )

    target = db.find_workflow_monitor_target("600001", "A", "daily", "forecast_ssf_ma20")
    candidate = db.list_forecast_ssf_candidates()[0]
    assert target.id == original_target.id
    assert target.paused is True
    assert target.enabled is False
    assert candidate.stock_code == original_candidate.stock_code
    assert candidate.evidence == {"before": True}


def test_workflow_target_conflict_safe_upsert_preserves_one_durable_owner(tmp_path):
    db = _sqlite_storage(tmp_path)

    first = db.upsert_workflow_monitor_target(
        "600001",
        "A",
        "daily",
        "forecast_ssf_ma20",
        _typed_condition(workflow="forecast_ssf_ma20", version=1),
        "first",
        enabled=True,
        reset_last_state=False,
    )
    second = db.upsert_workflow_monitor_target(
        "600001",
        "A",
        "daily",
        "forecast_ssf_ma20",
        _typed_condition(workflow="forecast_ssf_ma20", version=2),
        "second",
        enabled=True,
        reset_last_state=False,
    )

    targets = [target for target in db.list_monitor_targets() if target.workflow == "forecast_ssf_ma20"]
    assert first.id == second.id
    assert [(target.stock_code, target.market, target.frequency, target.workflow) for target in targets] == [
        ("600001", "A", "daily", "forecast_ssf_ma20")
    ]
