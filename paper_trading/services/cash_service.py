from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from paper_trading.domain.enums import AccountStatus, CashEventType
from paper_trading.storage.models import PaperAccount, PaperCashLedger
from paper_trading.storage.repository import PaperTradingRepository

_MONEY = Decimal("0.0001")
_NAV = Decimal("0.000001")


@dataclass(frozen=True)
class CashFlowResult:
    account: PaperAccount
    ledger: PaperCashLedger
    cash_available: Decimal


class CashService:
    def __init__(self, repo: PaperTradingRepository):
        self.repo = repo

    def deposit(self, account_id: int, amount: Decimal, trade_date: date, note: str | None = None) -> CashFlowResult:
        account = self._active_account(account_id)
        amount = self._positive_money(amount)
        nav = self._current_nav(account)
        share_delta = (amount / nav).quantize(_NAV)
        ledger = self.repo.add_cash_event(
            account_id,
            CashEventType.DEPOSIT,
            amount,
            trade_date=trade_date,
            net_asset_value=nav,
            share_delta=share_delta,
            note=note,
        )
        self.repo.update_account_nav_state(
            account,
            share_count=Decimal(account.share_count or 0) + share_delta,
            net_asset_value=nav,
            cumulative_deposit=Decimal(account.cumulative_deposit or 0) + amount,
            cumulative_withdrawal=Decimal(account.cumulative_withdrawal or 0),
        )
        return CashFlowResult(account=account, ledger=ledger, cash_available=self.repo.get_cash_available(account_id))

    def withdraw(self, account_id: int, amount: Decimal, trade_date: date, note: str | None = None) -> CashFlowResult:
        account = self._active_account(account_id)
        amount = self._positive_money(amount)
        cash_available = self.repo.get_cash_available(account_id)
        if amount > cash_available:
            raise ValueError(f"withdrawal amount {amount} exceeds available cash {cash_available}")
        nav = self._current_nav(account)
        share_delta = -(amount / nav).quantize(_NAV)
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
            note=note,
        )
        self.repo.update_account_nav_state(
            account,
            share_count=next_shares,
            net_asset_value=nav,
            cumulative_deposit=Decimal(account.cumulative_deposit or 0),
            cumulative_withdrawal=Decimal(account.cumulative_withdrawal or 0) + amount,
        )
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
        amount = Decimal(amount).quantize(_MONEY)
        if amount <= 0:
            raise ValueError("cash flow amount must be positive")
        return amount

    @staticmethod
    def _current_nav(account: PaperAccount) -> Decimal:
        nav = Decimal(account.net_asset_value or 0).quantize(_NAV)
        if nav <= 0:
            raise ValueError("account NAV must be positive")
        return nav
