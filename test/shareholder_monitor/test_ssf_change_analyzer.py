import pandas as pd

from shareholder_monitor.ssf_change_analyzer import analyze_ssf_change


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
