import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from storage.model.stock_monitor_target import StockMonitorTarget, tb_name_stock_monitor_target


def test_model_table_name():
    assert tb_name_stock_monitor_target == "stock_monitor_targets"


def test_model_has_required_columns():
    cols = [c.key for c in StockMonitorTarget.__table__.columns]
    for required in ["id", "stock_code", "market", "condition", "note",
                     "frequency", "reset_mode", "enabled",
                     "last_state", "triggered_at", "created_at"]:
        assert required in cols, f"Missing column: {required}"
