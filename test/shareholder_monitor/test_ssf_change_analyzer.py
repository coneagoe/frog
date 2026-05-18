import pandas as pd

from shareholder_monitor.ssf_change_analyzer import (
    SSFChangeAnalysisOutcome,
    analyze_ssf_change,
)


def test_analyze_ssf_change_builds_rankable_stock_signal():
    history = pd.DataFrame(
        {
            "股票代码": ["000001"] * 5,
            "公告日期": pd.to_datetime(["2024-03-31"] * 3 + ["2023-12-31"] * 2),
            "股东名称": [
                "全国社保基金一一八组合",
                "全国社保基金四零六组合",
                "香港中央结算有限公司",
                "全国社保基金一一八组合",
                "全国社保基金五零三组合",
            ],
            "持有数量（万股）": [1200.0, 600.0, 2000.0, 1000.0, 500.0],
            "占总流通股本持股比例": [1.5, 0.8, 2.0, 1.2, 0.6],
            "持股变动": [200.0, 600.0, 0.0, 0.0, 0.0],
        }
    )

    signal = analyze_ssf_change("000001", history)

    assert signal is not None
    assert signal["stock_id"] == "000001"
    assert signal["event_types"] == ["new_entry", "increase", "exit"]
    assert signal["ssf_holder_count_now"] == 2
    assert signal["ssf_holder_count_prev"] == 2
    assert signal["ssf_total_hold_ratio_change"] > 0
    assert signal["score"] > 0


def test_analyze_ssf_change_ignores_holders_with_nan_amounts_in_aggregates():
    history = pd.DataFrame(
        {
            "股票代码": ["000001"] * 3,
            "公告日期": pd.to_datetime(["2024-03-31"] * 2 + ["2023-12-31"]),
            "股东名称": [
                "全国社保基金一一八组合",
                "全国社保基金四零六组合",
                "全国社保基金一一八组合",
            ],
            "持有数量（万股）": [float("nan"), 600.0, 500.0],
            "占总流通股本持股比例": [float("nan"), 0.8, 0.6],
            "持股变动": [0.0, 600.0, 0.0],
        }
    )

    signal = analyze_ssf_change("000001", history)

    assert signal is not None
    assert signal["event_types"] == ["new_entry", "exit"]
    assert signal["ssf_holder_count_now"] == 1
    assert signal["ssf_holder_count_prev"] == 1
    assert len(signal["detail_json"]["holders"]) == 2


def test_analyze_ssf_change_reports_insufficient_history_with_fewer_than_two_periods():
    history = pd.DataFrame(
        {
            "股票代码": ["000001"],
            "公告日期": pd.to_datetime(["2024-03-31"]),
            "股东名称": ["全国社保基金一一八组合"],
            "持有数量（万股）": [1200.0],
            "占总流通股本持股比例": [1.5],
            "持股变动": [200.0],
        }
    )

    assert (
        analyze_ssf_change("000001", history)
        is SSFChangeAnalysisOutcome.INSUFFICIENT_HISTORY
    )


def test_analyze_ssf_change_returns_none_when_ssf_holders_are_unchanged():
    history = pd.DataFrame(
        {
            "股票代码": ["000001"] * 4,
            "公告日期": pd.to_datetime(["2024-03-31"] * 2 + ["2023-12-31"] * 2),
            "股东名称": [
                "全国社保基金一一八组合",
                "全国社保基金四零六组合",
                "全国社保基金一一八组合",
                "全国社保基金四零六组合",
            ],
            "持有数量（万股）": [1200.0, 600.0, 1200.0, 600.0],
            "占总流通股本持股比例": [1.5, 0.8, 1.5, 0.8],
            "持股变动": [0.0, 0.0, 0.0, 0.0],
        }
    )

    assert analyze_ssf_change("000001", history) is None


def test_analyze_ssf_change_returns_negative_score_when_all_ssf_holders_exit():
    history = pd.DataFrame(
        {
            "股票代码": ["000001"] * 2,
            "公告日期": pd.to_datetime(["2024-03-31", "2023-12-31"]),
            "股东名称": ["香港中央结算有限公司", "全国社保基金一一八组合"],
            "持有数量（万股）": [2000.0, 1200.0],
            "占总流通股本持股比例": [2.0, 1.5],
            "持股变动": [0.0, -1200.0],
        }
    )

    signal = analyze_ssf_change("000001", history)

    assert signal is not None
    assert signal["event_types"] == ["exit"]
    assert signal["ssf_holder_count_now"] == 0
    assert signal["ssf_holder_count_prev"] == 1
    assert signal["score"] == -50.0


def test_analyze_ssf_change_returns_exit_signal_when_latest_period_has_no_ssf_holder():
    history = pd.DataFrame(
        {
            "股票代码": ["000001", "000001"],
            "公告日期": pd.to_datetime(["2024-03-31", "2023-12-31"]),
            "股东名称": ["香港中央结算有限公司", "全国社保基金四零六组合"],
            "持有数量（万股）": [2000.0, 900.0],
            "占总流通股本持股比例": [2.0, 1.1],
            "持股变动": [0.0, 0.0],
        }
    )

    signal = analyze_ssf_change("000001", history)

    assert signal is not None
    assert signal["event_types"] == ["exit"]


def test_analyze_ssf_change_aggregates_duplicate_holder_rows_per_period():
    history = pd.DataFrame(
        {
            "股票代码": ["000001"] * 5,
            "公告日期": pd.to_datetime(["2024-03-31"] * 2 + ["2023-12-31"] * 3),
            "股东名称": [
                "全国社保基金一一八组合",
                "全国社保基金一一八组合",
                "全国社保基金一一八组合",
                "全国社保基金一一八组合",
                "全国社保基金五零三组合",
            ],
            "持有数量（万股）": [700.0, 500.0, 400.0, 500.0, 600.0],
            "占总流通股本持股比例": [0.9, 0.6, 0.5, 0.6, 0.7],
            "持股变动": [300.0, 200.0, 0.0, 0.0, 0.0],
        }
    )

    signal = analyze_ssf_change("000001", history)

    assert signal is not None
    assert signal["event_types"] == ["increase", "exit"]
    assert signal["ssf_holder_count_now"] == 1
    assert signal["ssf_holder_count_prev"] == 2
    assert signal["ssf_total_hold_ratio_now"] == 1.5
    assert signal["ssf_total_hold_ratio_prev"] == 1.8
    assert signal["detail_json"]["holders"] == [
        {
            "holder_name": "全国社保基金一一八组合",
            "event_type": "increase",
            "latest_amount": 1200.0,
            "prev_amount": 900.0,
        },
        {
            "holder_name": "全国社保基金五零三组合",
            "event_type": "exit",
            "latest_amount": None,
            "prev_amount": 600.0,
        },
    ]
