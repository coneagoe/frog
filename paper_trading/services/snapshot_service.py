from datetime import date
from decimal import Decimal

from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperAccountSnapshot
from paper_trading.storage.repository import PaperTradingRepository


class SnapshotService:
    def __init__(self, repo: PaperTradingRepository, market_data: MarketDataProvider):
        self.repo = repo
        self.market_data = market_data

    def generate_snapshot(
        self, account_id: int, trade_date: date
    ) -> PaperAccountSnapshot:
        cash_available = self.repo.get_cash_available(account_id)
        cash_frozen = self.repo.get_cash_frozen(account_id)
        market_value = Decimal("0.0000")
        unrealized_pnl = Decimal("0.0000")
        positions = self.repo.get_positions(account_id)
        active_positions = [
            position for position in positions if int(position.total_quantity or 0) > 0
        ]
        for position in active_positions:
            close = self.market_data.get_daily_bar(position.symbol, trade_date).close
            position_value = (Decimal(position.total_quantity) * close).quantize(
                Decimal("0.0001")
            )
            market_value += position_value
            unrealized_pnl += position_value - Decimal(position.cost_amount or 0)
        return self.repo.save_snapshot(
            account_id=account_id,
            trade_date=trade_date,
            cash_available=cash_available,
            cash_frozen=cash_frozen,
            market_value=market_value.quantize(Decimal("0.0001")),
            total_assets=(cash_available + cash_frozen + market_value).quantize(
                Decimal("0.0001")
            ),
            realized_pnl=sum(
                (Decimal(position.realized_pnl or 0) for position in positions),
                Decimal("0"),
            ).quantize(Decimal("0.0001")),
            unrealized_pnl=unrealized_pnl.quantize(Decimal("0.0001")),
            position_count=len(active_positions),
            order_count=self.repo.count_orders(account_id, trade_date),
            trade_count=self.repo.count_trades(account_id, trade_date),
        )
