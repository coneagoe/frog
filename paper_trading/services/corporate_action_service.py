import json
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Protocol

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
    PaperOrderEventType,
    ReplayTimeProvenance,
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
            event_at,
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
        if any(
            event.quality_status.value != "valid" and event.event_type is not NavReplayEventType.MARKET_VALUATION
            for event in events
        ):
            raise ValueError("replay contains events with unknown chronology; repair historical timestamps first")
        initial_events = [event for event in events if event.event_type is NavReplayEventType.INITIAL]
        if not initial_events or event_at < min(event.event_at for event in initial_events):
            raise ValueError(
                "corporate action precedes the proven baseline; repair historical chronology before applying it"
            )
        if any(
            event.event_type is NavReplayEventType.CORPORATE_ACTION and event.event_at == event_at for event in events
        ):
            raise ValueError("corporate action ordering is ambiguous; repair event timestamps first")
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
        effective_at: datetime,
    ) -> None:
        """Keep the mutable position projection aligned with the replayed action."""
        position = self.repo.lock_position(account_id, market, symbol)
        lots = self.repo.lock_lots(account_id, market, symbol)
        current_quantity = Decimal(position.total_quantity or 0) if position is not None else Decimal("0")
        current_cost = Decimal(position.cost_amount or 0) if position is not None else Decimal("0")
        has_prior_action = any(
            action.market == market.value and action.symbol == symbol
            for action in self.repo.list_corporate_actions(account_id)
        )
        self._validate_holding(
            position,
            lots,
            market,
            symbol,
            current_quantity,
            current_cost,
            Decimal("0"),
            validate_projection=not has_prior_action,
        )
        if position is None:
            if impact.before_quantity:
                raise ValueError("replayed holding has no position projection")
            return
        final_holdings = getattr(materialized, "holdings", {}) or {}
        final_costs = getattr(materialized, "costs", {}) or {}
        holding_key = f"{market.value}:{symbol}"
        final_quantity = quantize_shares(final_holdings.get(holding_key, Decimal("0")))
        final_cost = quantize_account_money(final_costs.get(holding_key, Decimal("0")))
        position.total_quantity = self._integer_quantity(final_quantity)
        position.frozen_quantity = self._integer_quantity(
            self._materialized_frozen_quantity(account_id, market, symbol, effective_at, action_type, parameters)
        )
        position.cost_amount = final_cost
        materialized_lots = self._materialize_lots(
            account_id,
            market,
            symbol,
            effective_at,
            action_type,
            parameters,
        )
        if len(materialized_lots) != len(lots):
            raise ValueError("replay lot count does not match position projection")
        for lot, materialized_lot in zip(
            sorted(lots, key=lambda item: (item.buy_trade_date, item.id)), materialized_lots
        ):
            lot.remaining_quantity = self._integer_quantity(materialized_lot["remaining"])
            lot.projected_cost_price = quantize_account_money(materialized_lot["projected_cost_price"])

    def _materialize_lots(
        self,
        account_id: int,
        market: Market,
        symbol: str,
        effective_at: datetime,
        action_type: CorporateActionType,
        parameters: Mapping[str, Decimal],
    ) -> list[dict[str, Any]]:
        persisted_lots = self.repo.lock_lots(account_id, market, symbol)
        simulated: list[dict[str, Any]] = [
            {
                "original": Decimal(lot.original_quantity),
                "remaining": Decimal(lot.original_quantity),
                "cost_price": Decimal(lot.cost_price),
                "projected_cost_price": Decimal(lot.cost_price),
                "buy_trade_date": lot.buy_trade_date,
                "buy_trade_at": datetime.combine(lot.buy_trade_date, datetime.min.time(), tzinfo=timezone.utc),
            }
            for lot in persisted_lots
            if lot.source == "imported"
        ]
        events: list[tuple[datetime, int, str, Any]] = []
        for trade in self.repo.list_trades(account_id):
            if trade.market == market.value and trade.symbol == symbol:
                events.append((self._persisted_utc(trade.trade_time), trade.id, "trade", trade))
        for action in self.repo.list_corporate_actions(account_id):
            if action.market == market.value and action.symbol == symbol:
                events.append((self._persisted_utc(action.event_at), action.id, "action", action))
        events.append(
            (
                effective_at,
                0,
                "pending_action",
                (action_type, parameters),
            )
        )
        for event_at, source_id, kind, payload in sorted(events, key=lambda item: (item[0], item[1], item[2])):
            if kind == "trade":
                trade = payload
                if trade.side == "buy":
                    simulated.append(
                        {
                            "original": Decimal(trade.quantity),
                            "remaining": Decimal(trade.quantity),
                            "cost_price": quantize_account_money(
                                (Decimal(trade.amount) + Decimal(trade.fees)) / Decimal(trade.quantity)
                            ),
                            "projected_cost_price": quantize_account_money(
                                (Decimal(trade.amount) + Decimal(trade.fees)) / Decimal(trade.quantity)
                            ),
                            "buy_trade_date": trade.trade_date,
                            "buy_trade_at": self._persisted_utc(trade.trade_time),
                        }
                    )
                else:
                    self._consume_lot_inventory(simulated, Decimal(trade.quantity))
                continue
            if kind == "action":
                action = payload
                current_type = CorporateActionType(action.event_type)
                current_parameters = action.parameters
            else:
                current_type, current_parameters = payload
            action_factor = self._action_quantity_factor(current_type, current_parameters)
            for item in simulated:
                if item["buy_trade_at"] > event_at:
                    continue
                before_remaining = Decimal(item["remaining"])
                item["remaining"] = quantize_shares(item["remaining"] * action_factor)
                if not item["remaining"]:
                    continue
                if current_type is CorporateActionType.RIGHTS_ISSUE:
                    added_cost = (
                        before_remaining
                        * Decimal(current_parameters["subscription_ratio"])
                        * Decimal(current_parameters["subscription_price"])
                    )
                    item["projected_cost_price"] = quantize_account_money(
                        (before_remaining * Decimal(item["projected_cost_price"]) + added_cost) / item["remaining"]
                    )
                elif action_factor:
                    item["projected_cost_price"] = quantize_account_money(
                        Decimal(item["projected_cost_price"]) / action_factor
                    )
        return simulated

    @staticmethod
    def _action_quantity_factor(action_type: CorporateActionType, parameters: Mapping[str, Decimal]) -> Decimal:
        if action_type in {CorporateActionType.SPLIT, CorporateActionType.REVERSE_SPLIT}:
            return Decimal(parameters["ratio"])
        if action_type is CorporateActionType.BONUS_SHARE:
            return Decimal("1") + Decimal(parameters["bonus_ratio"])
        if action_type is CorporateActionType.RIGHTS_ISSUE:
            return Decimal("1") + Decimal(parameters["subscription_ratio"])
        return Decimal("1")

    def _materialized_frozen_quantity(
        self,
        account_id: int,
        market: Market,
        symbol: str,
        effective_at: datetime,
        pending_type: CorporateActionType,
        pending_parameters: Mapping[str, Decimal],
    ) -> Decimal:
        """Rebuild frozen sell quantity from order and action chronology."""
        actions: list[tuple[datetime, CorporateActionType, Mapping[str, Decimal]]] = [
            (self._persisted_utc(action.event_at), CorporateActionType(action.event_type), action.parameters)
            for action in self.repo.list_corporate_actions(account_id)
            if action.market == market.value and action.symbol == symbol
        ]
        actions.append((effective_at, pending_type, pending_parameters))
        frozen = Decimal("0")
        for order in self.repo.list_orders(account_id):
            if (
                order.market != market.value
                or order.symbol != symbol
                or order.side != "sell"
                or order.status not in {"accepted", "partially_filled"}
            ):
                continue
            order_events = self.repo.list_effective_order_events(account_id, order.id)
            if not order_events or any(
                event.event_time_provenance != ReplayTimeProvenance.CANONICAL_UTC.value for event in order_events
            ):
                raise ValueError("reservation chronology is unproven; repair historical order facts first")
            reservation_events = [
                event for event in order_events if event.event_type == PaperOrderEventType.RESERVED.value
            ]
            if not reservation_events:
                raise ValueError("reservation chronology is unproven; repair historical order facts first")
            order_frozen = sum((Decimal(event.quantity_delta) for event in order_events), Decimal("0"))
            if not order_frozen:
                continue
            factor = Decimal("1")
            order_at = min(self._persisted_utc(event.event_at) for event in reservation_events)
            for action_at, action_type, parameters in sorted(actions, key=lambda item: item[0]):
                if action_at < order_at:
                    continue
                factor *= self._action_quantity_factor(action_type, parameters)
            frozen += quantize_shares(order_frozen * factor)
        return quantize_shares(frozen)

    @staticmethod
    def _consume_lot_inventory(lots: list[dict[str, Any]], quantity: Decimal) -> None:
        for lot in sorted(lots, key=lambda item: item["buy_trade_date"]):
            consumed = min(lot["remaining"], quantity)
            lot["remaining"] -= consumed
            quantity -= consumed
            if not quantity:
                return
        if quantity:
            raise ValueError("sell quantity exceeds replay lots")

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
        position,
        lots,
        market: Market,
        symbol: str,
        quantity: Decimal,
        cost: Decimal,
        cash: Decimal,
        *,
        validate_projection: bool,
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
            if original < 0 or lot_remaining < 0 or lot_cost < 0:
                raise ValueError("position lot values are invalid")
            # Remaining quantity is a mutable projection and may exceed the
            # acquisition quantity after a split or bonus-share action.
            remaining += lot_remaining
            aggregate_cost += lot_remaining * lot_cost
        if validate_projection and (
            remaining != quantity or quantize_account_money(aggregate_cost) != quantize_account_money(cost)
        ):
            raise ValueError("position aggregate does not match lots")

    @staticmethod
    def _integer_quantity(value: Decimal) -> int:
        if value != value.to_integral_value():
            raise ValueError("corporate action produces a fractional quantity unsupported by holdings")
        return int(value)
