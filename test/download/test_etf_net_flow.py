from download.etf_net_flow import (
    calculate_flow_turnover_ratio,
    calculate_net_flow_amount,
    calculate_net_share_change,
    estimate_etf_traded_price,
)


def test_calculate_net_share_change_returns_difference_between_share_sizes() -> None:
    assert calculate_net_share_change(125.5, 120.0) == 5.5


def test_calculate_net_flow_amount_keeps_negative_redemption_sign() -> None:
    assert calculate_net_flow_amount(-2.5, 1.2) == -30000.0


def test_estimate_etf_traded_price_uses_amount_and_volume_units() -> None:
    assert estimate_etf_traded_price(240.0, 200.0, 9.9) == 12.0


def test_estimate_etf_traded_price_falls_back_to_positive_close() -> None:
    assert estimate_etf_traded_price(0.0, 200.0, 3.45) == 3.45


def test_estimate_etf_traded_price_returns_none_when_price_inputs_missing() -> None:
    assert estimate_etf_traded_price(None, 200.0, None) is None
    assert estimate_etf_traded_price(240.0, 0.0, 0.0) is None


def test_calculate_flow_turnover_ratio_uses_index_turnover_units() -> None:
    assert calculate_flow_turnover_ratio(25000.0, 500.0) == 0.05


def test_calculate_flow_turnover_ratio_returns_none_for_missing_turnover() -> None:
    assert calculate_flow_turnover_ratio(25000.0, None) is None


def test_calculate_flow_turnover_ratio_returns_none_for_zero_turnover() -> None:
    assert calculate_flow_turnover_ratio(25000.0, 0.0) is None
