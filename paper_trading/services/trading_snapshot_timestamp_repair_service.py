from collections.abc import Callable
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from paper_trading.schemas.repairs import (
    TradingSnapshotTimestampRepairCandidate,
    TradingSnapshotTimestampRepairRequest,
    TradingSnapshotTimestampRepairResult,
)
from paper_trading.storage.repository import PaperTradingRepository, canonical_trading_snapshot_event_at

MAX_REPAIR_CANDIDATES = 100


def _utc(event_at: datetime) -> datetime:
    if event_at.tzinfo is None or event_at.utcoffset() is None:
        return event_at.replace(tzinfo=timezone.utc)
    return event_at.astimezone(timezone.utc)


class TradingSnapshotTimestampRepairService:
    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    def run(
        self,
        account_id: int,
        start_date: date,
        end_date: date | None = None,
        apply: bool = False,
    ) -> TradingSnapshotTimestampRepairResult:
        request = TradingSnapshotTimestampRepairRequest(
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
            apply=apply,
        )
        resolved_end_date = request.effective_end_date
        with self._session_factory() as session:
            try:
                repo = PaperTradingRepository(session)
                if apply:
                    repo.lock_account(account_id)
                elif repo.get_account(account_id) is None:
                    raise KeyError(f"paper account not found: {account_id}")

                matched_count = 0
                updated_count = 0
                candidates: list[TradingSnapshotTimestampRepairCandidate] = []
                for snapshot in repo.list_trading_snapshots_in_date_range(account_id, start_date, resolved_end_date):
                    canonical_event_at = canonical_trading_snapshot_event_at(snapshot.trade_date)
                    current_event_at = _utc(snapshot.event_at)
                    if current_event_at != canonical_event_at:
                        matched_count += 1
                        if len(candidates) < MAX_REPAIR_CANDIDATES:
                            candidates.append(
                                TradingSnapshotTimestampRepairCandidate(
                                    snapshot_id=snapshot.id,
                                    trade_date=snapshot.trade_date,
                                    event_at=current_event_at,
                                    canonical_event_at=canonical_event_at,
                                )
                            )
                        if apply:
                            snapshot.event_at = canonical_event_at
                            updated_count += 1

                if apply:
                    session.flush()
                    session.commit()
                else:
                    session.rollback()

                return TradingSnapshotTimestampRepairResult(
                    account_id=account_id,
                    start_date=start_date,
                    end_date=resolved_end_date,
                    dry_run=not apply,
                    matched_count=matched_count,
                    updated_count=updated_count,
                    candidates=candidates,
                )
            except Exception:
                session.rollback()
                raise
