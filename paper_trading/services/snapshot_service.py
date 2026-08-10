from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperAccountSnapshot, PaperValuationGap
from paper_trading.storage.repository import PaperTradingRepository


@dataclass(frozen=True)
class SnapshotOutcome:
    status: str
    snapshot: PaperAccountSnapshot | None = None
    valuation_gap: PaperValuationGap | None = None


class SnapshotService:
    def __init__(self, repo: PaperTradingRepository, market_data: MarketDataProvider):
        self.repo = repo
        self.market_data = market_data

    def generate_snapshot(self, account_id: int, trade_date: date) -> PaperAccountSnapshot:
        cash_available = self.repo.get_cash_available(account_id)
        cash_frozen = self.repo.get_cash_frozen(account_id)
        pending_settlement = self.repo.get_pending_settlement_total(account_id)
        market_value = Decimal("0.0000")
        unrealized_pnl = Decimal("0.0000")
        positions = self.repo.get_positions(account_id)
        active_positions = [position for position in positions if int(position.total_quantity or 0) > 0]
        for position in active_positions:
            position_market = getattr(position, "market", None)
            close = self.market_data.get_daily_bar(position.symbol, trade_date, market=position_market).close
            position_value = (Decimal(position.total_quantity) * close).quantize(Decimal("0.0001"))
            market_value += position_value
            unrealized_pnl += position_value - Decimal(position.cost_amount or 0)

        account = self.repo.get_account(account_id)
        if account is None:
            raise KeyError(f"paper account not found: {account_id}")
        share_count = Decimal(account.share_count or 0).quantize(Decimal("0.000001"))
        total_assets = (cash_available + cash_frozen + market_value + pending_settlement).quantize(Decimal("0.0001"))
        net_asset_value = None
        if share_count > 0:
            net_asset_value = (total_assets / share_count).quantize(Decimal("0.000001"))
            self.repo.update_account_nav_state(
                account,
                share_count=share_count,
                net_asset_value=net_asset_value,
                cumulative_deposit=Decimal(account.cumulative_deposit or 0),
                cumulative_withdrawal=Decimal(account.cumulative_withdrawal or 0),
            )
        return self.repo.save_snapshot(
            account_id=account_id,
            trade_date=trade_date,
            cash_available=cash_available,
            cash_frozen=cash_frozen,
            market_value=market_value.quantize(Decimal("0.0001")),
            total_assets=total_assets,
            realized_pnl=Decimal(account.realized_pnl or 0).quantize(Decimal("0.0001")),
            unrealized_pnl=unrealized_pnl.quantize(Decimal("0.0001")),
            position_count=len(active_positions),
            order_count=self.repo.count_orders(account_id, trade_date),
            trade_count=self.repo.count_trades(account_id, trade_date),
            net_asset_value=net_asset_value,
            share_count=share_count,
            cumulative_deposit=Decimal(account.cumulative_deposit or 0).quantize(Decimal("0.0001")),
            cumulative_withdrawal=Decimal(account.cumulative_withdrawal or 0).quantize(Decimal("0.0001")),
            net_cash_flow=(
                Decimal(account.cumulative_deposit or 0) - Decimal(account.cumulative_withdrawal or 0)
            ).quantize(Decimal("0.0001")),
            pending_settlement=pending_settlement,
        )

    def generate_snapshot_or_gap(self, account_id: int, trade_date: date) -> SnapshotOutcome:
        missing_symbols: list[str] = []
        details: list[dict[str, Any]] = []
        for position in self.repo.get_positions(account_id):
            if int(position.total_quantity or 0) <= 0:
                continue
            position_market = getattr(position, "market", None)
            market = getattr(position_market, "value", position_market)
            try:
                self.market_data.get_daily_bar(position.symbol, trade_date, market=market)
            except KeyError as exc:
                missing_symbols.append(position.symbol)
                details.append({"symbol": position.symbol, "market": market, "error": str(exc)})
        if missing_symbols:
            gap = self.repo.upsert_valuation_gap(
                account_id,
                trade_date,
                sorted(missing_symbols),
                sorted(details, key=lambda detail: (detail["market"] or "", detail["symbol"])),
            )
            return SnapshotOutcome(status="valuation_gap", valuation_gap=gap)

        snapshot = self.generate_snapshot(account_id, trade_date)
        existing_gap = self.repo.get_valuation_gap(account_id, trade_date)
        resolved_gap = existing_gap
        if existing_gap is not None and not existing_gap.resolved:
            resolved_gap = self.repo.upsert_valuation_gap(account_id, trade_date, [], [], resolved=True)
        return SnapshotOutcome(status="complete", snapshot=snapshot, valuation_gap=resolved_gap)
