from decimal import Decimal

from paper_trading.schemas.accounts import ImportPositionItem
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

    def update_account_fees(
        self,
        account_id: int,
        commission_rate: Decimal | None = None,
        min_commission: Decimal | None = None,
        stamp_duty_rate: Decimal | None = None,
        transfer_fee_rate: Decimal | None = None,
    ) -> PaperAccount | None:
        return self.repo.update_account_fees(
            account_id=account_id,
            commission_rate=commission_rate,
            min_commission=min_commission,
            stamp_duty_rate=stamp_duty_rate,
            transfer_fee_rate=transfer_fee_rate,
        )

    def delete_account(self, account_id: int) -> bool:
        return self.repo.delete_account(account_id)

    def import_positions(self, account_id: int, positions: list[ImportPositionItem]) -> None:
        if self.repo.get_account(account_id) is None:
            raise ValueError(f"paper account not found: {account_id}")
        if self.repo.get_positions(account_id) or self.repo.count_position_lots(account_id) > 0:
            raise ValueError("account already has positions")
        # Create lots first (one per item, even for duplicate symbols)
        for item in positions:
            self.repo.create_position_lot(
                account_id=account_id,
                symbol=item.symbol,
                buy_trade_date=item.buy_trade_date,
                original_quantity=item.quantity,
                remaining_quantity=item.quantity,
                cost_price=item.cost_price,
                source="imported",
            )
        # Aggregate positions per symbol (one position per symbol)
        from collections import defaultdict

        total_qty: dict[str, int] = defaultdict(int)
        total_cost: dict[str, Decimal] = defaultdict(Decimal)
        for item in positions:
            total_qty[item.symbol] += item.quantity
            total_cost[item.symbol] += item.cost_price * item.quantity
        for symbol in total_qty:
            self.repo.upsert_position(
                account_id=account_id,
                symbol=symbol,
                total_quantity=total_qty[symbol],
                frozen_quantity=0,
                cost_amount=total_cost[symbol],
                realized_pnl=Decimal("0"),
                source="imported",
            )
