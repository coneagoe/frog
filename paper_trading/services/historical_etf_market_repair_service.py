from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from paper_trading.domain.enums import Market
from paper_trading.services.order_delete_service import OrderDeleteService
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.repository import PaperTradingRepository


@dataclass(frozen=True)
class RepairCandidate:
    account_id: int
    order_id: int
    symbol: str
    trade_date: date


@dataclass(frozen=True)
class RepairedAccount:
    account_id: int
    order_ids: list[int]
    replay_start_date: date


@dataclass(frozen=True)
class FailedAccount:
    account_id: int
    error: str


@dataclass(frozen=True)
class HistoricalEtfMarketRepairResult:
    dry_run: bool
    candidates: list[RepairCandidate]
    corrected_orders: list[RepairCandidate]
    repaired_accounts: list[RepairedAccount]
    skipped_accounts: list[int]
    failed_accounts: list[FailedAccount]


class HistoricalEtfMarketRepairService:
    def __init__(self, session_factory: Callable[[], Session], market_data: MarketDataProvider):
        self._session_factory = session_factory
        self._market_data = market_data

    def run(self, apply: bool = False) -> HistoricalEtfMarketRepairResult:
        with self._session_factory() as session:
            candidates = [
                RepairCandidate(order.account_id, order.id, order.symbol, order.trade_date)
                for order in PaperTradingRepository(session).list_catalogue_etf_a_share_orders()
            ]

        if not apply:
            return HistoricalEtfMarketRepairResult(True, candidates, [], [], [], [])

        candidates_by_account: dict[int, list[RepairCandidate]] = defaultdict(list)
        for candidate in candidates:
            candidates_by_account[candidate.account_id].append(candidate)

        corrected_orders: list[RepairCandidate] = []
        repaired_accounts: list[RepairedAccount] = []
        skipped_accounts: list[int] = []
        failed_accounts: list[FailedAccount] = []
        for account_id in sorted(candidates_by_account):
            repaired = self._repair_account(account_id)
            if isinstance(repaired, FailedAccount):
                failed_accounts.append(repaired)
            elif repaired is None:
                skipped_accounts.append(account_id)
            else:
                corrected_orders.extend(candidates_by_account[account_id])
                repaired_accounts.append(repaired)

        return HistoricalEtfMarketRepairResult(
            False,
            candidates,
            corrected_orders,
            repaired_accounts,
            skipped_accounts,
            failed_accounts,
        )

    def _repair_account(self, account_id: int) -> RepairedAccount | FailedAccount | None:
        with self._session_factory() as session:
            try:
                repo = PaperTradingRepository(session)
                repo.lock_account(account_id)
                orders = repo.list_catalogue_etf_a_share_orders(account_id)
                if not orders:
                    session.rollback()
                    return None
                order_ids = [order.id for order in orders]
                start_date = min(order.trade_date for order in orders)
                repo.update_orders_market(order_ids, Market.ETF)
                OrderDeleteService(repo, self._market_data).rebuild_account_from(account_id, start_date, order_ids)
                session.commit()
                return RepairedAccount(account_id, order_ids, start_date)
            except Exception:
                session.rollback()
                return FailedAccount(account_id, "repair failed")
