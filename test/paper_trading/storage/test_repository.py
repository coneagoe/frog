from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from paper_trading.domain.enums import CashEventType, OrderSide, OrderStatus
from paper_trading.storage.models import PaperTradeValidityCheck
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def test_create_account_initializes_nav_share_state(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)

    account = repo.create_account("nav-demo", Decimal("100000.00"))
    ledger = repo.list_cash_ledger(account.id)

    assert account.net_asset_value == Decimal("1.000000")
    assert account.share_count == Decimal("100000.000000")
    assert account.cumulative_deposit == Decimal("100000.0000")
    assert account.cumulative_withdrawal == Decimal("0.0000")
    assert ledger[0].event_type == "deposit"
    assert ledger[0].net_asset_value == Decimal("1.000000")
    assert ledger[0].share_delta == Decimal("100000.000000")


def test_add_cash_event_persists_nav_share_fields(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("cash-event-demo", Decimal("100000.00"))

    event = repo.add_cash_event(
        account.id,
        CashEventType.WITHDRAWAL,
        Decimal("-5000.0000"),
        trade_date=date(2026, 7, 20),
        net_asset_value=Decimal("1.250000"),
        share_delta=Decimal("-4000.000000"),
        note="withdraw",
    )

    assert event.trade_date == date(2026, 7, 20)
    assert event.net_asset_value == Decimal("1.250000")
    assert event.share_delta == Decimal("-4000.000000")


def test_create_account_deposits_initial_cash(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'repo.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))
    session.commit()

    assert account.id is not None
    assert repo.get_cash_available(account.id) == Decimal("100000.0000")
    engine.dispose()


def test_create_order_persists_accepted_order(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'repo.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))

    order = repo.create_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 6, 16),
        status=OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.00"),
        frozen_quantity=0,
        idempotency_key="k1",
    )
    session.commit()

    assert repo.get_order(order.id).status == OrderStatus.ACCEPTED.value
    engine.dispose()


def test_order_validity_summary_and_detail_are_persisted(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'repo.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        OrderStatus.ACCEPTED,
    )

    repo.update_order_validity(order, "valid", "VALID")
    check = repo.create_trade_validity_check(
        order_id=order.id,
        account_id=account.id,
        symbol="000001.SZ",
        trade_date=date(2026, 6, 16),
        side="buy",
        input_price=Decimal("10.00"),
        daily_low=Decimal("9.00"),
        daily_high=Decimal("10.50"),
        limit_up_price=Decimal("11.00"),
        limit_down_price=Decimal("9.00"),
        touched_limit_up=False,
        touched_limit_down=True,
        price_in_range=True,
        status="valid",
        reason_code="VALID",
        reason_detail="Price is inside daily range",
        data_granularity="daily",
    )
    session.commit()

    saved = repo.get_order(order.id)
    assert saved.validity_status == "valid"
    assert saved.validity_reason == "VALID"
    assert saved.validity_checked_at is not None
    assert repo.list_trade_validity_checks(order.id)[0].id == check.id
    engine.dispose()


def test_delete_account_deletes_trade_validity_checks_before_orders(tmp_path):
    """delete_account removes PaperTradeValidityCheck rows so FK to orders does not fail."""
    engine = create_engine(f"sqlite:///{tmp_path / 'del_account.db'}")
    Base.metadata.create_all(engine)
    session: Session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        OrderStatus.ACCEPTED,
    )
    repo.create_trade_validity_check(
        order_id=order.id,
        account_id=account.id,
        symbol="000001.SZ",
        trade_date=date(2026, 6, 16),
        side="buy",
        input_price=Decimal("10.00"),
        daily_low=None,
        daily_high=None,
        status="unchecked",
        reason_code="MARKET_DATA_UNAVAILABLE",
        reason_detail="test",
        data_granularity="daily",
    )
    session.commit()

    # Verify the check exists before deletion
    assert session.query(PaperTradeValidityCheck).filter_by(account_id=account.id).count() == 1

    # Delete the account
    deleted = repo.delete_account(account.id)
    session.commit()

    assert deleted is True
    # Verify the account and its related rows are gone
    assert repo.get_account(account.id) is None
    assert session.query(PaperTradeValidityCheck).filter_by(account_id=account.id).count() == 0
    engine.dispose()


def test_round_trip_repository_creates_and_lists_closed_cycle(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("analytics-demo", Decimal("100000.00"))

    # Create real order and trade for the round-trip open
    open_order = repo.create_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 6, 16),
        status=OrderStatus.FILLED,
        frozen_cash=Decimal("1000.0000"),
    )
    open_trade = repo.create_trade(
        order_id=open_order.id,
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        price=Decimal("10.00"),
        amount=Decimal("1000.0000"),
        fees=Decimal("5.0000"),
        trade_date=date(2026, 6, 16),
    )

    cycle = repo.create_round_trip(
        account_id=account.id,
        symbol="000001.SZ",
        open_trade_id=open_trade.id,
        open_trade_date=date(2026, 6, 16),
        entry_amount=Decimal("1000.0000"),
        fees=Decimal("5.0000"),
    )

    # Create real order and trade for the round-trip close
    close_order = repo.create_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.SELL,
        quantity=100,
        limit_price=Decimal("11.00"),
        trade_date=date(2026, 6, 20),
        status=OrderStatus.FILLED,
    )
    close_trade = repo.create_trade(
        order_id=close_order.id,
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.SELL,
        quantity=100,
        price=Decimal("11.00"),
        amount=Decimal("1100.0000"),
        fees=Decimal("10.0000"),
        trade_date=date(2026, 6, 20),
    )

    repo.update_round_trip(
        cycle,
        close_trade_id=close_trade.id,
        close_trade_date=date(2026, 6, 20),
        exit_amount=Decimal("1100.0000"),
        fees=Decimal("10.0000"),
        realized_pnl=Decimal("90.0000"),
        return_pct=Decimal("0.090000"),
        holding_days=4,
        status="closed",
    )
    sqlite_session.commit()

    rows = repo.list_round_trips(account.id)
    assert len(rows) == 1
    assert rows[0].symbol == "000001.SZ"
    assert rows[0].status == "closed"
    assert rows[0].realized_pnl == Decimal("90.0000")


def test_create_account_sets_default_fee_config(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))
    session.commit()

    assert account.fee_preset == "a_share"
    assert account.commission_rate == Decimal("0.00030000")
    assert account.min_commission == Decimal("5.0000")
    assert account.stamp_duty_rate == Decimal("0.00050000")
    assert account.transfer_fee_rate == Decimal("0.00001000")
    engine.dispose()


def test_create_account_accepts_custom_fee_config(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(
        name="custom-fee",
        initial_cash=Decimal("100000.00"),
        fee_preset="a_share",
        commission_rate=Decimal("0.00025"),
        min_commission=Decimal("3.00"),
        stamp_duty_rate=Decimal("0.0004"),
        transfer_fee_rate=Decimal("0.00002"),
    )
    session.commit()

    assert account.fee_preset == "a_share"
    assert account.commission_rate == Decimal("0.00025000")
    assert account.min_commission == Decimal("3.0000")
    assert account.stamp_duty_rate == Decimal("0.00040000")
    assert account.transfer_fee_rate == Decimal("0.00002000")
    engine.dispose()


@pytest.mark.parametrize(
    "field",
    ["commission_rate", "min_commission", "stamp_duty_rate", "transfer_fee_rate"],
)
def test_create_account_rejects_negative_fee_config(tmp_path, field):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    values = {
        "commission_rate": Decimal("0.0003"),
        "min_commission": Decimal("5.00"),
        "stamp_duty_rate": Decimal("0.0005"),
        "transfer_fee_rate": Decimal("0.00001"),
    }
    values[field] = Decimal("-0.0001")

    with pytest.raises(ValueError, match=field):
        repo.create_account(
            name="negative-fee",
            initial_cash=Decimal("100000.00"),
            commission_rate=values["commission_rate"],
            min_commission=values["min_commission"],
            stamp_duty_rate=values["stamp_duty_rate"],
            transfer_fee_rate=values["transfer_fee_rate"],
        )
    engine.dispose()


def test_create_account_preserves_zero_fee_config(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(
        name="zero-fee",
        initial_cash=Decimal("100000.00"),
        commission_rate=Decimal("0"),
        min_commission=Decimal("0"),
        stamp_duty_rate=Decimal("0"),
        transfer_fee_rate=Decimal("0"),
    )
    session.commit()

    assert account.commission_rate == Decimal("0E-8")
    assert account.min_commission == Decimal("0.0000")
    assert account.stamp_duty_rate == Decimal("0E-8")
    assert account.transfer_fee_rate == Decimal("0E-8")
    engine.dispose()


def test_update_account_fees_updates_only_provided_fields(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))
    updated = repo.update_account_fees(
        account.id,
        commission_rate=Decimal("0.0002"),
        min_commission=Decimal("3.00"),
    )
    session.commit()

    assert updated is not None
    assert updated.commission_rate == Decimal("0.00020000")
    assert updated.min_commission == Decimal("3.0000")
    assert updated.stamp_duty_rate == Decimal("0.00050000")
    assert updated.transfer_fee_rate == Decimal("0.00001000")
    engine.dispose()


def test_update_account_fees_rejects_negative_values(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))

    with pytest.raises(ValueError, match="commission_rate"):
        repo.update_account_fees(account.id, commission_rate=Decimal("-0.0001"))
    engine.dispose()


def test_update_account_fees_rejects_empty_update(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))

    with pytest.raises(ValueError, match="at least one fee field"):
        repo.update_account_fees(account.id)
    engine.dispose()


def test_update_account_fees_returns_none_for_missing_account(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    assert repo.update_account_fees(999, commission_rate=Decimal("0.0002")) is None
    engine.dispose()


def test_order_and_trade_comments_are_persisted(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper_comments.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 18),
        OrderStatus.ACCEPTED,
        comment="突破买入",
    )
    repo.create_trade(
        order.id,
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        Decimal("1000.00"),
        Decimal("5.00"),
        date(2026, 7, 18),
        comment="突破买入",
    )

    assert repo.get_order(order.id).comment == "突破买入"
    assert repo.list_trades(account.id)[0].comment == "突破买入"
    engine.dispose()


def test_update_order_comment_syncs_linked_trades_and_clears_blank(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper_comment_update.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 18),
        OrderStatus.ACCEPTED,
        comment="old",
    )
    trade = repo.create_trade(
        order.id,
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        Decimal("1000.00"),
        Decimal("5.00"),
        date(2026, 7, 18),
        comment="old",
    )

    # Keep a linked PaperTrade object loaded before the update
    loaded_trade = repo.list_trades(account.id)[0]
    assert loaded_trade.id == trade.id
    assert loaded_trade.comment == "old"

    repo.update_order_comment(order, "new reason")
    assert repo.get_order(order.id).comment == "new reason"
    # Loaded trade object observes the updated comment in-memory
    assert loaded_trade.comment == "new reason"

    repo.update_order_comment(order, "")
    assert repo.get_order(order.id).comment is None
    # Loaded trade object observes the cleared comment in-memory
    assert loaded_trade.comment is None
    engine.dispose()


def test_delete_account_removes_round_trips(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("delete-round-trips", Decimal("100000.00"))

    order = repo.create_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 6, 16),
        status=OrderStatus.FILLED,
        frozen_cash=Decimal("1000.0000"),
    )
    trade = repo.create_trade(
        order_id=order.id,
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        price=Decimal("10.00"),
        amount=Decimal("1000.0000"),
        fees=Decimal("5.0000"),
        trade_date=date(2026, 6, 16),
    )

    repo.create_round_trip(
        account_id=account.id,
        symbol="000001.SZ",
        open_trade_id=trade.id,
        open_trade_date=date(2026, 6, 16),
        entry_amount=Decimal("1000.0000"),
        fees=Decimal("5.0000"),
    )

    assert repo.delete_account(account.id) is True
    sqlite_session.commit()

    assert repo.list_round_trips(account.id) == []


def test_delete_order_returns_deleted_order_and_removes_row(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("demo", Decimal("100000"))
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 19),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    sqlite_session.commit()

    deleted = repo.delete_order(order.id)

    assert deleted is not None
    assert deleted.id == order.id
    sqlite_session.flush()
    with pytest.raises(KeyError):
        repo.get_order(order.id)


def test_clear_account_rebuild_state_preserves_initial_cash(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("demo", Decimal("100000"))
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 19),
        OrderStatus.FILLED,
    )
    trade = repo.create_trade(
        order.id,
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        Decimal("1000.0000"),
        Decimal("5.0000"),
        date(2026, 7, 19),
    )
    repo.add_cash_event(account.id, CashEventType.TRADE, Decimal("-1005.0000"), order_id=order.id, trade_id=trade.id)
    # Trade-derived position/lot — should be deleted by clear_account_rebuild_state
    repo.upsert_position(
        account.id, "000001", total_quantity=100, frozen_quantity=0, cost_amount=Decimal("1005.0000"), source="trade"
    )
    repo.create_position_lot(account.id, "000001", date(2026, 7, 19), 100, 100, Decimal("10.00"), source="trade")
    # Imported lot with remaining_quantity < original_quantity (simulating a sell reducing it)
    # This lot must be reset to original_quantity after clear.
    repo.create_position_lot(
        account.id,
        "000002",
        date(2026, 7, 1),
        original_quantity=300,
        remaining_quantity=100,
        cost_price=Decimal("9.00"),
        source="imported",
    )
    # Imported aggregate position (may have been mutated by trades) — will be rebuilt from lots
    repo.upsert_position(
        account.id, "000002", total_quantity=100, frozen_quantity=0, cost_amount=Decimal("900.0000"), source="imported"
    )
    repo.save_snapshot(
        account_id=account.id,
        trade_date=date(2026, 7, 19),
        cash_available=Decimal("98995"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("1000"),
        total_assets=Decimal("99995"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=1,
        order_count=1,
        trade_count=1,
    )
    sqlite_session.commit()

    repo.clear_account_rebuild_state(account.id)

    assert repo.list_trades(account.id) == []
    # Trade-derived lot deleted
    assert repo.count_position_lots(account.id) == 1
    # Imported lot's remaining_quantity reset to original_quantity
    lots = repo.get_lots(account.id, "000002")
    assert len(lots) == 1
    assert lots[0].remaining_quantity == 300
    assert lots[0].original_quantity == 300
    # All positions rebuilt from imported lots only
    positions = repo.get_positions(account.id)
    assert len(positions) == 1
    assert positions[0].symbol == "000002"
    assert positions[0].source == "imported"
    assert positions[0].total_quantity == 300
    assert positions[0].cost_amount == Decimal("2700.0000")  # 300 * 9.00
    assert repo.list_snapshots(account.id) == []
    ledger = repo.list_cash_ledger(account.id)
    assert len(ledger) == 1
    assert ledger[0].note == "initial_cash"
    assert Decimal(ledger[0].amount) == Decimal("100000.0000")


def test_clear_account_rebuild_state_resets_same_symbol_imported_after_trade(sqlite_session):
    """Imported position for a symbol is rebuilt from imported lots even when
    trade-derived lots for the same symbol existed."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("demo", Decimal("100000"))

    # Imported baseline: 200 shares @ 9.00
    repo.create_position_lot(
        account.id,
        "000001",
        date(2026, 7, 1),
        original_quantity=200,
        remaining_quantity=200,
        cost_price=Decimal("9.00"),
        source="imported",
    )
    repo.upsert_position(
        account.id,
        "000001",
        total_quantity=200,
        frozen_quantity=0,
        cost_amount=Decimal("1800.0000"),
        source="imported",
    )
    # Trade buy on same symbol: 100 shares @ 10.00 — mutates aggregate position
    repo.create_position_lot(
        account.id,
        "000001",
        date(2026, 7, 19),
        original_quantity=100,
        remaining_quantity=100,
        cost_price=Decimal("10.00"),
        source="trade",
    )
    repo.upsert_position(
        account.id,
        "000001",
        total_quantity=300,
        frozen_quantity=0,
        cost_amount=Decimal("2800.0000"),
        source="trade",
    )
    sqlite_session.commit()

    repo.clear_account_rebuild_state(account.id)

    # Trade lot deleted; imported lot reset to original_quantity
    lots = repo.get_lots(account.id, "000001")
    assert len(lots) == 1
    assert lots[0].source == "imported"
    assert lots[0].remaining_quantity == 200
    # Position rebuilt from imported lot only
    positions = repo.get_positions(account.id)
    assert len(positions) == 1
    assert positions[0].symbol == "000001"
    assert positions[0].source == "imported"
    assert positions[0].total_quantity == 200
    assert positions[0].cost_amount == Decimal("1800.0000")


def test_reset_orders_for_replay_resets_replayable_statuses(sqlite_session):
    """Orders with ACCEPTED, FILLED, PARTIALLY_FILLED, NEW statuses get reset."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("demo", Decimal("100000"))

    # Create orders with various replayable statuses and rejection info set
    statuses = [
        OrderStatus.ACCEPTED,
        OrderStatus.FILLED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.NEW,
    ]
    orders = {}
    for i, status in enumerate(statuses):
        orders[status] = repo.create_order(
            account.id,
            f"00000{i}",
            OrderSide.BUY,
            100,
            Decimal("10.00"),
            date(2026, 7, 19),
            status,
            frozen_cash=Decimal("1005.0000"),
            rejection_code="REJ001" if status != OrderStatus.ACCEPTED else None,
            rejection_reason="some reason" if status != OrderStatus.ACCEPTED else None,
        )
        # Set filled_quantity via raw update since create_order doesn't expose it
        if status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED):
            orders[status].filled_quantity = 50
    sqlite_session.commit()

    repo.reset_orders_for_replay(account.id)

    for status, order in orders.items():
        reloaded = repo.get_order(order.id)
        assert reloaded.status == OrderStatus.ACCEPTED.value, f"{status} should reset to ACCEPTED"
        assert reloaded.filled_quantity == 0, f"{status} filled_quantity should be 0"
        assert reloaded.rejection_code is None, f"{status} rejection_code should be None"
        assert reloaded.rejection_reason is None, f"{status} rejection_reason should be None"


def test_reset_orders_for_replay_preserves_canceled_rejected(sqlite_session):
    """Orders with CANCELLED or REJECTED status remain unchanged."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("demo", Decimal("100000"))

    rejected = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 19),
        OrderStatus.REJECTED,
        frozen_cash=Decimal("0"),
        rejection_code="BAD_SYMBOL",
        rejection_reason="unknown symbol",
    )
    rejected.filled_quantity = 0
    cancelled = repo.create_order(
        account.id,
        "000002",
        OrderSide.SELL,
        50,
        Decimal("20.00"),
        date(2026, 7, 20),
        OrderStatus.CANCELLED,
        frozen_cash=Decimal("0"),
    )
    sqlite_session.commit()

    repo.reset_orders_for_replay(account.id)

    reloaded_rejected = repo.get_order(rejected.id)
    assert reloaded_rejected.status == OrderStatus.REJECTED.value
    assert reloaded_rejected.rejection_code == "BAD_SYMBOL"
    assert reloaded_rejected.rejection_reason == "unknown symbol"

    reloaded_cancelled = repo.get_order(cancelled.id)
    assert reloaded_cancelled.status == OrderStatus.CANCELLED.value
    assert reloaded_cancelled.rejection_code is None
    assert reloaded_cancelled.rejection_reason is None


def test_list_order_trade_dates_returns_sorted_distinct_dates(sqlite_session):
    """list_order_trade_dates returns distinct trade_dates sorted ascending."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("demo", Decimal("100000"))

    # Create orders with various trade dates including duplicates
    dates = [date(2026, 7, 21), date(2026, 7, 19), date(2026, 7, 20), date(2026, 7, 19), date(2026, 7, 22)]
    for i, d in enumerate(dates):
        repo.create_order(
            account.id,
            f"00000{i}",
            OrderSide.BUY,
            100,
            Decimal("10.00"),
            d,
            OrderStatus.ACCEPTED,
            frozen_cash=Decimal("1005.0000"),
        )
    sqlite_session.commit()

    result = repo.list_order_trade_dates(account.id)

    assert result == [date(2026, 7, 19), date(2026, 7, 20), date(2026, 7, 21), date(2026, 7, 22)]


def test_create_order_persists_market_default_a_share(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("market-demo", Decimal("100000.00"))
    order = repo.create_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
    )
    assert order.market == "a_share"


def test_create_order_persists_market_hk_connect(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("market-hk", Decimal("100000.00"))
    order = repo.create_order(
        account_id=account.id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("400.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
        market="hk_connect",
    )
    assert order.market == "hk_connect"


def test_create_trade_persists_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("trade-mkt", Decimal("100000.00"))
    order = repo.create_order(
        account_id=account.id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("400.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
        market="hk_connect",
    )
    trade = repo.create_trade(
        order_id=order.id,
        account_id=account.id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        price=Decimal("400.00"),
        amount=Decimal("40000.00"),
        fees=Decimal("100.00"),
        trade_date=date(2026, 7, 21),
        market="hk_connect",
    )
    assert trade.market == "hk_connect"


def test_position_persists_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("pos-mkt", Decimal("100000.00"))
    pos = repo.upsert_position(
        account_id=account.id,
        symbol="00700",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("40000.00"),
        market="hk_connect",
    )
    assert pos.market == "hk_connect"


def test_account_hk_fee_fields_default_to_none(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-fees", Decimal("100000.00"))
    assert account.hk_commission_rate is None
    assert account.hk_min_commission is None


def test_update_account_hk_fees_persists(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-fees-upd", Decimal("100000.00"))
    updated = repo.update_account_hk_fees(
        account.id,
        hk_commission_rate=Decimal("0.0002"),
        hk_min_commission=Decimal("18.00"),
        hk_stamp_duty_rate=Decimal("0.0013"),
        hk_trading_fee_rate=Decimal("0.0000565"),
        hk_sfc_levy_rate=Decimal("0.0000027"),
        hk_afrc_levy_rate=Decimal("0.0000015"),
        hk_settlement_fee_rate=Decimal("0.00002"),
    )
    assert updated is not None
    reloaded = repo.get_account(account.id)
    assert reloaded is not None
    assert reloaded.hk_commission_rate == Decimal("0.0002")
    assert reloaded.hk_stamp_duty_rate == Decimal("0.0013")


def test_create_pending_settlement(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("settle-demo", Decimal("100000.00"))
    pending = repo.create_pending_settlement(
        account_id=account.id,
        amount=Decimal("50000.00"),
        expected_settle_date=date(2026, 7, 23),
        trade_id=1,
        source="hk_sell",
    )
    assert pending.account_id == account.id
    assert pending.settled is False


def test_settle_pending_releases_cash(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("settle-rel", Decimal("100000.00"))
    pending = repo.create_pending_settlement(
        account_id=account.id,
        amount=Decimal("50000.00"),
        expected_settle_date=date(2026, 7, 23),
        trade_id=1,
        source="hk_sell",
    )
    repo.settle_pending(pending.id)
    assert pending.settled is True
