import pandas as pd

from common.const import (
    COL_AMOUNT,
    COL_CLOSE,
    COL_DATE,
    COL_ETF_ESTIMATED_TRADED_PRICE,
    COL_ETF_ID,
    COL_ETF_NET_FLOW_AMOUNT,
    COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO,
    COL_ETF_NET_SHARE_CHANGE,
    COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE,
    COL_ETF_TOTAL_SHARE,
    COL_INDEX_CODE,
    COL_INDEX_TURNOVER_AMOUNT,
    COL_VOLUME,
)
from download.etf_net_flow import (
    ETFNetFlowDiagnosticReason,
    calculate_flow_turnover_ratio,
    calculate_net_flow_amount,
    calculate_net_share_change,
    estimate_etf_traded_price,
    rebuild_etf_net_flow,
)


class FakeETFNetFlowStorage:
    def __init__(
        self,
        *,
        share_rows: list[dict],
        daily_rows: list[dict] | None = None,
        turnover_rows: list[dict] | None = None,
    ) -> None:
        self.share_rows = share_rows
        self.daily_rows = daily_rows or []
        self.turnover_rows = turnover_rows or []
        self.load_share_calls: list[dict] = []
        self.load_daily_calls: list[dict] = []
        self.load_turnover_calls: list[dict] = []
        self.saved_frames: list[pd.DataFrame] = []

    def load_etf_share_size(
        self,
        etf_id: str,
        start_date: str,
        end_date: str,
        include_prior_effective: bool = False,
    ) -> pd.DataFrame:
        self.load_share_calls.append(
            {
                "etf_id": etf_id,
                "start_date": start_date,
                "end_date": end_date,
                "include_prior_effective": include_prior_effective,
            }
        )
        return pd.DataFrame(self.share_rows)

    def load_etf_daily(self, etf_id: str, start_date: str, end_date: str) -> pd.DataFrame:
        self.load_daily_calls.append({"etf_id": etf_id, "start_date": start_date, "end_date": end_date})
        return pd.DataFrame(self.daily_rows)

    def load_index_daily_turnover(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        self.load_turnover_calls.append({"ts_code": ts_code, "start_date": start_date, "end_date": end_date})
        return pd.DataFrame(self.turnover_rows)

    def save_etf_net_flow(self, df: pd.DataFrame) -> bool:
        self.saved_frames.append(df.copy())
        return True


def _share_row(date: str, total_share: float) -> dict:
    return {COL_ETF_ID: "510300", COL_DATE: date, COL_ETF_TOTAL_SHARE: total_share}


def _daily_row(date: str, amount: float | None, volume: float | None, close: float | None) -> dict:
    return {COL_ETF_ID: "510300", COL_DATE: date, COL_AMOUNT: amount, COL_VOLUME: volume, COL_CLOSE: close}


def _turnover_row(date: str, amount: float | None) -> dict:
    return {COL_INDEX_CODE: "000300.SH", COL_DATE: date, COL_INDEX_TURNOVER_AMOUNT: amount}


def _saved_row(storage: FakeETFNetFlowStorage) -> dict:
    assert len(storage.saved_frames) == 1
    return storage.saved_frames[0].iloc[0].to_dict()


def test_rebuild_etf_net_flow_saves_derived_rows_for_mapped_etf() -> None:
    storage = FakeETFNetFlowStorage(
        share_rows=[_share_row("2024-01-02", 100.0), _share_row("2024-01-03", 103.0)],
        daily_rows=[_daily_row("2024-01-03", 240.0, 200.0, 11.0)],
        turnover_rows=[_turnover_row("2024-01-03", 720.0)],
    )

    result = rebuild_etf_net_flow(
        storage=storage,
        etf_code="510300.SH",
        start_date="2024-01-03",
        end_date="2024-01-03",
    )

    assert result.etf_code == "510300"
    assert result.saved_rows == 1
    assert result.diagnostics == ()
    assert storage.load_share_calls == [
        {
            "etf_id": "510300",
            "start_date": "2024-01-03",
            "end_date": "2024-01-03",
            "include_prior_effective": True,
        }
    ]
    assert storage.load_daily_calls == [{"etf_id": "510300", "start_date": "2024-01-03", "end_date": "2024-01-03"}]
    assert storage.load_turnover_calls == [
        {"ts_code": "000300.SH", "start_date": "2024-01-03", "end_date": "2024-01-03"}
    ]
    row = _saved_row(storage)
    assert row == {
        COL_ETF_ID: "510300",
        COL_DATE: "2024-01-03",
        COL_ETF_TOTAL_SHARE: 103.0,
        COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE: 100.0,
        COL_ETF_NET_SHARE_CHANGE: 3.0,
        COL_ETF_ESTIMATED_TRADED_PRICE: 12.0,
        COL_ETF_NET_FLOW_AMOUNT: 360000.0,
        COL_INDEX_CODE: "000300.SH",
        COL_INDEX_TURNOVER_AMOUNT: 720.0,
        COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO: 0.5,
    }


def test_rebuild_etf_net_flow_uses_prior_effective_share_before_start_date() -> None:
    storage = FakeETFNetFlowStorage(
        share_rows=[_share_row("2024-01-01", 98.0), _share_row("2024-01-04", 101.0)],
        daily_rows=[_daily_row("2024-01-04", 150.0, 100.0, 9.0)],
        turnover_rows=[_turnover_row("2024-01-04", 300.0)],
    )

    result = rebuild_etf_net_flow(
        storage=storage,
        etf_code="510300",
        start_date="2024-01-04",
        end_date="2024-01-04",
    )

    assert result.saved_rows == 1
    row = _saved_row(storage)
    assert row[COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE] == 98.0
    assert row[COL_ETF_NET_SHARE_CHANGE] == 3.0


def test_rebuild_etf_net_flow_skips_row_when_prior_share_is_missing() -> None:
    storage = FakeETFNetFlowStorage(
        share_rows=[_share_row("2024-01-03", 103.0)],
        daily_rows=[_daily_row("2024-01-03", 240.0, 200.0, 11.0)],
        turnover_rows=[_turnover_row("2024-01-03", 720.0)],
    )

    result = rebuild_etf_net_flow(
        storage=storage,
        etf_code="510300",
        start_date="2024-01-03",
        end_date="2024-01-03",
    )

    assert result.saved_rows == 0
    assert storage.saved_frames == []
    assert [diagnostic.reason for diagnostic in result.diagnostics] == [ETFNetFlowDiagnosticReason.MISSING_PRIOR_SHARE]
    assert result.diagnostics[0].trade_date == "2024-01-03"


def test_rebuild_etf_net_flow_missing_mapping_skips_loader_calls() -> None:
    storage = FakeETFNetFlowStorage(share_rows=[])

    result = rebuild_etf_net_flow(
        storage=storage,
        etf_code="560000.SH",
        start_date="2024-01-03",
        end_date="2024-01-03",
    )

    assert result.etf_code == "560000"
    assert result.saved_rows == 0
    assert storage.load_share_calls == []
    assert storage.load_daily_calls == []
    assert storage.load_turnover_calls == []
    assert storage.saved_frames == []
    assert [diagnostic.reason for diagnostic in result.diagnostics] == [ETFNetFlowDiagnosticReason.MISSING_MAPPING]
    assert result.diagnostics[0].trade_date is None


def test_rebuild_etf_net_flow_skips_row_when_etf_daily_price_support_is_missing() -> None:
    storage = FakeETFNetFlowStorage(
        share_rows=[_share_row("2024-01-02", 100.0), _share_row("2024-01-03", 103.0)],
        daily_rows=[],
        turnover_rows=[_turnover_row("2024-01-03", 720.0)],
    )

    result = rebuild_etf_net_flow(
        storage=storage,
        etf_code="510300",
        start_date="2024-01-03",
        end_date="2024-01-03",
    )

    assert result.saved_rows == 0
    assert storage.saved_frames == []
    assert [diagnostic.reason for diagnostic in result.diagnostics] == [
        ETFNetFlowDiagnosticReason.MISSING_ETF_DAILY_PRICE
    ]
    assert result.diagnostics[0].trade_date == "2024-01-03"


def test_rebuild_etf_net_flow_missing_index_turnover_saves_row_with_null_ratio() -> None:
    storage = FakeETFNetFlowStorage(
        share_rows=[_share_row("2024-01-02", 100.0), _share_row("2024-01-03", 103.0)],
        daily_rows=[_daily_row("2024-01-03", 240.0, 200.0, 11.0)],
        turnover_rows=[],
    )

    result = rebuild_etf_net_flow(
        storage=storage,
        etf_code="510300",
        start_date="2024-01-03",
        end_date="2024-01-03",
    )

    assert result.saved_rows == 1
    assert [diagnostic.reason for diagnostic in result.diagnostics] == [
        ETFNetFlowDiagnosticReason.MISSING_INDEX_TURNOVER
    ]
    row = _saved_row(storage)
    assert row[COL_INDEX_TURNOVER_AMOUNT] is None
    assert row[COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO] is None


def test_rebuild_etf_net_flow_zero_index_turnover_saves_row_with_null_ratio() -> None:
    storage = FakeETFNetFlowStorage(
        share_rows=[_share_row("2024-01-02", 100.0), _share_row("2024-01-03", 103.0)],
        daily_rows=[_daily_row("2024-01-03", 240.0, 200.0, 11.0)],
        turnover_rows=[_turnover_row("2024-01-03", 0.0)],
    )

    result = rebuild_etf_net_flow(
        storage=storage,
        etf_code="510300",
        start_date="2024-01-03",
        end_date="2024-01-03",
    )

    assert result.saved_rows == 1
    assert [diagnostic.reason for diagnostic in result.diagnostics] == [ETFNetFlowDiagnosticReason.ZERO_INDEX_TURNOVER]
    row = _saved_row(storage)
    assert row[COL_INDEX_TURNOVER_AMOUNT] == 0.0
    assert row[COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO] is None


def test_rebuild_etf_net_flow_uses_close_price_fallback_when_amount_volume_cannot_price() -> None:
    storage = FakeETFNetFlowStorage(
        share_rows=[_share_row("2024-01-02", 100.0), _share_row("2024-01-03", 103.0)],
        daily_rows=[_daily_row("2024-01-03", None, 200.0, 8.5)],
        turnover_rows=[_turnover_row("2024-01-03", 255.0)],
    )

    result = rebuild_etf_net_flow(
        storage=storage,
        etf_code="510300",
        start_date="2024-01-03",
        end_date="2024-01-03",
    )

    assert result.saved_rows == 1
    row = _saved_row(storage)
    assert row[COL_ETF_ESTIMATED_TRADED_PRICE] == 8.5
    assert row[COL_ETF_NET_FLOW_AMOUNT] == 255000.0
    assert row[COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO] == 1.0


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
