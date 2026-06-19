from decimal import Decimal

from paper_trading.storage.models import PaperAccount
from paper_trading.storage.repository import PaperTradingRepository


class AccountService:
    def __init__(self, repo: PaperTradingRepository):
        self.repo = repo

    def create_account(self, name: str, initial_cash: Decimal) -> PaperAccount:
        return self.repo.create_account(name=name, initial_cash=initial_cash)

    def get_account(self, account_id: int) -> PaperAccount | None:
        return self.repo.get_account(account_id)

    def list_accounts(self) -> list[PaperAccount]:
        return self.repo.list_accounts()

    def delete_account(self, account_id: int) -> bool:
        return self.repo.delete_account(account_id)
