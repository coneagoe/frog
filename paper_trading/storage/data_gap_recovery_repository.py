from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from paper_trading.domain.enums import (
    DataGapRecoveryAccountStatus,
    DataGapRecoveryApprovalDecision,
    DataGapRecoveryAttemptOutcome,
    DataGapRecoveryBatchStatus,
    DataGapRecoveryClassification,
    DataGapRecoveryRouting,
    DataGapRecoveryStatus,
    Market,
)
from paper_trading.storage.models import (
    DailyBarDiagnostic,
    PaperAccount,
    PaperDataGapRecoveryAccount,
    PaperDataGapRecoveryAlert,
    PaperDataGapRecoveryApproval,
    PaperDataGapRecoveryAttempt,
    PaperDataGapRecoveryBatch,
    PaperDataGapRecoveryCandidate,
    PaperDataGapRecoveryGap,
)

_STOCK_ID = re.compile(r"^[0-9]{6}$", re.ASCII)


class DataGapRecoveryRepository:
    """Persistence boundary for append-only recovery evidence and summaries."""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _validate_identity(market: str, stock_id: str, adjust: str) -> None:
        if market != Market.A_SHARE.value or adjust != "bfq" or not _STOCK_ID.fullmatch(stock_id):
            raise ValueError("data gap identity must be a_share/bfq with a six-digit ASCII stock_id")

    def record_gap(
        self, business_date: date, market: str, stock_id: str, adjust: str, summary: dict[str, Any]
    ) -> PaperDataGapRecoveryGap:
        self._validate_identity(market, stock_id, adjust)
        gap = self.session.scalar(
            select(PaperDataGapRecoveryGap).where(
                PaperDataGapRecoveryGap.business_date == business_date,
                PaperDataGapRecoveryGap.market == market,
                PaperDataGapRecoveryGap.stock_id == stock_id,
                PaperDataGapRecoveryGap.adjust == adjust,
            )
        )
        if gap is None:
            gap = PaperDataGapRecoveryGap(
                business_date=business_date, market=market, stock_id=stock_id, adjust=adjust, summary=summary
            )
            self.session.add(gap)
        else:
            gap.summary = summary
            gap.last_observed_at = func.now()
        self.session.flush()
        return gap

    def update_gap_summary(self, gap_id: int, summary: dict[str, Any]) -> None:
        gap = self.session.get(PaperDataGapRecoveryGap, gap_id)
        if gap is None:
            raise KeyError(gap_id)
        gap.summary = summary
        self.session.flush()

    def list_unresolved_ordinary_diagnostics(self, *, business_date: date) -> list[DailyBarDiagnostic]:
        return list(
            self.session.scalars(
                select(DailyBarDiagnostic)
                .where(
                    DailyBarDiagnostic.business_date == business_date,
                    DailyBarDiagnostic.market == Market.A_SHARE.value,
                    DailyBarDiagnostic.adjust == "bfq",
                    DailyBarDiagnostic.classification.in_(("missing_market_data", "missing_exact_date")),
                    DailyBarDiagnostic.resolved.is_(False),
                )
                .order_by(DailyBarDiagnostic.business_date, DailyBarDiagnostic.stock_id, DailyBarDiagnostic.id)
            )
        )

    def get_or_create_gap_from_diagnostic(
        self,
        diagnostic: DailyBarDiagnostic,
        *,
        routing: DataGapRecoveryRouting,
        classification: DataGapRecoveryClassification,
    ) -> PaperDataGapRecoveryGap:
        existing = self.session.scalar(
            select(PaperDataGapRecoveryGap).where(
                PaperDataGapRecoveryGap.business_date == diagnostic.business_date,
                PaperDataGapRecoveryGap.market == diagnostic.market,
                PaperDataGapRecoveryGap.stock_id == diagnostic.stock_id,
                PaperDataGapRecoveryGap.adjust == diagnostic.adjust,
            )
        )
        summary = dict(existing.summary) if existing is not None else {}
        summary.update(
            classification=classification.value,
            routing=routing.value,
            source="daily_bar_diagnostic",
        )
        return self.record_gap(
            diagnostic.business_date,
            diagnostic.market,
            diagnostic.stock_id,
            diagnostic.adjust,
            summary,
        )

    def record_recovery_classification(
        self,
        gap_id: int,
        classification: DataGapRecoveryClassification,
        routing: DataGapRecoveryRouting,
        evidence: dict[str, Any],
    ) -> None:
        gap = self.session.get(PaperDataGapRecoveryGap, gap_id)
        if gap is None:
            raise KeyError(gap_id)
        summary = dict(gap.summary)
        summary.update(classification=classification.value, routing=routing.value, evidence=evidence)
        self.update_gap_summary(gap_id, summary)

    def resolve_gap(self, gap_id: int) -> None:
        gap = self.session.get(PaperDataGapRecoveryGap, gap_id)
        if gap is None:
            raise KeyError(gap_id)
        gap.status = DataGapRecoveryStatus.RECOVERED
        gap.resolved_at = datetime.now(timezone.utc)
        self.session.flush()

    def record_candidate(
        self, gap_id: int, candidate_hash: str, payload: dict[str, Any], validation: dict[str, Any], source: str
    ) -> PaperDataGapRecoveryCandidate:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", candidate_hash):
            raise ValueError("candidate_hash must be a 64-character SHA-256 hex digest")
        candidate = PaperDataGapRecoveryCandidate(
            gap_id=gap_id, candidate_hash=candidate_hash, payload=payload, validation=validation, source=source
        )
        self.session.add(candidate)
        self.session.flush()
        return candidate

    def record_attempt(
        self, gap_id: int, batch_id: int | None, outcome: DataGapRecoveryAttemptOutcome, evidence: dict[str, Any]
    ) -> PaperDataGapRecoveryAttempt:
        attempt = PaperDataGapRecoveryAttempt(gap_id=gap_id, batch_id=batch_id, outcome=outcome, evidence=evidence)
        self.session.add(attempt)
        self.session.flush()
        return attempt

    def record_batch(self, status: DataGapRecoveryBatchStatus, summary: dict[str, Any]) -> PaperDataGapRecoveryBatch:
        batch = PaperDataGapRecoveryBatch(status=status, summary=summary)
        self.session.add(batch)
        self.session.flush()
        return batch

    def finalize_batch(
        self,
        batch_id: int,
        status: DataGapRecoveryBatchStatus,
        *,
        gap_count: int,
        recovered_count: int,
        failed_count: int,
        summary: dict[str, Any],
    ) -> PaperDataGapRecoveryBatch:
        batch = self.session.get(PaperDataGapRecoveryBatch, batch_id)
        if batch is None:
            raise KeyError(batch_id)
        batch.status = status
        batch.gap_count = gap_count
        batch.recovered_count = recovered_count
        batch.failed_count = failed_count
        batch.summary = summary
        batch.finished_at = datetime.now(timezone.utc)
        self.session.flush()
        return batch

    def record_approval(
        self,
        gap_id: int,
        decision: DataGapRecoveryApprovalDecision,
        candidate_hash: str,
        approver_user_id: int | None,
        approver_snapshot: dict[str, Any],
    ) -> PaperDataGapRecoveryApproval:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", candidate_hash):
            raise ValueError("candidate_hash must be a 64-character SHA-256 hex digest")
        candidate = self.session.scalar(
            select(PaperDataGapRecoveryCandidate).where(
                PaperDataGapRecoveryCandidate.gap_id == gap_id,
                PaperDataGapRecoveryCandidate.candidate_hash == candidate_hash,
            )
        )
        if candidate is None:
            raise ValueError("approval candidate does not exist")
        approval = PaperDataGapRecoveryApproval(
            gap_id=gap_id,
            decision=decision,
            candidate_hash=candidate_hash,
            approver_user_id=approver_user_id,
            approver_snapshot=approver_snapshot,
        )
        self.session.add(approval)
        self.session.flush()
        return approval

    def record_alert(self, gap_id: int, cycle_key: str, evidence: dict[str, Any]) -> PaperDataGapRecoveryAlert:
        alert = PaperDataGapRecoveryAlert(gap_id=gap_id, cycle_key=cycle_key, evidence=evidence)
        self.session.add(alert)
        self.session.flush()
        return alert

    def upsert_account_progress(
        self, gap_id: int, account_id: int, status: DataGapRecoveryAccountStatus, summary: dict[str, Any]
    ) -> PaperDataGapRecoveryAccount:
        progress = self.session.scalar(
            select(PaperDataGapRecoveryAccount).where(
                PaperDataGapRecoveryAccount.gap_id == gap_id, PaperDataGapRecoveryAccount.account_id == account_id
            )
        )
        if progress is None:
            progress = PaperDataGapRecoveryAccount(gap_id=gap_id, account_id=account_id, status=status, summary=summary)
            self.session.add(progress)
        else:
            progress.status = status
            progress.summary = summary
        self.session.flush()
        return progress

    def list_gaps(
        self,
        offset: int,
        page_size: int,
        *,
        status: DataGapRecoveryStatus | None = None,
        business_date: date | None = None,
        stock_id: str | None = None,
        owner_user_id: int | None = None,
    ) -> list[PaperDataGapRecoveryGap]:
        query = select(PaperDataGapRecoveryGap)
        if status is not None:
            query = query.where(PaperDataGapRecoveryGap.status == status)
        if business_date is not None:
            query = query.where(PaperDataGapRecoveryGap.business_date == business_date)
        if stock_id is not None:
            query = query.where(PaperDataGapRecoveryGap.stock_id == stock_id)
        if owner_user_id is not None:
            query = (
                query.join(PaperDataGapRecoveryAccount)
                .join(PaperAccount)
                .where(PaperAccount.owner_user_id == owner_user_id)
                .distinct()
            )
        return list(
            self.session.scalars(
                query.order_by(
                    PaperDataGapRecoveryGap.business_date, PaperDataGapRecoveryGap.stock_id, PaperDataGapRecoveryGap.id
                )
                .offset(offset)
                .limit(page_size)
            )
        )

    def count_gaps(self, **filters: Any) -> int:
        query = select(func.count()).select_from(PaperDataGapRecoveryGap)
        status = filters.get("status")
        if status is not None:
            query = query.where(PaperDataGapRecoveryGap.status == status)
        for name in ("business_date", "stock_id"):
            if filters.get(name) is not None:
                query = query.where(getattr(PaperDataGapRecoveryGap, name) == filters[name])
        owner_user_id = filters.get("owner_user_id")
        if owner_user_id is not None:
            query = (
                query.join(PaperDataGapRecoveryAccount)
                .join(PaperAccount)
                .where(PaperAccount.owner_user_id == owner_user_id)
            )
            query = query.with_only_columns(func.count(PaperDataGapRecoveryGap.id.distinct()))
        return int(self.session.scalar(query) or 0)

    def get_gap(self, gap_id: int, owner_user_id: int | None = None) -> PaperDataGapRecoveryGap | None:
        query = select(PaperDataGapRecoveryGap).where(PaperDataGapRecoveryGap.id == gap_id)
        if owner_user_id is not None:
            query = (
                query.join(PaperDataGapRecoveryAccount)
                .join(PaperAccount)
                .where(PaperAccount.owner_user_id == owner_user_id)
                .distinct()
            )
        return self.session.scalar(query)

    def gap_evidence(self, gap_id: int, owner_user_id: int | None = None) -> dict[str, list[Any]]:
        if owner_user_id is not None and self.get_gap(gap_id, owner_user_id) is None:
            return {key: [] for key in ("candidates", "attempts", "approvals", "accounts", "alerts")}
        accounts = select(PaperDataGapRecoveryAccount).where(PaperDataGapRecoveryAccount.gap_id == gap_id)
        if owner_user_id is not None:
            accounts = accounts.join(PaperAccount).where(PaperAccount.owner_user_id == owner_user_id)
        return {
            "candidates": list(
                self.session.scalars(
                    select(PaperDataGapRecoveryCandidate).where(PaperDataGapRecoveryCandidate.gap_id == gap_id)
                )
            ),
            "attempts": list(
                self.session.scalars(
                    select(PaperDataGapRecoveryAttempt).where(PaperDataGapRecoveryAttempt.gap_id == gap_id)
                )
            ),
            "approvals": list(
                self.session.scalars(
                    select(PaperDataGapRecoveryApproval).where(PaperDataGapRecoveryApproval.gap_id == gap_id)
                )
            ),
            "accounts": list(self.session.scalars(accounts)),
            "alerts": list(
                self.session.scalars(
                    select(PaperDataGapRecoveryAlert).where(PaperDataGapRecoveryAlert.gap_id == gap_id)
                )
            ),
        }

    def list_batches(
        self,
        offset: int,
        page_size: int,
        *,
        status: DataGapRecoveryBatchStatus | None = None,
        owner_user_id: int | None = None,
    ) -> list[PaperDataGapRecoveryBatch]:
        query = select(PaperDataGapRecoveryBatch)
        if status is not None:
            query = query.where(PaperDataGapRecoveryBatch.status == status)
        if owner_user_id is not None:
            query = (
                query.join(PaperDataGapRecoveryAttempt)
                .join(
                    PaperDataGapRecoveryAccount,
                    PaperDataGapRecoveryAccount.gap_id == PaperDataGapRecoveryAttempt.gap_id,
                )
                .join(PaperAccount)
                .where(PaperAccount.owner_user_id == owner_user_id)
                .distinct()
            )
        return list(
            self.session.scalars(
                query.order_by(PaperDataGapRecoveryBatch.created_at, PaperDataGapRecoveryBatch.id)
                .offset(offset)
                .limit(page_size)
            )
        )

    def count_batches(self, status: DataGapRecoveryBatchStatus | None = None, owner_user_id: int | None = None) -> int:
        query = select(func.count()).select_from(PaperDataGapRecoveryBatch)
        if status is not None:
            query = query.where(PaperDataGapRecoveryBatch.status == status)
        if owner_user_id is not None:
            query = (
                query.join(PaperDataGapRecoveryAttempt)
                .join(
                    PaperDataGapRecoveryAccount,
                    PaperDataGapRecoveryAccount.gap_id == PaperDataGapRecoveryAttempt.gap_id,
                )
                .join(PaperAccount)
                .where(PaperAccount.owner_user_id == owner_user_id)
                .with_only_columns(func.count(PaperDataGapRecoveryBatch.id.distinct()))
            )
        return int(self.session.scalar(query) or 0)

    def get_batch(self, batch_id: int, owner_user_id: int | None = None) -> PaperDataGapRecoveryBatch | None:
        query = select(PaperDataGapRecoveryBatch).where(PaperDataGapRecoveryBatch.id == batch_id)
        if owner_user_id is not None:
            query = (
                query.join(PaperDataGapRecoveryAttempt)
                .join(
                    PaperDataGapRecoveryAccount,
                    PaperDataGapRecoveryAccount.gap_id == PaperDataGapRecoveryAttempt.gap_id,
                )
                .join(PaperAccount)
                .where(PaperAccount.owner_user_id == owner_user_id)
                .distinct()
            )
        return self.session.scalar(query)

    def batch_evidence(self, batch_id: int, owner_user_id: int | None = None) -> dict[str, list[Any]]:
        attempt_query = select(PaperDataGapRecoveryAttempt).where(PaperDataGapRecoveryAttempt.batch_id == batch_id)
        if owner_user_id is not None:
            attempt_query = (
                attempt_query.join(
                    PaperDataGapRecoveryAccount,
                    PaperDataGapRecoveryAccount.gap_id == PaperDataGapRecoveryAttempt.gap_id,
                )
                .join(PaperAccount)
                .where(PaperAccount.owner_user_id == owner_user_id)
                .distinct()
            )
        visible_attempts = attempt_query.subquery()
        return {
            "attempts": list(
                self.session.scalars(
                    select(PaperDataGapRecoveryAttempt).join(
                        visible_attempts, PaperDataGapRecoveryAttempt.id == visible_attempts.c.id
                    )
                )
            ),
            "gaps": list(
                self.session.scalars(
                    select(PaperDataGapRecoveryGap)
                    .join(visible_attempts, PaperDataGapRecoveryGap.id == visible_attempts.c.gap_id)
                    .distinct()
                )
            ),
            "alerts": list(
                self.session.scalars(
                    select(PaperDataGapRecoveryAlert)
                    .join(visible_attempts, PaperDataGapRecoveryAlert.gap_id == visible_attempts.c.gap_id)
                    .distinct()
                )
            ),
        }
