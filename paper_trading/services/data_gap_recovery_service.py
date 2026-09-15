from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable

import numpy as np
import pandas as pd

from common.const import COL_DATE, COL_STOCK_ID, AdjustType, PeriodType
from download.download_manager import _validate_stock_history_data
from download.provider_order import parse_stock_history_provider_order
from paper_trading.domain.enums import (
    DataGapRecoveryAttemptOutcome,
    DataGapRecoveryClassification,
    DataGapRecoveryRouting,
    DataGapRecoveryStatus,
)
from storage import get_storage

logger = logging.getLogger(__name__)
_STOCK_ID = re.compile(r"^[0-9]{6}$", re.ASCII)


def _json_safe_candidate_value(value: Any) -> Any:
    """Normalize provider row values without relying on JSON's string fallback."""
    missing = pd.isna(value)
    if isinstance(missing, (bool, np.bool_)) and missing:
        return None
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return None if not np.isfinite(value) else value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, np.datetime64):
        return None if np.isnat(value) else pd.Timestamp(value).isoformat()
    if isinstance(value, np.generic):
        return _json_safe_candidate_value(value.item())
    if isinstance(value, Mapping):
        return {str(key): _json_safe_candidate_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_json_safe_candidate_value(item) for item in value]
    if pd.isna(value):
        return None
    raise TypeError(f"candidate row value is not JSON serializable: {type(value).__name__}")


def canonical_candidate_payload(
    candidate: pd.DataFrame, *, market: str, stock_id: str, business_date: date, adjust: str
) -> dict[str, Any]:
    if market != "a_share" or adjust != "bfq" or _STOCK_ID.fullmatch(stock_id) is None or len(candidate) != 1:
        raise ValueError("approved candidate must be one a_share/bfq row with a six-digit symbol")
    row = candidate.iloc[0]
    if str(row[COL_STOCK_ID]) != stock_id or pd.to_datetime(row[COL_DATE]).date() != business_date:
        raise ValueError("approved candidate identity or date does not match the gap")
    return {
        "market": market,
        "stock_id": stock_id,
        "business_date": business_date.isoformat(),
        "adjust": adjust,
        "row": {str(key): _json_safe_candidate_value(value) for key, value in row.items()},
    }


def canonical_candidate_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class GapRecoveryResult:
    gap_id: int
    status: str
    provider: str | None = None
    error: str | None = None
    classification: str = DataGapRecoveryClassification.NO_IMPACT.value
    routing: str = DataGapRecoveryRouting.ORDINARY.value


class _RecoveryWriteError(RuntimeError):
    pass


class _RecoveryPersistenceError(RuntimeError):
    pass


class DataGapRecoveryService:
    """Recover only the exact A-share daily BFQ row represented by a gap."""

    def __init__(
        self,
        *,
        storage: Any | None = None,
        downloader: Any | None = None,
        repository: Any | None = None,
        alert_service: Any | None = None,
    ):
        if storage is None:
            storage = get_storage()
        if downloader is None:
            from download.dl import Downloader

            downloader = Downloader()
        self.storage = storage
        self.downloader = downloader
        # Keep the in-memory fallback for existing callers that do not inject a repository.
        self.repository = repository
        self.alert_service = alert_service

    def recover_gaps(self, gaps: Iterable[Any], *, batch_id: int | None = None) -> list[GapRecoveryResult]:
        results = []
        for gap in gaps:
            try:
                results.append(self.recover_gap(gap, batch_id=batch_id))
            except Exception as exc:  # noqa: BLE001
                logger.exception("BFQ gap recovery failed at batch boundary: gap_id=%s", getattr(gap, "id", None))
                self._send_recovery_system_failure(gap, exc)
                results.append(self._result(gap, "failed", error=str(exc)))
        return results

    def recover_unresolved_ordinary_gaps(
        self, gaps: Iterable[Any], *, batch_id: int | None = None
    ) -> list[GapRecoveryResult]:
        results: list[GapRecoveryResult] = []
        for gap in gaps:
            try:
                classification, routing = self._diagnostic(gap)
            except Exception as exc:
                setattr(exc, "partial_results", list(results))
                self._send_recovery_system_failure(gap, exc)
                raise
            if routing != DataGapRecoveryRouting.ORDINARY.value:
                results.append(
                    GapRecoveryResult(
                        gap.id,
                        "failed",
                        error="gap routing is not ordinary",
                        classification=classification,
                        routing=routing,
                    )
                )
                continue
            if self._is_terminal(gap):
                results.append(self._result(gap, "skipped", classification=classification, routing=routing))
                continue
            try:
                result = self.recover_gap(gap, batch_id=batch_id)
                if result.status == "failed":
                    self.maybe_escalate_gap(
                        gap,
                        user_id=0,
                        user_snapshot={"actor": "system", "source": "data_gap_recovery"},
                    )
                results.append(replace(result, classification=classification, routing=routing))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Unified ordinary gap recovery failed: gap_id=%s", getattr(gap, "id", None))
                results.append(
                    GapRecoveryResult(gap.id, "failed", error=str(exc), classification=classification, routing=routing)
                )
        return results

    def recover_gap(self, gap: Any, *, batch_id: int | None = None) -> GapRecoveryResult:
        classification, routing = self._diagnostic(gap)
        status = self._status(gap)
        if self._is_terminal(gap) and status != DataGapRecoveryStatus.ESCALATED.value:
            return self._result(gap, "skipped", classification=classification, routing=routing)
        if routing != DataGapRecoveryRouting.ORDINARY.value and status != DataGapRecoveryStatus.ESCALATED.value:
            return self._result(
                gap,
                "failed",
                error="gap routing is not ordinary",
                classification=classification,
                routing=routing,
            )
        business_date: date = gap.business_date
        stock_id = gap.stock_id
        if (
            gap.market != "a_share"
            or gap.adjust != "bfq"
            or not isinstance(stock_id, str)
            or _STOCK_ID.fullmatch(stock_id) is None
        ):
            return self._result(
                gap, "failed", error="invalid gap identity", classification=classification, routing=routing
            )
        try:
            existing = self._read_exact(stock_id, business_date)
            if not existing.empty:
                self._resolve(gap)
                return self._result(gap, "skipped", classification=classification, routing=routing)

            request_date = business_date.strftime("%Y%m%d")
            for provider in parse_stock_history_provider_order():
                try:
                    candidate = self.downloader.dl_history_data_stock_by_provider(
                        provider, stock_id, request_date, request_date, PeriodType.DAILY, AdjustType.BFQ
                    )
                    candidate = _validate_stock_history_data(candidate)
                    exact = candidate[
                        (candidate[COL_STOCK_ID].astype(str) == stock_id)
                        & (pd.to_datetime(candidate[COL_DATE]).dt.date == business_date)
                    ]
                    if len(exact) != 1:
                        raise ValueError("provider result did not contain exactly one requested row")
                    exact = exact.iloc[[0]].copy()
                    # Persist the exact validated provider row before any later
                    # escalation decision.  This is the same canonical boundary
                    # used by approved execution; it is evidence, not a second
                    # provider validation path.
                    escalated = self._status(gap) == DataGapRecoveryStatus.ESCALATED.value
                    if self.repository is not None and hasattr(self.repository, "record_candidate"):
                        payload = canonical_candidate_payload(
                            exact,
                            market=gap.market,
                            stock_id=stock_id,
                            business_date=business_date,
                            adjust=gap.adjust,
                        )
                        self.repository.record_candidate(
                            gap.id,
                            canonical_candidate_hash(payload),
                            payload,
                            {"validated": True, "provider": provider},
                            provider,
                        )
                    if escalated:
                        self._record_attempt(
                            gap,
                            batch_id,
                            DataGapRecoveryAttemptOutcome.RECOVERED,
                            provider,
                            classification=classification,
                            routing=routing,
                        )
                        return self._result(
                            gap, "pending_approval", provider, classification=classification, routing=routing
                        )
                    if not self.storage.save_history_data_stock(exact, PeriodType.DAILY, AdjustType.BFQ):
                        raise _RecoveryWriteError("save returned False")
                    if self._read_exact(stock_id, business_date).empty:
                        raise _RecoveryWriteError("exact-key readback did not find recovered row")
                except _RecoveryWriteError as exc:
                    self._record_attempt(
                        gap,
                        batch_id,
                        DataGapRecoveryAttemptOutcome.FAILED,
                        provider,
                        classification=classification,
                        routing=routing,
                    )
                    self._send_recovery_system_failure(gap, exc)
                    return self._result(gap, "failed", provider, str(exc), classification, routing)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("BFQ gap provider failed: stock_id=%s provider=%s error=%s", stock_id, provider, exc)
                    continue
                self._record_attempt(
                    gap,
                    batch_id,
                    DataGapRecoveryAttemptOutcome.RECOVERED,
                    provider,
                    classification=classification,
                    routing=routing,
                )
                self._resolve(gap)
                return self._result(gap, "recovered", provider, classification=classification, routing=routing)

            self._record_attempt(
                gap,
                batch_id,
                DataGapRecoveryAttemptOutcome.NOT_FOUND,
                None,
                classification=classification,
                routing=routing,
            )
            error = RuntimeError("all providers failed")
            self._send_recovery_system_failure(gap, error)
            return self._result(gap, "failed", error=str(error), classification=classification, routing=routing)
        except _RecoveryPersistenceError as exc:
            self._send_recovery_system_failure(gap, exc)
            return self._result(gap, "failed", error=str(exc), classification=classification, routing=routing)
        except Exception as exc:  # noqa: BLE001
            self._record_attempt(
                gap,
                batch_id,
                DataGapRecoveryAttemptOutcome.FAILED,
                None,
                classification=classification,
                routing=routing,
            )
            self._send_recovery_system_failure(gap, exc)
            return self._result(gap, "failed", error=str(exc), classification=classification, routing=routing)

    def maybe_escalate_gap(
        self,
        gap: Any,
        *,
        user_id: int,
        user_snapshot: dict[str, Any],
        as_of: date | None = None,
        reason: str | None = None,
    ) -> bool:
        """Escalate an unresolved gap once either service threshold is reached."""
        if self.repository is None or not hasattr(self.repository, "escalate_gap"):
            return False
        current_status = getattr(gap, "status", DataGapRecoveryStatus.OPEN)
        if getattr(current_status, "value", current_status) != DataGapRecoveryStatus.OPEN.value:
            return False
        evidence = self.repository.gap_evidence(gap.id)
        attempts = evidence.get("attempts", [])
        unavailable_batches = {
            attempt.batch_id
            for attempt in attempts
            if getattr(attempt, "outcome", None) == DataGapRecoveryAttemptOutcome.NOT_FOUND
            and getattr(attempt, "batch_id", None) is not None
        }
        today = as_of or date.today()
        business_days = sum(
            (gap.business_date + timedelta(days=offset)).weekday() < 5
            for offset in range(max(0, (today - gap.business_date).days + 1))
        )
        if len(unavailable_batches) < 3 and business_days < 5:
            return False
        self.repository.escalate_gap(gap.id, user_id, user_snapshot, reason=reason)
        self._send_escalation(gap)
        return True

    def send_account_recovery_failure(self, gap: Any, *, account_id: int, error: Exception) -> None:
        """Record an account alert without allowing mail failures to affect recovery."""
        if self.alert_service is None:
            return
        try:
            self.alert_service.send_account_recovery_failure(
                gap, account_id=account_id, failure_class=self._failure_class(error)
            )
        except Exception:  # noqa: BLE001
            logger.exception("Data-gap account alert failed: gap_id=%s account_id=%s", gap.id, account_id)

    @staticmethod
    def _failure_class(error: Exception) -> str:
        return type(error).__name__.lower().replace("error", "") or "failure"

    def _send_escalation(self, gap: Any) -> None:
        if self.alert_service is None:
            return
        try:
            self.alert_service.send_escalation(gap, failure_class="threshold")
        except Exception:  # noqa: BLE001
            logger.exception("Data-gap escalation alert failed: gap_id=%s", gap.id)

    def _send_recovery_system_failure(self, gap: Any, error: Exception) -> None:
        if self.alert_service is None:
            return
        try:
            self.alert_service.send_recovery_system_failure(gap, failure_class=self._failure_class(error))
        except Exception:  # noqa: BLE001
            logger.exception("Data-gap recovery system alert failed: gap_id=%s", getattr(gap, "id", None))

    def execute_approved_gap(
        self, gap: Any, candidate_hash: str, candidate: pd.DataFrame | None = None
    ) -> GapRecoveryResult:
        """Write an approved candidate only if it is still the current candidate."""
        classification, routing = self._diagnostic(gap)
        if self.repository is None or not hasattr(self.repository, "execute_approved_candidate"):
            return self._result(
                gap,
                "failed",
                error="authoritative approval repository is required",
                classification=classification,
                routing=routing,
            )

        def write(locked_gap: Any, payload: dict[str, Any] | Any = None, resolve_gap: Any = None) -> GapRecoveryResult:
            locked_classification, locked_routing = self._diagnostic(locked_gap)
            if locked_classification == DataGapRecoveryClassification.NO_IMPACT.value:
                return self._result(locked_gap, "skipped", classification=locked_classification, routing=locked_routing)
            if callable(payload) and resolve_gap is None:
                resolve_gap = payload
                payload = None
            if isinstance(payload, dict):
                stored_payload = payload
                stored_candidate = pd.DataFrame([stored_payload["row"]])
            elif candidate is not None:
                stored_payload = canonical_candidate_payload(
                    candidate,
                    market=locked_gap.market,
                    stock_id=locked_gap.stock_id,
                    business_date=locked_gap.business_date,
                    adjust=locked_gap.adjust,
                )
                stored_candidate = candidate
            else:
                raise ValueError("approved candidate payload is required")
            if canonical_candidate_hash(stored_payload) != candidate_hash:
                raise ValueError("approved candidate payload does not match approved hash")
            existing = self._read_exact(locked_gap.stock_id, locked_gap.business_date)
            if not existing.empty:
                if not self._exact_rows_match_candidate(existing, stored_candidate, locked_gap):
                    raise _RecoveryWriteError("existing exact row differs from approved candidate")
                if resolve_gap is None:
                    self._resolve(locked_gap)
                else:
                    try:
                        resolve_gap(locked_gap.id)
                    except Exception as exc:
                        raise _RecoveryPersistenceError(str(exc)) from exc
                return self._result(
                    locked_gap, "recovered", classification=locked_classification, routing=locked_routing
                )
            if not self.storage.save_history_data_stock(stored_candidate, PeriodType.DAILY, AdjustType.BFQ):
                raise _RecoveryWriteError("save returned False")
            if self._read_exact(locked_gap.stock_id, locked_gap.business_date).empty:
                raise _RecoveryWriteError("exact-key readback did not find recovered row")
            if resolve_gap is None:
                self._resolve(locked_gap)
            else:
                try:
                    resolve_gap(locked_gap.id)
                except Exception as exc:  # noqa: BLE001
                    raise _RecoveryPersistenceError(str(exc)) from exc
            return self._result(locked_gap, "recovered", classification=locked_classification, routing=locked_routing)

        try:
            result = self.repository.execute_approved_candidate(gap.id, candidate_hash, write)
            if not isinstance(result, GapRecoveryResult):
                raise ValueError("approval repository did not execute the write callback")
            return result
        except Exception as exc:  # noqa: BLE001
            status = "pending_approval" if "stale" in str(exc) else "failed"
            return self._result(gap, status, error=str(exc), classification=classification, routing=routing)

    @staticmethod
    def _is_terminal(gap: Any) -> bool:
        status = DataGapRecoveryService._status(gap)
        summary = getattr(gap, "summary", None)
        explicit_no_impact = (
            isinstance(summary, dict) and summary.get("classification") == DataGapRecoveryClassification.NO_IMPACT.value
        )
        return (
            status
            in {
                DataGapRecoveryStatus.PERMANENTLY_UNRESOLVED.value,
                DataGapRecoveryStatus.PENDING_APPROVAL.value,
            }
            or explicit_no_impact
        )

    @staticmethod
    def _status(gap: Any) -> str | None:
        status = getattr(gap, "status", None)
        return getattr(status, "value", status)

    @staticmethod
    def _diagnostic(gap: Any) -> tuple[str, str]:
        summary = getattr(gap, "summary", None)
        if not isinstance(summary, dict):
            summary = {}
        classification = summary.get("classification", DataGapRecoveryClassification.NO_IMPACT.value)
        if classification not in {item.value for item in DataGapRecoveryClassification}:
            classification = DataGapRecoveryClassification.NO_IMPACT.value
        routing = summary.get("routing", DataGapRecoveryRouting.ORDINARY.value)
        if routing not in {item.value for item in DataGapRecoveryRouting}:
            routing = DataGapRecoveryRouting.APPROVAL_ESCALATION.value
        return classification, routing

    def _result(
        self,
        gap: Any,
        status: str,
        provider: str | None = None,
        error: str | None = None,
        classification: str | None = None,
        routing: str | None = None,
    ) -> GapRecoveryResult:
        default_classification, default_routing = self._diagnostic(gap)
        return GapRecoveryResult(
            gap.id,
            status,
            provider,
            error,
            classification if classification is not None else default_classification,
            routing if routing is not None else default_routing,
        )

    def _read_exact(self, stock_id: str, business_date: date) -> pd.DataFrame:
        value = business_date.isoformat()
        rows = self.storage.load_history_data_stock(
            stock_id, PeriodType.DAILY, AdjustType.BFQ, start_date=value, end_date=value
        )
        if rows.empty or COL_STOCK_ID not in rows or COL_DATE not in rows:
            return rows.iloc[0:0]
        return rows[
            (rows[COL_STOCK_ID].astype(str) == stock_id)
            & (pd.to_datetime(rows[COL_DATE], errors="coerce").dt.date == business_date)
        ]

    @staticmethod
    def _exact_rows_match_candidate(existing: pd.DataFrame, candidate: pd.DataFrame, gap: Any) -> bool:
        candidate_payload = canonical_candidate_payload(
            candidate,
            market=gap.market,
            stock_id=gap.stock_id,
            business_date=gap.business_date,
            adjust=gap.adjust,
        )
        return all(
            canonical_candidate_payload(
                row.to_frame().T,
                market=gap.market,
                stock_id=gap.stock_id,
                business_date=gap.business_date,
                adjust=gap.adjust,
            )
            == candidate_payload
            for _, row in existing.iterrows()
        )

    def _record_attempt(
        self,
        gap: Any,
        batch_id: int | None,
        outcome: DataGapRecoveryAttemptOutcome,
        provider: str | None,
        *,
        classification: str,
        routing: str,
    ) -> None:
        if self.repository is not None:
            evidence = {
                "classification": classification,
                "routing": routing,
            }
            if provider:
                evidence["provider"] = provider
            try:
                self.repository.record_attempt(gap.id, batch_id, outcome, evidence)
            except Exception as exc:  # noqa: BLE001
                raise _RecoveryPersistenceError(str(exc)) from exc

    def _resolve(self, gap: Any) -> None:
        if self.repository is not None and hasattr(self.repository, "resolve_gap"):
            try:
                self.repository.resolve_gap(gap.id)
            except Exception as exc:  # noqa: BLE001
                raise _RecoveryPersistenceError(str(exc)) from exc
        else:
            gap.status = DataGapRecoveryStatus.RECOVERED.value
            gap.resolved_at = datetime.now(timezone.utc)
