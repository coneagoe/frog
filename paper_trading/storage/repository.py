import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import String, func, or_
from sqlalchemy import cast as sa_cast
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from paper_trading.domain.enums import (
    REPLAY_REJECTION_MARKER,
    AccountStatus,
    CashEventType,
    CorporateActionType,
    ETFEligibilityStatus,
    FeePreset,
    LedgerRebuildStatus,
    Market,
    MatchingRunStatus,
    NavReplayEventType,
    OrderSide,
    OrderStatus,
    PendingSettlementSource,
    PositionSource,
    ReplayTimeProvenance,
    RoundTripStatus,
    SnapshotPointType,
    SnapshotQualityStatus,
    TradeValidityStatus,
)
from paper_trading.domain.fees import DEFAULT_FEE_PRESET, get_fee_preset
from paper_trading.domain.market_data_diagnostics import canonical_adjust_label, canonical_stock_id
from paper_trading.domain.nav_replay import NavSeriesReplay, ReplayEvent
from paper_trading.domain.precision import (
    quantize_account_money,
    quantize_nav,
    quantize_rounding_residual,
    quantize_shares,
    require_finite,
)
from paper_trading.storage.models import (
    DailyBarDiagnostic,
    ETFEligibility,
    PaperAccount,
    PaperAccountSnapshot,
    PaperCashLedger,
    PaperCorporateAction,
    PaperLedgerRebuild,
    PaperMatchingRun,
    PaperOrder,
    PaperPendingSettlement,
    PaperPosition,
    PaperPositionLot,
    PaperPositionRoundTrip,
    PaperTrade,
    PaperTradeValidityCheck,
    PaperValuationGap,
)
from storage.domain_enums import (
    DailyBarDiagnosticAdjust,
    DailyBarDiagnosticClassification,
    validate_provider_outcomes,
)
from storage.model.etf_basic import ETFBasic

_BARE_ETF_SYMBOL = re.compile(r"^\d{6}$")


def _whole_quantity(value: int | Decimal, field_name: str) -> int:
    quantity = Decimal(value)
    if not quantity.is_finite() or quantity != quantity.to_integral_value():
        raise ValueError(f"{field_name} must be a finite whole quantity")
    return int(quantity)


def _require_bare_etf_symbol(symbol: str) -> str:
    if not _BARE_ETF_SYMBOL.fullmatch(symbol):
        raise ValueError("ETF symbol must be a bare six-digit value")
    return symbol


def _validate_fee_values(**values: Decimal | None) -> None:
    for field_name, value in values.items():
        if value is not None and value < 0:
            raise ValueError(f"{field_name} must be non-negative")


def _require_fee_update(**values: Decimal | None) -> None:
    if all(value is None for value in values.values()):
        raise ValueError("at least one fee field is required")


class PaperTradingRepository:
    def __init__(self, session: Session):
        self.session = session

    def _get_decimal_value(self, column: Any, *criteria: Any) -> Decimal | None:
        """Read a numeric column without SQLite's ORM float conversion."""
        query: Any = self.session.query(column).filter(*criteria)
        if self.session.bind is not None and self.session.bind.dialect.name == "sqlite":
            query = self.session.query(sa_cast(column, String)).filter(*criteria)
        value = query.scalar()
        return None if value is None else Decimal(str(value))

    def list_etf_eligibility(self, status: str | None = None) -> list[ETFEligibility]:
        query = self.session.query(ETFEligibility)
        if status is not None:
            query = query.filter(ETFEligibility.status == ETFEligibilityStatus(status).value)
        return list(query.order_by(ETFEligibility.symbol.asc()).all())

    def get_etf_eligibility(self, symbol: str) -> ETFEligibility | None:
        symbol = _require_bare_etf_symbol(symbol)
        return cast(ETFEligibility | None, self.session.get(ETFEligibility, symbol))

    def upsert_etf_eligibility(
        self,
        symbol: str,
        name: str,
        exchange: str,
        list_status: str,
        refreshed_at: datetime,
        status: ETFEligibilityStatus | None = None,
    ) -> ETFEligibility:
        symbol = _require_bare_etf_symbol(symbol)
        eligibility = self.get_etf_eligibility(symbol)
        if eligibility is None:
            eligibility = ETFEligibility(
                symbol=symbol,
                name=name,
                exchange=exchange,
                list_status=list_status,
                last_seen_at=refreshed_at,
                last_refresh_at=refreshed_at,
                status=(status or ETFEligibilityStatus.UNKNOWN).value,
            )
            self.session.add(eligibility)
        else:
            eligibility.name = name
            eligibility.exchange = exchange
            eligibility.list_status = list_status
            eligibility.last_seen_at = refreshed_at
            eligibility.last_refresh_at = refreshed_at
            if status is not None:
                eligibility.status = status.value
                if status is ETFEligibilityStatus.DISABLED:
                    eligibility.reviewed_at = None
                    eligibility.reviewed_by = None
        self.session.flush()
        return eligibility

    def classify_etf_eligibility(self, symbol: str, status: ETFEligibilityStatus, reviewed_by: str) -> ETFEligibility:
        symbol = _require_bare_etf_symbol(symbol)
        if status not in {ETFEligibilityStatus.SUPPORTED, ETFEligibilityStatus.MONEY_MARKET}:
            raise ValueError("ETF eligibility classification must be supported or money_market")
        reviewed_by = reviewed_by.strip()
        if not reviewed_by:
            raise ValueError("reviewed_by must not be blank")
        eligibility = self.get_etf_eligibility(symbol)
        if eligibility is None:
            raise KeyError(f"ETF eligibility not found: {symbol}")
        eligibility.status = status.value
        eligibility.reviewed_by = reviewed_by
        eligibility.reviewed_at = datetime.now(timezone.utc)
        self.session.flush()
        return eligibility

    def upsert_daily_bar_diagnostic(
        self,
        business_date: date,
        market: str | Market,
        stock_id: str,
        adjust: str,
        classification: str,
        provider_outcomes: list[dict[str, Any]],
        resolved: bool,
    ) -> DailyBarDiagnostic:
        market = Market(market).value
        normalized_stock_id = canonical_stock_id(stock_id)
        adjust = DailyBarDiagnosticAdjust(canonical_adjust_label(adjust)).value
        classification = DailyBarDiagnosticClassification(classification).value
        provider_outcomes = validate_provider_outcomes(provider_outcomes)
        now = datetime.now(timezone.utc)
        values = {
            "business_date": business_date,
            "market": market,
            "stock_id": normalized_stock_id,
            "adjust": adjust,
            "classification": classification,
            "provider_outcomes": provider_outcomes,
            "first_observed_at": now,
            "last_observed_at": now,
            "resolved": resolved,
        }
        dialect_name = self.session.get_bind().dialect.name
        if dialect_name == "postgresql":
            statement: Any = postgresql_insert(DailyBarDiagnostic).values(**values)
        elif dialect_name == "sqlite":
            statement = sqlite_insert(DailyBarDiagnostic).values(**values)
        else:
            statement = None

        if statement is not None:
            statement = statement.on_conflict_do_update(
                index_elements=[
                    DailyBarDiagnostic.business_date,
                    DailyBarDiagnostic.market,
                    DailyBarDiagnostic.stock_id,
                    DailyBarDiagnostic.adjust,
                ],
                set_={
                    "classification": statement.excluded.classification,
                    "provider_outcomes": statement.excluded.provider_outcomes,
                    "last_observed_at": statement.excluded.last_observed_at,
                    "resolved": statement.excluded.resolved,
                },
            ).returning(DailyBarDiagnostic)
            result = self.session.execute(statement.execution_options(populate_existing=True)).scalar_one()
            return cast(DailyBarDiagnostic, result)

        diagnostic = (
            self.session.query(DailyBarDiagnostic)
            .filter_by(business_date=business_date, market=market, stock_id=normalized_stock_id, adjust=adjust)
            .one_or_none()
        )
        if diagnostic is None:
            diagnostic = DailyBarDiagnostic(**values)
            self.session.add(diagnostic)
        else:
            setattr(diagnostic, "classification", classification)
            setattr(diagnostic, "provider_outcomes", provider_outcomes)
            setattr(diagnostic, "last_observed_at", now)
            setattr(diagnostic, "resolved", resolved)
        self.session.flush()
        return diagnostic

    def list_daily_bar_diagnostics(self) -> list[DailyBarDiagnostic]:
        return list(
            self.session.query(DailyBarDiagnostic)
            .order_by(DailyBarDiagnostic.business_date.asc(), DailyBarDiagnostic.stock_id.asc())
            .all()
        )

    def list_eligible_daily_bar_rebuild_orders(self) -> list[PaperOrder]:
        return list(
            self.session.query(PaperOrder)
            .join(
                DailyBarDiagnostic,
                (DailyBarDiagnostic.business_date == PaperOrder.trade_date)
                & (DailyBarDiagnostic.market == PaperOrder.market)
                & (DailyBarDiagnostic.stock_id == PaperOrder.symbol)
                & (DailyBarDiagnostic.adjust == "bfq"),
            )
            .filter(
                PaperOrder.market == Market.A_SHARE.value,
                PaperOrder.status == OrderStatus.ACCEPTED.value,
                DailyBarDiagnostic.resolved.is_(False),
                DailyBarDiagnostic.classification == "missing_exact_date",
            )
            .order_by(PaperOrder.account_id.asc(), PaperOrder.trade_date.asc(), PaperOrder.id.asc())
            .all()
        )

    def has_unresolved_daily_bar_diagnostic(
        self, business_date: date, market: str | Market, stock_id: str, adjust: str = "bfq"
    ) -> bool:
        market = Market(market).value
        adjust = canonical_adjust_label(adjust)
        return (
            self.session.query(DailyBarDiagnostic.id)
            .filter(
                DailyBarDiagnostic.business_date == business_date,
                DailyBarDiagnostic.market == market,
                DailyBarDiagnostic.stock_id == canonical_stock_id(stock_id),
                DailyBarDiagnostic.adjust == adjust,
                DailyBarDiagnostic.resolved.is_(False),
            )
            .first()
            is not None
        )

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
        _validate_fee_values(
            commission_rate=commission_rate,
            min_commission=min_commission,
            stamp_duty_rate=stamp_duty_rate,
            transfer_fee_rate=transfer_fee_rate,
            etf_commission_rate=etf_commission_rate,
        )
        preset_name = FeePreset(fee_preset or DEFAULT_FEE_PRESET)
        preset = get_fee_preset(preset_name)
        cash = Decimal(initial_cash)
        if cash <= 0:
            raise ValueError("initial_cash must be positive")
        initial_nav = Decimal("1.000000")
        cash = quantize_account_money(require_finite(cash, "initial_cash"))
        initial_shares = quantize_shares(cash)
        initial_deposit = quantize_account_money(cash)
        account = PaperAccount(
            name=name,
            initial_cash=cash,
            fee_preset=preset_name,
            commission_rate=commission_rate if commission_rate is not None else preset.commission_rate,
            min_commission=min_commission if min_commission is not None else preset.min_commission,
            stamp_duty_rate=stamp_duty_rate if stamp_duty_rate is not None else preset.stamp_duty_rate,
            transfer_fee_rate=transfer_fee_rate if transfer_fee_rate is not None else preset.transfer_fee_rate,
            etf_commission_rate=etf_commission_rate,
            share_count=initial_shares,
            net_asset_value=initial_nav,
            cumulative_deposit=initial_deposit,
            cumulative_withdrawal=Decimal("0.0000"),
        )
        self.session.add(account)
        self.session.flush()
        if account.created_at is None:
            self.session.refresh(account)
        event_at = account.created_at
        if event_at is None:
            raise RuntimeError("paper account created_at is missing after flush")
        if event_at.tzinfo is None or event_at.utcoffset() is None:
            event_at = event_at.replace(tzinfo=timezone.utc)
        else:
            event_at = event_at.astimezone(timezone.utc)
        self.add_cash_event(
            account.id,
            CashEventType.DEPOSIT,
            initial_deposit,
            trade_date=event_at.date(),
            net_asset_value=initial_nav,
            share_delta=initial_shares,
            occurred_at=event_at,
            note="initial_cash",
        )
        self.create_initial_snapshot(account, event_at=event_at)
        return account

    def get_account(self, account_id: int) -> PaperAccount | None:
        return cast(PaperAccount | None, self.session.get(PaperAccount, account_id))

    def lock_account(self, account_id: int) -> PaperAccount:
        account = self.session.query(PaperAccount).filter(PaperAccount.id == account_id).with_for_update().one_or_none()
        if account is None:
            raise KeyError(f"paper account not found: {account_id}")
        return account

    def add_account_realized_pnl(self, account: PaperAccount, amount: Decimal) -> PaperAccount:
        account.realized_pnl = quantize_account_money(Decimal(account.realized_pnl or 0) + amount)
        self.session.flush()
        return account

    def list_accounts(self) -> list[PaperAccount]:
        return list(self.session.query(PaperAccount).order_by(PaperAccount.id.asc()).all())

    def update_account_fees(
        self,
        account_id: int,
        commission_rate: Decimal | None = None,
        min_commission: Decimal | None = None,
        stamp_duty_rate: Decimal | None = None,
        transfer_fee_rate: Decimal | None = None,
    ) -> PaperAccount | None:
        _require_fee_update(
            commission_rate=commission_rate,
            min_commission=min_commission,
            stamp_duty_rate=stamp_duty_rate,
            transfer_fee_rate=transfer_fee_rate,
        )
        _validate_fee_values(
            commission_rate=commission_rate,
            min_commission=min_commission,
            stamp_duty_rate=stamp_duty_rate,
            transfer_fee_rate=transfer_fee_rate,
        )
        account = self.get_account(account_id)
        if account is None:
            return None
        if commission_rate is not None:
            account.commission_rate = commission_rate
        if min_commission is not None:
            account.min_commission = min_commission
        if stamp_duty_rate is not None:
            account.stamp_duty_rate = stamp_duty_rate
        if transfer_fee_rate is not None:
            account.transfer_fee_rate = transfer_fee_rate
        self.session.flush()
        return account

    def update_account_hk_fees(
        self,
        account_id: int,
        hk_commission_rate: Decimal | None = None,
        hk_min_commission: Decimal | None = None,
        hk_stamp_duty_rate: Decimal | None = None,
        hk_trading_fee_rate: Decimal | None = None,
        hk_sfc_levy_rate: Decimal | None = None,
        hk_afrc_levy_rate: Decimal | None = None,
        hk_settlement_fee_rate: Decimal | None = None,
    ) -> PaperAccount | None:
        _require_fee_update(
            hk_commission_rate=hk_commission_rate,
            hk_min_commission=hk_min_commission,
            hk_stamp_duty_rate=hk_stamp_duty_rate,
            hk_trading_fee_rate=hk_trading_fee_rate,
            hk_sfc_levy_rate=hk_sfc_levy_rate,
            hk_afrc_levy_rate=hk_afrc_levy_rate,
            hk_settlement_fee_rate=hk_settlement_fee_rate,
        )
        _validate_fee_values(
            hk_commission_rate=hk_commission_rate,
            hk_min_commission=hk_min_commission,
            hk_stamp_duty_rate=hk_stamp_duty_rate,
            hk_trading_fee_rate=hk_trading_fee_rate,
            hk_sfc_levy_rate=hk_sfc_levy_rate,
            hk_afrc_levy_rate=hk_afrc_levy_rate,
            hk_settlement_fee_rate=hk_settlement_fee_rate,
        )
        account = self.get_account(account_id)
        if account is None:
            return None
        if hk_commission_rate is not None:
            account.hk_commission_rate = hk_commission_rate
        if hk_min_commission is not None:
            account.hk_min_commission = hk_min_commission
        if hk_stamp_duty_rate is not None:
            account.hk_stamp_duty_rate = hk_stamp_duty_rate
        if hk_trading_fee_rate is not None:
            account.hk_trading_fee_rate = hk_trading_fee_rate
        if hk_sfc_levy_rate is not None:
            account.hk_sfc_levy_rate = hk_sfc_levy_rate
        if hk_afrc_levy_rate is not None:
            account.hk_afrc_levy_rate = hk_afrc_levy_rate
        if hk_settlement_fee_rate is not None:
            account.hk_settlement_fee_rate = hk_settlement_fee_rate
        self.session.flush()
        return account

    def update_account_etf_fees(
        self, account_id: int, etf_commission_rate: Decimal | None = None
    ) -> PaperAccount | None:
        _require_fee_update(etf_commission_rate=etf_commission_rate)
        _validate_fee_values(etf_commission_rate=etf_commission_rate)
        account = self.get_account(account_id)
        if account is None:
            return None
        account.etf_commission_rate = etf_commission_rate
        self.session.flush()
        return account

    def delete_account(self, account_id: int) -> bool:
        account = self.get_account(account_id)
        if account is None:
            return False

        self.session.query(PaperTradeValidityCheck).filter(PaperTradeValidityCheck.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperCashLedger).filter(PaperCashLedger.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperCorporateAction).filter(PaperCorporateAction.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperPositionRoundTrip).filter(PaperPositionRoundTrip.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperTrade).filter(PaperTrade.account_id == account_id).delete(synchronize_session=False)
        self.session.query(PaperOrder).filter(PaperOrder.account_id == account_id).delete(synchronize_session=False)
        self.session.query(PaperPositionLot).filter(PaperPositionLot.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperPosition).filter(PaperPosition.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperAccountSnapshot).filter(PaperAccountSnapshot.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperPendingSettlement).filter(PaperPendingSettlement.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperMatchingRun).filter(PaperMatchingRun.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperValuationGap).filter(PaperValuationGap.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.delete(account)
        self.session.flush()
        return True

    def add_cash_event(
        self,
        account_id: int,
        event_type: CashEventType | str,
        amount: Decimal,
        order_id: int | None = None,
        trade_id: int | None = None,
        note: str | None = None,
        trade_date: date | None = None,
        net_asset_value: Decimal | None = None,
        share_delta: Decimal | None = None,
        rounding_residual: Decimal = Decimal("0"),
        occurred_at: datetime | None = None,
    ) -> PaperCashLedger:
        if occurred_at is not None and (occurred_at.tzinfo is None or occurred_at.utcoffset() is None):
            raise ValueError("occurred_at must include a timezone offset")
        persisted_amount = quantize_account_money(amount)
        persisted_nav = None if net_asset_value is None else quantize_nav(net_asset_value)
        persisted_shares = None if share_delta is None else quantize_shares(share_delta)
        persisted_residual = (
            quantize_rounding_residual(persisted_amount - persisted_shares * persisted_nav)
            if persisted_nav is not None and persisted_shares is not None
            else quantize_rounding_residual(rounding_residual)
        )
        event = PaperCashLedger(
            account_id=account_id,
            event_type=CashEventType(event_type).value,
            amount=persisted_amount,
            order_id=order_id,
            trade_id=trade_id,
            trade_date=trade_date,
            net_asset_value=persisted_nav,
            share_delta=persisted_shares,
            rounding_residual=persisted_residual,
            occurred_at=(occurred_at or datetime.now(timezone.utc)).astimezone(timezone.utc),
            event_time_provenance=ReplayTimeProvenance.CANONICAL_UTC.value,
            note=note,
        )
        self.session.add(event)
        self.session.flush()
        return event

    def update_account_nav_state(
        self,
        account: PaperAccount,
        *,
        share_count: Decimal,
        net_asset_value: Decimal,
        cumulative_deposit: Decimal,
        cumulative_withdrawal: Decimal,
    ) -> PaperAccount:
        account.share_count = quantize_shares(share_count)
        account.net_asset_value = quantize_nav(net_asset_value)
        account.cumulative_deposit = quantize_account_money(cumulative_deposit)
        account.cumulative_withdrawal = quantize_account_money(cumulative_withdrawal)
        self.session.flush()
        return account

    def get_cash_available(self, account_id: int) -> Decimal:
        total = (
            self.session.query(func.coalesce(func.sum(PaperCashLedger.amount), 0))
            .filter(PaperCashLedger.account_id == account_id)
            .scalar()
        )
        return Decimal(str(total)).quantize(Decimal("0.0001"))

    def get_cash_available_internal(self, account_id: int) -> Decimal:
        amount_query: Any = self.session.query(PaperCashLedger.amount)
        if self.session.bind is not None and self.session.bind.dialect.name == "sqlite":
            amount_query = self.session.query(sa_cast(PaperCashLedger.amount, String))
        amounts = amount_query.filter(PaperCashLedger.account_id == account_id).all()
        values = (Decimal(str(amount)) for (amount,) in amounts)
        return quantize_account_money(sum((quantize_account_money(value) for value in values), Decimal("0")))

    def get_cash_available_as_of(self, account_id: int, as_of: date) -> Decimal:
        total = (
            self.session.query(func.coalesce(func.sum(PaperCashLedger.amount), 0))
            .filter(
                PaperCashLedger.account_id == account_id,
                or_(PaperCashLedger.trade_date.is_(None), PaperCashLedger.trade_date <= as_of),
            )
            .scalar()
        )
        return Decimal(str(total)).quantize(Decimal("0.0001"))

    def get_cash_available_as_of_internal(self, account_id: int, as_of: date) -> Decimal:
        """Return accounting-precision cash available through ``as_of``.

        SQLite stores SQLAlchemy numerics as floating point values when they
        are aggregated directly.  Read the values as text there and sum
        Decimal values in Python, just as the all-time internal accessor does.
        """
        query: Any = self.session.query(PaperCashLedger.amount).filter(
            PaperCashLedger.account_id == account_id,
            or_(PaperCashLedger.trade_date.is_(None), PaperCashLedger.trade_date <= as_of),
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "sqlite":
            query = self.session.query(sa_cast(PaperCashLedger.amount, String)).filter(
                PaperCashLedger.account_id == account_id,
                or_(PaperCashLedger.trade_date.is_(None), PaperCashLedger.trade_date <= as_of),
            )
        values = (Decimal(str(amount)) for (amount,) in query.all())
        return quantize_account_money(sum((quantize_account_money(value) for value in values), Decimal("0")))

    def get_cash_frozen(self, account_id: int) -> Decimal:
        return self.get_cash_frozen_internal(account_id).quantize(Decimal("0.0001"))

    def get_cash_frozen_internal(self, account_id: int) -> Decimal:
        query: Any = self.session.query(PaperOrder.frozen_cash).filter(
            PaperOrder.account_id == account_id,
            PaperOrder.status == OrderStatus.ACCEPTED.value,
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "sqlite":
            query = self.session.query(sa_cast(PaperOrder.frozen_cash, String)).filter(
                PaperOrder.account_id == account_id,
                PaperOrder.status == OrderStatus.ACCEPTED.value,
            )
        values = (Decimal(str(row[0])) for row in query.all())
        return quantize_account_money(sum(values, Decimal("0")))

    @staticmethod
    def _normalize_comment(comment: str | None) -> str | None:
        if comment is None or comment == "":
            return None
        return comment

    def create_order(
        self,
        account_id: int,
        symbol: str,
        side: OrderSide,
        quantity: int,
        limit_price: Decimal,
        trade_date: date,
        status: OrderStatus,
        frozen_cash: Decimal = Decimal("0"),
        frozen_quantity: int = 0,
        idempotency_key: str | None = None,
        rejection_code: str | None = None,
        rejection_reason: str | None = None,
        comment: str | None = None,
        market: str | None = None,
    ) -> PaperOrder:
        normalized_idempotency_key = idempotency_key.strip() if idempotency_key and idempotency_key.strip() else None
        order = PaperOrder(
            account_id=account_id,
            symbol=symbol,
            side=side.value,
            quantity=_whole_quantity(quantity, "quantity"),
            limit_price=quantize_account_money(limit_price),
            trade_date=trade_date,
            status=status.value,
            frozen_cash=quantize_account_money(frozen_cash),
            frozen_quantity=_whole_quantity(frozen_quantity, "frozen_quantity"),
            idempotency_key=normalized_idempotency_key,
            rejection_code=rejection_code,
            rejection_reason=rejection_reason,
            comment=self._normalize_comment(comment),
            market=Market(market or Market.A_SHARE).value,
        )
        self.session.add(order)
        self.session.flush()
        return order

    def get_order_by_idempotency_key(self, account_id: int, idempotency_key: str) -> PaperOrder | None:
        return (
            self.session.query(PaperOrder)
            .filter(PaperOrder.account_id == account_id, PaperOrder.idempotency_key == idempotency_key)
            .one_or_none()
        )

    def get_corporate_action_by_idempotency_key(self, account_id: int, key: str) -> PaperCorporateAction | None:
        return (
            self.session.query(PaperCorporateAction)
            .filter(PaperCorporateAction.account_id == account_id, PaperCorporateAction.idempotency_key == key)
            .one_or_none()
        )

    def lock_corporate_action_by_idempotency_key(self, account_id: int, key: str) -> PaperCorporateAction | None:
        query = self.session.query(PaperCorporateAction).filter(
            PaperCorporateAction.account_id == account_id,
            PaperCorporateAction.idempotency_key == key,
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            query = query.with_for_update()
        return query.one_or_none()

    def create_corporate_action(self, **values: Any) -> PaperCorporateAction:
        if "event_type" in values:
            values["event_type"] = CorporateActionType(values["event_type"]).value
        if "market" in values:
            values["market"] = Market(values["market"]).value
        if "parameters" in values:
            values["parameters"] = {
                name: str(require_finite(Decimal(value), f"parameters.{name}"))
                for name, value in values["parameters"].items()
            }
        for field_name in (
            "cash_delta",
            "before_cost_amount",
            "after_cost_amount",
            "before_cash_available",
            "after_cash_available",
        ):
            if field_name in values and values[field_name] is not None:
                values[field_name] = quantize_account_money(values[field_name])
        for field_name in ("quantity_delta", "before_quantity", "after_quantity"):
            if field_name in values and values[field_name] is not None:
                values[field_name] = quantize_shares(values[field_name])
        event_at = values.get("event_at")
        if event_at is not None and (event_at.tzinfo is None or event_at.utcoffset() is None):
            raise ValueError("event_at must include a timezone offset")
        if event_at is not None:
            values["event_at"] = event_at.astimezone(timezone.utc)
        values["event_time_provenance"] = ReplayTimeProvenance.CANONICAL_UTC.value
        action = PaperCorporateAction(**values)
        self.session.add(action)
        self.session.flush()
        return action

    def list_corporate_actions(
        self,
        account_id: int,
        symbol: str | None = None,
        event_type: str | CorporateActionType | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[PaperCorporateAction]:
        query = self.session.query(PaperCorporateAction).filter(PaperCorporateAction.account_id == account_id)
        if symbol is not None:
            query = query.filter(PaperCorporateAction.symbol == symbol)
        if event_type is not None:
            query = query.filter(PaperCorporateAction.event_type == CorporateActionType(event_type).value)
        if start_at is not None:
            query = query.filter(PaperCorporateAction.event_at >= self._normalize_datetime_filter(start_at))
        if end_at is not None:
            query = query.filter(PaperCorporateAction.event_at <= self._normalize_datetime_filter(end_at))
        return list(query.order_by(PaperCorporateAction.event_at.asc(), PaperCorporateAction.id.asc()).all())

    @staticmethod
    def _normalize_datetime_filter(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("corporate-action time filters must include a timezone offset")
        return value.astimezone(timezone.utc)

    def get_order(self, order_id: int) -> PaperOrder:
        order = self.session.get(PaperOrder, order_id)
        if order is None:
            raise KeyError(f"paper order not found: {order_id}")
        return order

    def list_orders(self, account_id: int) -> list[PaperOrder]:
        return list(
            self.session.query(PaperOrder)
            .filter(PaperOrder.account_id == account_id)
            .order_by(PaperOrder.id.asc())
            .all()
        )

    def list_orders_page(
        self,
        account_id: int,
        start_date: date,
        end_date: date,
        page: int,
        page_size: int,
    ) -> tuple[list[PaperOrder], int]:
        query = self.session.query(PaperOrder).filter(
            PaperOrder.account_id == account_id,
            PaperOrder.trade_date >= start_date,
            PaperOrder.trade_date <= end_date,
        )
        total = query.count()
        offset = (page - 1) * page_size
        orders = (
            query.order_by(PaperOrder.trade_date.desc(), PaperOrder.id.desc()).offset(offset).limit(page_size).all()
        )
        return list(orders), total

    def list_catalogue_etf_a_share_orders(self, account_id: int | None = None) -> list[PaperOrder]:
        query = (
            self.session.query(PaperOrder)
            .join(ETFBasic, PaperOrder.symbol == ETFBasic.基金代码)
            .filter(
                PaperOrder.market == Market.A_SHARE.value,
                func.length(PaperOrder.symbol) == 6,
            )
        )
        if account_id is not None:
            query = query.filter(PaperOrder.account_id == account_id)
        return [
            order
            for order in query.order_by(
                PaperOrder.account_id.asc(), PaperOrder.trade_date.asc(), PaperOrder.id.asc()
            ).all()
            if order.symbol.isdigit()
        ]

    def update_orders_market(self, order_ids: list[int], market: Market) -> int:
        if not order_ids:
            return 0
        changed = (
            self.session.query(PaperOrder)
            .filter(PaperOrder.id.in_(order_ids))
            .update({PaperOrder.market: market.value}, synchronize_session=False)
        )
        self.session.flush()
        return int(changed)

    def list_cash_ledger(self, account_id: int) -> list[PaperCashLedger]:
        return list(
            self.session.query(PaperCashLedger)
            .filter(PaperCashLedger.account_id == account_id)
            .order_by(PaperCashLedger.occurred_at.asc(), PaperCashLedger.id.asc())
            .all()
        )

    @staticmethod
    def _replay_event_time(
        event_at: datetime | None,
        trade_date: date | None,
        *,
        persisted_timezone_aware: bool = False,
    ) -> tuple[datetime, SnapshotQualityStatus]:
        """Normalize replay time; SQLite's aware-column values are canonical UTC."""
        if event_at is None:
            return (
                datetime.combine(trade_date or date.min, time.min, tzinfo=timezone.utc),
                SnapshotQualityStatus.INVALID,
            )
        if event_at.tzinfo is None or event_at.utcoffset() is None:
            if persisted_timezone_aware:
                return event_at.replace(tzinfo=timezone.utc), SnapshotQualityStatus.VALID
            return event_at.replace(tzinfo=timezone.utc), SnapshotQualityStatus.INVALID
        return event_at.astimezone(timezone.utc), SnapshotQualityStatus.VALID

    def _replay_persisted_event_time(
        self, event_at: datetime | None, trade_date: date | None, provenance: str | None
    ) -> tuple[datetime, SnapshotQualityStatus]:
        normalized_time, time_quality = self._replay_event_time(
            event_at,
            trade_date,
            persisted_timezone_aware=provenance == ReplayTimeProvenance.CANONICAL_UTC.value,
        )
        if provenance != ReplayTimeProvenance.CANONICAL_UTC.value:
            return normalized_time, SnapshotQualityStatus.INVALID
        return normalized_time, time_quality

    @staticmethod
    def _replay_decimal(value: Decimal | None, quantizer: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            return quantizer(Decimal(str(value)))
        except (ArithmeticError, TypeError, ValueError):
            return None

    @staticmethod
    def _replay_source_id(source_kind: str, row_id: int) -> str:
        return f"{source_kind}:{row_id}"

    @staticmethod
    def _validate_replay_range(
        start_at: datetime | None, end_at: datetime | None
    ) -> tuple[datetime | None, datetime | None]:
        for name, value in (("start_at", start_at), ("end_at", end_at)):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{name} must include a timezone offset")
        normalized_start = None if start_at is None else start_at.astimezone(timezone.utc)
        normalized_end = None if end_at is None else end_at.astimezone(timezone.utc)
        if normalized_start is not None and normalized_end is not None and normalized_start > normalized_end:
            raise ValueError("start_at must not be after end_at")
        return normalized_start, normalized_end

    def list_replay_events(
        self, account_id: int, start_at: datetime | None = None, end_at: datetime | None = None
    ) -> list[ReplayEvent]:
        """Return deterministic, UTC-normalized replay inputs from persisted account history."""
        start_at, end_at = self._validate_replay_range(start_at, end_at)
        events: list[ReplayEvent] = []

        account = self.get_account(account_id)
        for ledger in self.list_cash_ledger(account_id):
            ledger_event_type = CashEventType(ledger.event_type)
            if account is not None and self._is_creation_initial_cash_event(account, ledger):
                continue
            event_at, quality_status = self._replay_persisted_event_time(
                ledger.occurred_at, ledger.trade_date, ledger.event_time_provenance
            )
            # Only external cash movements are CASH_FLOW. Internal ledger rows
            # remain visible as settlement facts, but never mint/burn shares.
            replay_event_type = (
                NavReplayEventType.CASH_FLOW
                if ledger_event_type in {CashEventType.DEPOSIT, CashEventType.WITHDRAWAL}
                else NavReplayEventType.TRADE_SETTLEMENT
            )
            events.append(
                ReplayEvent(
                    event_at=event_at,
                    trade_date=ledger.trade_date or event_at.date(),
                    event_type=replay_event_type,
                    source_id=self._replay_source_id("paper_cash_ledger", ledger.id),
                    source_kind="paper_cash_ledger",
                    payload={
                        "amount": self._replay_decimal(ledger.amount, quantize_account_money),
                        "pricing_nav": self._replay_decimal(ledger.net_asset_value, quantize_nav),
                        "share_delta": self._replay_decimal(ledger.share_delta, quantize_shares),
                        "rounding_residual": (
                            self._replay_decimal(ledger.rounding_residual, quantize_rounding_residual)
                            if ledger.net_asset_value is not None or ledger.share_delta is not None
                            else None
                        ),
                        "ledger_event_type": ledger_event_type.value,
                        "order_id": ledger.order_id,
                        "trade_id": ledger.trade_id,
                    },
                    quality_status=quality_status,
                )
            )

        for trade in self.list_trades(account_id):
            event_at, quality_status = self._replay_persisted_event_time(
                trade.trade_time, trade.trade_date, trade.event_time_provenance
            )
            events.append(
                ReplayEvent(
                    event_at=event_at,
                    trade_date=trade.trade_date,
                    event_type=NavReplayEventType.TRADE_SETTLEMENT,
                    source_id=self._replay_source_id("paper_trades", trade.id),
                    source_kind="paper_trades",
                    payload={
                        "amount": self._replay_decimal(trade.amount, quantize_account_money),
                        "fees": self._replay_decimal(trade.fees, quantize_account_money),
                        "side": trade.side,
                        "quantity": trade.quantity,
                        "price": self._replay_decimal(trade.price, quantize_account_money),
                        "symbol": trade.symbol,
                        "market": trade.market,
                        "order_id": trade.order_id,
                        "trade_id": trade.id,
                        "settlement": True,
                    },
                    quality_status=quality_status,
                )
            )

        for action in self.list_corporate_actions(account_id):
            event_at, quality_status = self._replay_persisted_event_time(
                action.event_at, action.affected_start_date, action.event_time_provenance
            )
            events.append(
                ReplayEvent(
                    event_at=event_at,
                    trade_date=action.affected_start_date or event_at.date(),
                    event_type=NavReplayEventType.CORPORATE_ACTION,
                    source_id=self._replay_source_id("paper_corporate_actions", action.id),
                    source_kind="paper_corporate_actions",
                    payload={
                        "cash_delta": self._replay_decimal(action.cash_delta, quantize_account_money),
                        "quantity_delta": self._replay_decimal(action.quantity_delta, quantize_shares),
                        "parameters": action.parameters,
                        "symbol": action.symbol,
                        "market": action.market,
                        "action_type": action.event_type,
                        "affected_start_date": action.affected_start_date,
                        "affected_end_date": action.affected_end_date,
                        "cash_ledger_event_type": CashEventType.CORPORATE_ACTION.value,
                        "before_quantity": self._replay_decimal(action.before_quantity, quantize_shares),
                        "after_quantity": self._replay_decimal(action.after_quantity, quantize_shares),
                        "before_cost_amount": self._replay_decimal(action.before_cost_amount, quantize_account_money),
                        "after_cost_amount": self._replay_decimal(action.after_cost_amount, quantize_account_money),
                        "before_cash_available": self._replay_decimal(
                            action.before_cash_available, quantize_account_money
                        ),
                        "after_cash_available": self._replay_decimal(
                            action.after_cash_available, quantize_account_money
                        ),
                    },
                    quality_status=quality_status,
                )
            )

        for snapshot in self.list_snapshots(account_id):
            event_at, time_quality = self._replay_persisted_event_time(
                snapshot.event_at,
                snapshot.trade_date,
                getattr(snapshot, "event_time_provenance", None),
            )
            quality_status = (
                time_quality
                if time_quality is SnapshotQualityStatus.INVALID
                else SnapshotQualityStatus(snapshot.quality_status)
            )
            events.append(
                ReplayEvent(
                    event_at=event_at,
                    trade_date=snapshot.trade_date,
                    event_type=(
                        NavReplayEventType.INITIAL
                        if snapshot.point_type == SnapshotPointType.INITIAL.value
                        else NavReplayEventType.MARKET_VALUATION
                    ),
                    source_id=self._replay_source_id("paper_account_snapshots", snapshot.id),
                    source_kind=(
                        "creation"
                        if snapshot.point_type == SnapshotPointType.INITIAL.value
                        else "paper_account_snapshots"
                    ),
                    payload={
                        "opening_cash": self._replay_decimal(snapshot.cash_available, quantize_account_money),
                        "opening_shares": self._replay_decimal(snapshot.share_count, quantize_shares),
                        "total_assets": self._replay_decimal(snapshot.total_assets, quantize_account_money),
                        "share_count": self._replay_decimal(snapshot.share_count, quantize_shares),
                        "nav": self._replay_decimal(snapshot.net_asset_value, quantize_nav),
                    },
                    quality_status=quality_status,
                )
            )

        baseline_events = [
            event
            for event in events
            if event.event_type is NavReplayEventType.INITIAL
            and event.source_kind == "creation"
            and event.quality_status is SnapshotQualityStatus.VALID
            and event.event_at < (start_at or datetime.max.replace(tzinfo=timezone.utc))
        ]
        baseline = max(baseline_events, key=NavSeriesReplay._sort_key) if baseline_events else None
        filtered = [
            event
            for event in events
            if (start_at is None or event.event_at >= start_at) and (end_at is None or event.event_at <= end_at)
        ]
        if baseline is not None and baseline not in filtered:
            filtered.insert(0, baseline)
        return sorted(filtered, key=NavSeriesReplay._sort_key)

    def _is_creation_initial_cash_event(self, account: PaperAccount, ledger: PaperCashLedger) -> bool:
        """Identify only the immutable creation event represented by INITIAL."""
        initial_snapshots = [
            snapshot
            for snapshot in self.list_snapshots(account.id)
            if snapshot.point_type == SnapshotPointType.INITIAL.value
        ]
        if len(initial_snapshots) != 1 or ledger.event_type != CashEventType.DEPOSIT.value:
            return False
        first_ledger_id = min(event.id for event in self.list_cash_ledger(account.id))
        if ledger.id != first_ledger_id:
            return False
        snapshot = initial_snapshots[0]
        ledger_at, ledger_quality = self._replay_persisted_event_time(
            ledger.occurred_at, ledger.trade_date, ledger.event_time_provenance
        )
        snapshot_at, snapshot_quality = self._replay_persisted_event_time(
            snapshot.event_at, snapshot.trade_date, snapshot.event_time_provenance
        )
        if (
            ledger.note != "initial_cash"
            or ledger_quality is not SnapshotQualityStatus.VALID
            or snapshot_quality is not SnapshotQualityStatus.VALID
            or ledger_at != snapshot_at
            or ledger.trade_date != snapshot.trade_date
        ):
            return False
        try:
            return (
                Decimal(str(ledger.amount)) == Decimal(str(account.initial_cash))
                and Decimal(str(ledger.net_asset_value)) == Decimal("1")
                and Decimal(str(ledger.share_delta)) == Decimal(str(snapshot.share_count))
                and Decimal(str(ledger.rounding_residual)) == Decimal("0")
            )
        except (ArithmeticError, TypeError, ValueError):
            return False

    def get_replay_events(
        self, account_id: int, start_at: datetime | None = None, end_at: datetime | None = None
    ) -> list[ReplayEvent]:
        """Compatibility alias for callers that use getter naming."""
        return self.list_replay_events(account_id, start_at=start_at, end_at=end_at)

    def latest_valid_nav_before(self, account_id: int, occurred_at: datetime) -> Decimal | None:
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone offset")
        snapshots = (
            self.session.query(PaperAccountSnapshot)
            .filter(
                PaperAccountSnapshot.account_id == account_id,
                PaperAccountSnapshot.point_type == SnapshotPointType.TRADING.value,
                PaperAccountSnapshot.quality_status == SnapshotQualityStatus.VALID.value,
                PaperAccountSnapshot.event_at <= occurred_at,
            )
            .order_by(PaperAccountSnapshot.event_at.desc(), PaperAccountSnapshot.id.desc())
            .all()
        )
        for snapshot in snapshots:
            nav = Decimal(snapshot.net_asset_value or 0)
            if nav.is_finite() and nav > 0:
                return quantize_nav(nav)
        return None

    def list_trades(self, account_id: int) -> list[PaperTrade]:
        return list(
            self.session.query(PaperTrade)
            .filter(PaperTrade.account_id == account_id)
            .order_by(PaperTrade.id.asc())
            .all()
        )

    def list_trades_page(
        self,
        account_id: int,
        start_date: date,
        end_date: date,
        page: int,
        page_size: int,
    ) -> tuple[list[PaperTrade], int]:
        query = self.session.query(PaperTrade).filter(
            PaperTrade.account_id == account_id,
            PaperTrade.trade_date >= start_date,
            PaperTrade.trade_date <= end_date,
        )
        total = query.count()
        offset = (page - 1) * page_size
        trades = (
            query.order_by(PaperTrade.trade_date.desc(), PaperTrade.id.desc()).offset(offset).limit(page_size).all()
        )
        return list(trades), total

    def list_snapshots(self, account_id: int) -> list[PaperAccountSnapshot]:
        return list(
            self.session.query(PaperAccountSnapshot)
            .filter(PaperAccountSnapshot.account_id == account_id)
            .order_by(PaperAccountSnapshot.event_at.asc(), PaperAccountSnapshot.id.asc())
            .all()
        )

    def upsert_valuation_gap(
        self,
        account_id: int,
        trade_date: date,
        missing_symbols: list[str],
        details: list[dict[str, Any]],
        resolved: bool = False,
    ) -> PaperValuationGap:
        now = datetime.now(timezone.utc)
        gap = (
            self.session.query(PaperValuationGap).filter_by(account_id=account_id, trade_date=trade_date).one_or_none()
        )
        if gap is None:
            gap = PaperValuationGap(
                account_id=account_id,
                trade_date=trade_date,
                missing_symbols=missing_symbols,
                details=details,
                first_observed_at=now,
                last_observed_at=now,
                resolved=resolved,
            )
            self.session.add(gap)
        else:
            gap.last_observed_at = now
            gap.resolved = resolved
            if not resolved:
                gap.missing_symbols = missing_symbols
                gap.details = details
        self.session.flush()
        return gap

    def get_valuation_gap(self, account_id: int, trade_date: date) -> PaperValuationGap | None:
        return (
            self.session.query(PaperValuationGap).filter_by(account_id=account_id, trade_date=trade_date).one_or_none()
        )

    def get_accounts_for_snapshot(self, trade_date: date, account_id: int | None = None) -> list[int]:
        position_query = self.session.query(PaperPosition.account_id).filter(PaperPosition.total_quantity > 0)
        order_query = self.session.query(PaperOrder.account_id).filter(PaperOrder.trade_date == trade_date)
        valuation_end = datetime.combine(trade_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
        active_account_query = self.session.query(PaperAccount.id).filter(
            PaperAccount.status == AccountStatus.ACTIVE.value,
            PaperAccount.created_at < valuation_end,
        )
        if account_id is not None:
            position_query = position_query.filter(PaperPosition.account_id == account_id)
            order_query = order_query.filter(PaperOrder.account_id == account_id)
            active_account_query = active_account_query.filter(PaperAccount.id == account_id)
        ids = {int(value) for (value,) in position_query.all()}
        ids.update(int(value) for (value,) in order_query.all())
        ids.update(int(value) for (value,) in active_account_query.all())
        return sorted(ids)

    def get_orders_for_matching(self, trade_date: date, account_id: int | None = None) -> list[PaperOrder]:
        query = self.session.query(PaperOrder).filter(
            PaperOrder.trade_date == trade_date,
            PaperOrder.status == OrderStatus.ACCEPTED.value,
        )
        if account_id is not None:
            query = query.filter(PaperOrder.account_id == account_id)
        return list(query.order_by(PaperOrder.id.asc()).all())

    def get_orders_for_matching_locked(self, trade_date: date, account_id: int | None = None) -> list[PaperOrder]:
        """Return accepted orders while locking them for this transaction."""
        query = self.session.query(PaperOrder).filter(
            PaperOrder.trade_date == trade_date,
            PaperOrder.status == OrderStatus.ACCEPTED.value,
        )
        if account_id is not None:
            query = query.filter(PaperOrder.account_id == account_id)
        return list(query.with_for_update(skip_locked=True).order_by(PaperOrder.id.asc()).all())

    def update_order_status(
        self,
        order: PaperOrder,
        status: OrderStatus,
        rejection_code: str | None = None,
        rejection_reason: str | None = None,
    ) -> PaperOrder:
        order.status = status.value
        order.rejection_code = rejection_code
        order.rejection_reason = rejection_reason
        order.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return order

    def update_order_validity(self, order: PaperOrder, status: str, reason: str) -> PaperOrder:
        order.validity_status = TradeValidityStatus(status).value
        order.validity_reason = reason
        order.validity_checked_at = datetime.now(timezone.utc)
        order.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return order

    def create_trade_validity_check(self, **values: Any) -> PaperTradeValidityCheck:
        check = PaperTradeValidityCheck(**values)
        self.session.add(check)
        self.session.flush()
        return check

    def list_trade_validity_checks(self, order_id: int) -> list[PaperTradeValidityCheck]:
        return list(
            self.session.query(PaperTradeValidityCheck)
            .filter(PaperTradeValidityCheck.order_id == order_id)
            .order_by(PaperTradeValidityCheck.id.asc())
            .all()
        )

    def get_positions(self, account_id: int) -> list[PaperPosition]:
        return list(
            self.session.query(PaperPosition)
            .filter(PaperPosition.account_id == account_id)
            .order_by(PaperPosition.symbol.asc())
            .all()
        )

    def count_position_lots(self, account_id: int) -> int:
        return int(
            self.session.query(func.count(PaperPositionLot.id))
            .filter(PaperPositionLot.account_id == account_id)
            .scalar()
        )

    def upsert_position(
        self,
        account_id: int,
        market: str | Market,
        symbol: str,
        total_quantity: int | Decimal,
        frozen_quantity: int | Decimal,
        cost_amount: Decimal,
        realized_pnl: Decimal = Decimal("0"),
        source: str = "trade",
    ) -> PaperPosition:
        market = Market(market).value
        source = PositionSource(source).value
        position = self.get_position(account_id, market, symbol)
        if position is None:
            position = PaperPosition(account_id=account_id, market=market, symbol=symbol, source=source)
            self.session.add(position)
        position.total_quantity = _whole_quantity(total_quantity, "total_quantity")
        position.frozen_quantity = _whole_quantity(frozen_quantity, "frozen_quantity")
        position.cost_amount = quantize_account_money(cost_amount)
        position.realized_pnl = quantize_account_money(realized_pnl)
        self.session.flush()
        return position

    def create_position_lot(
        self,
        account_id: int,
        market: str | Market,
        symbol: str,
        buy_trade_date: date,
        original_quantity: int | Decimal,
        remaining_quantity: int | Decimal,
        cost_price: Decimal,
        source: str = "trade",
    ) -> PaperPositionLot:
        market = Market(market).value
        lot = PaperPositionLot(
            account_id=account_id,
            symbol=symbol,
            buy_trade_date=buy_trade_date,
            original_quantity=_whole_quantity(original_quantity, "original_quantity"),
            remaining_quantity=_whole_quantity(remaining_quantity, "remaining_quantity"),
            cost_price=quantize_account_money(cost_price),
            source=PositionSource(source).value,
            market=market,
        )
        self.session.add(lot)
        self.session.flush()
        return lot

    def create_initial_snapshot(self, account: PaperAccount, *, event_at: datetime) -> PaperAccountSnapshot:
        if event_at.tzinfo is None or event_at.utcoffset() is None:
            raise ValueError("event_at must include a timezone offset")
        initial_cash = quantize_account_money(Decimal(account.initial_cash))
        initial_shares = quantize_shares(initial_cash)
        event_at = event_at.astimezone(timezone.utc)
        snapshot = PaperAccountSnapshot(
            account_id=account.id,
            trade_date=event_at.date(),
            event_at=event_at,
            point_type=SnapshotPointType.INITIAL.value,
            quality_status=SnapshotQualityStatus.VALID.value,
            cash_available=initial_cash,
            cash_frozen=Decimal("0.0000"),
            market_value=Decimal("0.0000"),
            total_assets=initial_cash,
            realized_pnl=Decimal("0.0000"),
            unrealized_pnl=Decimal("0.0000"),
            position_count=0,
            order_count=0,
            trade_count=0,
            pending_settlement=Decimal("0.0000"),
            net_asset_value=Decimal("1.000000"),
            share_count=initial_shares,
            cumulative_deposit=initial_cash,
            cumulative_withdrawal=Decimal("0.0000"),
            net_cash_flow=initial_cash,
            event_time_provenance=ReplayTimeProvenance.CANONICAL_UTC.value,
        )
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    def save_snapshot(self, **values: Any) -> PaperAccountSnapshot:
        event_at = values.get("event_at")
        if event_at is not None and (event_at.tzinfo is None or event_at.utcoffset() is None):
            raise ValueError("event_at must include a timezone offset")
        if event_at is not None:
            values["event_at"] = event_at.astimezone(timezone.utc)
        values["event_time_provenance"] = ReplayTimeProvenance.CANONICAL_UTC.value
        self._quantize_snapshot_values(values)
        snapshot = PaperAccountSnapshot(**values)
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    def save_trading_snapshot(self, **values: Any) -> PaperAccountSnapshot:
        """Create or update the single trading snapshot for an account date."""
        event_at = values.get("event_at")
        if event_at is not None and (event_at.tzinfo is None or event_at.utcoffset() is None):
            raise ValueError("event_at must include a timezone offset")
        if event_at is not None:
            values["event_at"] = event_at.astimezone(timezone.utc)
        values["event_time_provenance"] = ReplayTimeProvenance.CANONICAL_UTC.value
        self._quantize_snapshot_values(values)
        account_id = values["account_id"]
        trade_date = values["trade_date"]
        snapshot = (
            self.session.query(PaperAccountSnapshot)
            .filter_by(
                account_id=account_id,
                trade_date=trade_date,
                point_type=SnapshotPointType.TRADING.value,
            )
            .one_or_none()
        )
        if snapshot is None:
            snapshot = PaperAccountSnapshot(**values)
            self.session.add(snapshot)
        else:
            for field, value in values.items():
                setattr(snapshot, field, value)
        self.session.flush()
        for field, value in values.items():
            setattr(snapshot, field, value)
        return snapshot

    @staticmethod
    def _quantize_snapshot_values(values: dict[str, Any]) -> None:
        for field_name in (
            "cash_available",
            "cash_frozen",
            "market_value",
            "total_assets",
            "realized_pnl",
            "unrealized_pnl",
            "cumulative_deposit",
            "cumulative_withdrawal",
            "net_cash_flow",
            "pending_settlement",
        ):
            if field_name in values and values[field_name] is not None:
                values[field_name] = quantize_account_money(values[field_name])
        if values.get("net_asset_value") is not None:
            values["net_asset_value"] = quantize_nav(values["net_asset_value"])
        if values.get("share_count") is not None:
            values["share_count"] = quantize_shares(values["share_count"])

    def delete_trading_snapshot(self, account_id: int, trade_date: date) -> None:
        (
            self.session.query(PaperAccountSnapshot)
            .filter_by(
                account_id=account_id,
                trade_date=trade_date,
                point_type=SnapshotPointType.TRADING.value,
            )
            .delete(synchronize_session="fetch")
        )
        self.session.flush()

    def replace_trading_snapshots(
        self,
        account_id: int,
        start_date: date,
        end_date: date,
        snapshots: list[dict[str, Any]],
    ) -> list[PaperAccountSnapshot]:
        """Replace only derived trading snapshots in an inclusive account/date range."""
        if start_date > end_date:
            raise ValueError("start_date must not be after end_date")
        for values in snapshots:
            if not isinstance(values, dict):
                raise ValueError("snapshot replacement values must be mappings")
            if values.get("account_id") != account_id:
                raise ValueError("snapshot account_id must match replacement account")
            if values.get("point_type", SnapshotPointType.TRADING.value) != SnapshotPointType.TRADING.value:
                raise ValueError("snapshot replacement can only write trading points")
            try:
                SnapshotQualityStatus(values.get("quality_status", SnapshotQualityStatus.VALID.value))
            except ValueError as exc:
                raise ValueError("snapshot quality_status must be a valid SnapshotQualityStatus") from exc
            trade_date = values.get("trade_date")
            if not isinstance(trade_date, date) or not start_date <= trade_date <= end_date:
                raise ValueError("snapshot trade_date must be within replacement range")
            event_at = values.get("event_at")
            if event_at is not None and (event_at.tzinfo is None or event_at.utcoffset() is None):
                raise ValueError("snapshot event_at must include a timezone offset")
            for field_name in (
                "cash_available", "cash_frozen", "market_value", "total_assets",
                "realized_pnl", "unrealized_pnl", "net_asset_value", "share_count",
                "cumulative_deposit", "cumulative_withdrawal", "net_cash_flow", "pending_settlement",
            ):
                if field_name in values and values[field_name] is not None:
                    require_finite(Decimal(values[field_name]), field_name)
        with self.session.begin_nested():
            (
                self.session.query(PaperAccountSnapshot)
                .filter(
                    PaperAccountSnapshot.account_id == account_id,
                    PaperAccountSnapshot.point_type == SnapshotPointType.TRADING.value,
                    PaperAccountSnapshot.trade_date >= start_date,
                    PaperAccountSnapshot.trade_date <= end_date,
                )
                .delete(synchronize_session="fetch")
            )
            self.session.flush()
            return [
                self.save_trading_snapshot(**{**values, "point_type": SnapshotPointType.TRADING.value})
                for values in snapshots
            ]

    def count_orders(self, account_id: int, trade_date: date) -> int:
        return int(
            self.session.query(func.count(PaperOrder.id))
            .filter(PaperOrder.account_id == account_id, PaperOrder.trade_date == trade_date)
            .scalar()
        )

    def count_trades(self, account_id: int, trade_date: date) -> int:
        return int(
            self.session.query(func.count(PaperTrade.id))
            .filter(PaperTrade.account_id == account_id, PaperTrade.trade_date == trade_date)
            .scalar()
        )

    def update_matching_run_counts(
        self,
        run: PaperMatchingRun,
        processed: int,
        filled: int,
        skipped: int,
        rejected: int,
        failed: int,
        status: str,
        warning_count: int = 0,
        error_details: str | None = None,
    ) -> PaperMatchingRun:
        run.processed_count = processed
        run.filled_count = filled
        run.skipped_count = skipped
        run.rejected_count = rejected
        run.failed_count = failed
        run.warning_count = warning_count
        run.status = status
        run.error_details = error_details
        run.finished_at = datetime.now(timezone.utc)
        self.session.flush()
        return run

    def create_matching_run(self, trade_date: date, account_id: int | None, status: str) -> PaperMatchingRun:
        run = PaperMatchingRun(trade_date=trade_date, account_id=account_id, status=status)
        self.session.add(run)
        self.session.flush()
        return run

    def acquire_matching_run(self, trade_date: date, account_id: int | None) -> tuple[PaperMatchingRun, bool]:
        """Acquire the sole active run for a date/account scope.

        The unique active-scope index installed by the schema migration closes
        the race between the lookup and insert on databases supporting it.
        """
        active = (
            self.session.query(PaperMatchingRun)
            .filter(
                PaperMatchingRun.trade_date == trade_date,
                PaperMatchingRun.account_id == account_id,
                PaperMatchingRun.scope_key == (str(account_id) if account_id is not None else "all"),
                PaperMatchingRun.status == MatchingRunStatus.RUNNING.value,
            )
            .with_for_update()
            .first()
        )
        if active is not None:
            return active, False
        run = PaperMatchingRun(
            trade_date=trade_date,
            account_id=account_id,
            scope_key=str(account_id) if account_id is not None else "all",
            status=MatchingRunStatus.RUNNING.value,
        )
        self.session.add(run)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            active = (
                self.session.query(PaperMatchingRun)
                .filter(
                    PaperMatchingRun.trade_date == trade_date,
                    PaperMatchingRun.scope_key == (str(account_id) if account_id is not None else "all"),
                    PaperMatchingRun.status == MatchingRunStatus.RUNNING.value,
                )
                .first()
            )
            if active is None:
                raise
            return active, False
        return run, True

    def list_matching_runs(self) -> list[PaperMatchingRun]:
        return list(self.session.query(PaperMatchingRun).order_by(PaperMatchingRun.id.asc()).all())

    def get_matching_run(self, run_id: int) -> PaperMatchingRun:
        run = cast(PaperMatchingRun | None, self.session.get(PaperMatchingRun, run_id))
        if run is None:
            raise KeyError(f"paper matching run not found: {run_id}")
        return run

    def create_trade(
        self,
        order_id: int,
        account_id: int,
        symbol: str,
        side: OrderSide,
        quantity: int,
        price: Decimal,
        amount: Decimal,
        fees: Decimal,
        trade_date: date,
        comment: str | None = None,
        market: str | None = None,
        trade_time: datetime | None = None,
    ) -> PaperTrade:
        if trade_time is not None and (trade_time.tzinfo is None or trade_time.utcoffset() is None):
            raise ValueError("trade_time must include a timezone offset")
        trade = PaperTrade(
            order_id=order_id,
            account_id=account_id,
            symbol=symbol,
            side=side.value,
            quantity=_whole_quantity(quantity, "quantity"),
            price=quantize_account_money(price),
            amount=quantize_account_money(amount),
            fees=quantize_account_money(fees),
            trade_date=trade_date,
            trade_time=(trade_time or datetime.now(timezone.utc)).astimezone(timezone.utc),
            comment=self._normalize_comment(comment),
            market=Market(market or Market.A_SHARE).value,
            event_time_provenance=ReplayTimeProvenance.CANONICAL_UTC.value,
        )
        self.session.add(trade)
        self.session.flush()
        return trade

    def update_order_comment(self, order: PaperOrder, comment: str | None) -> PaperOrder:
        normalized = self._normalize_comment(comment)
        order.comment = normalized
        order.updated_at = datetime.now(timezone.utc)
        self.session.query(PaperTrade).filter(PaperTrade.order_id == order.id).update(
            {PaperTrade.comment: normalized},
            synchronize_session="fetch",
        )
        self.session.flush()
        return order

    def get_position(self, account_id: int, market: str | Market, symbol: str) -> PaperPosition | None:
        market = Market(market).value
        return (
            self.session.query(PaperPosition)
            .filter(
                PaperPosition.account_id == account_id,
                PaperPosition.market == market,
                PaperPosition.symbol == symbol,
            )
            .one_or_none()
        )

    def lock_position(self, account_id: int, market: str | Market, symbol: str) -> PaperPosition | None:
        query = self.session.query(PaperPosition).filter(
            PaperPosition.account_id == account_id,
            PaperPosition.market == Market(market).value,
            PaperPosition.symbol == symbol,
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            query = query.with_for_update()
        return query.one_or_none()

    def lock_lots(self, account_id: int, market: str | Market, symbol: str) -> list[PaperPositionLot]:
        query = self.session.query(PaperPositionLot).filter(
            PaperPositionLot.account_id == account_id,
            PaperPositionLot.market == Market(market).value,
            PaperPositionLot.symbol == symbol,
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            query = query.with_for_update()
        return list(query.order_by(PaperPositionLot.buy_trade_date.asc(), PaperPositionLot.id.asc()).all())

    def delete_position(self, position: PaperPosition) -> None:
        self.session.delete(position)
        self.session.flush()

    def get_lots(self, account_id: int, market: str | Market, symbol: str) -> list[PaperPositionLot]:
        market = Market(market).value
        return list(
            self.session.query(PaperPositionLot)
            .filter(
                PaperPositionLot.account_id == account_id,
                PaperPositionLot.market == market,
                PaperPositionLot.symbol == symbol,
            )
            .order_by(PaperPositionLot.buy_trade_date.asc(), PaperPositionLot.id.asc())
            .all()
        )

    def create_round_trip(
        self,
        account_id: int,
        market: str | Market,
        symbol: str,
        open_trade_id: int,
        open_trade_date: date,
        entry_amount: Decimal,
        fees: Decimal,
    ) -> PaperPositionRoundTrip:
        cycle = PaperPositionRoundTrip(
            account_id=account_id,
            market=Market(market).value,
            symbol=symbol,
            open_trade_id=open_trade_id,
            open_trade_date=open_trade_date,
            entry_amount=entry_amount,
            fees=fees,
            status=RoundTripStatus.OPEN.value,
        )
        self.session.add(cycle)
        self.session.flush()
        return cycle

    def get_open_round_trip(self, account_id: int, market: str | Market, symbol: str) -> PaperPositionRoundTrip | None:
        market = Market(market).value
        return (
            self.session.query(PaperPositionRoundTrip)
            .filter(
                PaperPositionRoundTrip.account_id == account_id,
                PaperPositionRoundTrip.market == market,
                PaperPositionRoundTrip.symbol == symbol,
                PaperPositionRoundTrip.status == RoundTripStatus.OPEN.value,
            )
            .order_by(PaperPositionRoundTrip.id.desc())
            .first()
        )

    def update_round_trip(self, cycle: PaperPositionRoundTrip, **values: Any) -> PaperPositionRoundTrip:
        for key, value in values.items():
            setattr(cycle, key, value)
        cycle.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return cycle

    def list_round_trips(self, account_id: int) -> list[PaperPositionRoundTrip]:
        return list(
            self.session.query(PaperPositionRoundTrip)
            .filter(PaperPositionRoundTrip.account_id == account_id)
            .order_by(PaperPositionRoundTrip.open_trade_date.asc(), PaperPositionRoundTrip.id.asc())
            .all()
        )

    def delete_round_trips(self, account_id: int) -> int:
        deleted = (
            self.session.query(PaperPositionRoundTrip)
            .filter(PaperPositionRoundTrip.account_id == account_id)
            .delete(synchronize_session=False)
        )
        self.session.flush()
        return int(deleted)

    def delete_order(self, order_id: int) -> PaperOrder | None:
        order = cast(PaperOrder | None, self.session.get(PaperOrder, order_id))
        if order is None:
            return None
        self.session.delete(order)
        return order

    def create_ledger_rebuild(
        self,
        account_id: int,
        start_date: date,
        triggering_order_ids: list[int],
        deleted_counts: dict[str, int],
        regenerated_counts: dict[str, int],
    ) -> PaperLedgerRebuild:
        rebuild = PaperLedgerRebuild(
            account_id=account_id,
            start_date=start_date,
            triggering_order_ids=triggering_order_ids,
            trigger_evidence={"triggering_order_ids": triggering_order_ids},
            status=LedgerRebuildStatus.COMPLETED.value,
            deleted_counts=deleted_counts,
            regenerated_counts=regenerated_counts,
            finished_at=datetime.now(timezone.utc),
        )
        self.session.add(rebuild)
        self.session.flush()
        return rebuild

    def create_ledger_rebuild_started(
        self,
        account_id: int,
        start_date: date,
        trigger_evidence: dict[str, Any] | None = None,
        triggering_order_ids: list[int] | None = None,
    ) -> PaperLedgerRebuild:
        rebuild = PaperLedgerRebuild(
            account_id=account_id,
            start_date=start_date,
            triggering_order_ids=triggering_order_ids or [],
            trigger_evidence=trigger_evidence or {},
            status=LedgerRebuildStatus.RUNNING.value,
            deleted_counts={},
            regenerated_counts={},
        )
        self.session.add(rebuild)
        self.session.flush()
        return rebuild

    def complete_ledger_rebuild(
        self,
        rebuild: PaperLedgerRebuild,
        deleted_counts: dict[str, int],
        regenerated_counts: dict[str, int],
    ) -> PaperLedgerRebuild:
        rebuild.status = LedgerRebuildStatus.COMPLETED.value
        rebuild.deleted_counts = deleted_counts
        rebuild.regenerated_counts = regenerated_counts
        rebuild.error_details = None
        rebuild.finished_at = datetime.now(timezone.utc)
        self.session.flush()
        return rebuild

    def create_ledger_rebuild_failed(
        self,
        account_id: int,
        start_date: date,
        trigger_evidence: dict[str, Any] | None,
        error_details: str,
        deleted_counts: dict[str, int] | None = None,
        regenerated_counts: dict[str, int] | None = None,
        triggering_order_ids: list[int] | None = None,
    ) -> PaperLedgerRebuild:
        rebuild = PaperLedgerRebuild(
            account_id=account_id,
            start_date=start_date,
            triggering_order_ids=triggering_order_ids or [],
            trigger_evidence=trigger_evidence or {},
            status=LedgerRebuildStatus.FAILED.value,
            deleted_counts=deleted_counts or {},
            regenerated_counts=regenerated_counts or {},
            error_details=error_details,
            finished_at=datetime.now(timezone.utc),
        )
        self.session.add(rebuild)
        self.session.flush()
        return rebuild

    def _rebuild_positions_from_surviving_lots(self, account_id: int) -> None:
        self.session.query(PaperPosition).filter(PaperPosition.account_id == account_id).delete(
            synchronize_session="fetch"
        )
        lots = (
            self.session.query(PaperPositionLot)
            .filter(PaperPositionLot.account_id == account_id, PaperPositionLot.remaining_quantity > 0)
            .order_by(PaperPositionLot.market.asc(), PaperPositionLot.symbol.asc(), PaperPositionLot.id.asc())
            .all()
        )
        total_qty: dict[tuple[str, str], int] = defaultdict(int)
        total_cost: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
        sources: dict[tuple[str, str], set[str]] = defaultdict(set)
        for lot in lots:
            key = (lot.market, lot.symbol)
            remaining_quantity = int(lot.remaining_quantity or 0)
            total_qty[key] += remaining_quantity
            total_cost[key] += Decimal(lot.cost_price) * remaining_quantity
            sources[key].add(lot.source)
        for market, symbol in total_qty:
            source = (
                PositionSource.IMPORTED.value
                if sources[(market, symbol)] == {PositionSource.IMPORTED.value}
                else PositionSource.TRADE.value
            )
            self.session.add(
                PaperPosition(
                    account_id=account_id,
                    symbol=symbol,
                    total_quantity=total_qty[(market, symbol)],
                    frozen_quantity=0,
                    cost_amount=quantize_account_money(total_cost[(market, symbol)]),
                    realized_pnl=Decimal("0"),
                    source=source,
                    market=market,
                )
            )

    def _restore_lot_quantities_as_of(self, account_id: int, start_date: date) -> Decimal:
        self.session.query(PaperPositionLot).filter(PaperPositionLot.account_id == account_id).update(
            {PaperPositionLot.remaining_quantity: PaperPositionLot.original_quantity},
            synchronize_session="fetch",
        )
        realized_pnl = Decimal("0")
        pre_start_sells = (
            self.session.query(PaperTrade)
            .filter(
                PaperTrade.account_id == account_id,
                PaperTrade.trade_date < start_date,
                PaperTrade.side == OrderSide.SELL.value,
            )
            .order_by(PaperTrade.trade_date.asc(), PaperTrade.id.asc())
            .all()
        )
        for trade in pre_start_sells:
            remaining = int(trade.quantity)
            cost_reduction = Decimal("0")
            for lot in self.get_lots(account_id, trade.market, trade.symbol):
                if remaining <= 0:
                    break
                available = int(lot.remaining_quantity or 0)
                used = min(available, remaining)
                lot.remaining_quantity = available - used
                cost_reduction += Decimal(used) * Decimal(lot.cost_price)
                remaining -= used
            realized_pnl += Decimal(trade.amount) - Decimal(trade.fees) - cost_reduction
        return quantize_account_money(realized_pnl)

    def clear_account_rebuild_state_from(self, account_id: int, start_date: date) -> dict[str, int]:
        counts: dict[str, int] = {}
        account = self.get_account(account_id)
        if account is None:
            raise KeyError(f"paper account not found: {account_id}")
        deleted_trade_ids = [
            row[0]
            for row in self.session.query(PaperTrade.id)
            .filter(PaperTrade.account_id == account_id, PaperTrade.trade_date >= start_date)
            .all()
        ]
        cash_event_delete_predicates = [PaperCashLedger.trade_date >= start_date]
        pending_settlement_delete_predicates = [PaperPendingSettlement.expected_settle_date >= start_date]
        if deleted_trade_ids:
            cash_event_delete_predicates.append(PaperCashLedger.trade_id.in_(deleted_trade_ids))
            pending_settlement_delete_predicates.append(PaperPendingSettlement.trade_id.in_(deleted_trade_ids))
        counts["cash_events"] = (
            self.session.query(PaperCashLedger)
            .filter(
                PaperCashLedger.account_id == account_id,
                PaperCashLedger.event_type.in_(
                    [
                        CashEventType.FREEZE.value,
                        CashEventType.RELEASE.value,
                        CashEventType.TRADE.value,
                        CashEventType.FEE.value,
                    ]
                ),
                or_(*cash_event_delete_predicates),
            )
            .delete(synchronize_session=False)
        )
        counts["round_trips"] = (
            self.session.query(PaperPositionRoundTrip)
            .filter(
                PaperPositionRoundTrip.account_id == account_id,
                or_(
                    PaperPositionRoundTrip.open_trade_date >= start_date,
                    PaperPositionRoundTrip.close_trade_date >= start_date,
                ),
            )
            .delete(synchronize_session=False)
        )
        counts["snapshots"] = (
            self.session.query(PaperAccountSnapshot)
            .filter(
                PaperAccountSnapshot.account_id == account_id,
                PaperAccountSnapshot.trade_date >= start_date,
                PaperAccountSnapshot.point_type == SnapshotPointType.TRADING.value,
            )
            .delete(synchronize_session=False)
        )
        counts["valuation_gaps"] = (
            self.session.query(PaperValuationGap)
            .filter(PaperValuationGap.account_id == account_id, PaperValuationGap.trade_date >= start_date)
            .delete(synchronize_session=False)
        )
        counts["pending_settlements"] = (
            self.session.query(PaperPendingSettlement)
            .filter(
                PaperPendingSettlement.account_id == account_id,
                or_(*pending_settlement_delete_predicates),
            )
            .delete(synchronize_session=False)
        )
        counts["trades"] = (
            self.session.query(PaperTrade)
            .filter(PaperTrade.account_id == account_id, PaperTrade.trade_date >= start_date)
            .delete(synchronize_session=False)
        )
        counts["trade_lots"] = (
            self.session.query(PaperPositionLot)
            .filter(
                PaperPositionLot.account_id == account_id,
                PaperPositionLot.source == PositionSource.TRADE.value,
                PaperPositionLot.buy_trade_date >= start_date,
            )
            .delete(synchronize_session=False)
        )
        account.realized_pnl = self._restore_lot_quantities_as_of(account_id, start_date)
        self._rebuild_positions_from_surviving_lots(account_id)
        self.session.flush()
        return {key: int(value) for key, value in counts.items()}

    def clear_account_rebuild_state(
        self, account_id: int, *, preserve_execution_history: bool = False
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        account = self.get_account(account_id)
        if account is None:
            raise KeyError(f"paper account not found: {account_id}")
        account.realized_pnl = Decimal("0")
        imported_lots = (
            self.session.query(PaperPositionLot)
            .filter(
                PaperPositionLot.account_id == account_id,
                PaperPositionLot.source == PositionSource.IMPORTED.value,
            )
            .all()
        )
        if not preserve_execution_history:
            counts["validity_checks"] = (
                self.session.query(PaperTradeValidityCheck)
                .filter(PaperTradeValidityCheck.account_id == account_id)
                .delete(synchronize_session=False)
            )
        counts["cash_events"] = (
            self.session.query(PaperCashLedger)
            .filter(
                PaperCashLedger.account_id == account_id,
                PaperCashLedger.event_type.in_(
                    [
                        CashEventType.FREEZE.value,
                        CashEventType.RELEASE.value,
                        CashEventType.TRADE.value,
                        CashEventType.FEE.value,
                    ]
                ),
            )
            .delete(synchronize_session=False)
        )
        counts["round_trips"] = (
            self.session.query(PaperPositionRoundTrip)
            .filter(PaperPositionRoundTrip.account_id == account_id)
            .delete(synchronize_session=False)
        )
        counts["trades"] = (
            self.session.query(PaperTrade).filter(PaperTrade.account_id == account_id).delete(synchronize_session=False)
        )
        counts["snapshots"] = (
            self.session.query(PaperAccountSnapshot)
            .filter(
                PaperAccountSnapshot.account_id == account_id,
                PaperAccountSnapshot.point_type == SnapshotPointType.TRADING.value,
            )
            .delete(synchronize_session=False)
        )
        counts["pending_settlements"] = (
            self.session.query(PaperPendingSettlement)
            .filter(PaperPendingSettlement.account_id == account_id)
            .delete(synchronize_session=False)
        )
        if not preserve_execution_history:
            counts["matching_runs"] = (
                self.session.query(PaperMatchingRun)
                .filter(PaperMatchingRun.account_id == account_id)
                .delete(synchronize_session=False)
            )
        # Delete trade-derived lots; imported lots are the durable baseline.
        counts["trade_lots"] = (
            self.session.query(PaperPositionLot)
            .filter(
                PaperPositionLot.account_id == account_id,
                PaperPositionLot.source == PositionSource.TRADE.value,
            )
            .delete(synchronize_session=False)
        )
        # Reset imported lots to their original quantity (undo any sell reductions).
        self.session.query(PaperPositionLot).filter(
            PaperPositionLot.account_id == account_id,
            PaperPositionLot.source == PositionSource.IMPORTED.value,
        ).update(
            {PaperPositionLot.remaining_quantity: PaperPositionLot.original_quantity},
            synchronize_session="fetch",
        )
        imported_lots = (
            self.session.query(PaperPositionLot)
            .filter(
                PaperPositionLot.account_id == account_id,
                PaperPositionLot.source == PositionSource.IMPORTED.value,
            )
            .all()
        )
        # Delete all positions (aggregate state must be rebuilt from imported lots).
        counts["positions"] = (
            self.session.query(PaperPosition)
            .filter(PaperPosition.account_id == account_id)
            .delete(synchronize_session="fetch")
        )
        # Rebuild aggregate positions from surviving imported lots.
        total_qty: dict[tuple[str, str], int] = defaultdict(int)
        total_cost: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
        for lot in imported_lots:
            key = (lot.market, lot.symbol)
            total_qty[key] += int(lot.remaining_quantity)
            total_cost[key] += Decimal(lot.cost_price) * int(lot.remaining_quantity)
        for market, symbol in total_qty:
            position = PaperPosition(
                account_id=account_id,
                symbol=symbol,
                total_quantity=total_qty[(market, symbol)],
                frozen_quantity=0,
                cost_amount=quantize_account_money(total_cost[(market, symbol)]),
                realized_pnl=Decimal("0"),
                source=PositionSource.IMPORTED.value,
                market=market,
            )
            self.session.add(position)
        self.session.flush()
        return {key: int(value) for key, value in counts.items()}

    def reset_orders_for_replay(self, account_id: int) -> None:
        # Reset orders that can be replayed (active statuses).
        self.session.query(PaperOrder).filter(
            PaperOrder.account_id == account_id,
            PaperOrder.status.in_(
                [
                    OrderStatus.ACCEPTED.value,
                    OrderStatus.FILLED.value,
                    OrderStatus.PARTIALLY_FILLED.value,
                    OrderStatus.NEW.value,
                ]
            ),
        ).update(
            {
                PaperOrder.status: OrderStatus.ACCEPTED.value,
                PaperOrder.filled_quantity: 0,
                PaperOrder.rejection_code: None,
                PaperOrder.rejection_reason: None,
            },
            synchronize_session=False,
        )
        # Also reset REJECTED orders whose rejection was induced by a prior
        # replay (carry the replay marker).  These rejections may become
        # resolvable after a later delete and should be reconsidered.
        self.session.query(PaperOrder).filter(
            PaperOrder.account_id == account_id,
            PaperOrder.status == OrderStatus.REJECTED.value,
            PaperOrder.rejection_reason.like(f"{REPLAY_REJECTION_MARKER}%"),
        ).update(
            {
                PaperOrder.status: OrderStatus.ACCEPTED.value,
                PaperOrder.filled_quantity: 0,
                PaperOrder.rejection_code: None,
                PaperOrder.rejection_reason: None,
            },
            synchronize_session=False,
        )
        self.session.flush()

    def reset_orders_for_replay_from(self, account_id: int, start_date: date) -> None:
        self.session.query(PaperOrder).filter(
            PaperOrder.account_id == account_id,
            PaperOrder.trade_date >= start_date,
            PaperOrder.status.in_(
                [
                    OrderStatus.ACCEPTED.value,
                    OrderStatus.FILLED.value,
                    OrderStatus.PARTIALLY_FILLED.value,
                    OrderStatus.NEW.value,
                ]
            ),
        ).update(
            {
                PaperOrder.status: OrderStatus.ACCEPTED.value,
                PaperOrder.filled_quantity: 0,
                PaperOrder.rejection_code: None,
                PaperOrder.rejection_reason: None,
            },
            synchronize_session=False,
        )
        self.session.query(PaperOrder).filter(
            PaperOrder.account_id == account_id,
            PaperOrder.trade_date >= start_date,
            PaperOrder.status == OrderStatus.REJECTED.value,
            PaperOrder.rejection_reason.like(f"{REPLAY_REJECTION_MARKER}%"),
        ).update(
            {
                PaperOrder.status: OrderStatus.ACCEPTED.value,
                PaperOrder.filled_quantity: 0,
                PaperOrder.rejection_code: None,
                PaperOrder.rejection_reason: None,
            },
            synchronize_session=False,
        )
        self.session.flush()

    # ------------------------------------------------------------------
    # Pending settlement (HK Connect)
    # ------------------------------------------------------------------

    def create_pending_settlement(
        self,
        account_id: int,
        amount: Decimal,
        expected_settle_date: date,
        trade_id: int | None = None,
        source: str = PendingSettlementSource.HK_SELL.value,
    ) -> PaperPendingSettlement:
        pending = PaperPendingSettlement(
            account_id=account_id,
            amount=quantize_account_money(amount),
            expected_settle_date=expected_settle_date,
            trade_id=trade_id,
            source=PendingSettlementSource(source).value,
            settled=False,
        )
        self.session.add(pending)
        self.session.flush()
        return pending

    def list_pending_settlements(self, account_id: int) -> list[PaperPendingSettlement]:
        return list(
            self.session.query(PaperPendingSettlement)
            .filter(
                PaperPendingSettlement.account_id == account_id,
                PaperPendingSettlement.settled.is_(False),
            )
            .order_by(PaperPendingSettlement.expected_settle_date.asc())
            .all()
        )

    def settle_pending(self, pending_id: int) -> PaperPendingSettlement:
        pending = cast(PaperPendingSettlement, self.session.get(PaperPendingSettlement, pending_id))
        if pending is None:
            raise KeyError(f"pending settlement not found: {pending_id}")
        if pending.settled:
            return pending
        pending.settled = True
        # Add cash to ledger as trade event
        amount = self._get_decimal_value(PaperPendingSettlement.amount, PaperPendingSettlement.id == pending_id)
        assert amount is not None
        self.add_cash_event(
            pending.account_id,
            CashEventType.TRADE,
            amount,
            trade_id=pending.trade_id,
            note="hk_sell_settlement",
        )
        self.session.flush()
        return pending

    def get_pending_settlement_total(self, account_id: int) -> Decimal:
        return self.get_pending_settlement_total_internal(account_id).quantize(Decimal("0.0001"))

    def get_pending_settlement_total_internal(self, account_id: int) -> Decimal:
        query: Any = self.session.query(PaperPendingSettlement.amount).filter(
            PaperPendingSettlement.account_id == account_id,
            PaperPendingSettlement.settled.is_(False),
        )
        if self.session.bind is not None and self.session.bind.dialect.name == "sqlite":
            query = self.session.query(sa_cast(PaperPendingSettlement.amount, String)).filter(
                PaperPendingSettlement.account_id == account_id,
                PaperPendingSettlement.settled.is_(False),
            )
        values = (Decimal(str(row[0])) for row in query.all())
        return quantize_account_money(sum(values, Decimal("0")))

    def list_order_trade_dates(self, account_id: int) -> list[date]:
        rows = (
            self.session.query(PaperOrder.trade_date)
            .filter(PaperOrder.account_id == account_id)
            .distinct()
            .order_by(PaperOrder.trade_date.asc())
            .all()
        )
        return [row[0] for row in rows]
