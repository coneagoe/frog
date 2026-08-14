import pytest

from monitor.condition_validation import validate_condition
from monitor.domain_enums import (
    ForecastSSFCandidateState,
    MonitorFrequency,
    MonitorMarket,
    MonitorResetMode,
)


def test_enum_values_match_persisted_contract():
    assert [value.value for value in MonitorMarket] == ["A", "HK", "ETF"]
    assert [value.value for value in MonitorFrequency] == ["daily", "intraday"]
    assert [value.value for value in MonitorResetMode] == ["auto", "manual"]
    assert "delisted_or_unlisted" in {value.value for value in ForecastSSFCandidateState}


def test_validate_condition_accepts_typed_workflow_price_vs_ma_condition():
    condition = {
        "type": "price_vs_ma",
        "direction": "above",
        "period": 20,
        "workflow": "forecast_ssf_ma20",
    }

    assert validate_condition(condition) == condition


def test_validate_condition_accepts_close_cross_ma():
    condition = {"type": "close_cross_ma", "direction": "above", "period": 20}

    assert validate_condition(condition) == condition


@pytest.mark.parametrize(
    ("condition", "message"),
    [
        ({"type": "unknown"}, "condition.type"),
        ({"type": "ma_cross", "direction": "above", "fast": 5, "slow": 20}, "condition.direction"),
        ({"type": "price_threshold", "direction": "above"}, "condition.value"),
        ({"type": "price_vs_ma", "direction": "above", "period": 0}, "condition.period"),
        ({"workflow": "forecast_ssf_ma20"}, "condition.type"),
    ],
)
def test_validate_condition_rejects_invalid_contract(condition, message):
    with pytest.raises(ValueError, match=message):
        validate_condition(condition)
