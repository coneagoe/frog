import json
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable, Mapping, Protocol

from sqlalchemy.orm import Session

from paper_trading.domain.corporate_actions import (
    CorporateActionImpact,
    calculate_corporate_action_impact,
    validate_corporate_action_parameters,
)
from paper_trading.domain.enums import (
    AccountStatus,
    CashEventType,
    CorporateActionType,
    Market,
    NavReplayEventType,
    SnapshotQualityStatus,
)
from paper_trading.domain.errors import CorporateActionError
from paper_trading.domain.nav_replay import NavSeriesReplay, ReplayEvent
from paper_trading.domain.precision import quantize_account_money, quantize_shares, require_finite
from paper_trading.services.nav_series import NavSeriesBuilder
from paper_trading.services.snapshot_recalculation_service import (
    SnapshotRecalculationResult,
    SnapshotRecalculationService,
)
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperCorporateAction, PaperValuationGap
from paper_trading.storage.repository import PaperTradingRepository


class CorporateActionIdempotencyConflict(CorporateActionError):
    def __init__(self, key: str):
        super().__init__(
            "IDEMPOTENCY_KEY_CONFLICT",
            f"idempotency key already belongs to a different corporate action: {key}",
        )


class _RecalculationService(Protocol):
    def recalculate(
        self, account_id: int, start_date: date, end_date: date, session: Session | None = None
    ) -> SnapshotRecalculationResult: ...


@dataclass(frozen=True)
class CorporateActionResult:
    event: PaperCorporateAction
    impact: CorporateActionImpact
    recalculation: SnapshotRecalculationResult


class CorporateActionService:
    def __init__(
        self,
        repo: PaperTradingRepository,
        market_data: MarketDataProvider | None = None,
        recalculation_service: _RecalculationService | None = None,
        session_factory: Callable[[], Session] | None = None,
    ):
        self.repo = repo
        self.market_data = market_data
        self.recalculation_service = recalculation_service or (
            SnapshotRecalculationService(session_factory or (lambda: repo.session), market_data)
            if market_data
            else None
        )

    def apply(
        self,
        account_id: int,
        symbol: str,
        event_type: CorporateActionType,
        event_at: datetime,
        idempotency_key: str,
        parameters: Mapping[str, Decimal],
        market: Market = Market.A_SHARE,
    ) -> CorporateActionResult:
        event_at = self._utc(event_at)
        action_type = CorporateActionType(event_type)
        resolved_market = Market(market)
        if not symbol or not idempotency_key or not idempotency_key.strip():
            raise ValueError("symbol and idempotency_key are required")
        canonical_parameters = self._canonical_parameters(parameters)
        validate_corporate_action_parameters(action_type, canonical_parameters)
        persisted_parameters = {name: format(value, "f") for name, value in canonical_parameters.items()}
        account = self.repo.lock_account(account_id)
        existing = self.repo.lock_corporate_action_by_idempotency_key(account_id, idempotency_key)
        if existing is not None:
            if self._same_request(existing, symbol, resolved_market, action_type, event_at, canonical_parameters):
                impact = self._impact_from_event(existing)
                return CorporateActionResult(existing, impact, self._recalculation_from_event(existing, account_id))
            raise CorporateActionIdempotencyConflict(idempotency_key)
        if account.status != AccountStatus.ACTIVE.value:
            raise ValueError(f"paper account is not active: {account_id}")

        quantity, cost, cash, materialized = self._replay_state_before_action(
            account_id, resolved_market, symbol, event_at, action_type, canonical_parameters
        )
        impact = calculate_corporate_action_impact(action_type, quantity, cost, cash, canonical_parameters)
        if action_type is CorporateActionType.RIGHTS_ISSUE:
            impact = replace(
                impact,
                after_cost_amount=quantize_account_money(impact.before_cost_amount - impact.cash_delta),
            )

        self._update_position_projection(
            account_id,
            resolved_market,
            symbol,
            action_type,
            canonical_parameters,
            impact,
            materialized,
        )

        if impact.cash_delta:
            self.repo.add_cash_event(
                account_id,
                CashEventType.CORPORATE_ACTION,
                impact.cash_delta,
                trade_date=event_at.date(),
                occurred_at=event_at,
                note=action_type.value,
            )
        latest_date = self._latest_affected_date(account_id, event_at.date())
        event = self.repo.create_corporate_action(
            account_id=account_id,
            market=resolved_market,
            symbol=symbol,
            event_type=action_type,
            event_at=event_at,
            idempotency_key=idempotency_key,
            parameters=persisted_parameters,
            cash_delta=impact.cash_delta,
            quantity_delta=impact.quantity_delta,
            before_quantity=impact.before_quantity,
            after_quantity=impact.after_quantity,
            before_cost_amount=impact.before_cost_amount,
            after_cost_amount=impact.after_cost_amount,
            before_cash_available=impact.before_cash_available,
            after_cash_available=impact.after_cash_available,
            affected_start_date=event_at.date(),
            affected_end_date=latest_date,
            processed_at=datetime.now(timezone.utc),
        )
        self.repo.session.flush()
        recalculation = self._empty_recalculation(account_id)
        if self.recalculation_service is not None and latest_date >= event_at.date():
            recalculation = self.recalculation_service.recalculate(
                account_id, event_at.date(), latest_date, session=self.repo.session
            )
            if recalculation.failed_dates:
                raise RuntimeError(
                    "snapshot recalculation failed for "
                    + ", ".join(day.isoformat() for day in recalculation.failed_dates)
                    + (f": {'; '.join(recalculation.errors)}" if recalculation.errors else "")
                )
        event.processing_metadata = self._recalculation_metadata(recalculation)
        self.repo.session.flush()
        return CorporateActionResult(event, impact, recalculation)

    def _replay_state_before_action(
        self,
        account_id: int,
        market: Market,
        symbol: str,
        event_at: datetime,
        action_type: CorporateActionType,
        parameters: Mapping[str, Decimal],
    ) -> tuple[Decimal, Decimal, Decimal, object]:
        """Replay pre-action eligibility and materialize the post-action history."""
        events, baseline = NavSeriesBuilder(repo=self.repo).prepare(account_id)
        if any(event.quality_status.value != "valid" for event in events):
            raise ValueError("replay contains events with unknown chronology; repair historical timestamps first")
        same_time_trades = [
            event
            for event in events
            if event.event_type is NavReplayEventType.TRADE_SETTLEMENT and event.event_at == event_at
        ]
        if same_time_trades:
            raise ValueError("corporate action and trade chronology is ambiguous; repair event timestamps first")
        synthetic = ReplayEvent(
            event_at=event_at,
            trade_date=event_at.date(),
            event_type=NavReplayEventType.CORPORATE_ACTION,
            source_id="paper_corporate_actions:pending",
            source_kind="paper_corporate_actions",
            payload={
                "market": market.value,
                "symbol": symbol,
                "action_type": action_type.value,
                "parameters": parameters,
            },
            quality_status=SnapshotQualityStatus.VALID,
        )
        pending_key = NavSeriesReplay._sort_key(synthetic)
        preceding = [event for event in events if NavSeriesReplay._sort_key(event) < pending_key]
        replay = NavSeriesReplay().replay(
            [event for event in preceding if event.event_type is not NavReplayEventType.INITIAL], baseline
        )
        state = replay.points[-1] if replay.points else None
        holding_key = f"{market.value}:{symbol}"
        holdings = dict(baseline.get("holdings", {})) if state is None or state.holdings is None else state.holdings
        costs = dict(baseline.get("costs", {})) if state is None or state.costs is None else state.costs
        cash = Decimal(str(baseline.get("cash", "0"))) if state is None or state.cash is None else state.cash
        pre_state = (
            quantize_shares(holdings.get(holding_key, Decimal("0"))),
            quantize_account_money(costs.get(holding_key, Decimal("0"))),
            quantize_account_money(cash),
        )
        materialized = (
            NavSeriesReplay()
            .replay(
                [event for event in events if event.event_type is not NavReplayEventType.INITIAL] + [synthetic],
                baseline,
            )
            .points[-1]
        )
        return (*pre_state, materialized)

    def _update_position_projection(
        self,
        account_id: int,
        market: Market,
        symbol: str,
        action_type: CorporateActionType,
        parameters: Mapping[str, Decimal],
        impact: CorporateActionImpact,
        materialized: object,
    ) -> None:
        """Keep the mutable position projection aligned with the replayed action."""
        position = self.repo.lock_position(account_id, market, symbol)
        lots = self.repo.lock_lots(account_id, market, symbol)
        current_quantity = Decimal(position.total_quantity or 0) if position is not None else Decimal("0")
        current_cost = Decimal(position.cost_amount or 0) if position is not None else Decimal("0")
        self._validate_holding(position, lots, market, symbol, current_quantity, current_cost, Decimal("0"))
        if position is None:
            if impact.before_quantity:
                raise ValueError("replayed holding has no position projection")
            return
        final_holdings = getattr(materialized, "holdings", {}) or {}
        final_costs = getattr(materialized, "costs", {}) or {}
        holding_key = f"{market.value}:{symbol}"
        final_quantity = quantize_shares(final_holdings.get(holding_key, Decimal("0")))
        final_cost = quantize_account_money(final_costs.get(holding_key, Decimal("0")))
        factor = impact.after_quantity / impact.before_quantity if impact.before_quantity else Decimal("0")
        position.total_quantity = self._integer_quantity(final_quantity)
        position.frozen_quantity = self._integer_quantity(
            quantize_shares(Decimal(position.frozen_quantity or 0) * factor)
        )
        position.cost_amount = final_cost
        for lot in lots:
            old_remaining = Decimal(lot.remaining_quantity or 0)
            lot_remaining = quantize_shares(old_remaining * factor) if impact.before_quantity else Decimal("0")
            lot.original_quantity = (
                self._integer_quantity(quantize_shares(Decimal(lot.original_quantity or 0) * factor))
                if impact.before_quantity
                else 0
            )
            lot.remaining_quantity = self._integer_quantity(lot_remaining)
            if not lot_remaining or not final_quantity:
                lot.cost_price = Decimal("0")
            else:
                lot.cost_price = quantize_account_money(final_cost / final_quantity)
        if lots and final_quantity != quantize_shares(
            sum((Decimal(lot.remaining_quantity) for lot in lots), Decimal("0"))
        ):
            remaining_total = sum((Decimal(lot.remaining_quantity) for lot in lots), Decimal("0"))
            if not remaining_total:
                lots[0].remaining_quantity = self._integer_quantity(final_quantity)
            else:
                lots[-1].remaining_quantity = self._integer_quantity(
                    quantize_shares(Decimal(lots[-1].remaining_quantity) + final_quantity - remaining_total)
                )
        for lot in lots:
            if final_quantity and lot.remaining_quantity:
                lot.cost_price = quantize_account_money(final_cost / final_quantity)
        if lots:
            lot_cost = sum((Decimal(lot.remaining_quantity) * Decimal(lot.cost_price) for lot in lots), Decimal("0"))
            residual = final_cost - quantize_account_money(lot_cost)
            last = next((lot for lot in reversed(lots) if lot.remaining_quantity), None)
            if last is not None:
                last.cost_price = quantize_account_money(
                    Decimal(last.cost_price) + residual / Decimal(last.remaining_quantity)
                )

    def list(self, account_id: int, **filters: object) -> list[PaperCorporateAction]:
        return self.repo.list_corporate_actions(account_id, **filters)  # type: ignore[arg-type]

    def _latest_affected_date(self, account_id: int, start: date) -> date:
        dates = [
            row.trade_date
            for row in self.repo.list_snapshots(account_id)
            if row.point_type == "trading" and row.trade_date >= start
        ]
        gap_dates = [
            row.trade_date
            for row in self.repo.session.query(PaperValuationGap)
            .filter(PaperValuationGap.account_id == account_id)
            .all()
            if row.trade_date >= start
        ]
        return max([start, *dates, *gap_dates])

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event_at must include a timezone offset")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _canonical_parameters(parameters: Mapping[str, Decimal]) -> dict[str, Decimal]:
        result: dict[str, Decimal] = {}
        for name in sorted(parameters):
            try:
                value = require_finite(Decimal(parameters[name]), name)
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be finite") from exc
            result[name] = Decimal(format(value.normalize(), "f"))
        return result

    @staticmethod
    def _same_request(
        event: PaperCorporateAction,
        symbol: str,
        market: Market,
        event_type: CorporateActionType,
        event_at: datetime,
        parameters: dict[str, Decimal],
    ) -> bool:
        persisted_parameters = {name: format(value, "f") for name, value in parameters.items()}
        return (
            event.symbol == symbol
            and event.market == market.value
            and event.event_type == event_type.value
            and CorporateActionService._persisted_utc(event.event_at) == event_at
            and json.dumps(event.parameters, sort_keys=True) == json.dumps(persisted_parameters, sort_keys=True)
        )

    @staticmethod
    def _persisted_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _impact_from_event(event: PaperCorporateAction) -> CorporateActionImpact:
        return CorporateActionImpact(
            cash_delta=Decimal(event.cash_delta),
            quantity_delta=Decimal(event.quantity_delta),
            before_quantity=Decimal(event.before_quantity),
            after_quantity=Decimal(event.after_quantity),
            before_cost_amount=Decimal(event.before_cost_amount),
            after_cost_amount=Decimal(event.after_cost_amount),
            before_cash_available=Decimal(event.before_cash_available),
            after_cash_available=Decimal(event.after_cash_available),
            affected_start_date=event.affected_start_date,
            affected_end_date=event.affected_end_date,
        )

    @staticmethod
    def _empty_recalculation(account_id: int) -> SnapshotRecalculationResult:
        return SnapshotRecalculationResult(account_id, [], [], [], [])

    @staticmethod
    def _recalculation_metadata(result: SnapshotRecalculationResult) -> dict[str, object]:
        return {
            "updated_dates": [value.isoformat() for value in result.updated_dates],
            "unavailable_dates": [value.isoformat() for value in result.unavailable_dates],
            "failed_dates": [value.isoformat() for value in result.failed_dates],
            "errors": list(result.errors),
        }

    @classmethod
    def _recalculation_from_event(cls, event: PaperCorporateAction, account_id: int) -> SnapshotRecalculationResult:
        metadata = event.processing_metadata or {}

        def parse_dates(name: str) -> list[date]:
            return [date.fromisoformat(value) for value in metadata.get(name, [])]

        return SnapshotRecalculationResult(
            account_id,
            parse_dates("updated_dates"),
            parse_dates("unavailable_dates"),
            parse_dates("failed_dates"),
            [str(value) for value in metadata.get("errors", [])],
        )

    @staticmethod
    def _validate_holding(
        position, lots, market: Market, symbol: str, quantity: Decimal, cost: Decimal, cash: Decimal
    ) -> None:
        values = (quantity, cost, cash)
        if any(not value.is_finite() for value in values) or any(value < 0 for value in values):
            raise ValueError("account or position values are invalid")
        if position is None:
            if lots:
                raise ValueError("position lots exist without an aggregate position")
            return
        frozen = Decimal(position.frozen_quantity or 0)
        if position.symbol != symbol or position.market != market.value or not frozen.is_finite() or frozen < 0:
            raise ValueError("position identity or quantities are invalid")
        if frozen > quantity:
            raise ValueError("position frozen quantity exceeds total quantity")
        remaining = Decimal("0")
        aggregate_cost = Decimal("0")
        for lot in lots:
            original = Decimal(lot.original_quantity)
            lot_remaining = Decimal(lot.remaining_quantity)
            lot_cost = Decimal(lot.cost_price)
            if lot.symbol != symbol or lot.market != market.value:
                raise ValueError("position lot identity is invalid")
            if any(not value.is_finite() for value in (original, lot_remaining, lot_cost)):
                raise ValueError("position lot values are invalid")
            if original < 0 or lot_remaining < 0 or lot_remaining > original or lot_cost < 0:
                raise ValueError("position lot values are invalid")
            remaining += lot_remaining
            aggregate_cost += lot_remaining * lot_cost
        if remaining != quantity or quantize_account_money(aggregate_cost) != quantize_account_money(cost):
            raise ValueError("position aggregate does not match lots")

    @staticmethod
    def _integer_quantity(value: Decimal) -> int:
        if value != value.to_integral_value():
            raise ValueError("corporate action produces a fractional quantity unsupported by holdings")
        return int(value)
