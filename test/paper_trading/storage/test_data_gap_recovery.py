from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from paper_trading.domain.enums import (
    DataGapRecoveryAccountStatus,
    DataGapRecoveryAlertDeliveryState,
    DataGapRecoveryApprovalDecision,
    DataGapRecoveryAttemptOutcome,
    DataGapRecoveryBatchStatus,
    DataGapRecoveryClassification,
    DataGapRecoveryRouting,
    DataGapRecoveryStatus,
)
from paper_trading.storage.data_gap_recovery_repository import DataGapRecoveryRepository
from paper_trading.storage.models import (
    DailyBarDiagnostic,
    PaperAccount,
    PaperAccountSnapshot,
    PaperCashLedger,
    PaperDataGapRecoveryAccount,
    PaperDataGapRecoveryAlert,
    PaperDataGapRecoveryApproval,
    PaperDataGapRecoveryAttempt,
    PaperDataGapRecoveryBatch,
    PaperDataGapRecoveryGap,
    PaperLedgerRebuild,
    PaperOrder,
)
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.auth import User
from storage.model.base import Base
from storage.storage_db import (
    _ENUM_GOVERNED_PAPER_TRADING_TABLES,
    _PAPER_TRADING_TABLES_WITH_GOVERNED_FOREIGN_KEYS,
    _non_enum_governed_paper_trading_tables,
)


def test_recovery_classification_and_routing_are_closed_values():
    from paper_trading.domain.enums import DataGapRecoveryClassification, DataGapRecoveryRouting

    assert {item.value for item in DataGapRecoveryClassification} == {
        "order_dependent",
        "valuation_only",
        "no_impact",
    }
    assert DataGapRecoveryRouting.ORDINARY.value == "ordinary"


def test_gap_model_has_a_share_bfq_identity_and_governed_outcomes(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    columns = PaperDataGapRecoveryGap.__table__.c
    assert {"business_date", "market", "stock_id", "adjust", "summary"} <= set(columns.keys())
    assert isinstance(PaperDataGapRecoveryAttempt.__table__.c.outcome.type.enum_class, type)
    assert PaperDataGapRecoveryAttempt.__table__.c.outcome.type.enum_class is DataGapRecoveryAttemptOutcome
    assert PaperDataGapRecoveryAccount.__table__.c.status.type.enum_class is DataGapRecoveryAccountStatus
    assert PaperDataGapRecoveryBatch.__table__.c.status.type.enum_class is DataGapRecoveryBatchStatus
    assert PaperDataGapRecoveryAlert.__table__.c.delivery_state.type.enum_class is DataGapRecoveryAlertDeliveryState
    assert {c.name for c in PaperDataGapRecoveryGap.__table__.constraints} >= {
        "ck_paper_data_gap_recovery_a_share",
        "ck_paper_data_gap_recovery_bfq",
        "ck_paper_data_gap_recovery_stock_id_six_ascii_digits",
    }


def test_repository_validates_identity_and_preserves_append_only_evidence(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = DataGapRecoveryRepository(session)
        with pytest.raises(ValueError):
            repository.record_gap(date(2026, 1, 2), "hk_connect", "000001", "bfq", {})
        gap = repository.record_gap(date(2026, 1, 2), "a_share", "000001", "bfq", {"missing": True})
        candidate = repository.record_candidate(gap.id, "a" * 64, {"caller": "payload"}, {"ok": True}, "caller")
        attempt = repository.record_attempt(gap.id, None, DataGapRecoveryAttemptOutcome.NOT_FOUND, {"x": 1})
        assert candidate.payload == {"caller": "payload"}
        assert attempt.outcome == DataGapRecoveryAttemptOutcome.NOT_FOUND
        with pytest.raises(AttributeError):
            getattr(repository, "update_gap")(gap.id, {})
        with pytest.raises(AttributeError):
            getattr(repository, "delete_gap")(gap.id)


def test_candidate_hash_and_approval_binding_are_enforced(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = DataGapRecoveryRepository(session)
        gap = repository.record_gap(date(2026, 1, 2), "a_share", "000001", "bfq", {})
        with pytest.raises(ValueError):
            repository.record_candidate(gap.id, "not-a-sha256", {}, {}, "caller")
        with pytest.raises(ValueError):
            repository.record_approval(gap.id, DataGapRecoveryApprovalDecision.APPROVED, "b" * 64, None, {})
        candidate = repository.record_candidate(gap.id, "b" * 64, {}, {}, "caller")
        approval = repository.record_approval(
            gap.id, DataGapRecoveryApprovalDecision.APPROVED, candidate.candidate_hash, None, {}
        )
        assert approval.candidate_hash == candidate.candidate_hash


def test_locked_escalation_approval_rejection_and_reopen_preserve_evidence(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = DataGapRecoveryRepository(session)
        gap = repository.record_gap(date(2026, 1, 2), "a_share", "000001", "bfq", {"impact": "none"})
        candidate = repository.record_candidate(gap.id, "a" * 64, {"order": 1}, {"ok": True}, "caller")
        user = {"id": 7, "email": "reviewer@example.com", "role": "reviewer"}

        repository.escalate_gap(gap.id, 7, user, reason="needs review")
        repository.reject_gap(gap.id, candidate.candidate_hash, 7, user, reason="not trustworthy")
        assert gap.status == DataGapRecoveryStatus.PERMANENTLY_UNRESOLVED
        assert gap.summary == {"impact": "none"}
        repository.reopen_gap(gap.id, 7, user, reason="new source available")

        assert gap.status == DataGapRecoveryStatus.OPEN
        evidence = repository.gap_evidence(gap.id)
        assert len(evidence["candidates"]) == 1
        assert [row.decision for row in evidence["approvals"]] == [
            DataGapRecoveryApprovalDecision.REJECTED,
            DataGapRecoveryApprovalDecision.REOPENED,
        ]
        assert evidence["approvals"][0].approver_snapshot["reason"] == "not trustworthy"
        assert evidence["approvals"][0].approver_snapshot["user_id"] == 7
        assert evidence["approvals"][1].approver_snapshot["email"] == "reviewer@example.com"
        assert evidence["attempts"][0].evidence == {
            "event": "escalated",
            "id": 7,
            "email": "reviewer@example.com",
            "role": "reviewer",
            "user_id": 7,
            "reason": "needs review",
        }


def test_stale_candidate_hash_invalidates_to_pending_approval_without_losing_candidate(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = DataGapRecoveryRepository(session)
        gap = repository.record_gap(date(2026, 1, 2), "a_share", "000001", "bfq", {"keep": True})
        repository.record_candidate(gap.id, "a" * 64, {}, {}, "caller")
        repository.record_candidate(gap.id, "b" * 64, {}, {}, "caller")
        repository.escalate_gap(gap.id, 7, {"email": "reviewer@example.com"})

        result = repository.approve_gap(gap.id, "a" * 64, 7, {"email": "reviewer@example.com"})

        assert result is gap
        assert gap.status == DataGapRecoveryStatus.PENDING_APPROVAL
        assert gap.latest_candidate_hash == "b" * 64
        assert gap.summary == {"keep": True}
        assert len(repository.gap_evidence(gap.id)["candidates"]) == 2


def test_transitions_reject_invalid_source_states_and_preserve_attempts(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = DataGapRecoveryRepository(session)
        gap = repository.record_gap(date(2026, 1, 2), "a_share", "000001", "bfq", {})
        candidate = repository.record_candidate(gap.id, "a" * 64, {}, {}, "caller")
        repository.escalate_gap(gap.id, 7, {"email": "r@example.com"})
        with pytest.raises(ValueError, match="only open"):
            repository.escalate_gap(gap.id, 7, {"email": "r@example.com"})
        repository.reject_gap(gap.id, candidate.candidate_hash, 7, {"email": "r@example.com"})
        with pytest.raises(ValueError, match="escalated or pending"):
            repository.reject_gap(gap.id, candidate.candidate_hash, 7, {"email": "r@example.com"})
        assert len(repository.gap_evidence(gap.id)["attempts"]) == 1


def test_record_candidate_locks_gap_before_updating_latest_candidate_hash(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = DataGapRecoveryRepository(session)
        gap = repository.record_gap(date(2026, 1, 2), "a_share", "000001", "bfq", {})
        locked_gap_ids = []
        original_locked_gap = repository._locked_gap

        def locked_gap(gap_id):
            locked_gap_ids.append(gap_id)
            return original_locked_gap(gap_id)

        monkeypatch.setattr(repository, "_locked_gap", locked_gap)

        repository.record_candidate(gap.id, "a" * 64, {}, {}, "caller")
        assert gap.latest_candidate_hash == "a" * 64

        repository.record_candidate(gap.id, "b" * 64, {}, {}, "caller")
        assert gap.latest_candidate_hash == "b" * 64
        assert locked_gap_ids == [gap.id, gap.id]


def test_recording_existing_gap_updates_last_observed_at(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = DataGapRecoveryRepository(session)
        gap = repository.record_gap(date(2026, 1, 2), "a_share", "000001", "bfq", {})
        first = gap.last_observed_at
        gap = repository.record_gap(date(2026, 1, 2), "a_share", "000001", "bfq", {})
        assert gap.last_observed_at >= first


def test_repository_lists_stably_and_updates_only_summary(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = DataGapRecoveryRepository(session)
        repository.record_gap(date(2026, 1, 2), "a_share", "000002", "bfq", {})
        repository.record_gap(date(2026, 1, 2), "a_share", "000001", "bfq", {})
        rows = repository.list_gaps(0, 1)
        assert [row.stock_id for row in rows] == ["000001"]
        row = rows[0]
        repository.update_gap_summary(row.id, {"resolved": True})
        updated = session.get(PaperDataGapRecoveryGap, row.id)
        assert updated is not None
        assert updated.summary == {"resolved": True}


def test_recovery_batch_has_explicit_run_metadata_and_attempt_fk(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    batch = PaperDataGapRecoveryBatch.__table__
    attempt = PaperDataGapRecoveryAttempt.__table__
    assert {"download_id", "cutoff", "finished_at", "gap_count", "recovered_count", "failed_count"} <= set(
        batch.c.keys()
    )
    assert any(fk.target_fullname == f"{batch.name}.id" for fk in attempt.c.batch_id.foreign_keys)
    assert {"gap_id", "cycle_key", "created_at"} <= set(PaperDataGapRecoveryAlert.__table__.c.keys())
    assert any(
        constraint.name == "uq_paper_data_gap_recovery_alert_cycle"
        for constraint in PaperDataGapRecoveryAlert.__table__.constraints
    )


def test_repository_finalizes_batch_with_counts_and_finished_at(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = DataGapRecoveryRepository(session)
        batch = repository.record_batch(DataGapRecoveryBatchStatus.RUNNING, {"business_date": "2026-08-07"})
        repository.finalize_batch(
            batch.id,
            DataGapRecoveryBatchStatus.FAILED,
            gap_count=2,
            recovered_count=1,
            failed_count=1,
            summary={"retryable": True},
        )
        session.commit()
        stored = repository.get_batch(batch.id)
        assert stored is not None
        assert stored.status == DataGapRecoveryBatchStatus.FAILED
        assert (stored.gap_count, stored.recovered_count, stored.failed_count) == (2, 1, 1)
        assert stored.finished_at is not None


def test_batch_account_recovery_excludes_unrelated_prior_batch_gap(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = DataGapRecoveryRepository(session)
        account = PaperTradingRepository(session).create_account("batch-scoped", Decimal("100"))
        session.add(
            PaperOrder(
                account_id=account.id,
                symbol="000001",
                side="buy",
                quantity=1,
                limit_price=Decimal("10"),
                trade_date=date(2026, 1, 2),
                status="accepted",
            )
        )
        session.flush()
        current_gap = repository.record_gap(date(2026, 1, 2), "a_share", "000001", "bfq", {})
        prior_gap = repository.record_gap(date(2026, 1, 3), "a_share", "000002", "bfq", {})
        batch = repository.record_batch(DataGapRecoveryBatchStatus.COMPLETED, {})
        repository.record_attempt(current_gap.id, batch.id, DataGapRecoveryAttemptOutcome.NOT_FOUND, {})
        repository.record_attempt(prior_gap.id, None, DataGapRecoveryAttemptOutcome.NOT_FOUND, {})

        monkeypatch.setattr(
            repository,
            "_account_replay_events",
            lambda account_id: [
                type("Event", (), {"payload": {"symbol": "000001"}, "trade_date": date(2026, 1, 2)})(),
                type("Event", (), {"payload": {"symbol": "000002"}, "trade_date": date(2026, 1, 3)})(),
            ],
        )

        result = repository.list_batch_account_recovery(batch.id)

        assert [(item["gap_id"], item["account_id"]) for item in result] == [(current_gap.id, account.id)]


def test_owner_scoped_gap_and_batch_queries_are_distinct_and_do_not_leak_evidence(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = DataGapRecoveryRepository(session)
        owner_user = User(email="owner@example.com", password_hash="hash", email_verified_at=datetime.now(timezone.utc))
        other_user = User(email="other@example.com", password_hash="hash", email_verified_at=datetime.now(timezone.utc))
        session.add_all([owner_user, other_user])
        session.flush()
        owner = PaperAccount(name="owner", initial_cash=Decimal("100"), owner_user_id=owner_user.id)
        other = PaperAccount(name="other", initial_cash=Decimal("100"), owner_user_id=other_user.id)
        session.add_all([owner, other])
        session.flush()
        visible = repository.record_gap(date(2026, 1, 2), "a_share", "000001", "bfq", {})
        hidden = repository.record_gap(date(2026, 1, 2), "a_share", "000002", "bfq", {})
        repository.upsert_account_progress(visible.id, owner.id, DataGapRecoveryAccountStatus.PENDING, {})
        repository.upsert_account_progress(visible.id, other.id, DataGapRecoveryAccountStatus.PENDING, {})
        repository.upsert_account_progress(hidden.id, other.id, DataGapRecoveryAccountStatus.PENDING, {})
        batch = repository.record_batch(DataGapRecoveryBatchStatus.COMPLETED, {})
        repository.record_attempt(visible.id, batch.id, DataGapRecoveryAttemptOutcome.NOT_FOUND, {"visible": True})
        repository.record_attempt(hidden.id, batch.id, DataGapRecoveryAttemptOutcome.NOT_FOUND, {"hidden": True})

        assert [gap.id for gap in repository.list_gaps(0, 50, owner_user_id=owner_user.id)] == [visible.id]
        assert repository.count_gaps(owner_user_id=owner_user.id) == 1


def test_recovery_tables_are_excluded_from_plain_metadata_bootstrap_on_postgresql():
    recovery_tables = {
        "paper_data_gap_recovery_gaps",
        "paper_data_gap_recovery_candidates",
        "paper_data_gap_recovery_attempts",
        "paper_data_gap_recovery_approvals",
        "paper_data_gap_recovery_accounts",
        "paper_data_gap_recovery_batches",
        "paper_data_gap_recovery_alerts",
    }

    assert recovery_tables <= _ENUM_GOVERNED_PAPER_TRADING_TABLES
    assert {
        "paper_data_gap_recovery_candidates",
        "paper_data_gap_recovery_attempts",
        "paper_data_gap_recovery_approvals",
        "paper_data_gap_recovery_accounts",
        "paper_data_gap_recovery_alerts",
    } <= _PAPER_TRADING_TABLES_WITH_GOVERNED_FOREIGN_KEYS
    assert not recovery_tables & {
        table.name for table in _non_enum_governed_paper_trading_tables(type("D", (), {"name": "postgresql"})())
    }


def test_repository_selects_only_unresolved_ordinary_bfq_diagnostics(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        diagnostics = PaperTradingRepository(session)
        for business_date, stock_id, classification, adjust, resolved in (
            (date(2026, 1, 2), "000001", "missing_exact_date", "bfq", False),
            (date(2026, 1, 2), "000002", "missing_market_data", "bfq", True),
            (date(2026, 1, 3), "000003", "missing_exact_date", "bfq", False),
            (date(2026, 1, 2), "000004", "provider_error", "bfq", False),
            (date(2026, 1, 2), "000005", "missing_exact_date", "qfq", False),
        ):
            diagnostics.upsert_daily_bar_diagnostic(
                business_date, "a_share", stock_id, adjust, classification, [], resolved
            )
        repository = DataGapRecoveryRepository(session)

        target = repository.list_unresolved_ordinary_diagnostics(business_date=date(2026, 1, 2))

        assert [(row.business_date, row.stock_id) for row in target] == [(date(2026, 1, 2), "000001")]


def test_repository_reuses_gap_identity_and_updates_classification_without_duplicates(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = DataGapRecoveryRepository(session)
        diagnostic = DailyBarDiagnostic(
            business_date=date(2026, 1, 2), market="a_share", stock_id="000001", adjust="bfq"
        )
        first = repository.get_or_create_gap_from_diagnostic(
            diagnostic,
            routing=DataGapRecoveryRouting.ORDINARY,
            classification=DataGapRecoveryClassification.ORDER_DEPENDENT,
        )
        first.summary["unrelated"] = "preserved"
        second = repository.get_or_create_gap_from_diagnostic(
            diagnostic,
            routing=DataGapRecoveryRouting.ORDINARY,
            classification=DataGapRecoveryClassification.VALUATION_ONLY,
        )

        assert first.id == second.id
        assert session.query(PaperDataGapRecoveryGap).count() == 1
        assert second.summary["classification"] == DataGapRecoveryClassification.VALUATION_ONLY.value
        assert second.summary["routing"] == DataGapRecoveryRouting.ORDINARY.value
        assert second.summary["source"] == "daily_bar_diagnostic"
        assert second.summary["unrelated"] == "preserved"


def test_repository_records_recovery_classification_as_summary_evidence(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = DataGapRecoveryRepository(session)
        gap = repository.record_gap(date(2026, 1, 2), "a_share", "000001", "bfq", {"existing": True})

        repository.record_recovery_classification(
            gap.id,
            DataGapRecoveryClassification.NO_IMPACT,
            DataGapRecoveryRouting.ORDINARY,
            {"reason": "no downstream use"},
        )

        assert gap.summary == {
            "existing": True,
            "classification": DataGapRecoveryClassification.NO_IMPACT.value,
            "routing": DataGapRecoveryRouting.ORDINARY.value,
            "evidence": {"reason": "no downstream use"},
        }


def test_unified_recovery_does_not_create_account_approval_or_alert_rows(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = DataGapRecoveryRepository(session)
        gap = repository.record_gap(date(2026, 1, 2), "a_share", "000001", "bfq", {"routing": "ordinary"})
        repository.record_recovery_classification(
            gap.id,
            classification=DataGapRecoveryClassification.NO_IMPACT,
            routing=DataGapRecoveryRouting.ORDINARY,
            evidence={"source": "issue_113"},
        )

        assert session.query(PaperDataGapRecoveryAccount).count() == 0
        assert session.query(PaperDataGapRecoveryApproval).count() == 0
        assert session.query(PaperDataGapRecoveryAlert).count() == 0
        assert session.query(PaperCashLedger).count() == 0
        assert session.query(PaperAccountSnapshot).count() == 0
        assert session.query(PaperLedgerRebuild).count() == 0
        assert session.query(PaperAccount).count() == 0


def test_repository_records_ledger_and_snapshot_recovery_steps_independently(tmp_path):
    """Catches persistence that overwrites one account step with the other."""
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = DataGapRecoveryRepository(session)
        account = PaperTradingRepository(session).create_account("step-statuses", Decimal("100"))
        gap = repository.record_gap(date(2026, 1, 2), "a_share", "000001", "bfq", {})

        repository.record_account_recovery_step(gap.id, account.id, "ledger", "completed", {"rows": 3})
        progress = repository.record_account_recovery_step(
            gap.id, account.id, "snapshot", "failed", {"error": "missing close"}
        )

        assert progress.summary["ledger"] == {"status": "completed", "evidence": {"rows": 3}}
        assert progress.summary["snapshot"] == {"status": "failed", "evidence": {"error": "missing close"}}


def test_repository_retry_selection_keeps_completed_ledger_when_snapshot_failed(tmp_path):
    """Catches retry selection that re-runs completed ledger work."""
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = DataGapRecoveryRepository(session)
        account = PaperTradingRepository(session).create_account("retry-selection", Decimal("100"))
        gap = repository.record_gap(date(2026, 1, 2), "a_share", "000001", "bfq", {})
        repository.record_account_recovery_step(gap.id, account.id, "ledger", "completed", {})
        repository.record_account_recovery_step(gap.id, account.id, "snapshot", "failed", {"attempt": 1})

        retryable = repository.list_retryable_account_progress()

        assert [(row.gap_id, row.account_id) for row in retryable] == [(gap.id, account.id)]
        assert retryable[0].summary["ledger"]["status"] == "completed"
        assert retryable[0].summary["snapshot"]["status"] == "failed"
