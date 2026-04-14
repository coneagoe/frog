import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from common.const import COL_CLOSE
from monitor.condition import ConditionResult, evaluate_condition
from storage.model.stock_monitor_target import StockMonitorTarget, tb_name_stock_monitor_target


# ── Model smoke tests (keep from Task 1) ──────────────────────────────────────

def test_model_table_name():
    assert tb_name_stock_monitor_target == "stock_monitor_targets"


def test_model_has_required_columns():
    cols = [c.key for c in StockMonitorTarget.__table__.columns]
    for required in ["id", "stock_code", "market", "condition", "note",
                     "frequency", "reset_mode", "enabled",
                     "last_state", "triggered_at", "created_at"]:
        assert required in cols, f"Missing column: {required}"


# ── CRUD smoke test (Task 2) ────────────────────────────────────────────────

def test_load_monitor_targets_returns_list():
    """load_monitor_targets returns list of StockMonitorTarget objects."""
    from storage.storage_db import StorageDb

    mock_session = MagicMock()
    mock_target = StockMonitorTarget(
        id=1, stock_code="600519", market="A",
        condition={"type": "price_threshold", "direction": "below", "value": 1500.0},
        frequency="daily", reset_mode="auto", enabled=True, last_state=False,
    )
    mock_session.query.return_value.filter_by.return_value.filter_by.return_value.all.return_value = [mock_target]

    db = StorageDb.__new__(StorageDb)
    db.Session = MagicMock(return_value=mock_session)
    db.engine = MagicMock()

    results = db.load_monitor_targets(frequency="daily")
    assert len(results) == 1
    assert results[0].stock_code == "600519"


# ── Condition evaluation tests ─────────────────────────────────────────────────

def _make_prices(closes: list[float]) -> pd.DataFrame:
    """Helper: build a simple DataFrame with COL_CLOSE column."""
    return pd.DataFrame({COL_CLOSE: closes})


def test_price_threshold_above_triggers():
    cond = {"type": "price_threshold", "direction": "above", "value": 100.0}
    result = evaluate_condition(cond, current_price=101.0, history_df=None)
    assert result == ConditionResult.TRIGGERED


def test_price_threshold_above_not_triggered():
    cond = {"type": "price_threshold", "direction": "above", "value": 100.0}
    result = evaluate_condition(cond, current_price=99.0, history_df=None)
    assert result == ConditionResult.NOT_TRIGGERED


def test_price_threshold_below_triggers():
    cond = {"type": "price_threshold", "direction": "below", "value": 100.0}
    result = evaluate_condition(cond, current_price=99.0, history_df=None)
    assert result == ConditionResult.TRIGGERED


def test_price_threshold_no_price_returns_insufficient():
    cond = {"type": "price_threshold", "direction": "above", "value": 100.0}
    result = evaluate_condition(cond, current_price=None, history_df=None)
    assert result == ConditionResult.INSUFFICIENT_DATA


def test_price_cross_ma_above_triggers():
    # 20-day MA of 80.0 → price 90.0 is above MA
    closes = [80.0] * 20
    df = _make_prices(closes)
    cond = {"type": "price_cross_ma", "direction": "above", "period": 20}
    result = evaluate_condition(cond, current_price=90.0, history_df=df)
    assert result == ConditionResult.TRIGGERED


def test_price_cross_ma_below_triggers():
    closes = [100.0] * 20
    df = _make_prices(closes)
    cond = {"type": "price_cross_ma", "direction": "below", "period": 20}
    result = evaluate_condition(cond, current_price=90.0, history_df=df)
    assert result == ConditionResult.TRIGGERED


def test_ma_cross_golden_triggers():
    # fast MA(3) > slow MA(5) → golden cross
    closes = [10.0, 10.0, 10.0, 10.0, 10.0, 20.0, 20.0, 20.0]
    df = _make_prices(closes)
    cond = {"type": "ma_cross", "fast": 3, "slow": 5, "direction": "golden"}
    result = evaluate_condition(cond, current_price=None, history_df=df)
    assert result == ConditionResult.TRIGGERED


def test_ma_cross_death_triggers():
    # fast MA(3) < slow MA(5) → death cross
    closes = [20.0, 20.0, 20.0, 20.0, 20.0, 5.0, 5.0, 5.0]
    df = _make_prices(closes)
    cond = {"type": "ma_cross", "fast": 3, "slow": 5, "direction": "death"}
    result = evaluate_condition(cond, current_price=None, history_df=df)
    assert result == ConditionResult.TRIGGERED


def test_change_pct_above_triggers():
    cond = {"type": "change_pct", "direction": "above", "value": 5.0}
    result = evaluate_condition(cond, current_price=None, history_df=None, change_pct=6.5)
    assert result == ConditionResult.TRIGGERED


def test_change_pct_below_triggers():
    cond = {"type": "change_pct", "direction": "below", "value": -5.0}
    result = evaluate_condition(cond, current_price=None, history_df=None, change_pct=-6.0)
    assert result == ConditionResult.TRIGGERED


def test_rsi_overbought_triggers():
    # RSI >70: consecutive up days → RSI = 100
    cond = {"type": "rsi", "period": 14, "direction": "above", "value": 70.0}
    closes = [100.0 + i * 2 for i in range(20)]
    df = _make_prices(closes)
    result = evaluate_condition(cond, current_price=None, history_df=df)
    assert result == ConditionResult.TRIGGERED


def test_rsi_oversold_triggers():
    # RSI <30: consecutive down days → RSI = 0
    cond = {"type": "rsi", "period": 14, "direction": "below", "value": 30.0}
    closes = [100.0 - i * 2 for i in range(20)]
    df = _make_prices(closes)
    result = evaluate_condition(cond, current_price=None, history_df=df)
    assert result == ConditionResult.TRIGGERED


def test_rsi_flat_prices_returns_not_triggered():
    """Flat price series → gain=0, loss=0 → RSI=50 → NOT_TRIGGERED for above-70 threshold."""
    cond = {"type": "rsi", "period": 14, "direction": "above", "value": 70.0}
    closes = [100.0] * 20
    df = _make_prices(closes)
    result = evaluate_condition(cond, current_price=None, history_df=df)
    assert result == ConditionResult.NOT_TRIGGERED


def test_insufficient_data_returns_insufficient():
    cond = {"type": "price_cross_ma", "direction": "above", "period": 20}
    df = _make_prices([100.0] * 5)  # only 5 rows, need 20
    result = evaluate_condition(cond, current_price=110.0, history_df=df)
    assert result == ConditionResult.INSUFFICIENT_DATA


def test_unknown_condition_type_raises():
    cond = {"type": "unknown_type"}
    with pytest.raises(ValueError, match="Unknown condition type"):
        evaluate_condition(cond, current_price=100.0, history_df=None)

