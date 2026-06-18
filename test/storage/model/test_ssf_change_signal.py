import os
import sys

import pytest
from sqlalchemy import create_engine, inspect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from storage.model.base import Base  # noqa: E402
from storage.model.ssf_change_signal import (  # noqa: E402
    SSFChangeSignal,
    tb_name_ssf_change_signal,
)


@pytest.fixture
def sqlite_engine(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    yield engine
    engine.dispose()


def test_ssf_change_signal_table_name():
    assert tb_name_ssf_change_signal == "ssf_change_signals"
    assert SSFChangeSignal.__tablename__ == "ssf_change_signals"


def test_ssf_change_signal_schema(sqlite_engine):
    Base.metadata.create_all(sqlite_engine)
    inspector = inspect(sqlite_engine)
    columns = {col["name"] for col in inspector.get_columns(tb_name_ssf_change_signal)}
    assert {
        "id",
        "stock_id",
        "ann_date",
        "status",
        "prev_ann_date",
        "event_types",
        "score",
        "ssf_holder_count_now",
        "ssf_holder_count_prev",
        "ssf_holder_count_change",
        "ssf_total_hold_ratio_now",
        "ssf_total_hold_ratio_prev",
        "ssf_total_hold_ratio_change",
        "detail_json",
        "created_at",
        "alert_sent_at",
    } <= columns

    unique_constraints = inspector.get_unique_constraints(tb_name_ssf_change_signal)
    assert any(set(constraint["column_names"]) == {"stock_id", "ann_date"} for constraint in unique_constraints)
