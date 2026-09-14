from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from paper_trading.domain.enums import (
    DataGapRecoveryAccountStatus,
    DataGapRecoveryAlertDeliveryState,
    DataGapRecoveryAttemptOutcome,
    DataGapRecoveryBatchStatus,
)
from paper_trading.storage.data_gap_recovery_repository import DataGapRecoveryRepository
from paper_trading.storage.models import (
    PaperAccount,
    PaperDataGapRecoveryAccount,
    PaperDataGapRecoveryAlert,
    PaperDataGapRecoveryAttempt,
    PaperDataGapRecoveryBatch,
    PaperDataGapRecoveryGap,
)
from storage.model.auth import User
from storage.model.base import Base
from storage.storage_db import (
    _ENUM_GOVERNED_PAPER_TRADING_TABLES,
    _PAPER_TRADING_TABLES_WITH_GOVERNED_FOREIGN_KEYS,
    _non_enum_governed_paper_trading_tables,
)


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
            repository.update_gap(gap.id, {})
        with pytest.raises(AttributeError):
            repository.delete_gap(gap.id)


def test_candidate_hash_and_approval_binding_are_enforced(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gaps.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = DataGapRecoveryRepository(session)
        gap = repository.record_gap(date(2026, 1, 2), "a_share", "000001", "bfq", {})
        with pytest.raises(ValueError):
            repository.record_candidate(gap.id, "not-a-sha256", {}, {}, "caller")
        with pytest.raises(ValueError):
            repository.record_approval(gap.id, "approved", "b" * 64, None, {})
        candidate = repository.record_candidate(gap.id, "b" * 64, {}, {}, "caller")
        approval = repository.record_approval(gap.id, "approved", candidate.candidate_hash, None, {})
        assert approval.candidate_hash == candidate.candidate_hash


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
        repository.update_gap_summary(rows[0].id, {"resolved": True})
        assert session.get(PaperDataGapRecoveryGap, rows[0].id).summary == {"resolved": True}


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
