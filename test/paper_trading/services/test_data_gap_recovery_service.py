from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from common.const import (
    COL_AMOUNT,
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    COL_VOLUME,
    AdjustType,
    PeriodType,
)
from paper_trading.domain.enums import DataGapRecoveryClassification, DataGapRecoveryRouting
from paper_trading.services.data_gap_recovery_service import DataGapRecoveryService


def _row(stock_id: str, business_date: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            COL_DATE: [business_date],
            COL_STOCK_ID: [stock_id],
            COL_OPEN: [10.0],
            COL_HIGH: [11.0],
            COL_LOW: [9.0],
            COL_CLOSE: [10.5],
            COL_VOLUME: [100.0],
            COL_AMOUNT: [1000.0],
        }
    )


def _service(storage: Mock, downloader: Mock, repository: Mock) -> DataGapRecoveryService:
    return DataGapRecoveryService(storage=storage, downloader=downloader, repository=repository)


def test_unified_recovery_records_classification_and_ordinary_routing():
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.return_value = _row("000001", "2026-08-07")
    repository = Mock()
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "ordinary"},
    )

    result = _service(storage, downloader, repository).recover_unresolved_ordinary_gaps([gap], batch_id=9)

    assert result[0].routing == DataGapRecoveryRouting.ORDINARY.value
    assert result[0].classification == DataGapRecoveryClassification.ORDER_DEPENDENT.value
    repository.record_attempt.assert_called()
    evidence = repository.record_attempt.call_args.args[3]
    assert evidence["classification"] == DataGapRecoveryClassification.ORDER_DEPENDENT.value
    assert evidence["routing"] == DataGapRecoveryRouting.ORDINARY.value


def test_unexpected_diagnostic_failure_carries_processed_results():
    storage = Mock()
    storage.load_history_data_stock.return_value = _row("000001", "2026-08-07")
    downloader = Mock()
    repository = Mock()

    class BrokenDiagnosticGap:
        id = 2

        @property
        def summary(self):
            raise ValueError("diagnostic unavailable")

    first = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "ordinary"},
    )

    with pytest.raises(ValueError, match="diagnostic unavailable") as raised:
        _service(storage, downloader, repository).recover_unresolved_ordinary_gaps(
            [first, BrokenDiagnosticGap()], batch_id=9
        )

    assert [item.status for item in raised.value.partial_results] == ["skipped"]


def test_failed_provider_gap_is_retryable_and_does_not_block_next_gap(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order", lambda: ["baostock"]
    )
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), pd.DataFrame(), _row("000002", "2026-08-08")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.side_effect = [RuntimeError("down"), _row("000002", "2026-08-08")]
    repository = Mock()
    gaps = [
        SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq"),
        SimpleNamespace(id=2, business_date=date(2026, 8, 8), stock_id="000002", market="a_share", adjust="bfq"),
    ]

    results = _service(storage, downloader, repository).recover_unresolved_ordinary_gaps(gaps, batch_id=9)

    assert [item.status for item in results] == ["failed", "recovered"]


def test_existing_exact_row_is_idempotent_and_does_not_call_provider():
    storage = Mock()
    storage.load_history_data_stock.return_value = _row("000001", "2026-08-07")
    downloader = Mock()
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_unresolved_ordinary_gaps([gap])

    assert result[0].status == "skipped"
    downloader.dl_history_data_stock_by_provider.assert_not_called()
    storage.save_history_data_stock.assert_not_called()


def test_account_repair_and_approval_routes_are_not_executed():
    storage, downloader, repository = Mock(), Mock(), Mock()
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "account_repair"},
    )

    result = _service(storage, downloader, repository).recover_unresolved_ordinary_gaps([gap])

    assert result[0].status == "failed"
    assert "ordinary" in (result[0].error or "")
    repository.upsert_account_progress.assert_not_called()
    repository.record_approval.assert_not_called()
    repository.record_alert.assert_not_called()


def test_invalid_routing_is_rejected_without_side_effects():
    storage, downloader, repository = Mock(), Mock(), Mock()
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"routing": "unexpected_route"},
    )

    result = _service(storage, downloader, repository).recover_unresolved_ordinary_gaps([gap])

    assert result[0].status == "failed"
    assert result[0].routing == DataGapRecoveryRouting.APPROVAL_ESCALATION.value
    assert "routing" in (result[0].error or "")
    storage.load_history_data_stock.assert_not_called()
    storage.save_history_data_stock.assert_not_called()
    downloader.dl_history_data_stock_by_provider.assert_not_called()
    repository.record_attempt.assert_not_called()
    repository.resolve_gap.assert_not_called()


def test_approval_escalation_route_is_rejected_without_side_effects():
    storage, downloader, repository = Mock(), Mock(), Mock()
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"routing": "approval_escalation"},
    )

    result = _service(storage, downloader, repository).recover_unresolved_ordinary_gaps([gap])

    assert result[0].status == "failed"
    assert result[0].routing == DataGapRecoveryRouting.APPROVAL_ESCALATION.value
    storage.load_history_data_stock.assert_not_called()
    downloader.dl_history_data_stock_by_provider.assert_not_called()
    repository.record_approval.assert_not_called()
    repository.record_alert.assert_not_called()


@pytest.mark.parametrize(
    "routing",
    [DataGapRecoveryRouting.ACCOUNT_REPAIR.value, DataGapRecoveryRouting.APPROVAL_ESCALATION.value, "invalid_route"],
)
def test_public_recover_gap_rejects_nonordinary_routes_before_all_side_effects(routing):
    storage, downloader, repository = Mock(), Mock(), Mock()
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"routing": routing},
    )

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "failed"
    assert result.routing in {item.value for item in DataGapRecoveryRouting}
    assert result.routing != DataGapRecoveryRouting.ORDINARY.value
    storage.load_history_data_stock.assert_not_called()
    storage.save_history_data_stock.assert_not_called()
    downloader.dl_history_data_stock_by_provider.assert_not_called()
    for method in (
        "record_attempt",
        "resolve_gap",
        "upsert_account_progress",
        "record_approval",
        "record_alert",
        "rebuild_account_ledger",
        "run_paper_trading_ledger_rebuild",
        "save_snapshot",
        "create_account",
        "create_initial_snapshot",
        "repair_account",
        "repair_order",
        "escalate_gap",
        "escalate_account",
    ):
        getattr(repository, method).assert_not_called()


def test_public_recover_gaps_isolates_nonordinary_gap_without_blocking_ordinary_gap():
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.return_value = _row("000001", "2026-08-07")
    repository = Mock()
    gaps = [
        SimpleNamespace(
            id=1,
            business_date=date(2026, 8, 7),
            stock_id="000001",
            market="a_share",
            adjust="bfq",
            summary={"routing": DataGapRecoveryRouting.ACCOUNT_REPAIR.value},
        ),
        SimpleNamespace(
            id=2,
            business_date=date(2026, 8, 7),
            stock_id="000001",
            market="a_share",
            adjust="bfq",
            summary={"routing": DataGapRecoveryRouting.ORDINARY.value},
        ),
    ]

    results = _service(storage, downloader, repository).recover_gaps(gaps)

    assert [result.status for result in results] == ["failed", "recovered"]
    assert storage.load_history_data_stock.call_count == 2
    downloader.dl_history_data_stock_by_provider.assert_called_once()
    repository.record_attempt.assert_called_once()
    repository.resolve_gap.assert_called_once_with(2)
    repository.upsert_account_progress.assert_not_called()
    repository.record_approval.assert_not_called()
    repository.record_alert.assert_not_called()
    repository.rebuild_account_ledger.assert_not_called()
    repository.run_paper_trading_ledger_rebuild.assert_not_called()
    repository.save_snapshot.assert_not_called()
    repository.create_account.assert_not_called()
    repository.create_initial_snapshot.assert_not_called()
    repository.repair_account.assert_not_called()
    repository.repair_order.assert_not_called()
    repository.escalate_gap.assert_not_called()
    repository.escalate_account.assert_not_called()


def test_existing_exact_row_skips_provider_and_repair():
    storage = Mock()
    storage.load_history_data_stock.return_value = _row("000001", "2026-08-07")
    downloader = Mock()
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "skipped"
    downloader.dl_history_data_stock_by_provider.assert_not_called()
    storage.save_history_data_stock.assert_not_called()
    repository.resolve_gap.assert_called_once_with(gap.id)


@pytest.mark.parametrize("stored_row", [_row("000002", "2026-08-07"), _row("000001", "2026-08-08")])
def test_non_matching_existing_row_does_not_skip_provider(stored_row):
    storage = Mock()
    storage.load_history_data_stock.return_value = stored_row
    downloader = Mock()
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "failed"
    downloader.dl_history_data_stock_by_provider.assert_called()


@pytest.mark.parametrize(
    ("market", "adjust", "stock_id"),
    [
        ("hk_connect", "bfq", "000001"),
        ("a_share", "qfq", "000001"),
        ("a_share", "bfq", "１２３４５６"),
    ],
)
def test_invalid_gap_identity_fails_before_storage_or_provider_interaction(market, adjust, stock_id):
    storage = Mock()
    downloader = Mock()
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id=stock_id, market=market, adjust=adjust)

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "failed"
    assert result.error
    storage.load_history_data_stock.assert_not_called()
    storage.save_history_data_stock.assert_not_called()
    downloader.dl_history_data_stock_by_provider.assert_not_called()


def test_empty_provider_result_falls_back_to_next_provider(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order",
        lambda: ["baostock", "tushare"],
    )
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "recovered"
    assert result.provider == "tushare"
    assert downloader.dl_history_data_stock_by_provider.call_count == 2


def test_invalid_provider_result_falls_back_to_next_provider(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order",
        lambda: ["baostock", "tushare"],
    )
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.side_effect = [
        pd.DataFrame({"unexpected": [1]}),
        _row("000001", "2026-08-07"),
    ]
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "recovered"
    assert result.provider == "tushare"


def test_first_valid_exact_provider_short_circuits_later_providers(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order",
        lambda: ["baostock", "tushare"],
    )
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.return_value = _row("000001", "2026-08-07")
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "recovered"
    downloader.dl_history_data_stock_by_provider.assert_called_once()


def test_attempt_persistence_failure_is_failed_and_does_not_fallback(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order",
        lambda: ["baostock", "tushare"],
    )
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.return_value = _row("000001", "2026-08-07")
    repository = Mock()
    repository.record_attempt.side_effect = RuntimeError("attempt persistence down")
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "failed"
    assert "attempt persistence down" in (result.error or "")
    downloader.dl_history_data_stock_by_provider.assert_called_once()
    repository.resolve_gap.assert_not_called()
    assert repository.record_attempt.call_count == 1


def test_resolution_persistence_failure_after_write_is_failed(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order", lambda: ["baostock"]
    )
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.return_value = _row("000001", "2026-08-07")
    repository = Mock()
    repository.resolve_gap.side_effect = RuntimeError("resolution persistence down")
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "failed"
    assert "resolution persistence down" in (result.error or "")
    repository.record_attempt.assert_called_once()


def test_missing_gap_uses_first_valid_exact_provider_row_and_reads_back():
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.side_effect = [
        _row("000002", "2026-08-07"),
        _row("000001", "2026-08-07"),
    ]
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "recovered"
    assert downloader.dl_history_data_stock_by_provider.call_count == 2
    assert all(
        call.args[2:4] == ("20260807", "20260807")
        for call in downloader.dl_history_data_stock_by_provider.call_args_list
    )
    assert all(
        call.args[4:] == (PeriodType.DAILY, AdjustType.BFQ)
        for call in downloader.dl_history_data_stock_by_provider.call_args_list
    )
    saved = storage.save_history_data_stock.call_args.args[0]
    assert len(saved) == 1
    assert saved.iloc[0][COL_STOCK_ID] == "000001"


def test_surrounding_provider_dates_are_narrowed_to_target_row():
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.return_value = pd.concat(
        [_row("000001", "2026-08-06"), _row("000001", "2026-08-07"), _row("000001", "2026-08-08")],
        ignore_index=True,
    )
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "recovered"
    saved = storage.save_history_data_stock.call_args.args[0]
    assert len(saved) == 1
    assert saved.iloc[0][COL_DATE].date() == date(2026, 8, 7)


def test_readback_failure_is_retryable():
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), pd.DataFrame()]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.return_value = _row("000001", "2026-08-07")
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "failed"
    assert "readback" in (result.error or "")


@pytest.mark.parametrize("readback_row", [_row("000002", "2026-08-07"), _row("000001", "2026-08-08")])
def test_non_matching_non_empty_readback_is_failure(readback_row):
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), readback_row]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.return_value = _row("000001", "2026-08-07")
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "failed"
    assert "readback" in (result.error or "")


def test_one_failed_gap_does_not_block_later_gap(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order", lambda: ["baostock"]
    )
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), pd.DataFrame(), _row("000002", "2026-08-08")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.side_effect = [RuntimeError("down"), _row("000002", "2026-08-08")]
    repository = Mock()
    gaps = [
        SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq"),
        SimpleNamespace(id=2, business_date=date(2026, 8, 8), stock_id="000002", market="a_share", adjust="bfq"),
    ]

    results = _service(storage, downloader, repository).recover_gaps(gaps)

    assert [item.status for item in results] == ["failed", "recovered"]


def test_repository_recording_failure_returns_failed_gap_and_does_not_block_later_gap(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order", lambda: ["baostock"]
    )
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), pd.DataFrame(), _row("000002", "2026-08-08")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.side_effect = [RuntimeError("down"), _row("000002", "2026-08-08")]
    repository = Mock()
    repository.record_attempt.side_effect = [RuntimeError("repository down"), None, None]
    gaps = [
        SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq"),
        SimpleNamespace(id=2, business_date=date(2026, 8, 8), stock_id="000002", market="a_share", adjust="bfq"),
    ]

    results = _service(storage, downloader, repository).recover_gaps(gaps)

    assert [item.status for item in results] == ["failed", "recovered"]
    assert "repository down" in (results[0].error or "")


def test_repository_resolution_failure_returns_failed_gap_and_does_not_block_later_gap(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order", lambda: ["baostock"]
    )
    storage = Mock()
    storage.load_history_data_stock.side_effect = [
        _row("000001", "2026-08-07"),
        pd.DataFrame(),
        _row("000002", "2026-08-08"),
    ]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.return_value = _row("000002", "2026-08-08")
    repository = Mock()
    repository.resolve_gap.side_effect = [RuntimeError("resolution repository down"), None]
    gaps = [
        SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq"),
        SimpleNamespace(id=2, business_date=date(2026, 8, 8), stock_id="000002", market="a_share", adjust="bfq"),
    ]

    results = _service(storage, downloader, repository).recover_gaps(gaps)

    assert [item.status for item in results] == ["failed", "recovered"]
    assert "resolution repository down" in (results[0].error or "")


def test_write_failure_is_retryable_and_does_not_accept_another_provider(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order",
        lambda: ["baostock", "tushare"],
    )
    storage = Mock()
    storage.load_history_data_stock.return_value = pd.DataFrame()
    storage.save_history_data_stock.return_value = False
    downloader = Mock(return_value=None)
    downloader.dl_history_data_stock_by_provider.return_value = _row("000001", "2026-08-07")
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "failed"
    downloader.dl_history_data_stock_by_provider.assert_called_once()
