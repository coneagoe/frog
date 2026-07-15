from decimal import Decimal

from paper_trading.storage.models import PaperAccount
from paper_trading.storage.repository import PaperTradingRepository


class AccountService:
    def __init__(self, repo: PaperTradingRepository):
        self.repo = repo

    def create_account(
        self,
        name: str,
        initial_cash: Decimal,
        fee_preset: str | None = None,
        commission_rate: Decimal | None = None,
        min_commission: Decimal | None = None,
        stamp_duty_rate: Decimal | None = None,
        transfer_fee_rate: Decimal | None = None,
    ) -> PaperAccount:
        return self.repo.create_account(
            name=name,
            initial_cash=initial_cash,
            fee_preset=fee_preset,
            commission_rate=commission_rate,
            min_commission=min_commission,
            stamp_duty_rate=stamp_duty_rate,
            transfer_fee_rate=transfer_fee_rate,
        )

    def get_account(self, account_id: int) -> PaperAccount | None:
        return self.repo.get_account(account_id)

    def list_accounts(self) -> list[PaperAccount]:
        return self.repo.list_accounts()

    def delete_account(self, account_id: int) -> bool:
        return self.repo.delete_account(account_id)
