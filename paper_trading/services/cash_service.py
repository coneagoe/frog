from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import cast

from paper_trading.domain.enums import AccountStatus, CashEventType, NavReplayEventType
from paper_trading.domain.nav_replay import NavSeriesReplay
from paper_trading.domain.precision import (
    quantize_account_money,
    quantize_nav,
    quantize_shares,
    require_finite,
)
from paper_trading.services.nav_series import NavSeriesBuilder
from paper_trading.services.snapshot_recalculation_service import SnapshotRecalculationService
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperAccount, PaperCashLedger
from paper_trading.storage.repository import PaperTradingRepository


@dataclass(frozen=True)
class CashFlowResult:
    account: PaperAccount
    ledger: PaperCashLedger
    cash_available: Decimal


class CashService:
    def __init__(self, repo: PaperTradingRepository, market_data: MarketDataProvider | None = None):
        self.repo = repo
        self.market_data = market_data

    def deposit(
        self,
        account_id: int,
        amount: Decimal,
        trade_date: date,
        note: str | None = None,
        occurred_at: datetime | None = None,
    ) -> CashFlowResult:
        account = self._active_account(account_id)
        amount = self._positive_money(amount)
        occurred_at = self._occurred_at(occurred_at)
        nav = self._cash_flow_nav(account_id, occurred_at)
        share_delta = quantize_shares(amount / nav)
        ledger = self.repo.add_cash_event(
            account_id,
            CashEventType.DEPOSIT,
            amount,
            trade_date=trade_date,
            net_asset_value=nav,
            share_delta=share_delta,
            occurred_at=occurred_at,
            note=note,
        )
        self._replay_from(account, trade_date)
        return CashFlowResult(account=account, ledger=ledger, cash_available=self.repo.get_cash_available(account_id))

    def withdraw(
        self,
        account_id: int,
        amount: Decimal,
        trade_date: date,
        note: str | None = None,
        occurred_at: datetime | None = None,
    ) -> CashFlowResult:
        account = self._active_account(account_id)
        amount = self._positive_money(amount)
        cash_available = self.repo.get_cash_available_internal(account_id)
        if amount > cash_available:
            display_amount = amount.quantize(Decimal("0.0001"))
            display_cash_available = cash_available.quantize(Decimal("0.0001"))
            raise ValueError(f"withdrawal amount {display_amount} exceeds available cash {display_cash_available}")
        occurred_at = self._occurred_at(occurred_at)
        nav = self._cash_flow_nav(account_id, occurred_at)
        share_delta = -quantize_shares(amount / nav)
        next_shares = Decimal(account.share_count or 0) + share_delta
        if next_shares < 0:
            raise ValueError("withdrawal would make share count negative")
        ledger = self.repo.add_cash_event(
            account_id,
            CashEventType.WITHDRAWAL,
            -amount,
            trade_date=trade_date,
            net_asset_value=nav,
            share_delta=share_delta,
            occurred_at=occurred_at,
            note=note,
        )
        self._replay_from(account, trade_date)
        return CashFlowResult(account=account, ledger=ledger, cash_available=self.repo.get_cash_available(account_id))

    def _active_account(self, account_id: int) -> PaperAccount:
        account = self.repo.get_account(account_id)
        if account is None:
            raise KeyError(f"paper account not found: {account_id}")
        if account.status != AccountStatus.ACTIVE.value:
            raise ValueError(f"paper account is not active: {account_id}")
        return account

    @staticmethod
    def _positive_money(amount: Decimal) -> Decimal:
        amount = quantize_account_money(require_finite(Decimal(amount), "cash flow amount"))
        if amount <= 0:
            raise ValueError("cash flow amount must be positive")
        return amount

    @staticmethod
    def _occurred_at(value: datetime | None) -> datetime:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("occurred_at must include a timezone offset")
        return value or datetime.now(timezone.utc)

    def _cash_flow_nav(self, account_id: int, occurred_at: datetime) -> Decimal:
        nav = self.repo.latest_valid_nav_before(account_id, occurred_at)
        if nav is not None:
            return nav
        return quantize_nav(Decimal("1"))

    def _replay_from(self, account: PaperAccount, start_date: date) -> None:
        snapshots = self.repo.list_snapshots(account.id)
        trading_dates = [snapshot.trade_date for snapshot in snapshots if snapshot.point_type == "trading"]
        if trading_dates:
            has_holdings = any(position.total_quantity > 0 for position in self.repo.get_positions(account.id))
            if has_holdings and self.market_data is None:
                raise ValueError("cash-flow replay requires market data for existing positions")
            SnapshotRecalculationService(
                lambda: self.repo.session, cast(MarketDataProvider, self.market_data)
            ).recalculate(account.id, start_date, max(trading_dates), session=self.repo.session)

        events, baseline = NavSeriesBuilder(repo=self.repo).prepare(account.id)
        result = NavSeriesReplay().replay(
            [event for event in events if event.event_type is not NavReplayEventType.INITIAL], baseline
        )
        if not result.points:
            raise ValueError("cash-flow replay produced no NAV state")
        point = result.points[-1]
        trading_snapshots = [
            snapshot for snapshot in self.repo.list_snapshots(account.id) if snapshot.point_type == "trading"
        ]
        if trading_snapshots:
            latest = trading_snapshots[-1]
            share_count = latest.share_count
            net_asset_value = latest.net_asset_value
            cumulative_deposit = latest.cumulative_deposit
            cumulative_withdrawal = latest.cumulative_withdrawal
        else:
            share_count = point.share_count
            net_asset_value = point.nav
            cumulative_deposit = point.cumulative_deposit
            cumulative_withdrawal = point.cumulative_withdrawal
        if net_asset_value is None or share_count is None:
            raise ValueError("cash-flow replay could not prove NAV state")
        self.repo.update_account_nav_state(
            account,
            share_count=share_count,
            net_asset_value=net_asset_value,
            cumulative_deposit=cumulative_deposit,
            cumulative_withdrawal=cumulative_withdrawal,
        )
