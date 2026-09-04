from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import Boolean, Enum, UniqueConstraint, create_engine, inspect
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

# Initialize the storage facade before its paper-trading model re-export.
import storage  # noqa: F401
from paper_trading.domain.enums import (
    Market,
    MatchingRunStatus,
    MigrationRepairReason,
    PaperOrderEventType,
    SnapshotPointType,
    SnapshotQualityStatus,
    SnapshotValuationQuality,
)
from paper_trading.storage.models import (
    DailyBarDiagnostic,
    PaperAccount,
    PaperAccountSnapshot,
    PaperCashLedger,
    PaperLedgerRebuild,
    PaperMatchingRun,
    PaperOrder,
    PaperOrderEvent,
    PaperPendingSettlement,
    PaperPosition,
    PaperPositionLot,
    PaperPositionRoundTrip,
    PaperTrade,
    PaperTradeValidityCheck,
    tb_name_daily_bar_diagnostics,
    tb_name_paper_accounts,
    tb_name_paper_orders,
    tb_name_paper_trade_validity_checks,
    tb_name_paper_trades,
)
from storage.model.base import Base


def test_position_lot_market_defaults_to_a_share(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        lot = PaperPositionLot(
            account_id=1,
            symbol="000001",
            buy_trade_date=date(2026, 7, 27),
            original_quantity=100,
            remaining_quantity=100,
            cost_price=Decimal("10.00"),
        )
        session.add(lot)
        session.flush()
        assert lot.market == "a_share"

    market_column = PaperPositionLot.__table__.c.market
    assert market_column.nullable is False
    assert market_column.server_default is not None
    engine.dispose()


def test_order_event_model_has_immutable_lifecycle_fact_contract():
    assert set(PaperOrderEventType) == {
        PaperOrderEventType.ACCEPTED,
        PaperOrderEventType.RESERVED,
        PaperOrderEventType.FILL,
        PaperOrderEventType.CANCEL,
        PaperOrderEventType.REJECT,
        PaperOrderEventType.RELEASE,
    }
    columns = PaperOrderEvent.__table__.c
    assert {
        "id",
        "account_id",
        "order_id",
        "trade_id",
        "market",
        "symbol",
        "event_type",
        "event_at",
        "quantity_delta",
        "cash_delta",
        "idempotency_key",
    } <= set(columns.keys())
    assert columns.event_at.nullable is False
    assert columns.quantity_delta.nullable is False
    assert columns.cash_delta.nullable is False
    assert columns.idempotency_key.nullable is False
    index_names = {index.name for index in PaperOrderEvent.__table__.indexes}
    assert {
        "uq_paper_order_events_idempotency",
        "ix_paper_order_events_account_event",
        "ix_paper_order_events_order_event",
    } <= index_names


def test_account_has_nullable_etf_commission_rate_column():
    column = PaperAccount.__table__.c.etf_commission_rate

    assert Market.ETF == "etf"
    assert column.nullable is True
    assert str(column.type) == "NUMERIC(20, 8)"


def test_account_has_nullable_owner_user_id_column():
    column = PaperAccount.__table__.c.owner_user_id

    assert column.nullable is True
    assert column.foreign_keys


def test_account_has_nullable_migration_repair_reason_column():
    column = PaperAccount.__table__.c.migration_repair_reason

    assert MigrationRepairReason.LEGACY_ORDERING_UNCERTAIN == "legacy_ordering_uncertain"
    assert list(MigrationRepairReason) == [MigrationRepairReason.LEGACY_ORDERING_UNCERTAIN]
    assert column.nullable is True
    assert isinstance(column.type, Enum)
    assert column.type.name == "paper_account_migration_repair_reason"
    assert column.server_default is None


def test_account_migration_repair_reason_round_trips_null_and_label(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        account = PaperAccount(name="repair-null", initial_cash=Decimal("100000.00"))
        session.add(account)
        session.flush()
        assert account.migration_repair_reason is None

        account.migration_repair_reason = MigrationRepairReason.LEGACY_ORDERING_UNCERTAIN.value
        session.commit()
        session.expire_all()

        loaded = session.get(PaperAccount, account.id)
        assert loaded is not None
        assert loaded.migration_repair_reason == MigrationRepairReason.LEGACY_ORDERING_UNCERTAIN.value

    engine.dispose()


def test_account_migration_repair_reason_rejects_unknown_value(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            PaperAccount(
                name="repair-unknown",
                initial_cash=Decimal("100000.00"),
                migration_repair_reason="unknown_repair",
            )
        )
        with pytest.raises((StatementError, ValueError)):
            session.flush()

    engine.dispose()


def test_paper_order_round_trips_nullable_and_non_nullable_values(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        order = PaperOrder(
            account_id=1,
            symbol="000001",
            side="buy",
            quantity=100,
            limit_price=Decimal("10.00"),
            trade_date=date(2026, 6, 16),
            status="accepted",
        )
        session.add(order)
        session.flush()

        assert order.quantity == 100
        assert order.rejection_code is None

    engine.dispose()


def test_paper_trading_tables_are_registered(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    assert tb_name_paper_accounts in inspector.get_table_names()
    assert tb_name_paper_orders in inspector.get_table_names()
    assert tb_name_paper_trades in inspector.get_table_names()
    assert tb_name_paper_trade_validity_checks in inspector.get_table_names()
    assert tb_name_daily_bar_diagnostics in inspector.get_table_names()

    order_columns = {column["name"] for column in inspector.get_columns(tb_name_paper_orders)}
    assert {"validity_status", "validity_reason", "validity_checked_at", "comment"} <= order_columns

    trade_columns = {column["name"] for column in inspector.get_columns(tb_name_paper_trades)}
    assert "comment" in trade_columns

    check_columns = {column["name"] for column in inspector.get_columns(tb_name_paper_trade_validity_checks)}
    assert {
        "id",
        "order_id",
        "account_id",
        "symbol",
        "trade_date",
        "side",
        "input_price",
        "daily_low",
        "daily_high",
        "limit_up_price",
        "limit_down_price",
        "touched_limit_up",
        "touched_limit_down",
        "price_in_range",
        "status",
        "reason_code",
        "reason_detail",
        "data_granularity",
        "created_at",
    } <= check_columns
    engine.dispose()


def test_daily_bar_diagnostic_has_business_key_and_json_outcomes():
    assert DailyBarDiagnostic.__table__.primary_key.columns.keys() == ["id"]
    assert {column.name for column in DailyBarDiagnostic.__table__.columns} >= {
        "business_date",
        "market",
        "stock_id",
        "adjust",
        "classification",
        "provider_outcomes",
        "first_observed_at",
        "last_observed_at",
        "resolved",
    }
    assert (
        "uq_daily_bar_diagnostics_business_key",
        ("business_date", "market", "stock_id", "adjust"),
    ) in {
        (constraint.name, tuple(column.name for column in constraint.columns))
        for constraint in DailyBarDiagnostic.__table__.constraints
        if constraint.name
    }


def test_market_qualified_position_and_round_trip_keys():
    position_constraints = {
        (constraint.name, tuple(column.name for column in constraint.columns))
        for constraint in PaperPosition.__table__.constraints
        if constraint.name
    }
    round_trip = PaperPositionRoundTrip.__table__

    assert ("uq_paper_positions_account_market_symbol", ("account_id", "market", "symbol")) in position_constraints
    assert round_trip.c.market.nullable is False
    assert round_trip.c.market.server_default is not None
    assert round_trip.c.market.type.name == "paper_market"


def test_daily_bar_diagnostic_resolved_has_postgresql_boolean_default():
    resolved = DailyBarDiagnostic.__table__.c.resolved
    assert isinstance(resolved.type, Boolean)
    assert str(resolved.server_default.arg) == "false"
    ddl = str(CreateTable(DailyBarDiagnostic.__table__).compile(dialect=dialect()))
    assert "resolved BOOLEAN DEFAULT false NOT NULL" in ddl


def test_matching_run_status_round_trips_lowercase_enum_value(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        run = PaperMatchingRun(trade_date=date(2026, 7, 31), status=MatchingRunStatus.RUNNING.value)
        session.add(run)
        session.commit()
        session.expire_all()

        loaded = session.get(PaperMatchingRun, run.id)
        assert loaded is not None
        assert loaded.status == MatchingRunStatus.RUNNING.value

    engine.dispose()


def test_matching_run_status_rejects_unknown_value(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(PaperMatchingRun(trade_date=date(2026, 7, 31), status="in_progress"))
        with pytest.raises((StatementError, ValueError)):
            session.flush()

    engine.dispose()


def test_selected_paper_columns_use_shared_value_enums():
    assert isinstance(PaperAccount.__table__.c.status.type, Enum)
    assert PaperAccount.__table__.c.status.type.name == "paper_account_status"
    assert PaperAccount.__table__.c.fee_preset.type.name == "paper_fee_preset"
    assert PaperAccount.__table__.c.migration_repair_reason.type.name == "paper_account_migration_repair_reason"
    assert PaperCashLedger.__table__.c.event_type.type.name == "paper_cash_event_type"
    assert PaperOrder.__table__.c.side.type.name == "paper_order_side"
    assert PaperTrade.__table__.c.side.type.name == "paper_order_side"
    assert PaperTradeValidityCheck.__table__.c.side.type.name == "paper_order_side"
    assert PaperOrder.__table__.c.status.type.name == "paper_order_status"
    assert PaperOrder.__table__.c.validity_status.type.name == "paper_trade_validity_status"
    assert PaperTradeValidityCheck.__table__.c.status.type.name == "paper_trade_validity_status"
    assert PaperOrder.__table__.c.market.type.name == "paper_market"
    assert PaperPosition.__table__.c.market.type.name == "paper_market"
    assert PaperPositionLot.__table__.c.market.type.name == "paper_market"
    assert PaperTrade.__table__.c.market.type.name == "paper_market"
    assert PaperTradeValidityCheck.__table__.c.market.type.name == "paper_market"
    assert PaperPositionRoundTrip.__table__.c.market.type.name == "paper_market"
    assert DailyBarDiagnostic.__table__.c.market.type.name == "paper_market"
    assert PaperPosition.__table__.c.source.type.name == "paper_position_source"
    assert PaperPositionLot.__table__.c.source.type.name == "paper_position_source"
    assert PaperPositionRoundTrip.__table__.c.status.type.name == "paper_round_trip_status"
    assert PaperTradeValidityCheck.__table__.c.data_granularity.type.name == "paper_trade_validity_granularity"
    assert PaperPendingSettlement.__table__.c.source.type.name == "paper_pending_settlement_source"
    assert PaperLedgerRebuild.__table__.c.status.type.name == "paper_ledger_rebuild_status"
    assert PaperMatchingRun.__table__.c.status.type.name == "paper_matching_run_status"
    assert PaperAccountSnapshot.__table__.c.point_type.type.name == "paper_snapshot_point_type"
    assert PaperAccountSnapshot.__table__.c.quality_status.type.name == "paper_snapshot_quality_status"
    assert PaperAccountSnapshot.__table__.c.valuation_quality.type.name == "paper_snapshot_valuation_quality"


def test_selected_paper_enum_columns_reject_unknown_values(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            PaperOrder(
                account_id=1,
                symbol="000001",
                side="borrow",
                quantity=100,
                limit_price=Decimal("10.00"),
                trade_date=date(2026, 8, 7),
                status="accepted",
            )
        )
        with pytest.raises((StatementError, ValueError)):
            session.flush()

    engine.dispose()


def test_selected_paper_enum_defaults_round_trip_as_readable_strings(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        account = PaperAccount(name="defaults", initial_cash=Decimal("100000.00"))
        session.add(account)
        session.flush()
        position = PaperPosition(account_id=account.id, symbol="000001")
        lot = PaperPositionLot(
            account_id=account.id,
            symbol="000001",
            buy_trade_date=date(2026, 8, 7),
            original_quantity=100,
            remaining_quantity=100,
            cost_price=Decimal("10.00"),
        )
        order = PaperOrder(
            account_id=account.id,
            symbol="000001",
            side="buy",
            quantity=100,
            limit_price=Decimal("10.00"),
            trade_date=date(2026, 8, 7),
            status="accepted",
        )
        session.add_all([position, lot, order])
        session.flush()
        cycle = PaperPositionRoundTrip(
            account_id=account.id,
            symbol="000001",
            open_trade_id=1,
            open_trade_date=date(2026, 8, 7),
        )
        check = PaperTradeValidityCheck(
            order_id=order.id,
            account_id=account.id,
            symbol="000001",
            trade_date=date(2026, 8, 7),
            side="buy",
            input_price=Decimal("10.00"),
            status="valid",
            reason_code="VALID",
        )
        rebuild = PaperLedgerRebuild(
            account_id=account.id,
            start_date=date(2026, 8, 7),
            triggering_order_ids=[],
            status="completed",
            trigger_evidence={"source": "test"},
            deleted_counts={},
            regenerated_counts={},
        )
        session.add_all([cycle, check, rebuild])
        session.commit()
        session.expire_all()

        loaded_account = session.get(PaperAccount, account.id)
        loaded_position = session.get(PaperPosition, position.id)
        loaded_lot = session.get(PaperPositionLot, lot.id)
        loaded_cycle = session.get(PaperPositionRoundTrip, cycle.id)
        loaded_check = session.get(PaperTradeValidityCheck, check.id)
        loaded_rebuild = session.get(PaperLedgerRebuild, rebuild.id)
        assert loaded_account is not None
        assert loaded_position is not None
        assert loaded_lot is not None
        assert loaded_cycle is not None
        assert loaded_check is not None
        assert loaded_rebuild is not None
        assert (loaded_account.status, loaded_account.fee_preset) == ("active", "a_share")
        assert (loaded_position.source, loaded_position.market) == ("trade", "a_share")
        assert (loaded_lot.source, loaded_lot.market) == ("trade", "a_share")
        assert loaded_cycle.status == "open"
        assert loaded_cycle.market == "a_share"
        assert loaded_check.data_granularity == "daily"
        assert loaded_rebuild.status == "completed"
        assert loaded_rebuild.trigger_evidence == {"source": "test"}
        assert loaded_rebuild.finished_at is None

    engine.dispose()


def _snapshot_financials() -> dict[str, Decimal | int]:
    return {
        "cash_available": Decimal("100000.0000"),
        "cash_frozen": Decimal("0.0000"),
        "market_value": Decimal("0.0000"),
        "total_assets": Decimal("100000.0000"),
        "realized_pnl": Decimal("0.0000"),
        "unrealized_pnl": Decimal("0.0000"),
        "position_count": 0,
        "order_count": 0,
        "trade_count": 0,
        "pending_settlement": Decimal("0.0000"),
    }


def _trading_snapshot(**overrides: object) -> PaperAccountSnapshot:
    values: dict[str, object] = {
        "account_id": 1,
        "trade_date": date(2026, 8, 25),
        "point_type": SnapshotPointType.TRADING.value,
        "event_at": datetime(2026, 8, 25, tzinfo=timezone.utc),
        "quality_status": SnapshotQualityStatus.VALID.value,
        **_snapshot_financials(),
    }
    values.update(overrides)
    return PaperAccountSnapshot(**values)


def test_snapshot_model_supports_ordered_quality_aware_points() -> None:
    snapshot = PaperAccountSnapshot(
        account_id=1,
        trade_date=date(2026, 8, 25),
        point_type=SnapshotPointType.INITIAL.value,
        event_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
        quality_status=SnapshotQualityStatus.VALID.value,
        invalid_reason=None,
        **_snapshot_financials(),
    )
    assert snapshot.point_type == "initial"
    assert snapshot.quality_status == "valid"
    assert snapshot.event_at == datetime(2026, 8, 25, tzinfo=timezone.utc)
    assert snapshot.invalid_reason is None
    assert PaperAccountSnapshot.__table__.c.point_type.nullable is False
    assert PaperAccountSnapshot.__table__.c.event_at.nullable is False
    assert PaperAccountSnapshot.__table__.c.quality_status.nullable is False
    assert PaperAccountSnapshot.__table__.c.invalid_reason.nullable is True
    assert PaperAccountSnapshot.__table__.c.point_type.default.arg == SnapshotPointType.TRADING.value
    assert PaperAccountSnapshot.__table__.c.quality_status.default.arg == SnapshotQualityStatus.VALID.value
    assert PaperAccountSnapshot.__table__.c.point_type.server_default is not None
    assert PaperAccountSnapshot.__table__.c.quality_status.server_default is not None
    assert PaperAccountSnapshot.__table__.c.event_at.server_default is not None
    assert SnapshotPointType.INITIAL == "initial"
    assert SnapshotPointType.TRADING == "trading"
    assert SnapshotQualityStatus.VALID == "valid"
    assert SnapshotQualityStatus.INVALID == "invalid"

    unique_constraints = {
        constraint.name
        for constraint in PaperAccountSnapshot.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert "uq_paper_account_snapshots_account_date" not in unique_constraints

    index_by_name = {index.name: index for index in PaperAccountSnapshot.__table__.indexes}
    event_index = index_by_name["ix_paper_account_snapshots_account_event"]
    assert tuple(column.name for column in event_index.columns) == ("account_id", "event_at", "id")
    assert event_index.unique is False

    initial_index = index_by_name["uq_paper_account_snapshots_account_initial"]
    assert tuple(column.name for column in initial_index.columns) == ("account_id",)
    assert initial_index.unique is True
    assert str(initial_index.dialect_options["postgresql"]["where"]) == "point_type = 'initial'"
    assert str(initial_index.dialect_options["sqlite"]["where"]) == "point_type = 'initial'"

    trading_index = index_by_name["uq_paper_account_snapshots_account_trading"]
    assert tuple(column.name for column in trading_index.columns) == ("account_id", "trade_date")
    assert trading_index.unique is True
    assert str(trading_index.dialect_options["postgresql"]["where"]) == "point_type = 'trading'"
    assert str(trading_index.dialect_options["sqlite"]["where"]) == "point_type = 'trading'"

    assert PaperAccountSnapshot.__table__.c.valuation_quality.nullable is True
    assert PaperAccountSnapshot.__table__.c.valuation_details.nullable is True
    assert SnapshotValuationQuality.CURRENT == "current"
    assert SnapshotValuationQuality.STALE_SUSPENDED == "stale_suspended"


def test_snapshot_model_persists_stale_metadata(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        snapshot = _trading_snapshot(
            valuation_quality="stale_suspended",
            valuation_details=[{"symbol": "000001.SZ", "source_date": "2026-08-22", "reason": "suspended"}],
        )
        session.add(snapshot)
        session.flush()
        assert snapshot.valuation_quality == "stale_suspended"
        assert snapshot.valuation_details == [
            {"symbol": "000001.SZ", "source_date": "2026-08-22", "reason": "suspended"}
        ]

        initial = PaperAccountSnapshot(
            account_id=1,
            trade_date=date(2026, 8, 25),
            point_type=SnapshotPointType.INITIAL.value,
            event_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
            quality_status=SnapshotQualityStatus.VALID.value,
            **_snapshot_financials(),
        )
        session.add(initial)
        session.flush()
        assert initial.valuation_quality is None
        assert initial.valuation_details is None

    engine.dispose()


def test_snapshot_point_and_quality_enums_reject_unknown_values(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            PaperAccountSnapshot(
                account_id=1,
                trade_date=date(2026, 8, 25),
                point_type="opening",
                event_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
                quality_status=SnapshotQualityStatus.VALID.value,
                invalid_reason=None,
                **_snapshot_financials(),
            )
        )
        with pytest.raises((StatementError, ValueError)):
            session.flush()

    with Session(engine) as session:
        session.add(
            PaperAccountSnapshot(
                account_id=1,
                trade_date=date(2026, 8, 25),
                point_type=SnapshotPointType.TRADING.value,
                event_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
                quality_status="suspect",
                invalid_reason="missing bar",
                **_snapshot_financials(),
            )
        )
        with pytest.raises((StatementError, ValueError)):
            session.flush()

    engine.dispose()


def test_snapshot_model_defaults_support_legacy_writers(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        snapshot = PaperAccountSnapshot(account_id=1, trade_date=date(2026, 8, 25), **_snapshot_financials())
        session.add(snapshot)
        session.flush()

        assert snapshot.point_type == SnapshotPointType.TRADING.value
        assert snapshot.quality_status == SnapshotQualityStatus.VALID.value
        assert snapshot.event_at.tzinfo is not None
        assert snapshot.invalid_reason is None
        assert snapshot.valuation_quality is None
        assert snapshot.valuation_details is None

    engine.dispose()


def test_snapshot_model_rejects_duplicate_initial_points(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            PaperAccountSnapshot(
                account_id=1,
                trade_date=date(2026, 8, 25),
                point_type=SnapshotPointType.INITIAL.value,
                event_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
                quality_status=SnapshotQualityStatus.VALID.value,
                **_snapshot_financials(),
            )
        )
        session.flush()
        session.add(
            PaperAccountSnapshot(
                account_id=1,
                trade_date=date(2026, 8, 26),
                point_type=SnapshotPointType.INITIAL.value,
                event_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
                quality_status=SnapshotQualityStatus.VALID.value,
                **_snapshot_financials(),
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()

    engine.dispose()


def test_snapshot_model_rejects_duplicate_trading_dates(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(_trading_snapshot())
        session.flush()
        session.add(
            _trading_snapshot(
                event_at=datetime(2026, 8, 25, 15, tzinfo=timezone.utc),
                cash_available=Decimal("98000.0000"),
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()

    engine.dispose()
