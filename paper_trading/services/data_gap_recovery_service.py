from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable

import pandas as pd

from common.const import COL_DATE, COL_STOCK_ID, AdjustType, PeriodType
from download.download_manager import _validate_stock_history_data
from download.provider_order import parse_stock_history_provider_order
from paper_trading.domain.enums import DataGapRecoveryAttemptOutcome, DataGapRecoveryStatus
from storage import get_storage

logger = logging.getLogger(__name__)
_STOCK_ID = re.compile(r"^[0-9]{6}$", re.ASCII)


@dataclass(frozen=True)
class GapRecoveryResult:
    gap_id: int
    status: str
    provider: str | None = None
    error: str | None = None


class _RecoveryWriteError(RuntimeError):
    pass


class DataGapRecoveryService:
    """Recover only the exact A-share daily BFQ row represented by a gap."""

    def __init__(self, *, storage: Any | None = None, downloader: Any | None = None, repository: Any | None = None):
        if storage is None:
            storage = get_storage()
        if downloader is None:
            from download.dl import Downloader

            downloader = Downloader()
        self.storage = storage
        self.downloader = downloader
        # Keep the in-memory fallback for existing callers that do not inject a repository.
        self.repository = repository

    def recover_gaps(self, gaps: Iterable[Any], *, batch_id: int | None = None) -> list[GapRecoveryResult]:
        results = []
        for gap in gaps:
            try:
                results.append(self.recover_gap(gap, batch_id=batch_id))
            except Exception as exc:  # noqa: BLE001
                logger.exception("BFQ gap recovery failed at batch boundary: gap_id=%s", getattr(gap, "id", None))
                results.append(GapRecoveryResult(gap.id, "failed", error=str(exc)))
        return results

    def recover_gap(self, gap: Any, *, batch_id: int | None = None) -> GapRecoveryResult:
        business_date: date = gap.business_date
        stock_id = gap.stock_id
        if (
            gap.market != "a_share"
            or gap.adjust != "bfq"
            or not isinstance(stock_id, str)
            or _STOCK_ID.fullmatch(stock_id) is None
        ):
            return GapRecoveryResult(gap.id, "failed", error="invalid gap identity")
        try:
            existing = self._read_exact(stock_id, business_date)
            if not existing.empty:
                self._resolve(gap)
                return GapRecoveryResult(gap.id, "skipped")

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
                    if not self.storage.save_history_data_stock(exact, PeriodType.DAILY, AdjustType.BFQ):
                        raise _RecoveryWriteError("save returned False")
                    if self._read_exact(stock_id, business_date).empty:
                        raise _RecoveryWriteError("exact-key readback did not find recovered row")
                    self._record_attempt(gap, batch_id, DataGapRecoveryAttemptOutcome.RECOVERED, provider)
                    self._resolve(gap)
                    return GapRecoveryResult(gap.id, "recovered", provider)
                except _RecoveryWriteError as exc:
                    self._record_attempt(gap, batch_id, DataGapRecoveryAttemptOutcome.FAILED, provider)
                    return GapRecoveryResult(gap.id, "failed", provider, str(exc))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("BFQ gap provider failed: stock_id=%s provider=%s error=%s", stock_id, provider, exc)
                    continue

            self._record_attempt(gap, batch_id, DataGapRecoveryAttemptOutcome.NOT_FOUND, None)
            return GapRecoveryResult(gap.id, "failed", error="all providers failed")
        except Exception as exc:  # noqa: BLE001
            self._record_attempt(gap, batch_id, DataGapRecoveryAttemptOutcome.FAILED, None)
            return GapRecoveryResult(gap.id, "failed", error=str(exc))

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

    def _record_attempt(
        self, gap: Any, batch_id: int | None, outcome: DataGapRecoveryAttemptOutcome, provider: str | None
    ) -> None:
        if self.repository is not None:
            try:
                self.repository.record_attempt(gap.id, batch_id, outcome, {"provider": provider} if provider else {})
            except Exception:  # noqa: BLE001
                logger.exception("Failed to persist BFQ gap recovery attempt: gap_id=%s", gap.id)

    def _resolve(self, gap: Any) -> None:
        if self.repository is not None and hasattr(self.repository, "resolve_gap"):
            try:
                self.repository.resolve_gap(gap.id)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to persist BFQ gap resolution: gap_id=%s", gap.id)
        else:
            gap.status = DataGapRecoveryStatus.RECOVERED.value
            gap.resolved_at = datetime.now(timezone.utc)
