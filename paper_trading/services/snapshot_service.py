from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, cast

from paper_trading.domain.enums import SnapshotPointType, SnapshotQualityStatus, SnapshotValuationQuality
from paper_trading.domain.precision import quantize_account_money, quantize_nav, quantize_shares
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperAccountSnapshot, PaperValuationGap
from paper_trading.storage.repository import PaperTradingRepository


def _quantize_account_money_if_finite(value: Decimal) -> Decimal:
    return quantize_account_money(value) if value.is_finite() else value


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
        *,
        preserve_account_nav: bool = False,
        event_at: datetime | None = None,
    ) -> PaperAccountSnapshot:
        cash_available = self.repo.get_cash_available_internal(account_id)
        cash_frozen = self.repo.get_cash_frozen_internal(account_id)
        pending_settlement = self.repo.get_pending_settlement_total_internal(account_id)
        market_value = Decimal("0")
        unrealized_pnl = Decimal("0")
        positions = self.repo.get_positions(account_id)
        active_positions = [position for position in positions if int(position.total_quantity or 0) > 0]
        resolved = valuations if valuations is not None else self._resolve_valuations(active_positions, trade_date)
        prices = {(item.market, item.symbol): item.price for item in resolved}
        for position in active_positions:
            market = self._normalized_market(getattr(position, "market", None))
            close = prices[(market, position.symbol)]
            if close is None:
                raise KeyError(f"No valuation available for {position.symbol} on {trade_date.isoformat()}")
            position_value = Decimal(position.total_quantity) * close
            market_value += position_value
            unrealized_pnl += position_value - Decimal(position.cost_amount or 0)

        account = self.repo.get_account(account_id)
        if account is None:
            raise KeyError(f"paper account not found: {account_id}")
        raw_share_count = None if account.share_count is None else Decimal(account.share_count)
        share_count = (
            None if raw_share_count is None or not raw_share_count.is_finite() else quantize_shares(raw_share_count)
        )
        raw_total = cash_available + cash_frozen + market_value + pending_settlement
        total_assets = _quantize_account_money_if_finite(raw_total)
        candidate = None
        if share_count is not None and share_count.is_finite() and share_count > 0:
            raw_candidate = raw_total / share_count
            candidate = quantize_nav(raw_candidate) if raw_candidate.is_finite() else raw_candidate
        net_asset_value, invalid_reason = _validated_trading_nav(share_count, candidate)
        if net_asset_value is not None and share_count is not None and not preserve_account_nav:
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
            event_at=event_at or datetime.now(timezone.utc),
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
            market_value=_quantize_account_money_if_finite(market_value),
            total_assets=total_assets,
            realized_pnl=_quantize_account_money_if_finite(Decimal(account.realized_pnl or 0)),
            unrealized_pnl=_quantize_account_money_if_finite(unrealized_pnl),
            position_count=len(active_positions),
            order_count=self.repo.count_orders(account_id, trade_date),
            trade_count=self.repo.count_trades(account_id, trade_date),
            net_asset_value=net_asset_value,
            share_count=share_count,
            cumulative_deposit=_quantize_account_money_if_finite(Decimal(account.cumulative_deposit or 0)),
            cumulative_withdrawal=_quantize_account_money_if_finite(Decimal(account.cumulative_withdrawal or 0)),
            net_cash_flow=_quantize_account_money_if_finite(
                Decimal(account.cumulative_deposit or 0) - Decimal(account.cumulative_withdrawal or 0)
            ),
            pending_settlement=pending_settlement,
        )

    def generate_snapshot_or_gap(
        self, account_id: int, trade_date: date, *, preserve_account_nav: bool = False
    ) -> SnapshotOutcome:
        positions = [
            position for position in self.repo.get_positions(account_id) if int(position.total_quantity or 0) > 0
        ]
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

        historical_event_at = None
        if preserve_account_nav:
            historical_event_at = next(
                (
                    snapshot.event_at
                    for snapshot in self.repo.list_snapshots(account_id)
                    if snapshot.trade_date == trade_date and snapshot.point_type == SnapshotPointType.TRADING.value
                ),
                None,
            )
        snapshot = self.generate_snapshot(
            account_id,
            trade_date,
            valuations,
            preserve_account_nav=preserve_account_nav,
            event_at=historical_event_at,
        )
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
                try:
                    suspended = (
                        getattr(self.market_data, "is_symbol_suspended", lambda *_args, **_kwargs: False)(
                            position.symbol, trade_date, market=market
                        )
                        is True
                    )
                    if suspended:
                        dated_close = getattr(
                            self.market_data, "get_latest_daily_close_with_date", lambda *_args, **_kwargs: None
                        )(position.symbol, trade_date, market=market)
                        if dated_close is not None:
                            price, source_date = dated_close
                            normalized_price = self._normalize_close(price)
                            if normalized_price is None:
                                raise ValueError("invalid close")
                            if not self._valid_source_date(source_date, trade_date):
                                valuations.append(
                                    PositionValuation(
                                        position.symbol,
                                        market,
                                        trade_date,
                                        None,
                                        None,
                                        None,
                                        "invalid_source_date",
                                    )
                                )
                                continue
                            valuations.append(
                                PositionValuation(
                                    position.symbol,
                                    market,
                                    trade_date,
                                    normalized_price,
                                    source_date,
                                    "stale_suspended",
                                    None,
                                )
                            )
                            continue
                        error = "missing_prior_close"
                    else:
                        error = "missing_exact_bar"
                except Exception:
                    error = "market_data_error"
                valuations.append(PositionValuation(position.symbol, market, trade_date, None, None, None, error))
            except Exception:
                valuations.append(
                    PositionValuation(position.symbol, market, trade_date, None, None, None, "market_data_error")
                )
            else:
                normalized_close = self._normalize_close(getattr(bar, "close", None))
                if normalized_close is not None:
                    valuations.append(
                        PositionValuation(
                            position.symbol, market, trade_date, normalized_close, trade_date, "current", None
                        )
                    )
                else:
                    valuations.append(
                        PositionValuation(position.symbol, market, trade_date, None, None, None, "invalid_close")
                    )
        return valuations

    @staticmethod
    def _normalize_close(value: Any) -> Decimal | None:
        try:
            close = Decimal(str(value))
        except (ArithmeticError, TypeError, ValueError):
            return None
        if not close.is_finite() or close <= 0:
            return None
        return close

    @staticmethod
    def _valid_source_date(value: Any, requested_date: date) -> bool:
        return isinstance(value, date) and not isinstance(value, datetime) and value <= requested_date

    @staticmethod
    def _normalized_market(market: Any) -> str | None:
        return cast(str | None, getattr(market, "value", market))

    @staticmethod
    def _valuation_detail(valuation: PositionValuation) -> dict[str, Any]:
        reason = valuation.error or "suspended_prior_close"
        return {
            "symbol": valuation.symbol,
            "market": valuation.market,
            "requested_date": valuation.requested_date.isoformat(),
            "source_date": valuation.source_date.isoformat() if valuation.source_date else None,
            "reason": reason,
        }

    @staticmethod
    def _detail_sort_key(detail: dict[str, Any]) -> tuple[str, str, str, str]:
        return (
            detail["market"] or "",
            detail["symbol"],
            detail["requested_date"],
            detail["reason"],
        )
