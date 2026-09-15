from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
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
    PaperOrder,
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
        gap = self._locked_gap(gap_id)
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
        gap = self._locked_gap(gap_id)
        candidate = PaperDataGapRecoveryCandidate(
            gap_id=gap_id, candidate_hash=candidate_hash, payload=payload, validation=validation, source=source
        )
        self.session.add(candidate)
        gap.latest_candidate_hash = candidate_hash
        self.session.flush()
        return candidate

    def record_attempt(
        self, gap_id: int, batch_id: int | None, outcome: DataGapRecoveryAttemptOutcome, evidence: dict[str, Any]
    ) -> PaperDataGapRecoveryAttempt:
        attempt = PaperDataGapRecoveryAttempt(gap_id=gap_id, batch_id=batch_id, outcome=outcome, evidence=evidence)
        self.session.add(attempt)
        self.session.flush()
        return attempt

    def record_batch(
        self,
        status: DataGapRecoveryBatchStatus,
        summary: dict[str, Any],
        *,
        download_id: str | None = None,
        cutoff: datetime | None = None,
    ) -> PaperDataGapRecoveryBatch:
        batch = PaperDataGapRecoveryBatch(status=status, summary=summary, download_id=download_id, cutoff=cutoff)
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

    def _locked_gap(self, gap_id: int) -> PaperDataGapRecoveryGap:
        gap = self.session.scalar(
            select(PaperDataGapRecoveryGap).where(PaperDataGapRecoveryGap.id == gap_id).with_for_update()
        )
        if gap is None:
            raise KeyError(gap_id)
        return gap

    @staticmethod
    def _authenticated_snapshot(user_id: int | None, snapshot: dict[str, Any], reason: str | None) -> dict[str, Any]:
        if user_id is None:
            raise ValueError("authenticated user is required")
        result = dict(snapshot)
        result["user_id"] = user_id
        if reason is not None:
            result["reason"] = reason
        return result

    def escalate_gap(
        self, gap_id: int, user_id: int, user_snapshot: dict[str, Any], *, reason: str | None = None
    ) -> PaperDataGapRecoveryGap:
        """Move an open gap to escalation and append its authenticated audit event."""
        gap = self._locked_gap(gap_id)
        if gap.status != DataGapRecoveryStatus.OPEN:
            raise ValueError("only open gaps can be escalated")
        snapshot = self._authenticated_snapshot(user_id, user_snapshot, reason)
        self.record_attempt(gap_id, None, DataGapRecoveryAttemptOutcome.FAILED, {"event": "escalated", **snapshot})
        gap.status = DataGapRecoveryStatus.ESCALATED
        self.session.flush()
        return gap

    def invalidate_stale_candidate(self, gap_id: int, candidate_hash: str) -> PaperDataGapRecoveryGap:
        """Invalidate a decision based on anything other than the current candidate."""
        gap = self._locked_gap(gap_id)
        if gap.latest_candidate_hash == candidate_hash:
            return gap
        gap.status = DataGapRecoveryStatus.PENDING_APPROVAL
        self.session.flush()
        return gap

    def _decide_gap(
        self,
        gap_id: int,
        decision: DataGapRecoveryApprovalDecision,
        candidate_hash: str,
        user_id: int | None,
        user_snapshot: dict[str, Any],
        reason: str | None,
        status: DataGapRecoveryStatus,
    ) -> PaperDataGapRecoveryGap:
        gap = self._locked_gap(gap_id)
        if gap.status not in {DataGapRecoveryStatus.ESCALATED, DataGapRecoveryStatus.PENDING_APPROVAL}:
            raise ValueError("approval decisions require an escalated or pending-approval gap")
        if gap.latest_candidate_hash != candidate_hash:
            gap.status = DataGapRecoveryStatus.PENDING_APPROVAL
            self.session.flush()
            return gap
        snapshot = self._authenticated_snapshot(user_id, user_snapshot, reason)
        self.record_approval(gap_id, decision, candidate_hash, user_id, snapshot)
        gap.status = status
        if status == DataGapRecoveryStatus.RECOVERED:
            gap.resolved_at = datetime.now(timezone.utc)
        else:
            gap.resolved_at = None
        self.session.flush()
        return gap

    def approve_gap(
        self,
        gap_id: int,
        candidate_hash: str,
        user_id: int,
        user_snapshot: dict[str, Any],
        *,
        reason: str | None = None,
    ) -> PaperDataGapRecoveryGap:
        return self._decide_gap(
            gap_id,
            DataGapRecoveryApprovalDecision.APPROVED,
            candidate_hash,
            user_id,
            user_snapshot,
            reason,
            DataGapRecoveryStatus.PENDING_APPROVAL,
        )

    def execute_approved_candidate(
        self, gap_id: int, candidate_hash: str, write_callback: Callable[[PaperDataGapRecoveryGap], Any]
    ) -> Any:
        """Lock and authorize a candidate while its write callback runs in this transaction."""
        gap = self._locked_gap(gap_id)
        if gap.status != DataGapRecoveryStatus.PENDING_APPROVAL:
            raise ValueError("approved writes require a pending-approval gap")
        if gap.latest_candidate_hash != candidate_hash:
            gap.status = DataGapRecoveryStatus.PENDING_APPROVAL
            self.session.flush()
            raise ValueError("approved candidate hash is stale")
        approval = self.session.scalar(
            select(PaperDataGapRecoveryApproval).where(
                PaperDataGapRecoveryApproval.gap_id == gap_id,
                PaperDataGapRecoveryApproval.candidate_hash == candidate_hash,
                PaperDataGapRecoveryApproval.decision == DataGapRecoveryApprovalDecision.APPROVED,
            )
        )
        if approval is None:
            raise ValueError("approved candidate decision is required")
        return write_callback(gap)

    def reject_gap(
        self,
        gap_id: int,
        candidate_hash: str,
        user_id: int,
        user_snapshot: dict[str, Any],
        *,
        reason: str | None = None,
    ) -> PaperDataGapRecoveryGap:
        return self._decide_gap(
            gap_id,
            DataGapRecoveryApprovalDecision.REJECTED,
            candidate_hash,
            user_id,
            user_snapshot,
            reason,
            DataGapRecoveryStatus.PERMANENTLY_UNRESOLVED,
        )

    def reopen_gap(
        self, gap_id: int, user_id: int, user_snapshot: dict[str, Any], *, reason: str | None = None
    ) -> PaperDataGapRecoveryGap:
        gap = self._locked_gap(gap_id)
        if gap.status != DataGapRecoveryStatus.PERMANENTLY_UNRESOLVED:
            raise ValueError("only permanently unresolved gaps can be reopened")
        snapshot = self._authenticated_snapshot(user_id, user_snapshot, reason)
        if gap.latest_candidate_hash is None:
            raise ValueError("cannot reopen a gap without a candidate")
        self.record_approval(
            gap_id,
            DataGapRecoveryApprovalDecision.REOPENED,
            gap.latest_candidate_hash,
            user_id,
            snapshot,
        )
        gap.status = DataGapRecoveryStatus.OPEN
        gap.resolved_at = None
        self.session.flush()
        return gap

    def record_alert(self, gap_id: int, cycle_key: str, evidence: dict[str, Any]) -> PaperDataGapRecoveryAlert:
        alert = PaperDataGapRecoveryAlert(gap_id=gap_id, cycle_key=cycle_key, evidence=evidence)
        self.session.add(alert)
        self.session.flush()
        return alert

    def claim_alert(
        self, gap_id: int, cycle_key: str, evidence: dict[str, Any]
    ) -> tuple[PaperDataGapRecoveryAlert, bool]:
        """Atomically claim an alert cycle; failed cycles get a retry cycle."""
        retry = 0
        collision_reads = 0
        while retry < 100:
            key = cycle_key if retry == 0 else f"{cycle_key}:retry:{retry}"
            try:
                with self.session.begin_nested():
                    alert = self.get_alert(gap_id, key)
                    if alert is not None:
                        if alert.delivery_state != DataGapRecoveryAlertDeliveryState.FAILED:
                            return alert, False
                        retry += 1
                        continue
                    return self.record_alert(gap_id, key, evidence), True
            except IntegrityError:
                # Re-read the contested key before allocating a retry. Otherwise a
                # concurrent pending/delivered insert could cause duplicate delivery.
                collision_reads += 1
                alert = self._read_alert_after_collision(gap_id, key)
                if alert is None:
                    if collision_reads >= 100:
                        break
                    continue
                collision_reads = 0
                if alert.delivery_state != DataGapRecoveryAlertDeliveryState.FAILED:
                    return alert, False
                retry += 1
        raise RuntimeError("unable to claim data-gap alert cycle")

    def _read_alert_after_collision(self, gap_id: int, cycle_key: str) -> PaperDataGapRecoveryAlert | None:
        """Read a winner after a savepoint collision without affecting the outer transaction."""
        with self.session.begin_nested():
            return self.get_alert(gap_id, cycle_key)

    def get_alert(self, gap_id: int, cycle_key: str) -> PaperDataGapRecoveryAlert | None:
        return self.session.scalar(
            select(PaperDataGapRecoveryAlert).where(
                PaperDataGapRecoveryAlert.gap_id == gap_id,
                PaperDataGapRecoveryAlert.cycle_key == cycle_key,
            )
        )

    def update_alert_delivery(
        self, alert_id: int, state: DataGapRecoveryAlertDeliveryState, metadata: dict[str, Any]
    ) -> PaperDataGapRecoveryAlert:
        alert = self.session.get(PaperDataGapRecoveryAlert, alert_id)
        if alert is None:
            raise KeyError(alert_id)
        evidence = dict(alert.evidence)
        evidence["delivery"] = metadata
        alert.evidence = evidence
        alert.delivery_state = state
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

    def record_account_recovery_step(
        self,
        gap_id: int,
        account_id: int,
        step: str,
        status: str,
        evidence: dict[str, Any],
    ) -> PaperDataGapRecoveryAccount:
        """Persist one recovery step without replacing the other step's evidence."""
        if step not in {"ledger", "snapshot"}:
            raise ValueError("recovery step must be ledger or snapshot")
        progress = self.session.scalar(
            select(PaperDataGapRecoveryAccount).where(
                PaperDataGapRecoveryAccount.gap_id == gap_id,
                PaperDataGapRecoveryAccount.account_id == account_id,
            )
        )
        if progress is None:
            progress = PaperDataGapRecoveryAccount(
                gap_id=gap_id,
                account_id=account_id,
                status=DataGapRecoveryAccountStatus.IN_PROGRESS,
                summary={},
            )
            self.session.add(progress)
        summary = dict(progress.summary or {})
        summary[step] = {"status": status, "evidence": evidence}
        progress.summary = summary
        progress.status = (
            DataGapRecoveryAccountStatus.RECOVERED
            if all(summary.get(name, {}).get("status") in {"completed", "recovered"} for name in ("ledger", "snapshot"))
            else DataGapRecoveryAccountStatus.FAILED
            if status == "failed"
            else DataGapRecoveryAccountStatus.IN_PROGRESS
        )
        progress.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return progress

    def list_retryable_account_progress(self) -> list[PaperDataGapRecoveryAccount]:
        """Return account work whose ledger or snapshot step is not complete."""
        rows = self.session.scalars(
            select(PaperDataGapRecoveryAccount).order_by(
                PaperDataGapRecoveryAccount.gap_id, PaperDataGapRecoveryAccount.account_id
            )
        )
        return [
            row
            for row in rows
            if any(
                row.summary.get(step, {}).get("status") not in {"completed", "recovered"}
                for step in ("ledger", "snapshot")
            )
        ]

    def list_batch_account_recovery(self, batch_id: int) -> list[dict[str, Any]]:
        """Return affected accounts and their earliest gap date for a batch."""
        batch = self.session.get(PaperDataGapRecoveryBatch, batch_id)
        if batch is None:
            raise KeyError(batch_id)
        cutoff = batch.cutoff.date() if batch.cutoff is not None else None
        rows = self.session.execute(
            select(
                PaperDataGapRecoveryGap.id,
                PaperOrder.account_id,
                func.min(PaperDataGapRecoveryGap.business_date),
            )
            .join(
                PaperDataGapRecoveryGap,
                (PaperDataGapRecoveryGap.stock_id == PaperOrder.symbol)
                & (PaperOrder.trade_date >= PaperDataGapRecoveryGap.business_date)
                & (cutoff is None or PaperOrder.trade_date <= cutoff),
            )
            .join(
                PaperDataGapRecoveryAttempt,
                PaperDataGapRecoveryAttempt.gap_id == PaperDataGapRecoveryGap.id,
            )
            .where(PaperDataGapRecoveryAttempt.batch_id == batch_id)
            .group_by(PaperDataGapRecoveryGap.id, PaperOrder.account_id)
            .order_by(PaperOrder.account_id, PaperDataGapRecoveryGap.id)
        ).all()
        result = [
            {
                "gap_id": int(gap_id),
                "account_id": int(account_id),
                "start_date": start_date,
                "end_date": cutoff or start_date,
            }
            for gap_id, account_id, start_date in rows
        ]
        known = {(item["gap_id"], item["account_id"]) for item in result}
        batch_gap_ids = set(
            self.session.scalars(
                select(PaperDataGapRecoveryAttempt.gap_id).where(PaperDataGapRecoveryAttempt.batch_id == batch_id)
            )
        )
        gap_rows = self.session.scalars(select(PaperDataGapRecoveryGap)).all()
        account_ids = self.session.scalars(select(PaperAccount.id)).all()
        for gap in gap_rows:
            if (
                gap.id not in batch_gap_ids
                or gap.status == DataGapRecoveryStatus.RECOVERED
                or gap.business_date > (cutoff or gap.business_date)
            ):
                continue
            for account_id in account_ids:
                for event in DataGapRecoveryRepository._account_replay_events(self, int(account_id)):
                    symbol = event.payload.get("symbol")
                    if (
                        symbol == gap.stock_id
                        and gap.business_date <= event.trade_date <= (cutoff or event.trade_date)
                        and (gap.id, int(account_id)) not in known
                    ):
                        result.append(
                            {
                                "gap_id": gap.id,
                                "account_id": int(account_id),
                                "start_date": gap.business_date,
                                "end_date": cutoff or gap.business_date,
                            }
                        )
                        known.add((gap.id, int(account_id)))
                        break
        return result

    def _account_replay_events(self, account_id: int) -> list[Any]:
        """Use the repository's canonical replay projection for recovery impact."""
        from paper_trading.storage.repository import PaperTradingRepository

        return PaperTradingRepository(self.session).list_replay_events(account_id)

    def list_retryable_recovery_work(self, cutoff: datetime | None = None) -> list[dict[str, Any]]:
        """Return incomplete account steps from current and prior batches."""
        end_date = cutoff.date() if cutoff is not None else None
        rows = self.session.scalars(
            select(PaperDataGapRecoveryAccount)
            .join(PaperDataGapRecoveryGap)
            .order_by(PaperDataGapRecoveryGap.business_date, PaperDataGapRecoveryAccount.account_id)
        )
        result: list[dict[str, Any]] = []
        for progress in rows:
            summary = progress.summary or {}
            if all(
                summary.get(step, {}).get("status") in {"completed", "recovered"} for step in ("ledger", "snapshot")
            ):
                continue
            gap = self.session.get(PaperDataGapRecoveryGap, progress.gap_id)
            if gap is None or (end_date is not None and gap.business_date > end_date):
                continue
            result.append(
                {
                    "gap_id": progress.gap_id,
                    "account_id": progress.account_id,
                    "start_date": gap.business_date,
                    "end_date": end_date or gap.business_date,
                }
            )
        return result

    def get_account_progress(self, gap_id: int, account_id: int) -> PaperDataGapRecoveryAccount | None:
        return self.session.scalar(
            select(PaperDataGapRecoveryAccount).where(
                PaperDataGapRecoveryAccount.gap_id == gap_id,
                PaperDataGapRecoveryAccount.account_id == account_id,
            )
        )

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
