from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from paper_trading.domain.enums import SnapshotPointType, SnapshotQualityStatus, SnapshotValuationQuality
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperAccountSnapshot, PaperValuationGap
from paper_trading.storage.repository import PaperTradingRepository

_NAV = Decimal("0.000001")
_MONEY = Decimal("0.0001")


def _quantize_finite(value: Decimal, quantum: Decimal) -> Decimal:
    return value.quantize(quantum) if value.is_finite() else value


def _validated_trading_nav(share_count: Decimal | None, candidate: Decimal | None) -> tuple[Decimal | None, str | None]:
    if share_count is None or not share_count.is_finite() or share_count <= 0:
        return None, "missing_share_state"
    if candidate is None:
        return None, "missing_nav"
    if not candidate.is_finite():
        return None, "non_finite_nav"
    if candidate <= 0:
        return None, "non_positive_nav"
    return candidate, None


@dataclass(frozen=True)
class SnapshotOutcome:
    status: str
    snapshot: PaperAccountSnapshot | None = None
    valuation_gap: PaperValuationGap | None = None


@dataclass(frozen=True)
class PositionValuation:
    symbol: str
    market: str | None
    requested_date: date
    price: Decimal | None
    source_date: date | None
    quality: str | None
    error: str | None


class SnapshotService:
    def __init__(self, repo: PaperTradingRepository, market_data: MarketDataProvider):
        self.repo = repo
        self.market_data = market_data

    def generate_snapshot(
        self,
        account_id: int,
        trade_date: date,
        valuations: list[PositionValuation] | None = None,
    ) -> PaperAccountSnapshot:
        cash_available = self.repo.get_cash_available(account_id)
        cash_frozen = self.repo.get_cash_frozen(account_id)
        pending_settlement = self.repo.get_pending_settlement_total(account_id)
        market_value = Decimal("0.0000")
        unrealized_pnl = Decimal("0.0000")
        positions = self.repo.get_positions(account_id)
        active_positions = [position for position in positions if int(position.total_quantity or 0) > 0]
        resolved = valuations if valuations is not None else self._resolve_valuations(active_positions, trade_date)
        prices = {(item.market, item.symbol): item.price for item in resolved}
        for position in active_positions:
            market = self._normalized_market(getattr(position, "market", None))
            close = prices[(market, position.symbol)]
            if close is None:
                raise KeyError(f"No valuation available for {position.symbol} on {trade_date.isoformat()}")
            position_value = (Decimal(position.total_quantity) * close).quantize(_MONEY)
            market_value += position_value
            unrealized_pnl += position_value - Decimal(position.cost_amount or 0)

        account = self.repo.get_account(account_id)
        if account is None:
            raise KeyError(f"paper account not found: {account_id}")
        share_count = None if account.share_count is None else _quantize_finite(Decimal(account.share_count), _NAV)
        raw_total = cash_available + cash_frozen + market_value + pending_settlement
        total_assets = _quantize_finite(raw_total, _MONEY)
        candidate = None
        if share_count is not None and share_count.is_finite() and share_count > 0:
            candidate = _quantize_finite(raw_total / share_count, _NAV)
        net_asset_value, invalid_reason = _validated_trading_nav(share_count, candidate)
        if net_asset_value is not None and share_count is not None:
            self.repo.update_account_nav_state(
                account,
                share_count=share_count,
                net_asset_value=net_asset_value,
                cumulative_deposit=Decimal(account.cumulative_deposit or 0),
                cumulative_withdrawal=Decimal(account.cumulative_withdrawal or 0),
            )
        quality_status = (
            SnapshotQualityStatus.VALID.value if invalid_reason is None else SnapshotQualityStatus.INVALID.value
        )
        stale_details = sorted(
            (self._valuation_detail(item) for item in resolved if item.quality == "stale_suspended"),
            key=self._detail_sort_key,
        )
        return self.repo.save_trading_snapshot(
            account_id=account_id,
            trade_date=trade_date,
            event_at=datetime.now(timezone.utc),
            point_type=SnapshotPointType.TRADING.value,
            quality_status=quality_status,
            invalid_reason=invalid_reason,
            valuation_quality=(
                SnapshotValuationQuality.STALE_SUSPENDED.value
                if stale_details
                else SnapshotValuationQuality.CURRENT.value
            ),
            valuation_details=stale_details or None,
            cash_available=cash_available,
            cash_frozen=cash_frozen,
            market_value=market_value.quantize(_MONEY),
            total_assets=total_assets,
            realized_pnl=Decimal(account.realized_pnl or 0).quantize(_MONEY),
            unrealized_pnl=unrealized_pnl.quantize(_MONEY),
            position_count=len(active_positions),
            order_count=self.repo.count_orders(account_id, trade_date),
            trade_count=self.repo.count_trades(account_id, trade_date),
            net_asset_value=net_asset_value,
            share_count=share_count,
            cumulative_deposit=Decimal(account.cumulative_deposit or 0).quantize(_MONEY),
            cumulative_withdrawal=Decimal(account.cumulative_withdrawal or 0).quantize(_MONEY),
            net_cash_flow=(
                Decimal(account.cumulative_deposit or 0) - Decimal(account.cumulative_withdrawal or 0)
            ).quantize(_MONEY),
            pending_settlement=pending_settlement,
        )

    def generate_snapshot_or_gap(self, account_id: int, trade_date: date) -> SnapshotOutcome:
        positions = [position for position in self.repo.get_positions(account_id) if int(position.total_quantity or 0) > 0]
        valuations = self._resolve_valuations(positions, trade_date)
        unavailable = [item for item in valuations if item.price is None]
        if unavailable:
            details = sorted((self._valuation_detail(item) for item in unavailable), key=self._detail_sort_key)
            gap = self.repo.upsert_valuation_gap(
                account_id,
                trade_date,
                [detail["symbol"] for detail in details],
                details,
            )
            delete_snapshot = getattr(self.repo, "delete_trading_snapshot", None)
            if delete_snapshot is not None:
                delete_snapshot(account_id, trade_date)
            return SnapshotOutcome(status="valuation_gap", valuation_gap=gap)

        snapshot = self.generate_snapshot(account_id, trade_date, valuations)
        existing_gap = self.repo.get_valuation_gap(account_id, trade_date)
        resolved_gap = existing_gap
        if existing_gap is not None and not existing_gap.resolved:
            resolved_gap = self.repo.upsert_valuation_gap(account_id, trade_date, [], [], resolved=True)
        return SnapshotOutcome(status="complete", snapshot=snapshot, valuation_gap=resolved_gap)

    def _resolve_valuations(self, positions: list[Any], trade_date: date) -> list[PositionValuation]:
        valuations: list[PositionValuation] = []
        for position in positions:
            market = self._normalized_market(getattr(position, "market", None))
            try:
                bar = self.market_data.get_daily_bar(position.symbol, trade_date, market=market)
            except KeyError:
                if getattr(self.market_data, "is_symbol_suspended", lambda *_args, **_kwargs: False)(
                    position.symbol, trade_date, market=market
                ):
                    dated_close = getattr(self.market_data, "get_latest_daily_close_with_date", lambda *_args, **_kwargs: None)(
                        position.symbol, trade_date, market=market
                    )
                    if dated_close is not None:
                        price, source_date = dated_close
                        valuations.append(
                            PositionValuation(
                                position.symbol, market, trade_date, price, source_date, "stale_suspended", None
                            )
                        )
                        continue
                    error = "missing_prior_close"
                else:
                    error = "missing_exact_bar"
                valuations.append(PositionValuation(position.symbol, market, trade_date, None, None, None, error))
            else:
                valuations.append(PositionValuation(position.symbol, market, trade_date, bar.close, trade_date, "current", None))
        return valuations

    @staticmethod
    def _normalized_market(market: Any) -> str | None:
        return getattr(market, "value", market)

    @staticmethod
    def _valuation_detail(valuation: PositionValuation) -> dict[str, Any]:
        return {
            "symbol": valuation.symbol,
            "market": valuation.market,
            "requested_date": valuation.requested_date.isoformat(),
            "source_date": valuation.source_date.isoformat() if valuation.source_date else None,
            "reason": valuation.error or "suspended_prior_close",
        }

    @staticmethod
    def _detail_sort_key(detail: dict[str, Any]) -> tuple[str, str, str, str]:
        return (
            detail["market"] or "",
            detail["symbol"],
            detail["requested_date"],
            detail["reason"],
        )
