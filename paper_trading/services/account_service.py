from collections import defaultdict
from decimal import Decimal

from paper_trading.domain.enums import Market
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
        etf_commission_rate: Decimal | None = None,
    ) -> PaperAccount:
        return self.repo.create_account(
            name=name,
            initial_cash=initial_cash,
            fee_preset=fee_preset,
            commission_rate=commission_rate,
            min_commission=min_commission,
            stamp_duty_rate=stamp_duty_rate,
            transfer_fee_rate=transfer_fee_rate,
            etf_commission_rate=etf_commission_rate,
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
        hk_commission_rate: Decimal | None = None,
        hk_min_commission: Decimal | None = None,
        hk_stamp_duty_rate: Decimal | None = None,
        hk_trading_fee_rate: Decimal | None = None,
        hk_sfc_levy_rate: Decimal | None = None,
        hk_afrc_levy_rate: Decimal | None = None,
        hk_settlement_fee_rate: Decimal | None = None,
        etf_commission_rate: Decimal | None = None,
    ) -> PaperAccount | None:
        a_share_fields = {
            "commission_rate": commission_rate,
            "min_commission": min_commission,
            "stamp_duty_rate": stamp_duty_rate,
            "transfer_fee_rate": transfer_fee_rate,
        }
        hk_fields = {
            "hk_commission_rate": hk_commission_rate,
            "hk_min_commission": hk_min_commission,
            "hk_stamp_duty_rate": hk_stamp_duty_rate,
            "hk_trading_fee_rate": hk_trading_fee_rate,
            "hk_sfc_levy_rate": hk_sfc_levy_rate,
            "hk_afrc_levy_rate": hk_afrc_levy_rate,
            "hk_settlement_fee_rate": hk_settlement_fee_rate,
        }
        etf_fields = {"etf_commission_rate": etf_commission_rate}
        has_a_share = any(v is not None for v in a_share_fields.values())
        has_hk = any(v is not None for v in hk_fields.values())
        has_etf = any(v is not None for v in etf_fields.values())

        if has_a_share:
            account = self.repo.update_account_fees(account_id=account_id, **a_share_fields)
            if account is None:
                return None
            if has_hk:
                account = self.repo.update_account_hk_fees(account_id, **hk_fields)
                if account is None:
                    return None
            if has_etf:
                return self.repo.update_account_etf_fees(account_id, **etf_fields)
            return account

        if has_hk:
            account = self.repo.update_account_hk_fees(account_id, **hk_fields)
            if account is None:
                return None
            if has_etf:
                return self.repo.update_account_etf_fees(account_id, **etf_fields)
            return account

        if has_etf:
            return self.repo.update_account_etf_fees(account_id, **etf_fields)

        # Existing A-share fee update path
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
                account_id,
                item.market,
                item.symbol,
                item.buy_trade_date,
                item.quantity,
                item.quantity,
                item.cost_price,
                source="imported",
            )
        # Aggregate positions by market-qualified symbol.
        total_qty: dict[tuple[Market, str], int] = defaultdict(int)
        total_cost: dict[tuple[Market, str], Decimal] = defaultdict(Decimal)
        for item in positions:
            key = (item.market, item.symbol)
            total_qty[key] += item.quantity
            total_cost[key] += item.cost_price * item.quantity
        for key, quantity in total_qty.items():
            market, symbol = key
            self.repo.upsert_position(
                account_id,
                market,
                symbol,
                quantity,
                0,
                total_cost[key],
                realized_pnl=Decimal("0"),
                source="imported",
            )
