from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from paper_trading.domain.enums import (
    CashEventType,
    ETFEligibilityStatus,
    Market,
    MatchingRunStatus,
    OrderSide,
    OrderStatus,
)
from paper_trading.storage.models import PaperTradeValidityCheck
from paper_trading.storage.repository import PaperTradingRepository
from storage.domain_enums import (
    DailyBarDiagnosticAdjust,
    DailyBarDiagnosticClassification,
    ProviderOutcomeStatus,
    validate_provider_outcomes,
)
from storage.model.base import Base
from storage.model.paper_trading import DailyBarDiagnostic


def test_daily_bar_diagnostic_scalar_columns_use_value_enums():
    assert DailyBarDiagnostic.__table__.c.adjust.type.name == "daily_bar_diagnostic_adjust"
    assert DailyBarDiagnostic.__table__.c.classification.type.name == "daily_bar_diagnostic_classification"
    assert tuple(member.value for member in DailyBarDiagnosticAdjust) == ("bfq", "qfq", "hfq")
    assert tuple(member.value for member in DailyBarDiagnosticClassification) == (
        "missing_market_data",
        "missing_exact_date",
        "provider_error",
        "downloaded",
        "resolved",
    )
    assert DailyBarDiagnostic.__table__.c.adjust.type.enums == [member.value for member in DailyBarDiagnosticAdjust]
    assert DailyBarDiagnostic.__table__.c.classification.type.enums == [
        member.value for member in DailyBarDiagnosticClassification
    ]


def test_etf_eligibility_repository_upserts_gets_and_filters_status(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    refreshed_at = datetime(2026, 8, 10, tzinfo=timezone.utc)
    repo.upsert_etf_eligibility("510300", "CSI 300 ETF", "SH", "L", refreshed_at)
    repo.upsert_etf_eligibility(
        "159915", "Chinext ETF", "SZ", "L", refreshed_at, status=ETFEligibilityStatus.MONEY_MARKET
    )

    classified = repo.classify_etf_eligibility("510300", ETFEligibilityStatus.SUPPORTED, "operator")

    assert repo.get_etf_eligibility("510300") is classified
    assert [row.symbol for row in repo.list_etf_eligibility()] == ["159915", "510300"]
    assert [row.symbol for row in repo.list_etf_eligibility("supported")] == ["510300"]


@pytest.mark.parametrize("symbol", ["510300.SH", "51030", "5103000", "5103A0"])
def test_etf_eligibility_repository_rejects_non_bare_symbols(sqlite_session, symbol):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)

    with pytest.raises(ValueError, match="bare six-digit"):
        repo.get_etf_eligibility(symbol)
    with pytest.raises(ValueError, match="bare six-digit"):
        repo.upsert_etf_eligibility(symbol, "ETF", "SH", "L", datetime(2026, 8, 10, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="bare six-digit"):
        repo.classify_etf_eligibility(symbol, ETFEligibilityStatus.SUPPORTED, "operator")


def test_etf_eligibility_repository_rejects_blank_reviewer(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    repo.upsert_etf_eligibility("510300", "CSI 300 ETF", "SH", "L", datetime(2026, 8, 10, tzinfo=timezone.utc))

    with pytest.raises(ValueError, match="reviewed_by"):
        repo.classify_etf_eligibility("510300", ETFEligibilityStatus.SUPPORTED, " \t")


def test_validate_provider_outcomes_normalizes_valid_values():
    outcomes = [{"provider": "tushare", "status": "empty", "detail": None}]

    normalized = validate_provider_outcomes(outcomes)

    assert normalized == outcomes
    assert normalized is not outcomes
    assert normalized[0] is not outcomes[0]
    assert tuple(member.value for member in ProviderOutcomeStatus) == ("downloaded", "empty", "error")


@pytest.mark.parametrize("value", [None, {}, ["empty"], [{"provider": "tushare"}], [{"status": "partial"}]])
def test_validate_provider_outcomes_rejects_invalid_contract(value):
    with pytest.raises(ValueError, match="provider_outcomes"):
        validate_provider_outcomes(value)


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


def test_create_account_persists_etf_commission_rate(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)

    account = repo.create_account("etf-fees", Decimal("100000"), etf_commission_rate=Decimal("0.00008"))

    assert account.etf_commission_rate == Decimal("0.00008000")


def test_acquire_matching_run_uses_canonical_active_status(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    trade_date = date(2026, 7, 31)

    first, first_owner = repo.acquire_matching_run(trade_date, None)
    second, second_owner = repo.acquire_matching_run(trade_date, None)

    assert first_owner is True
    assert second_owner is False
    assert second.id == first.id
    assert first.status == MatchingRunStatus.RUNNING.value


def test_replay_cleanup_removes_matching_runs(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("replay-status", Decimal("100000.00"))
    repo.create_matching_run(date(2026, 7, 31), account.id, MatchingRunStatus.COMPLETED.value)

    repo.clear_account_rebuild_state(account.id)

    assert repo.list_matching_runs() == []


def test_upsert_daily_bar_diagnostic_reuses_business_date_symbol_adjustment(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)

    first = repo.upsert_daily_bar_diagnostic(
        business_date=date(2026, 7, 28),
        market=Market.A_SHARE,
        stock_id="300996",
        adjust="bfq",
        classification="missing_market_data",
        provider_outcomes=[{"provider": "tushare", "status": "empty", "detail": None}],
        resolved=False,
    )
    second = repo.upsert_daily_bar_diagnostic(
        business_date=date(2026, 7, 28),
        market="a_share",
        stock_id="300996",
        adjust="bfq",
        classification="downloaded",
        provider_outcomes=[{"provider": "tushare", "status": "downloaded", "detail": None}],
        resolved=True,
    )

    assert second.id == first.id
    assert second.resolved is True
    assert second.classification == "downloaded"
    assert second.provider_outcomes == [{"provider": "tushare", "status": "downloaded", "detail": None}]
    assert repo.list_daily_bar_diagnostics() == [second]


@pytest.mark.parametrize(
    ("adjust", "classification", "outcomes"),
    [
        ("raw", "downloaded", []),
        ("bfq", "partial", []),
        ("bfq", "downloaded", [{"provider": "tushare", "status": "partial"}]),
        ("bfq", "downloaded", {"provider": "tushare", "status": "downloaded"}),
    ],
)
def test_upsert_daily_bar_diagnostic_rejects_invalid_finite_values(sqlite_session, adjust, classification, outcomes):
    Base.metadata.create_all(sqlite_session.get_bind())

    with pytest.raises(ValueError):
        PaperTradingRepository(sqlite_session).upsert_daily_bar_diagnostic(
            date(2026, 8, 8), "a_share", "000001", adjust, classification, outcomes, resolved=False
        )


def test_bfq_diagnostic_label_is_found_by_default_lookup(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)

    repo.upsert_daily_bar_diagnostic(
        business_date=date(2026, 7, 28),
        market="a_share",
        stock_id="300996",
        adjust="",
        classification="missing_market_data",
        provider_outcomes=[],
        resolved=False,
    )

    assert repo.has_unresolved_daily_bar_diagnostic(date(2026, 7, 28), "a_share", "300996") is True


def test_diagnostic_lookup_normalizes_exchange_suffixed_and_bare_stock_ids(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)

    diagnostic = repo.upsert_daily_bar_diagnostic(
        business_date=date(2026, 7, 28),
        market="a_share",
        stock_id="000002.SZ",
        adjust="bfq",
        classification="missing_market_data",
        provider_outcomes=[],
        resolved=False,
    )

    assert diagnostic.stock_id == "000002"
    assert repo.has_unresolved_daily_bar_diagnostic(date(2026, 7, 28), "a_share", "000002") is True
    assert repo.has_unresolved_daily_bar_diagnostic(date(2026, 7, 28), "a_share", "000002.SZ") is True


def test_provider_outcome_rejects_unknown_status_and_normalizes_detail():
    from paper_trading.domain.market_data_diagnostics import ProviderOutcome

    assert ProviderOutcome(provider="tushare", status="empty").detail is None
    with pytest.raises(ValueError, match="status"):
        ProviderOutcome(provider="tushare", status=cast(Any, "partial"))


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


def test_get_order_by_idempotency_key_returns_existing_order(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        OrderStatus.ACCEPTED,
        idempotency_key="order-1",
    )

    found = repo.get_order_by_idempotency_key(account.id, "order-1")
    assert found is not None
    assert found.id == order.id
    assert repo.get_order_by_idempotency_key(account.id, "missing") is None


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
        market="a_share",
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
        market="a_share",
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
        account.id,
        "a_share",
        "000001",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("1005.0000"),
        source="trade",
    )
    repo.create_position_lot(
        account.id, "a_share", "000001", date(2026, 7, 19), 100, 100, Decimal("10.00"), source="trade"
    )
    # Imported lot with remaining_quantity < original_quantity (simulating a sell reducing it)
    # This lot must be reset to original_quantity after clear.
    repo.create_position_lot(
        account.id,
        "a_share",
        "000002",
        date(2026, 7, 1),
        original_quantity=300,
        remaining_quantity=100,
        cost_price=Decimal("9.00"),
        source="imported",
    )
    # Imported aggregate position (may have been mutated by trades) — will be rebuilt from lots
    repo.upsert_position(
        account.id,
        "a_share",
        "000002",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("900.0000"),
        source="imported",
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
    lots = repo.get_lots(account.id, "a_share", "000002")
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
        "a_share",
        "000001",
        date(2026, 7, 1),
        original_quantity=200,
        remaining_quantity=200,
        cost_price=Decimal("9.00"),
        source="imported",
    )
    repo.upsert_position(
        account.id,
        "a_share",
        "000001",
        total_quantity=200,
        frozen_quantity=0,
        cost_amount=Decimal("1800.0000"),
        source="imported",
    )
    # Trade buy on same symbol: 100 shares @ 10.00 — mutates aggregate position
    repo.create_position_lot(
        account.id,
        "a_share",
        "000001",
        date(2026, 7, 19),
        original_quantity=100,
        remaining_quantity=100,
        cost_price=Decimal("10.00"),
        source="trade",
    )
    repo.upsert_position(
        account.id,
        "a_share",
        "000001",
        total_quantity=300,
        frozen_quantity=0,
        cost_amount=Decimal("2800.0000"),
        source="trade",
    )
    sqlite_session.commit()

    repo.clear_account_rebuild_state(account.id)

    # Trade lot deleted; imported lot reset to original_quantity
    lots = repo.get_lots(account.id, "a_share", "000001")
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


def test_rebuild_preserves_imported_hk_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-import", Decimal("100000"))
    repo.create_position_lot(
        account.id,
        "hk_connect",
        "00700",
        date(2026, 7, 1),
        original_quantity=100,
        remaining_quantity=100,
        cost_price=Decimal("400.00"),
        source="imported",
    )
    repo.upsert_position(
        account.id,
        "hk_connect",
        "00700",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("40000.0000"),
        source="imported",
    )
    sqlite_session.commit()

    repo.clear_account_rebuild_state(account.id)

    position = repo.get_position(account.id, "hk_connect", "00700")
    assert position is not None
    assert position.market == "hk_connect"


def test_rebuild_restores_same_symbol_imported_lots_by_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("mixed-import", Decimal("100000"))
    for market in ("a_share", "hk_connect"):
        repo.create_position_lot(
            account.id,
            market,
            "00700",
            date(2026, 7, 1),
            original_quantity=100,
            remaining_quantity=100,
            cost_price=Decimal("400.00"),
            source="imported",
        )
    repo.upsert_position(
        account.id,
        "a_share",
        "00700",
        total_quantity=200,
        frozen_quantity=0,
        cost_amount=Decimal("80000.0000"),
        source="imported",
    )
    sqlite_session.commit()

    repo.clear_account_rebuild_state(account.id)

    a_share_position = repo.get_position(account.id, "a_share", "00700")
    hk_connect_position = repo.get_position(account.id, "hk_connect", "00700")
    assert a_share_position is not None
    assert hk_connect_position is not None
    assert a_share_position.total_quantity == 100
    assert hk_connect_position.total_quantity == 100


def test_same_symbol_positions_and_lots_are_isolated_by_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("position-isolation", Decimal("100000"))

    repo.upsert_position(account.id, "a_share", "00700", 100, 0, Decimal("900"))
    repo.upsert_position(account.id, "hk_connect", "00700", 200, 0, Decimal("80000"))
    repo.create_position_lot(account.id, "a_share", "00700", date(2026, 7, 1), 100, 100, Decimal("9"))
    repo.create_position_lot(account.id, "hk_connect", "00700", date(2026, 7, 1), 200, 200, Decimal("400"))

    a_share_position = repo.get_position(account.id, "a_share", "00700")
    hk_connect_position = repo.get_position(account.id, "hk_connect", "00700")
    assert a_share_position is not None
    assert hk_connect_position is not None
    assert a_share_position.total_quantity == 100
    assert hk_connect_position.total_quantity == 200
    assert [lot.remaining_quantity for lot in repo.get_lots(account.id, "a_share", "00700")] == [100]
    assert [lot.remaining_quantity for lot in repo.get_lots(account.id, "hk_connect", "00700")] == [200]


def test_create_position_lot_requires_and_normalizes_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("lot-market", Decimal("100000"))

    lot = repo.create_position_lot(
        account.id,
        Market.HK_CONNECT,
        "00700",
        date(2026, 7, 1),
        100,
        100,
        Decimal("400"),
    )

    assert lot.market == "hk_connect"


def test_hk_diagnostic_does_not_select_same_symbol_a_share_order_for_rebuild(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("diagnostic-market", Decimal("100000"))
    order = repo.create_order(
        account.id,
        "00700",
        OrderSide.BUY,
        100,
        Decimal("10"),
        date(2026, 7, 1),
        OrderStatus.ACCEPTED,
        market="a_share",
    )
    repo.upsert_daily_bar_diagnostic(
        date(2026, 7, 1),
        "hk_connect",
        "00700",
        "bfq",
        "missing_exact_date",
        [],
        resolved=False,
    )

    assert repo.list_eligible_daily_bar_rebuild_orders() == []
    assert order.market == "a_share"


def test_eligible_daily_bar_rebuild_orders_include_etf_missing_exact_date(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    etf_account = repo.create_account("etf-retry", Decimal("100000"))
    hk_account = repo.create_account("hk-retry", Decimal("100000"))
    etf_order = repo.create_order(
        etf_account.id,
        "510300",
        OrderSide.BUY,
        100,
        Decimal("3.100"),
        date(2026, 8, 10),
        OrderStatus.ACCEPTED,
        market=Market.ETF,
    )
    hk_order = repo.create_order(
        hk_account.id,
        "00700",
        OrderSide.BUY,
        100,
        Decimal("400.000"),
        date(2026, 8, 10),
        OrderStatus.ACCEPTED,
        market=Market.HK_CONNECT,
    )
    repo.upsert_daily_bar_diagnostic(
        etf_order.trade_date, Market.ETF, etf_order.symbol, "qfq", "missing_exact_date", [], resolved=False
    )
    repo.upsert_daily_bar_diagnostic(
        hk_order.trade_date, Market.HK_CONNECT, hk_order.symbol, "bfq", "missing_exact_date", [], resolved=False
    )

    assert [item.id for item in repo.list_eligible_daily_bar_rebuild_orders()] == [etf_order.id]


def test_same_symbol_round_trips_are_isolated_by_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("round-trip-isolation", Decimal("100000"))

    for market in ("a_share", "hk_connect"):
        order = repo.create_order(
            account.id,
            "00700",
            OrderSide.BUY,
            100,
            Decimal("10"),
            date(2026, 7, 1),
            OrderStatus.FILLED,
            market=market,
        )
        trade = repo.create_trade(
            order.id,
            account.id,
            "00700",
            OrderSide.BUY,
            100,
            Decimal("10"),
            Decimal("1000"),
            Decimal("1"),
            date(2026, 7, 1),
            market=market,
        )
        repo.create_round_trip(account.id, market, "00700", trade.id, date(2026, 7, 1), Decimal("1000"), Decimal("1"))

    a_share_round_trip = repo.get_open_round_trip(account.id, "a_share", "00700")
    hk_connect_round_trip = repo.get_open_round_trip(account.id, "hk_connect", "00700")
    assert a_share_round_trip is not None
    assert hk_connect_round_trip is not None
    assert a_share_round_trip.market == "a_share"
    assert hk_connect_round_trip.market == "hk_connect"


def test_same_symbol_diagnostics_are_isolated_by_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    a_share = repo.upsert_daily_bar_diagnostic(
        business_date=date(2026, 7, 1),
        market="a_share",
        stock_id="00700",
        adjust="bfq",
        classification="missing_exact_date",
        provider_outcomes=[],
        resolved=False,
    )
    hk_connect = repo.upsert_daily_bar_diagnostic(
        business_date=date(2026, 7, 1),
        market="hk_connect",
        stock_id="00700",
        adjust="bfq",
        classification="missing_exact_date",
        provider_outcomes=[],
        resolved=False,
    )

    assert a_share.id != hk_connect.id
    assert repo.has_unresolved_daily_bar_diagnostic(date(2026, 7, 1), "a_share", "00700") is True
    assert repo.has_unresolved_daily_bar_diagnostic(date(2026, 7, 1), "hk_connect", "00700") is True


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
        market="hk_connect",
        symbol="00700",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("40000.00"),
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
