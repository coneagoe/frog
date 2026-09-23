import json
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
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
from paper_trading.domain.enums import DataGapRecoveryClassification, DataGapRecoveryRouting, DataGapRecoveryStatus
from paper_trading.domain.market_data_diagnostics import canonical_stock_id
from paper_trading.services.data_gap_recovery_service import (
    DataGapRecoveryService,
    canonical_candidate_hash,
    canonical_candidate_payload,
)


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
    policy = Mock()
    policy.evaluate.return_value = {
        "target_date_calendar": True,
        "ordinary_eligibility": True,
        "suspension": "active",
        "source": "test-authority",
        "freshness": True,
        "decision": True,
    }
    return DataGapRecoveryService(
        storage=storage, downloader=downloader, repository=repository, hk_recovery_policy=policy
    )


@pytest.mark.parametrize("stock_id", ["00700", "700", "0700", "00700.HK", "HK.00700"])
def test_hk_stock_identity_normalizes_to_five_ascii_digits(stock_id):
    assert canonical_stock_id(stock_id, "hk_connect") == "00700"


@pytest.mark.parametrize("stock_id", ["７００", "123456", "ABC", "000001"])
def test_hk_stock_identity_rejects_invalid_symbols(stock_id):
    with pytest.raises(ValueError):
        canonical_stock_id(stock_id, "hk_connect")


@pytest.mark.parametrize(
    "change",
    [
        {"target_date_calendar": False},
        {"ordinary_eligibility": False},
        {"suspension": "suspended"},
        {"suspension": "unknown"},
        {"source": None},
        {"freshness": False},
        {"decision": None},
    ],
)
def test_hk_authority_rejection_records_evidence_without_provider_or_write(change):
    storage, downloader, repository = Mock(), Mock(), Mock()
    policy = Mock()
    policy.evaluate.return_value = {
        "target_date_calendar": True,
        "ordinary_eligibility": True,
        "suspension": "active",
        "source": "official",
        "freshness": True,
        "decision": True,
        **change,
    }
    gap = SimpleNamespace(
        id=7,
        business_date=date(2026, 8, 7),
        stock_id="00700",
        market="hk_connect",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "ordinary"},
    )

    result = DataGapRecoveryService(
        storage=storage, downloader=downloader, repository=repository, hk_recovery_policy=policy
    ).recover_gap(gap, batch_id=3)

    assert result.status == "failed"
    downloader.dl_history_data_stock_by_provider.assert_not_called()
    downloader.dl_history_data_stock_hk_by_provider.assert_not_called()
    storage.save_history_data_stock.assert_not_called()
    evidence = repository.record_attempt.call_args.args[3]
    assert evidence["hk_authority"] == policy.evaluate.return_value


@pytest.mark.parametrize(
    "market,adjust,stock_id",
    [("etf", "bfq", "510300"), ("a_share", "qfq", "000001"), ("hk_connect", "qfq", "00700")],
)
def test_recovery_rejects_unsupported_identity_without_side_effects(market, adjust, stock_id):
    storage, downloader, repository = Mock(), Mock(), Mock()
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id=stock_id,
        market=market,
        adjust=adjust,
        summary={"classification": "order_dependent", "routing": "ordinary"},
    )

    result = DataGapRecoveryService(storage=storage, downloader=downloader, repository=repository).recover_gap(gap)

    assert result.status == "failed"
    storage.load_history_data_stock.assert_not_called()
    storage.save_history_data_stock.assert_not_called()
    downloader.dl_history_data_stock_by_provider.assert_not_called()
    repository.record_candidate.assert_not_called()


def test_escalation_waits_for_three_unavailable_batch_windows():
    repository = Mock()
    repository.gap_evidence.return_value = {
        "attempts": [
            SimpleNamespace(batch_id=1, outcome="not_found"),
            SimpleNamespace(batch_id=2, outcome="not_found"),
        ]
    }
    gap = SimpleNamespace(id=1, business_date=date(2026, 9, 1), summary={})
    service = _service(Mock(), Mock(), repository)

    assert service.maybe_escalate_gap(gap, user_id=7, user_snapshot={}, as_of=date(2026, 9, 2)) is False
    repository.escalate_gap.assert_not_called()

    repository.gap_evidence.return_value["attempts"].append(SimpleNamespace(batch_id=3, outcome="not_found"))
    assert service.maybe_escalate_gap(gap, user_id=7, user_snapshot={}, as_of=date(2026, 9, 2)) is True
    repository.escalate_gap.assert_called_once()


def test_escalation_occurs_after_five_business_days():
    repository = Mock()
    repository.gap_evidence.return_value = {"attempts": []}
    gap = SimpleNamespace(id=1, business_date=date(2026, 9, 7), summary={})
    service = _service(Mock(), Mock(), repository)

    assert service.maybe_escalate_gap(gap, user_id=7, user_snapshot={}, as_of=date(2026, 9, 11)) is True
    repository.escalate_gap.assert_called_once()


def test_escalation_counts_only_distinct_not_found_batches():
    repository = Mock()
    repository.gap_evidence.return_value = {
        "attempts": [
            SimpleNamespace(batch_id=1, outcome="failed"),
            SimpleNamespace(batch_id=1, outcome="not_found"),
            SimpleNamespace(batch_id=1, outcome="not_found"),
            SimpleNamespace(batch_id=2, outcome="recovered"),
            SimpleNamespace(batch_id=2, outcome="not_found"),
        ]
    }
    gap = SimpleNamespace(id=1, business_date=date(2026, 9, 7), summary={})

    assert (
        _service(Mock(), Mock(), repository).maybe_escalate_gap(
            gap, user_id=7, user_snapshot={}, as_of=date(2026, 9, 8)
        )
        is False
    )
    repository.escalate_gap.assert_not_called()


def test_threshold_escalation_sends_one_alert():
    repository = Mock()
    repository.gap_evidence.return_value = {
        "attempts": [SimpleNamespace(batch_id=i, outcome="not_found") for i in (1, 2, 3)]
    }
    alerts = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 9, 1), summary={})

    service = DataGapRecoveryService(storage=Mock(), downloader=Mock(), repository=repository, alert_service=alerts)
    assert service.maybe_escalate_gap(gap, user_id=7, user_snapshot={}, as_of=date(2026, 9, 2)) is True
    alerts.send_escalation.assert_called_once_with(gap, failure_class="threshold")


def test_escalation_alert_delivery_failure_does_not_mutate_recovery_state():
    repository = Mock()
    repository.gap_evidence.return_value = {"attempts": []}
    alerts = Mock()
    alerts.send_escalation.side_effect = RuntimeError("smtp unavailable")
    gap = SimpleNamespace(id=1, business_date=date(2026, 9, 7), summary={}, status="open")
    service = DataGapRecoveryService(storage=Mock(), downloader=Mock(), repository=repository, alert_service=alerts)

    assert service.maybe_escalate_gap(gap, user_id=7, user_snapshot={}, as_of=date(2026, 9, 11)) is True
    assert gap.status == "open"
    repository.escalate_gap.assert_called_once()


def test_threshold_path_calls_adapter_escalation_and_alert_without_airflow():
    class FreshSessionAdapter:
        def __init__(self):
            self.escalations = []

        def gap_evidence(self, _gap_id):
            return {"attempts": [SimpleNamespace(batch_id=i, outcome="not_found") for i in (1, 2, 3)]}

        def escalate_gap(self, gap_id, user_id, user_snapshot, *, reason=None):
            self.escalations.append((gap_id, user_id, user_snapshot, reason))

    repository = FreshSessionAdapter()
    alerts = Mock()
    gap = SimpleNamespace(id=7, business_date=date(2026, 9, 1), summary={}, status="open")
    service = DataGapRecoveryService(storage=Mock(), downloader=Mock(), repository=repository, alert_service=alerts)

    assert service.maybe_escalate_gap(gap, user_id=0, user_snapshot={"actor": "system"}, as_of=date(2026, 9, 2))
    assert repository.escalations == [(7, 0, {"actor": "system"}, None)]
    alerts.send_escalation.assert_called_once_with(gap, failure_class="threshold")


def test_four_business_days_does_not_count_weekend():
    repository = Mock()
    repository.gap_evidence.return_value = {"attempts": []}
    gap = SimpleNamespace(id=1, business_date=date(2026, 9, 10), summary={})

    assert (
        _service(Mock(), Mock(), repository).maybe_escalate_gap(
            gap, user_id=7, user_snapshot={}, as_of=date(2026, 9, 15)
        )
        is False
    )


def test_hk_escalation_counts_hk_trade_dates_with_injected_calendar():
    repository = Mock()
    repository.gap_evidence.return_value = {"attempts": []}
    calendar = Mock()
    calendar.is_trade_date.side_effect = lambda value: value not in {date(2026, 9, 12)}
    gap = SimpleNamespace(id=1, business_date=date(2026, 9, 10), market="hk_connect", summary={})

    service = DataGapRecoveryService(
        storage=Mock(), downloader=Mock(), repository=repository, hk_trade_calendar=calendar
    )

    assert service.maybe_escalate_gap(gap, user_id=7, user_snapshot={}, as_of=date(2026, 9, 15)) is True
    assert calendar.is_trade_date.call_count == 6


def test_account_recovery_failure_detail_is_sanitized_before_return_and_persistence(monkeypatch):
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    progress_repository = Mock()
    progress_repository.get_account_progress.return_value = None
    storage = Mock(Session=Mock(return_value=Mock()))
    monkeypatch.setattr(dag_module, "DataGapRecoveryRepository", lambda session: progress_repository)
    secret = "authorization=super-secret token=not-for-logs"

    result = dag_module.run_paper_trading_account_recovery(
        affected_account_ids=[11],
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 1),
        rebuild_account=Mock(side_effect=RuntimeError(secret)),
        recalculate_snapshots=Mock(),
        recovery_work=[{"gap_id": 7, "account_id": 11, "start_date": date(2026, 9, 1), "end_date": date(2026, 9, 1)}],
        storage=storage,
    )

    assert result["errors"][11] == "[redacted] [redacted]"
    assert "super-secret" not in str(progress_repository.record_account_recovery_step.call_args)


def test_approved_write_requires_authoritative_repository_and_approval():
    storage = Mock()
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "approval_escalation"},
    )

    result = DataGapRecoveryService(storage=storage, downloader=Mock()).execute_approved_gap(
        gap, "a" * 64, _row("000001", "2026-08-07")
    )
    assert result.status == "failed"
    storage.save_history_data_stock.assert_not_called()

    repository = Mock()
    repository.execute_approved_candidate.side_effect = ValueError("approved candidate is required")
    result = _service(storage, Mock(), repository).execute_approved_gap(gap, "a" * 64, _row("000001", "2026-08-07"))
    assert result.status == "failed"
    storage.save_history_data_stock.assert_not_called()


def test_approved_write_rechecks_hash_and_returns_pending_without_writing():
    storage, downloader, repository = Mock(), Mock(), Mock()
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        latest_candidate_hash="b" * 64,
        summary={"classification": "order_dependent", "routing": "approval_escalation"},
    )
    repository.execute_approved_candidate.side_effect = ValueError("approved candidate hash is stale")
    result = _service(storage, downloader, repository).execute_approved_gap(gap, "a" * 64, _row("000001", "2026-08-07"))

    assert result.status == "pending_approval"
    repository.execute_approved_candidate.assert_called_once()
    storage.save_history_data_stock.assert_not_called()


def test_approved_no_impact_gap_is_terminal_and_does_not_write():
    storage, downloader, repository = Mock(), Mock(), Mock()
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        latest_candidate_hash="a" * 64,
        summary={"classification": "no_impact", "routing": "approval_escalation"},
    )
    repository.execute_approved_candidate.side_effect = lambda _id, _hash, callback: callback(gap)
    result = _service(storage, downloader, repository).execute_approved_gap(gap, "a" * 64, _row("000001", "2026-08-07"))

    assert result.status == "skipped"
    storage.save_history_data_stock.assert_not_called()
    downloader.dl_history_data_stock_by_provider.assert_not_called()


def test_approved_write_uses_repository_locked_gap_for_readback_and_resolution():
    storage, downloader, repository = Mock(), Mock(), Mock()
    detached_gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "approval_escalation"},
    )
    locked_gap = SimpleNamespace(
        id=99,
        business_date=date(2026, 8, 8),
        stock_id="000002",
        market="a_share",
        adjust="bfq",
        summary={"classification": "valuation_only", "routing": "approval_escalation"},
    )
    repository.execute_approved_candidate.side_effect = lambda _id, _hash, callback: callback(locked_gap)
    storage.load_history_data_stock.return_value = _row("000002", "2026-08-08")
    storage.save_history_data_stock.return_value = True
    candidate = _row("000002", "2026-08-08")
    approved_payload = canonical_candidate_payload(
        candidate,
        market=locked_gap.market,
        stock_id=locked_gap.stock_id,
        business_date=locked_gap.business_date,
        adjust=locked_gap.adjust,
    )
    approved_hash = canonical_candidate_hash(approved_payload)

    result = _service(storage, downloader, repository).execute_approved_gap(detached_gap, approved_hash, candidate)

    assert result.gap_id == locked_gap.id
    assert result.classification == "valuation_only"
    repository.resolve_gap.assert_called_once_with(locked_gap.id)
    assert storage.load_history_data_stock.call_args.args[0] == locked_gap.stock_id
    assert storage.load_history_data_stock.call_args.kwargs["start_date"] == "2026-08-08"


def test_approved_write_skips_append_for_matching_preexisting_exact_row():
    storage, downloader, repository = Mock(), Mock(), Mock()
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "approval_escalation"},
    )
    candidate = _row("000001", "2026-08-07")
    storage.load_history_data_stock.return_value = candidate.copy()
    repository.execute_approved_candidate.side_effect = lambda _id, _hash, callback: callback(gap)
    approved_hash = canonical_candidate_hash(
        canonical_candidate_payload(
            candidate, market=gap.market, stock_id=gap.stock_id, business_date=gap.business_date, adjust=gap.adjust
        )
    )

    result = _service(storage, downloader, repository).execute_approved_gap(gap, approved_hash, candidate)

    assert result.status == "recovered"
    storage.save_history_data_stock.assert_not_called()
    repository.resolve_gap.assert_called_once_with(gap.id)


def test_approved_write_retry_after_resolution_failure_does_not_append_twice():
    storage, downloader, repository = Mock(), Mock(), Mock()
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "approval_escalation"},
    )
    candidate = _row("000001", "2026-08-07")
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), candidate.copy(), candidate.copy()]
    storage.save_history_data_stock.return_value = True
    repository.execute_approved_candidate.side_effect = lambda _id, _hash, callback: callback(
        gap, repository.resolve_gap
    )
    repository.resolve_gap.side_effect = [RuntimeError("commit failed"), None]
    approved_hash = canonical_candidate_hash(
        canonical_candidate_payload(
            candidate, market=gap.market, stock_id=gap.stock_id, business_date=gap.business_date, adjust=gap.adjust
        )
    )
    service = _service(storage, downloader, repository)

    first = service.execute_approved_gap(gap, approved_hash, candidate)
    second = service.execute_approved_gap(gap, approved_hash, candidate)

    assert first.status == "failed"
    assert second.status == "recovered"
    storage.save_history_data_stock.assert_called_once_with(candidate, PeriodType.DAILY, AdjustType.BFQ)
    assert repository.resolve_gap.call_count == 2


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


def test_escalated_candidate_is_pending_approval_without_history_write():
    storage, downloader, repository = Mock(), Mock(), Mock()
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        status=DataGapRecoveryStatus.ESCALATED,
        summary={"classification": "order_dependent", "routing": "approval_escalation"},
    )
    storage.load_history_data_stock.return_value = pd.DataFrame()
    downloader.dl_history_data_stock_by_provider.return_value = _row("000001", "2026-08-07")

    result = DataGapRecoveryService(storage=storage, downloader=downloader, repository=repository).recover_gap(gap)

    assert result.status == "pending_approval"
    repository.record_candidate.assert_called_once()
    storage.save_history_data_stock.assert_not_called()


def test_legacy_repository_without_candidate_recording_allows_ordinary_recovery():
    class LegacyRepository:
        def __init__(self):
            self.attempts = []
            self.resolved = []

        def record_attempt(self, gap_id, batch_id, outcome, evidence):
            self.attempts.append((gap_id, batch_id, outcome, evidence))

        def resolve_gap(self, gap_id):
            self.resolved.append(gap_id)

    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.return_value = _row("000001", "2026-08-07")
    repository = LegacyRepository()
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "ordinary"},
    )

    result = DataGapRecoveryService(storage=storage, downloader=downloader, repository=repository).recover_gap(gap)

    assert result.status == "recovered"
    assert repository.resolved == [gap.id]
    storage.save_history_data_stock.assert_called_once()


def test_recovery_without_repository_resolves_gap_in_memory():
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.return_value = _row("000001", "2026-08-07")
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "ordinary"},
    )

    before = datetime.now(timezone.utc)
    result = DataGapRecoveryService(storage=storage, downloader=downloader).recover_gap(gap)
    after = datetime.now(timezone.utc)

    assert result.status == "recovered"
    assert gap.status == DataGapRecoveryStatus.RECOVERED.value
    assert before <= gap.resolved_at <= after
    assert gap.resolved_at.tzinfo is timezone.utc


def test_escalated_recovery_without_candidate_recording_fails_before_pending_approval():
    class LegacyRepository:
        def record_attempt(self, gap_id, batch_id, outcome, evidence):
            pass

        def resolve_gap(self, gap_id):
            pass

    storage = Mock()
    storage.load_history_data_stock.return_value = pd.DataFrame()
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.return_value = _row("000001", "2026-08-07")
    repository = LegacyRepository()
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        status=DataGapRecoveryStatus.ESCALATED,
        summary={"classification": "order_dependent", "routing": "approval_escalation"},
    )

    result = DataGapRecoveryService(storage=storage, downloader=downloader, repository=repository).recover_gap(gap)

    assert result.status == "failed"
    assert "candidate evidence" in (result.error or "")
    storage.save_history_data_stock.assert_not_called()


def test_canonical_candidate_payload_normalizes_provider_scalars_for_persistence():
    candidate = pd.DataFrame(
        {
            COL_DATE: [np.datetime64("2026-08-07")],
            COL_STOCK_ID: [np.str_("000001")],
            COL_OPEN: [np.float64(10.0)],
            COL_HIGH: [np.float32(11.0)],
            COL_LOW: [np.float64(np.nan)],
            COL_CLOSE: [np.float64(10.5)],
            COL_VOLUME: [np.int64(100)],
            COL_AMOUNT: [pd.NaT],
            "decimal_value": [Decimal("1.2300")],
        }
    )

    payload = canonical_candidate_payload(
        candidate, market="a_share", stock_id="000001", business_date=date(2026, 8, 7), adjust="bfq"
    )
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    candidate_hash = canonical_candidate_hash(payload)

    assert json.loads(serialized) == payload
    assert candidate_hash == canonical_candidate_hash(json.loads(serialized))
    assert payload["row"][COL_LOW] is None
    assert payload["row"][COL_AMOUNT] is None


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


def test_recovery_accepts_narrow_injected_ports(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order",
        lambda: ["first", "second"],
    )

    class CandidateSource:
        def __init__(self):
            self.requested_providers = []

        def load(self, provider, stock_id, start_date, end_date, market):
            self.requested_providers.append(provider)
            assert (stock_id, start_date, end_date, market) == ("000001", "20260807", "20260807", "a_share")
            if provider == "first":
                return _row("000001", "2026-08-06")
            return pd.concat(
                [_row("000001", "2026-08-06"), _row("000001", "2026-08-07"), _row("000001", "2026-08-08")],
                ignore_index=True,
            )

    class MarketData:
        def __init__(self):
            self.rows = pd.DataFrame()
            self.saved = []

        def read_exact(self, stock_id, business_date, market):
            if self.rows.empty:
                return self.rows
            return self.rows[
                (self.rows[COL_STOCK_ID] == stock_id) & (pd.to_datetime(self.rows[COL_DATE]).dt.date == business_date)
            ]

        def save_exact(self, candidate, gap):
            self.saved.append(candidate.copy())
            self.rows = candidate.copy()
            return True

    class Evidence:
        def __init__(self):
            self.attempts = []
            self.resolved = []

        def record_attempt(self, gap_id, batch_id, outcome, evidence):
            self.attempts.append((gap_id, batch_id, outcome, evidence))

        def record_candidate(self, gap_id, candidate_hash, payload, evidence, provider):
            pass

        def gap_evidence(self, gap_id):
            return {"attempts": []}

        def escalate_gap(self, gap_id, user_id, user_snapshot, *, reason=None):
            pass

        def execute_approved_candidate(self, gap_id, approved_hash, callback):
            raise NotImplementedError

        def resolve_gap(self, gap_id):
            self.resolved.append(gap_id)

    source, market_data, evidence = CandidateSource(), MarketData(), Evidence()
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "ordinary"},
    )

    result = DataGapRecoveryService(
        candidate_source=source,
        market_data=market_data,
        evidence=evidence,
    ).recover_gap(gap, batch_id=9)

    assert result.status == "recovered"
    assert result.provider == "second"
    assert source.requested_providers == ["first", "second"]
    assert len(market_data.saved) == 1
    assert market_data.saved[0].iloc[0][COL_DATE].date() == gap.business_date
    assert evidence.resolved == [gap.id]

    retry = DataGapRecoveryService(
        candidate_source=source,
        market_data=market_data,
        evidence=evidence,
    ).recover_gap(gap, batch_id=10)

    assert retry.status == "skipped"
    assert source.requested_providers == ["first", "second"]
    assert len(market_data.saved) == 1
    assert evidence.resolved == [gap.id, gap.id]


def test_approved_execution_uses_injected_market_data_and_evidence_ports():
    class MarketData:
        def __init__(self):
            self.rows = pd.DataFrame()
            self.saved = []

        def read_exact(self, stock_id, business_date, market):
            if self.rows.empty:
                return self.rows
            return self.rows[
                (self.rows[COL_STOCK_ID] == stock_id) & (pd.to_datetime(self.rows[COL_DATE]).dt.date == business_date)
            ]

        def save_exact(self, candidate, gap):
            self.saved.append(candidate.copy())
            self.rows = candidate.copy()
            return True

    class Evidence:
        def __init__(self):
            self.resolved = []

        def execute_approved_candidate(self, gap_id, approved_hash, callback):
            assert gap_id == gap.id
            return callback(gap)

        def record_attempt(self, gap_id, batch_id, outcome, evidence):
            pass

        def record_candidate(self, gap_id, candidate_hash, payload, evidence, provider):
            pass

        def gap_evidence(self, gap_id):
            return {"attempts": []}

        def escalate_gap(self, gap_id, user_id, user_snapshot, *, reason=None):
            pass

        def resolve_gap(self, gap_id):
            self.resolved.append(gap_id)

    gap = SimpleNamespace(
        id=2,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "approval_escalation"},
    )
    candidate = _row("000001", "2026-08-07")
    payload = canonical_candidate_payload(
        candidate, market=gap.market, stock_id=gap.stock_id, business_date=gap.business_date, adjust=gap.adjust
    )
    market_data, evidence = MarketData(), Evidence()

    result = DataGapRecoveryService(
        candidate_source=Mock(),
        market_data=market_data,
        evidence=evidence,
    ).execute_approved_gap(gap, canonical_candidate_hash(payload), candidate)

    assert result.status == "recovered"
    assert len(market_data.saved) == 1
    assert evidence.resolved == [gap.id]


def test_evidence_only_port_records_immutable_escalated_candidate_and_executes_approval(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order", lambda: ["primary"]
    )

    class CandidateSource:
        def __init__(self):
            self.candidate = _row("000001", "2026-08-07")

        def load(self, provider, stock_id, start_date, end_date, market):
            assert (provider, stock_id, start_date, end_date, market) == (
                "primary",
                "000001",
                "20260807",
                "20260807",
                "a_share",
            )
            return self.candidate

    class MarketData:
        def __init__(self):
            self.rows = pd.DataFrame()
            self.saved = []

        def read_exact(self, stock_id, business_date, market):
            if self.rows.empty:
                return self.rows
            return self.rows[
                (self.rows[COL_STOCK_ID] == stock_id) & (pd.to_datetime(self.rows[COL_DATE]).dt.date == business_date)
            ]

        def save_exact(self, candidate, gap):
            self.saved.append(candidate.copy())
            self.rows = candidate.copy()
            return True

    class Evidence:
        def __init__(self):
            self.candidates = {}
            self.resolved = []
            self.escalations = []

        def record_attempt(self, gap_id, batch_id, outcome, evidence):
            pass

        def resolve_gap(self, gap_id):
            self.resolved.append(gap_id)

        def record_candidate(self, gap_id, candidate_hash, payload, evidence, provider):
            self.candidates[gap_id] = (candidate_hash, json.loads(json.dumps(payload)), evidence, provider)

        def gap_evidence(self, gap_id):
            return {"attempts": []}

        def escalate_gap(self, gap_id, user_id, user_snapshot, *, reason=None):
            self.escalations.append((gap_id, user_id, user_snapshot, reason))
            gap.status = DataGapRecoveryStatus.ESCALATED

        def execute_approved_candidate(self, gap_id, approved_hash, callback):
            candidate_hash, payload, _, _ = self.candidates[gap_id]
            assert approved_hash == candidate_hash
            return callback(gap, payload, self.resolve_gap)

    gap = SimpleNamespace(
        id=4,
        business_date=date(2026, 8, 7),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        status=DataGapRecoveryStatus.OPEN,
        summary={"classification": "order_dependent", "routing": "approval_escalation"},
    )
    source, market_data, evidence = CandidateSource(), MarketData(), Evidence()
    service = DataGapRecoveryService(candidate_source=source, market_data=market_data, evidence=evidence)

    assert service.maybe_escalate_gap(gap, user_id=7, user_snapshot={"actor": "operator"}, as_of=date(2026, 8, 14))
    assert evidence.escalations == [(gap.id, 7, {"actor": "operator"}, None)]

    pending = service.recover_gap(gap)

    assert pending.status == "pending_approval"
    candidate_hash, payload, candidate_evidence, provider = evidence.candidates[gap.id]
    assert candidate_hash == canonical_candidate_hash(payload)
    assert payload["row"][COL_CLOSE] == 10.5
    assert candidate_evidence == {"validated": True, "provider": "primary"}
    assert provider == "primary"

    source.candidate.loc[0, COL_CLOSE] = 999.0
    result = service.execute_approved_gap(gap, candidate_hash)

    assert result.status == "recovered"
    assert market_data.saved[0].iloc[0][COL_CLOSE] == 10.5
    assert evidence.resolved == [gap.id]


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


def test_non_string_gap_identity_fails_without_any_recovery_side_effects():
    storage, downloader, repository, alerts = Mock(), Mock(), Mock(), Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id=700, market="hk_connect", adjust="bfq")

    result = DataGapRecoveryService(
        storage=storage, downloader=downloader, repository=repository, alert_service=alerts
    ).recover_gap(gap)

    assert result.status == "failed"
    storage.load_history_data_stock.assert_not_called()
    storage.save_history_data_stock.assert_not_called()
    downloader.dl_history_data_stock_by_provider.assert_not_called()
    repository.record_attempt.assert_not_called()
    alerts.send_recovery_system_failure.assert_not_called()


def test_batch_invalid_non_string_identity_does_not_escalate_or_alert():
    storage, downloader, repository, alerts = Mock(), Mock(), Mock(), Mock()
    repository.gap_evidence.return_value = {"attempts": []}
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id=700, market="hk_connect", adjust="bfq")

    results = DataGapRecoveryService(
        storage=storage, downloader=downloader, repository=repository, alert_service=alerts
    ).recover_unresolved_ordinary_gaps([gap], batch_id=9)

    assert results[0].status == "failed"
    storage.load_history_data_stock.assert_not_called()
    storage.save_history_data_stock.assert_not_called()
    downloader.dl_history_data_stock_by_provider.assert_not_called()
    repository.record_attempt.assert_not_called()
    repository.escalate_gap.assert_not_called()
    alerts.send_escalation.assert_not_called()
    alerts.send_recovery_system_failure.assert_not_called()


def test_hk_recovery_normalizes_provider_row_before_write_readback_and_candidate_hash(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_hk_stock_history_provider_order", lambda: ["tushare"]
    )
    storage, downloader, repository = Mock(), Mock(), Mock()
    storage.load_history_data_stock_hk_ggt.side_effect = [pd.DataFrame(), _row("00700", "2026-08-07")]
    downloader.dl_history_data_stock_hk_by_provider.return_value = _row("700", "2026-08-07")
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="HK.00700",
        market="hk_connect",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "ordinary"},
    )

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "recovered"
    saved = storage.save_history_data_hk_stock.call_args.args[0]
    assert saved.iloc[0][COL_STOCK_ID] == "00700"
    candidate_hash, payload = repository.record_candidate.call_args.args[1:3]
    assert payload["stock_id"] == "00700"
    assert payload["row"][COL_STOCK_ID] == "00700"
    assert candidate_hash == canonical_candidate_hash(payload)
    assert storage.load_history_data_stock_hk_ggt.call_args_list[0].args[0] == "00700"


@pytest.mark.parametrize(
    "market, stock_id, loader",
    [("hk_connect", "00700", "load_history_data_stock_hk_ggt"), ("a_share", "000001", "load_history_data_stock")],
)
def test_duplicate_exact_rows_are_rejected_before_provider_calls(market, stock_id, loader):
    storage, downloader, repository = Mock(), Mock(), Mock()
    rows = pd.concat([_row(stock_id, "2026-08-07"), _row(stock_id, "2026-08-07")], ignore_index=True)
    getattr(storage, loader).return_value = rows
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id=stock_id,
        market=market,
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "ordinary"},
    )

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "failed"
    downloader.dl_history_data_stock_by_provider.assert_not_called()
    downloader.dl_history_data_stock_hk_by_provider.assert_not_called()
    storage.save_history_data_stock.assert_not_called()
    storage.save_history_data_hk_stock.assert_not_called()


def test_preexisting_hk_exact_row_skips_provider_and_write():
    storage, downloader, repository = Mock(), Mock(), Mock()
    storage.load_history_data_stock_hk_ggt.return_value = _row("00700", "2026-08-07")
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="00700",
        market="hk_connect",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "ordinary"},
    )

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "skipped"
    downloader.dl_history_data_stock_hk_by_provider.assert_not_called()
    storage.save_history_data_hk_stock.assert_not_called()


def test_approved_hk_conflicting_exact_row_fails_without_append():
    storage, downloader, repository = Mock(), Mock(), Mock()
    stored = _row("00700", "2026-08-07")
    candidate = stored.copy()
    candidate.loc[0, COL_CLOSE] = 99.0
    storage.load_history_data_stock_hk_ggt.return_value = stored
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="00700",
        market="hk_connect",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "approval_escalation"},
    )
    repository.execute_approved_candidate.side_effect = lambda _id, _hash, callback: callback(gap)
    payload = canonical_candidate_payload(
        candidate, market=gap.market, stock_id=gap.stock_id, business_date=gap.business_date, adjust=gap.adjust
    )

    result = _service(storage, downloader, repository).execute_approved_gap(
        gap, canonical_candidate_hash(payload), candidate
    )

    assert result.status == "failed"
    storage.save_history_data_hk_stock.assert_not_called()


def test_hk_provider_fallback_records_selected_provider_evidence(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_hk_stock_history_provider_order",
        lambda: ["invalid", "tushare"],
    )
    storage, downloader, repository = Mock(), Mock(), Mock()
    storage.load_history_data_stock_hk_ggt.side_effect = [pd.DataFrame(), _row("00700", "2026-08-07")]
    downloader.dl_history_data_stock_hk_by_provider.side_effect = [ValueError("invalid"), _row("00700", "2026-08-07")]
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="00700",
        market="hk_connect",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "ordinary"},
    )

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "recovered"
    assert result.provider == "tushare"
    assert repository.record_attempt.call_args.args[3]["provider"] == "tushare"


def test_hk_provider_loader_lookup_failure_falls_back_without_system_failure(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_hk_stock_history_provider_order",
        lambda: ["invalid", "tushare"],
    )
    storage = Mock()
    storage.load_history_data_stock_hk_ggt.side_effect = [pd.DataFrame(), _row("00700", "2026-08-07")]

    class DownloaderWithTransientHkLoaderLookup:
        def __init__(self):
            self.lookup_count = 0

        @property
        def dl_history_data_stock_hk_by_provider(self):
            self.lookup_count += 1
            if self.lookup_count == 1:
                raise RuntimeError("HK loader unavailable")
            return lambda *_args: _row("00700", "2026-08-07")

    downloader = DownloaderWithTransientHkLoaderLookup()
    repository = Mock()
    alerts = Mock()
    gap = SimpleNamespace(
        id=1,
        business_date=date(2026, 8, 7),
        stock_id="00700",
        market="hk_connect",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "ordinary"},
    )

    policy = Mock()
    policy.evaluate.return_value = {
        "target_date_calendar": True,
        "ordinary_eligibility": True,
        "suspension": "active",
        "source": "test-authority",
        "freshness": True,
        "decision": True,
    }
    service = DataGapRecoveryService(
        storage=storage, downloader=downloader, repository=repository, hk_recovery_policy=policy, alert_service=alerts
    )
    result = service.recover_gap(gap)

    assert result.status == "recovered"
    assert result.provider == "tushare"
    assert downloader.lookup_count == 2
    alerts.send_recovery_system_failure.assert_not_called()


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


def test_provider_loader_lookup_failure_falls_back_to_next_provider(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order",
        lambda: ["baostock", "tushare"],
    )
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]

    class DownloaderWithTransientLoaderLookup:
        def __init__(self):
            self.lookup_count = 0

        @property
        def dl_history_data_stock_by_provider(self):
            self.lookup_count += 1
            if self.lookup_count == 1:
                raise RuntimeError("loader unavailable")
            return lambda *_args: _row("000001", "2026-08-07")

    downloader = DownloaderWithTransientLoaderLookup()
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = DataGapRecoveryService(storage=storage, downloader=downloader, repository=repository).recover_gap(gap)

    assert result.status == "recovered"
    assert result.provider == "tushare"
    assert downloader.lookup_count == 2


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


def test_duplicate_a_share_readback_fails_without_resolving():
    duplicate_rows = pd.concat([_row("000001", "2026-08-07"), _row("000001", "2026-08-07")], ignore_index=True)
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), duplicate_rows]
    storage.save_history_data_stock.return_value = True
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.return_value = _row("000001", "2026-08-07")
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "failed"
    assert "multiple exact rows" in (result.error or "")
    repository.resolve_gap.assert_not_called()


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
