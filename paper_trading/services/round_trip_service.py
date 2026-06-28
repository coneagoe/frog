from decimal import Decimal

from paper_trading.domain.enums import OrderSide
from paper_trading.storage.models import PaperTrade
from paper_trading.storage.repository import PaperTradingRepository


class RoundTripService:
    def __init__(self, repo: PaperTradingRepository):
        self.repo = repo

    def record_fill(self, trade: PaperTrade, post_position_quantity: int) -> None:
        side = OrderSide(str(trade.side))
        if side == OrderSide.BUY:
            self._record_buy(trade)
            return
        self._record_sell(trade, post_position_quantity)

    def _record_buy(self, trade: PaperTrade) -> None:
        cycle = self.repo.get_open_round_trip(trade.account_id, trade.symbol)
        if cycle is None:
            self.repo.create_round_trip(
                account_id=trade.account_id,
                symbol=trade.symbol,
                open_trade_id=trade.id,
                open_trade_date=trade.trade_date,
                entry_amount=Decimal(trade.amount).quantize(Decimal("0.0001")),
                fees=Decimal(trade.fees).quantize(Decimal("0.0001")),
            )
            return
        self.repo.update_round_trip(
            cycle,
            entry_amount=(Decimal(cycle.entry_amount or 0) + Decimal(trade.amount)).quantize(Decimal("0.0001")),
            fees=(Decimal(cycle.fees or 0) + Decimal(trade.fees)).quantize(Decimal("0.0001")),
        )

    def _record_sell(self, trade: PaperTrade, post_position_quantity: int) -> None:
        cycle = self.repo.get_open_round_trip(trade.account_id, trade.symbol)
        if cycle is None:
            return
        exit_amount = (Decimal(cycle.exit_amount or 0) + Decimal(trade.amount)).quantize(Decimal("0.0001"))
        fees = (Decimal(cycle.fees or 0) + Decimal(trade.fees)).quantize(Decimal("0.0001"))
        realized_pnl = (exit_amount - Decimal(cycle.entry_amount or 0) - fees).quantize(Decimal("0.0001"))
        values = {
            "close_trade_id": trade.id,
            "close_trade_date": trade.trade_date,
            "exit_amount": exit_amount,
            "fees": fees,
            "realized_pnl": realized_pnl,
        }
        if post_position_quantity == 0:
            entry_amount = Decimal(cycle.entry_amount or 0)
            values["return_pct"] = (realized_pnl / entry_amount).quantize(Decimal("0.000001")) if entry_amount else None
            values["holding_days"] = (trade.trade_date - cycle.open_trade_date).days
            values["status"] = "closed"
        self.repo.update_round_trip(cycle, **values)
