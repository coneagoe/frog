from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.exc import SQLAlchemyError

from paper_trading.domain.enums import (
    CashEventType,
    MatchingRunStatus,
    OrderSide,
    OrderStatus,
    PaperOrderEventType,
)
from paper_trading.domain.fees import (
    calculate_a_share_fees,
    calculate_etf_fees,
    etf_fee_config_from_account,
    fee_config_from_account,
)
from paper_trading.domain.hk_connect_fees import (
    calculate_hk_connect_fees,
    hk_fee_config_from_account,
)
from paper_trading.domain.precision import quantize_account_money
from paper_trading.domain.rules import ensure_price_in_daily_range
from paper_trading.services.round_trip_service import RoundTripService
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperOrder
from paper_trading.storage.repository import PaperTradingRepository


class MatchingService:
    def __init__(
        self,
        repo: PaperTradingRepository,
        market_data: MarketDataProvider,
        snapshot_service: SnapshotService,
    ):
        self.repo = repo
        self.market_data = market_data
        self.snapshot_service = snapshot_service
        self.round_trip_service = RoundTripService(repo)

    def run(self, trade_date: date, account_id: int | None = None):
        if account_id is not None:
            self.repo.lock_account(account_id)
        run, owner = self.repo.acquire_matching_run(trade_date, account_id)
        if not owner:
            return run
        processed = filled = skipped = rejected = failed = warning_count = 0
        order_errors: list[str] = []
        for order in self.repo.get_orders_for_matching_locked(trade_date, account_id):
            processed += 1
            try:
                try:
                    bar = self.market_data.get_daily_bar(order.symbol, trade_date, market=order.market)
                except (KeyError, ValueError) as exc:
                    warning_count += 1
                    self._record_missing_exact_date_diagnostic(order, exc)
                    continue
                if bar.suspended:
                    self._reject_order(order, "SUSPENDED_SYMBOL", "Symbol is suspended")
                    rejected += 1
                    continue
                self._resolve_matching_diagnostic(order)
                try:
                    ensure_price_in_daily_range(Decimal(order.limit_price), bar.low, bar.high)
                except Exception:
                    skipped += 1
                    continue
                self._fill_order(order)
                self._resolve_matching_diagnostic(order)
                filled += 1
            except SQLAlchemyError:
                raise
            except Exception as exc:
                failed += 1
                order_errors.append(f"order={order.id}, account={order.account_id}, trade_date={trade_date}: {exc}")
        snapshot_errors: list[str] = []
        snapshot_accounts = self.repo.get_accounts_for_snapshot(trade_date, account_id)
        for current_account_id in sorted(set(snapshot_accounts)):
            try:
                outcome = self.snapshot_service.generate_snapshot_or_gap(current_account_id, trade_date)
                if outcome.status == "valuation_gap":
                    warning_count += 1
            except (KeyError, ValueError) as exc:
                snapshot_errors.append(f"account={current_account_id}, trade_date={trade_date}: {exc}")
        error_messages = [*order_errors, *snapshot_errors]
        status = (
            MatchingRunStatus.FAILED.value
            if error_messages
            else MatchingRunStatus.COMPLETED_WITH_WARNINGS.value
            if warning_count
            else MatchingRunStatus.COMPLETED.value
        )
        return self.repo.update_matching_run_counts(
            run,
            processed,
            filled,
            skipped,
            rejected,
            failed,
            status,
            warning_count=warning_count,
            error_details="; ".join(error_messages) if error_messages else None,
        )

    def match_order(self, order: PaperOrder) -> str:
        """Match a single accepted order.

        Returns one of ``'filled'``, ``'skipped'``, ``'rejected'``, ``'warning'``,
        or ``'failed'``.  Does NOT create a matching run record or generate a
        snapshot — callers handle those.

        Semantics follow :meth:`run`:
        * ``'filled'``  — order was filled, status updated to FILLED.
        * ``'rejected'`` — symbol suspended (calls _reject_order).
        * ``'skipped'``  — price out of range; order stays ACCEPTED.
        * ``'warning'`` — exact-date market data is missing; a durable
          diagnostic is recorded and the order stays ACCEPTED.
        * ``'failed'``   — non-missing market-data error or fill error; order
          stays ACCEPTED with no side effects (matching *failed* outcome).
        """
        try:
            bar = self.market_data.get_daily_bar(order.symbol, order.trade_date, market=order.market)
        except (KeyError, ValueError) as exc:
            self._record_missing_exact_date_diagnostic(order, exc)
            return "warning"
        except SQLAlchemyError:
            raise
        except Exception:
            return "failed"  # matches run() outer except → failed counter
        if bar.suspended:
            self._reject_order(order, "SUSPENDED_SYMBOL", "Symbol is suspended")
            return "rejected"
        self._resolve_matching_diagnostic(order)
        try:
            ensure_price_in_daily_range(Decimal(order.limit_price), bar.low, bar.high)
        except SQLAlchemyError:
            raise
        except Exception:
            return "skipped"  # stays ACCEPTED
        try:
            self._fill_order(order)
            self._resolve_matching_diagnostic(order)
            return "filled"
        except SQLAlchemyError:
            raise
        except Exception:
            return "failed"  # stays ACCEPTED (run() outer except → failed)

    def _reject_order(self, order: PaperOrder, code: str, reason: str) -> None:
        now = datetime.now(timezone.utc)
        lifecycle = self.repo.list_effective_order_events(order.account_id, order.id)
        lifecycle_id = lifecycle[0].id if lifecycle else order.id
        outstanding_quantity = max(
            sum((Decimal(event.quantity_delta) for event in lifecycle), Decimal("0")), Decimal("0")
        )
        outstanding_cash = max(-sum((Decimal(event.cash_delta) for event in lifecycle), Decimal("0")), Decimal("0"))
        if outstanding_cash > 0:
            self.repo.add_cash_event(
                order.account_id,
                CashEventType.RELEASE,
                outstanding_cash,
                order_id=order.id,
                trade_date=order.trade_date,
                note="reject_order_release",
            )
        if outstanding_quantity > 0:
            position = self.repo.get_position(order.account_id, order.market, order.symbol)
            if position is not None:
                position.frozen_quantity = max(0, int(position.frozen_quantity or 0) - int(outstanding_quantity))
        self.repo.append_order_event(
            order.account_id,
            order.id,
            order.market,
            order.symbol,
            PaperOrderEventType.REJECT,
            now,
            quantity_delta=Decimal("0"),
            cash_delta=Decimal("0"),
            idempotency_key=f"order:{order.id}:lifecycle:{lifecycle_id}:reject:{code}",
        )
        self.repo.append_order_event(
            order.account_id,
            order.id,
            order.market,
            order.symbol,
            PaperOrderEventType.RELEASE,
            now,
            quantity_delta=-outstanding_quantity,
            cash_delta=outstanding_cash,
            idempotency_key=f"order:{order.id}:lifecycle:{lifecycle_id}:release:reject",
        )
        self.repo.update_order_status(order, OrderStatus.REJECTED, code, reason)

    def _record_missing_exact_date_diagnostic(self, order: PaperOrder, error: Exception) -> None:
        adjust = self._diagnostic_adjust(order.market)
        self.repo.upsert_daily_bar_diagnostic(
            order.trade_date,
            order.market,
            order.symbol,
            adjust,
            "missing_exact_date",
            [{"provider": "market_data", "status": "empty", "detail": str(error)}],
            False,
        )

    def _resolve_matching_diagnostic(self, order: PaperOrder) -> None:
        adjust = self._diagnostic_adjust(order.market)
        if order.market in {"a_share", "etf"} and self.repo.has_unresolved_daily_bar_diagnostic(
            order.trade_date, order.market, order.symbol, adjust
        ):
            self.repo.upsert_daily_bar_diagnostic(
                order.trade_date,
                order.market,
                order.symbol,
                adjust,
                "resolved",
                [{"provider": "market_data", "status": "downloaded"}],
                True,
            )

    @staticmethod
    def _diagnostic_adjust(market: str) -> str:
        return "raw" if market == "etf" else "bfq"

    def _next_trade_date(self, trade_date: date, n: int) -> date:
        """Return the n-th future trade date after trade_date via market_data."""
        current = trade_date
        for _ in range(n):
            current = self.market_data.next_trade_date(current)
        return current

    def _fill_order(self, order: PaperOrder) -> None:
        side = OrderSide(order.side)
        price = Decimal(order.limit_price)
        quantity = int(order.quantity)
        account = self.repo.get_account(order.account_id)
        if account is None:
            raise ValueError(f"paper account not found: {order.account_id}")
        amount = quantize_account_money(Decimal(quantity) * price)

        # Market-aware fee calculation
        if order.market == "hk_connect":
            fee_config = hk_fee_config_from_account(account)
            fees = quantize_account_money(calculate_hk_connect_fees(side, amount, fee_config).total)
        elif order.market == "etf":
            fees = quantize_account_money(calculate_etf_fees(side, amount, etf_fee_config_from_account(account)).total)
        else:
            fees = quantize_account_money(calculate_a_share_fees(side, amount, fee_config_from_account(account)).total)

        trade = self.repo.create_trade(
            order.id,
            order.account_id,
            order.symbol,
            side,
            quantity,
            price,
            amount,
            fees,
            order.trade_date,
            comment=order.comment,
            market=order.market,
        )
        actual_cost = amount + fees
        lifecycle = self.repo.list_effective_order_events(order.account_id, order.id)
        outstanding_cash = max(-sum((Decimal(event.cash_delta) for event in lifecycle), Decimal("0")), Decimal("0"))
        release_cash = outstanding_cash - actual_cost
        lifecycle_id = self.repo.effective_order_lifecycle_id(order.account_id, order.id) or order.id
        self.repo.append_order_event(
            order.account_id,
            order.id,
            order.market,
            order.symbol,
            PaperOrderEventType.FILL,
            trade.trade_time if trade.trade_time.tzinfo else trade.trade_time.replace(tzinfo=timezone.utc),
            quantity_delta=-Decimal(quantity) if side == OrderSide.SELL else Decimal("0"),
            cash_delta=actual_cost if side == OrderSide.BUY else Decimal("0"),
            idempotency_key=f"order:{order.id}:lifecycle:{lifecycle_id}:fill:{trade.id}",
            trade_id=trade.id,
        )
        self.repo.append_order_event(
            order.account_id,
            order.id,
            order.market,
            order.symbol,
            PaperOrderEventType.RELEASE,
            trade.trade_time if trade.trade_time.tzinfo else trade.trade_time.replace(tzinfo=timezone.utc),
            quantity_delta=Decimal("0"),
            cash_delta=release_cash,
            idempotency_key=f"order:{order.id}:lifecycle:{lifecycle_id}:release:fill:{trade.id}",
            trade_id=trade.id,
        )
        if side == OrderSide.BUY:
            self._settle_buy(order, trade.id, amount, fees, release_cash)
            position = self.repo.get_position(order.account_id, order.market, order.symbol)
            self.round_trip_service.record_fill(
                trade,
                post_position_quantity=0 if position is None else int(position.total_quantity or 0),
            )
        else:
            self._settle_sell(order, trade.id, amount, fees)
            # HK sells create pending settlement (T+2) instead of immediate cash credit
            if order.market == "hk_connect":
                settle_date = self._next_trade_date(order.trade_date, 2)
                self.repo.create_pending_settlement(
                    account_id=order.account_id,
                    amount=amount - fees,
                    expected_settle_date=settle_date,
                    trade_id=trade.id,
                    source="hk_sell",
                )
            position = self.repo.get_position(order.account_id, order.market, order.symbol)
            self.round_trip_service.record_fill(
                trade,
                post_position_quantity=0 if position is None else int(position.total_quantity or 0),
            )
            if (
                position is not None
                and int(position.total_quantity or 0) <= 0
                and int(position.frozen_quantity or 0) == 0
            ):
                self.repo.delete_position(position)
        order.filled_quantity = quantity
        self.repo.update_order_status(order, OrderStatus.FILLED)

    def _settle_buy(
        self, order: PaperOrder, trade_id: int, amount: Decimal, fees: Decimal, release_cash: Decimal
    ) -> None:
        actual_cost = amount + fees
        if release_cash:
            self.repo.add_cash_event(
                order.account_id,
                CashEventType.RELEASE,
                release_cash,
                order_id=order.id,
                trade_id=trade_id,
                trade_date=order.trade_date,
            )
        position = self.repo.get_position(order.account_id, order.market, order.symbol)
        current_quantity = 0 if position is None else int(position.total_quantity or 0)
        current_cost = Decimal("0") if position is None else Decimal(position.cost_amount or 0)
        self.repo.upsert_position(
            order.account_id,
            order.market,
            order.symbol,
            total_quantity=current_quantity + int(order.quantity),
            frozen_quantity=(0 if position is None else int(position.frozen_quantity or 0)),
            cost_amount=quantize_account_money(current_cost + actual_cost),
        )
        self.repo.create_position_lot(
            order.account_id,
            order.market,
            order.symbol,
            order.trade_date,
            int(order.quantity),
            int(order.quantity),
            Decimal(order.limit_price),
        )

    def _settle_sell(self, order: PaperOrder, trade_id: int, amount: Decimal, fees: Decimal) -> None:
        # HK sells skip immediate cash credit — pending settlement is created in _fill_order
        if order.market != "hk_connect":
            self.repo.add_cash_event(
                order.account_id,
                CashEventType.TRADE,
                amount - fees,
                order_id=order.id,
                trade_id=trade_id,
                trade_date=order.trade_date,
            )
        position = self.repo.get_position(order.account_id, order.market, order.symbol)
        if position is None:
            return
        quantity_to_sell = int(order.quantity)
        remaining = quantity_to_sell
        cost_reduction = Decimal("0")
        for lot in self.repo.get_lots(order.account_id, order.market, order.symbol):
            if remaining <= 0:
                break
            used = min(int(lot.remaining_quantity or 0), remaining)
            lot.remaining_quantity = int(lot.remaining_quantity or 0) - used
            cost_reduction += Decimal(used) * Decimal(lot.cost_price)
            remaining -= used
        position.total_quantity = int(position.total_quantity or 0) - quantity_to_sell
        position.frozen_quantity = int(position.frozen_quantity or 0) - quantity_to_sell
        position.cost_amount = quantize_account_money(Decimal(position.cost_amount or 0) - cost_reduction)
        realized_pnl = quantize_account_money(amount - fees - cost_reduction)
        position.realized_pnl = quantize_account_money(Decimal(position.realized_pnl or 0) + realized_pnl)
        account = self.repo.get_account(order.account_id)
        if account is None:
            raise ValueError(f"paper account not found: {order.account_id}")
        self.repo.add_account_realized_pnl(account, realized_pnl)
