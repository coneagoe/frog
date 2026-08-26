from dataclasses import dataclass
from datetime import date
from typing import Callable

from sqlalchemy.orm import Session

from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperAccountSnapshot, PaperValuationGap
from paper_trading.storage.repository import PaperTradingRepository


@dataclass(frozen=True)
class SnapshotRecalculationResult:
    account_id: int
    updated_dates: list[date]
    unavailable_dates: list[date]
    failed_dates: list[date]
    errors: list[str]


class SnapshotRecalculationService:
    def __init__(self, session_factory: Callable[[], Session], market_data: MarketDataProvider):
        self.session_factory = session_factory
        self.market_data = market_data

    def recalculate(self, account_id: int, start_date: date, end_date: date) -> SnapshotRecalculationResult:
        if start_date > end_date:
            raise ValueError("start_date must be on or before end_date")

        session = self.session_factory()
        try:
            repo = PaperTradingRepository(session)
            if repo.get_account(account_id) is None:
                raise KeyError(f"paper account not found: {account_id}")

            dates = self._dates_with_valuation_state(repo, account_id, start_date, end_date)
            updated_dates: list[date] = []
            unavailable_dates: list[date] = []
            failed_dates: list[date] = []
            errors: list[str] = []
            snapshot_service = SnapshotService(repo, self.market_data)

            for trade_date in dates:
                try:
                    with session.begin_nested():
                        outcome = snapshot_service.generate_snapshot_or_gap(account_id, trade_date)
                    if outcome.status == "complete":
                        updated_dates.append(trade_date)
                    elif outcome.status == "valuation_gap":
                        unavailable_dates.append(trade_date)
                    else:
                        raise RuntimeError(f"unexpected snapshot outcome: {outcome.status}")
                except Exception as exc:
                    failed_dates.append(trade_date)
                    errors.append(f"{trade_date.isoformat()}: {exc}")

            session.commit()
            return SnapshotRecalculationResult(
                account_id, updated_dates, unavailable_dates, failed_dates, errors
            )
        finally:
            session.close()

    @staticmethod
    def _dates_with_valuation_state(
        repo: PaperTradingRepository, account_id: int, start_date: date, end_date: date
    ) -> list[date]:
        snapshot_dates = {
            trade_date
            for (trade_date,) in repo.session.query(PaperAccountSnapshot.trade_date)
            .filter(
                PaperAccountSnapshot.account_id == account_id,
                PaperAccountSnapshot.point_type == "trading",
                PaperAccountSnapshot.trade_date >= start_date,
                PaperAccountSnapshot.trade_date <= end_date,
            )
            .all()
        }
        gap_dates = {
            trade_date
            for (trade_date,) in repo.session.query(PaperValuationGap.trade_date)
            .filter(
                PaperValuationGap.account_id == account_id,
                PaperValuationGap.trade_date >= start_date,
                PaperValuationGap.trade_date <= end_date,
            )
            .all()
        }
        return sorted(snapshot_dates | gap_dates)
