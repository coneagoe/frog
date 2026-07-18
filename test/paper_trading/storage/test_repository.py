from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.storage.models import PaperTradeValidityCheck
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


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
