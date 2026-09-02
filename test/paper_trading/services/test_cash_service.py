from datetime import date, datetime, timezone, tzinfo
from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.domain.enums import SnapshotPointType, SnapshotQualityStatus
from paper_trading.schemas.accounts import CashFlowRequest
from paper_trading.services.cash_service import CashService
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base
from test.paper_trading.fakes import MarketDataProviderCompatibility


def _repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cash_service.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    return engine, session, PaperTradingRepository(session)


def test_deposit_adds_cash_and_mints_shares_without_changing_nav(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))

    result = CashService(repo).deposit(account.id, Decimal("25000.00"), date(2026, 7, 20), "add cash")
    session.commit()

    assert result.ledger.amount == Decimal("25000.0000")
    assert result.ledger.share_delta == Decimal("25000.000000")
    assert result.account.share_count == Decimal("125000.000000")
    assert result.account.net_asset_value == Decimal("1.000000")
    assert result.cash_available == Decimal("125000.0000")
    engine.dispose()


def test_deposit_with_initial_cash_note_is_replayed_as_ordinary_cash_flow(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("ordinary-initial-note", Decimal("100000.00"))

    result = CashService(repo).deposit(
        account.id,
        Decimal("25000.00"),
        date(2026, 7, 20),
        note="initial_cash",
        occurred_at=datetime(2026, 7, 20, 10, tzinfo=timezone.utc),
    )

    assert result.account.share_count == Decimal("125000.000000")
    assert len(repo.list_cash_ledger(account.id)) == 2
    engine.dispose()


@pytest.mark.parametrize("missing_field", ["net_asset_value", "share_delta", "rounding_residual"])
def test_initial_cash_note_with_incomplete_allocation_is_not_creation_event(tmp_path, missing_field):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("ambiguous-initial-note", Decimal("100.00"))
    ledger = repo.list_cash_ledger(account.id)[0]
    setattr(ledger, missing_field, None)

    with session.no_autoflush:
        assert repo._is_creation_initial_cash_event(account, ledger) is False
    engine.dispose()


@pytest.mark.parametrize("field", ["net_asset_value", "share_delta", "rounding_residual"])
def test_initial_cash_note_with_invalid_allocation_is_not_creation_event(tmp_path, field):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("invalid-initial-note", Decimal("100.00"))
    ledger = repo.list_cash_ledger(account.id)[0]
    setattr(ledger, field, "not-a-decimal")

    with session.no_autoflush:
        assert repo._is_creation_initial_cash_event(account, ledger) is False
    engine.dispose()


@pytest.mark.parametrize("value", ["not-a-decimal", "NaN", "Infinity"])
def test_initial_cash_note_invalid_allocation_reaches_replay_repair_path(tmp_path, monkeypatch, value):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("invalid-initial-e2e", Decimal("100.00"))
    initial = repo.list_cash_ledger(account.id)[0]
    initial.net_asset_value = value
    monkeypatch.setattr(repo, "list_cash_ledger", lambda account_id: [initial])

    with session.no_autoflush:
        events = repo.list_replay_events(account.id)
        invalid_event = next(event for event in events if event.source_id.endswith(f":{initial.id}"))
        assert invalid_event.payload.get("pricing_nav") is None
        with pytest.raises(ValueError, match="allocation requires pricing_nav"):
            CashService(repo)._replay_from(account, date(2026, 7, 20))
    engine.dispose()


def test_withdraw_reduces_cash_and_redeems_shares_without_changing_nav(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))

    result = CashService(repo).withdraw(account.id, Decimal("5000.00"), date(2026, 7, 20), "take cash")
    session.commit()

    assert result.ledger.amount == Decimal("-5000.0000")
    assert result.ledger.share_delta == Decimal("-5000.000000")
    assert result.account.share_count == Decimal("95000.000000")
    assert result.cash_available == Decimal("95000.0000")
    engine.dispose()


def test_withdraw_rejects_more_than_available_cash(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))

    with pytest.raises(ValueError, match="withdrawal amount 100001.0000 exceeds available cash 100000.0000"):
        CashService(repo).withdraw(account.id, Decimal("100001.00"), date(2026, 7, 20), None)

    assert len(repo.list_cash_ledger(account.id)) == 1
    engine.dispose()


def test_withdraw_authorizes_against_internal_cash_not_display_rounding(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("precision-boundary", Decimal("1.23456"))

    with pytest.raises(ValueError, match="withdrawal amount 1.2346 exceeds available cash 1.2346"):
        CashService(repo).withdraw(account.id, Decimal("1.23458"), date(2026, 7, 20), None)

    assert len(repo.list_cash_ledger(account.id)) == 1
    engine.dispose()


def test_withdraw_preserves_large_twelve_decimal_cash_eligibility(tmp_path):
    engine, session, repo = _repo(tmp_path)
    cash = Decimal("999999999999.125000000000")
    account = repo.create_account("large-precision-withdrawal", cash)

    assert repo.get_cash_available_internal(account.id) == cash
    result = CashService(repo).withdraw(account.id, cash, date(2026, 7, 20), None)

    assert result.ledger.amount == -cash
    assert result.cash_available == Decimal("0.0000")
    assert repo.get_cash_available_internal(account.id) == Decimal("0.000000000000")
    engine.dispose()


def test_cash_flow_before_valuation_uses_initial_nav(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    account.net_asset_value = Decimal("1.500000")
    occurred_at = datetime(2026, 7, 20, 9, tzinfo=timezone.utc)

    result = CashService(repo).deposit(account.id, Decimal("25000.00"), date(2026, 7, 20), occurred_at=occurred_at)

    assert result.ledger.net_asset_value == Decimal("1.000000")
    assert result.ledger.share_delta == Decimal("25000.000000")
    engine.dispose()


def test_same_date_cash_flow_uses_canonical_trading_snapshot_nav(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    snapshot_at = datetime(2026, 7, 20, 9, tzinfo=timezone.utc)
    snapshot = repo.save_trading_snapshot(
        account_id=account.id,
        trade_date=snapshot_at.date(),
        event_at=snapshot_at,
        point_type=SnapshotPointType.TRADING.value,
        quality_status=SnapshotQualityStatus.VALID.value,
        cash_available=Decimal("100000"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("0"),
        total_assets=Decimal("125000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=0,
        order_count=0,
        trade_count=0,
        net_asset_value=Decimal("1.250000"),
    )
    assert snapshot.event_at == datetime(2026, 7, 20, 23, 59, 59, 999999, tzinfo=timezone.utc)
    account.net_asset_value = Decimal("1.500000")

    class TradingDayMarketData:
        @staticmethod
        def is_trade_date(trade_date):
            return True

    result = CashService(repo, cast(MarketDataProvider, TradingDayMarketData())).deposit(
        account.id,
        Decimal("25000.00"),
        date(2026, 7, 20),
        occurred_at=datetime(2026, 7, 20, 10, tzinfo=timezone.utc),
    )

    assert result.ledger.net_asset_value == Decimal("1.250000")
    assert result.ledger.share_delta == Decimal("20000.000000")
    engine.dispose()


@pytest.mark.parametrize("operation", ["deposit", "withdraw"])
@pytest.mark.parametrize(
    ("prior_nav", "expected_nav"),
    [
        (Decimal("1.250000"), Decimal("1.250000")),
        (None, Decimal("1.000000")),
    ],
)
def test_cash_flow_ignores_later_cross_date_canonical_snapshot(tmp_path, operation, prior_nav, expected_nav):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account(f"cross-date-{operation}-{prior_nav}", Decimal("100000.00"))
    occurred_at = datetime(2026, 7, 20, 10, tzinfo=timezone.utc)

    class TradingDayMarketData:
        @staticmethod
        def is_trade_date(trade_date):
            return True

    if prior_nav is not None:
        repo.save_trading_snapshot(
            account_id=account.id,
            trade_date=date(2026, 7, 19),
            event_at=datetime(2026, 7, 19, 9, tzinfo=timezone.utc),
            point_type=SnapshotPointType.TRADING.value,
            quality_status=SnapshotQualityStatus.VALID.value,
            cash_available=Decimal("100000"),
            cash_frozen=Decimal("0"),
            market_value=Decimal("0"),
            total_assets=Decimal("125000"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            position_count=0,
            order_count=0,
            trade_count=0,
            net_asset_value=prior_nav,
        )
    later_snapshot = repo.save_trading_snapshot(
        account_id=account.id,
        trade_date=date(2026, 7, 21),
        event_at=datetime(2026, 7, 21, 9, tzinfo=timezone.utc),
        point_type=SnapshotPointType.TRADING.value,
        quality_status=SnapshotQualityStatus.VALID.value,
        cash_available=Decimal("100000"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("0"),
        total_assets=Decimal("150000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=0,
        order_count=0,
        trade_count=0,
        net_asset_value=Decimal("1.500000"),
    )
    assert later_snapshot is not None
    assert later_snapshot.event_at == datetime(2026, 7, 21, 23, 59, 59, 999999, tzinfo=timezone.utc)

    service = CashService(repo, cast(MarketDataProvider, TradingDayMarketData()))
    result = (
        service.deposit(account.id, Decimal("25000.00"), occurred_at.date(), occurred_at=occurred_at)
        if operation == "deposit"
        else service.withdraw(account.id, Decimal("25000.00"), occurred_at.date(), occurred_at=occurred_at)
    )

    assert result.ledger.net_asset_value == expected_nav
    assert result.ledger.share_delta == (
        Decimal("25000.000000") / expected_nav if operation == "deposit" else -(Decimal("25000.000000") / expected_nav)
    )
    engine.dispose()


def test_backdated_deposit_replays_existing_trading_snapshot(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("backdated", Decimal("100000.00"))
    snapshot_at = datetime(2026, 7, 21, 23, tzinfo=timezone.utc)
    repo.save_trading_snapshot(
        account_id=account.id,
        trade_date=snapshot_at.date(),
        event_at=snapshot_at,
        point_type=SnapshotPointType.TRADING.value,
        quality_status=SnapshotQualityStatus.VALID.value,
        cash_available=Decimal("100000"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("0"),
        total_assets=Decimal("100000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=0,
        order_count=0,
        trade_count=0,
        net_asset_value=Decimal("1"),
    )

    class EmptyMarketData(MarketDataProviderCompatibility):
        def is_trade_date(self, trade_date):
            return False

        def get_daily_bar(self, symbol, trade_date, market=None):
            return None

    result = CashService(repo, cast(MarketDataProvider, EmptyMarketData())).deposit(
        account.id,
        Decimal("25000.00"),
        date(2026, 7, 20),
        occurred_at=datetime(2026, 7, 20, 10, tzinfo=timezone.utc),
    )

    rebuilt = next(snapshot for snapshot in repo.list_snapshots(account.id) if snapshot.trade_date == date(2026, 7, 21))
    assert rebuilt.cash_available == Decimal("125000.0000")
    assert rebuilt.share_count == Decimal("125000.000000")
    assert result.account.share_count == Decimal("125000.000000")
    assert len(repo.list_cash_ledger(account.id)) == 2
    engine.dispose()


def test_backdated_deposit_replays_cash_only_account_without_market_data(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("cash-only-no-market-data", Decimal("100000.00"))
    snapshot_at = datetime(2026, 7, 21, 23, tzinfo=timezone.utc)
    repo.save_trading_snapshot(
        account_id=account.id,
        trade_date=snapshot_at.date(),
        event_at=snapshot_at,
        point_type=SnapshotPointType.TRADING.value,
        quality_status=SnapshotQualityStatus.VALID.value,
        cash_available=Decimal("100000"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("0"),
        total_assets=Decimal("100000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=0,
        order_count=0,
        trade_count=0,
        net_asset_value=Decimal("1"),
    )

    result = CashService(repo).deposit(
        account.id,
        Decimal("25000.00"),
        date(2026, 7, 20),
        occurred_at=datetime(2026, 7, 20, 10, tzinfo=timezone.utc),
    )

    rebuilt_dates = {
        snapshot.trade_date
        for snapshot in repo.list_snapshots(account.id)
        if date(2026, 7, 20) <= snapshot.trade_date <= date(2026, 7, 21)
    }
    assert rebuilt_dates == {date(2026, 7, 20), date(2026, 7, 21)}
    rebuilt = next(snapshot for snapshot in repo.list_snapshots(account.id) if snapshot.trade_date == date(2026, 7, 21))
    assert rebuilt.cash_available == Decimal("125000.0000")
    assert result.account.share_count == Decimal("125000.000000")
    engine.dispose()


def test_backdated_withdrawal_replays_existing_trading_snapshot(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("backdated-withdrawal", Decimal("100000.00"))
    snapshot_at = datetime(2026, 7, 21, 23, tzinfo=timezone.utc)
    repo.save_trading_snapshot(
        account_id=account.id,
        trade_date=snapshot_at.date(),
        event_at=snapshot_at,
        point_type=SnapshotPointType.TRADING.value,
        quality_status=SnapshotQualityStatus.VALID.value,
        cash_available=Decimal("100000"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("0"),
        total_assets=Decimal("100000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=0,
        order_count=0,
        trade_count=0,
        net_asset_value=Decimal("1"),
    )

    result = CashService(repo).withdraw(
        account.id,
        Decimal("25000.00"),
        date(2026, 7, 20),
        occurred_at=datetime(2026, 7, 20, 10, tzinfo=timezone.utc),
    )

    rebuilt = next(snapshot for snapshot in repo.list_snapshots(account.id) if snapshot.trade_date == date(2026, 7, 21))
    withdrawal = result.ledger
    assert rebuilt.cash_available == Decimal("75000.0000")
    assert rebuilt.share_count == Decimal("75000.000000")
    assert rebuilt.cumulative_withdrawal == Decimal("25000.0000")
    assert rebuilt.net_asset_value == Decimal("1.000000")
    assert withdrawal.amount == Decimal("-25000.0000")
    assert withdrawal.share_delta == Decimal("-25000.000000")
    assert withdrawal.event_time_provenance == "canonical_utc"
    assert result.account.share_count == Decimal("75000.000000")
    engine.dispose()


def test_backdated_withdrawal_rejects_cash_only_added_by_future_deposit(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("withdrawal-history", Decimal("100.00"))
    service = CashService(repo)
    service.deposit(
        account.id,
        Decimal("100.00"),
        date(2026, 7, 21),
        occurred_at=datetime(2026, 7, 21, 10, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="exceeds available cash 100.0000"):
        service.withdraw(
            account.id,
            Decimal("150.00"),
            date(2026, 7, 20),
            occurred_at=datetime(2026, 7, 20, 10, tzinfo=timezone.utc),
        )

    assert len(repo.list_cash_ledger(account.id)) == 2
    engine.dispose()


def test_forward_dated_deposit_recalculates_from_latest_snapshot(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("forward", Decimal("100000.00"))
    latest_at = datetime(2026, 7, 20, 23, tzinfo=timezone.utc)
    repo.save_trading_snapshot(
        account_id=account.id,
        trade_date=latest_at.date(),
        event_at=latest_at,
        point_type=SnapshotPointType.TRADING.value,
        quality_status=SnapshotQualityStatus.VALID.value,
        cash_available=Decimal("100000"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("0"),
        total_assets=Decimal("100000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=0,
        order_count=0,
        trade_count=0,
        net_asset_value=Decimal("1"),
    )

    result = CashService(repo).deposit(
        account.id,
        Decimal("25000.00"),
        date(2026, 7, 21),
        occurred_at=datetime(2026, 7, 21, 10, tzinfo=timezone.utc),
    )

    future = next(snapshot for snapshot in repo.list_snapshots(account.id) if snapshot.trade_date == date(2026, 7, 21))
    assert future.cash_available == Decimal("125000.0000")
    assert future.share_count == Decimal("125000.000000")
    assert result.account.share_count == Decimal("125000.000000")
    engine.dispose()


@pytest.mark.parametrize(
    ("operation", "amount", "nav"),
    [
        ("deposit", Decimal("10.000000000000"), Decimal("3.333333333333")),
        ("withdraw", Decimal("10.000000000000"), Decimal("3.333333333333")),
    ],
)
def test_cash_flow_records_signed_rounding_residual(tmp_path, operation, amount, nav):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account(f"rounding-{operation}", Decimal("100000.00"))
    snapshot_at = datetime(2026, 7, 20, 9, tzinfo=timezone.utc)
    repo.save_trading_snapshot(
        account_id=account.id,
        trade_date=snapshot_at.date(),
        event_at=snapshot_at,
        point_type=SnapshotPointType.TRADING.value,
        quality_status=SnapshotQualityStatus.VALID.value,
        cash_available=Decimal("100000"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("0"),
        total_assets=Decimal("100000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=0,
        order_count=0,
        trade_count=0,
        net_asset_value=nav,
    )
    service = CashService(repo)
    result = getattr(service, operation)(
        account.id,
        amount,
        date(2026, 7, 20),
        occurred_at=datetime(2026, 7, 20, 10, tzinfo=timezone.utc),
    )

    requested = amount if operation == "deposit" else -amount
    represented = result.ledger.share_delta * result.ledger.net_asset_value
    assert result.ledger.share_delta == result.ledger.share_delta.quantize(Decimal("0.000000000001"))
    assert result.ledger.rounding_residual == requested - represented
    assert result.ledger.rounding_residual != 0
    assert result.account.share_count == Decimal("100000") + result.ledger.share_delta
    engine.dispose()


@pytest.mark.parametrize("operation", ["deposit", "withdraw"])
def test_cash_flow_reconciles_persisted_residual_beyond_twelve_decimals(tmp_path, operation):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account(f"precise-{operation}", Decimal("100000.00"))
    snapshot_at = datetime(2026, 7, 20, 9, tzinfo=timezone.utc)
    nav = Decimal("3.333333333334")
    amount = Decimal("10.000000000000")
    repo.save_trading_snapshot(
        account_id=account.id,
        trade_date=snapshot_at.date(),
        event_at=snapshot_at,
        point_type=SnapshotPointType.TRADING.value,
        quality_status=SnapshotQualityStatus.VALID.value,
        cash_available=Decimal("100000"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("0"),
        total_assets=Decimal("100000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=0,
        order_count=0,
        trade_count=0,
        net_asset_value=nav,
    )

    result = getattr(CashService(repo), operation)(
        account.id,
        amount,
        date(2026, 7, 20),
        occurred_at=datetime(2026, 7, 20, 10, tzinfo=timezone.utc),
    )
    account_id = account.id
    ledger_id = result.ledger.id
    session.commit()
    session.expunge_all()
    ledger = next(event for event in repo.list_cash_ledger(account_id) if event.id == ledger_id)
    requested = amount if operation == "deposit" else -amount

    assert ledger.rounding_residual == requested - ledger.share_delta * ledger.net_asset_value
    assert abs(ledger.rounding_residual) > Decimal("0.000000000001")
    engine.dispose()


def test_replay_uses_persisted_cash_flow_share_delta_and_residual(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("persisted-share-delta", Decimal("100000.00"))
    event_at = datetime(2026, 7, 20, 10, tzinfo=timezone.utc)
    ledger = repo.add_cash_event(
        account.id,
        "deposit",
        Decimal("10.0000"),
        trade_date=event_at.date(),
        net_asset_value=Decimal("3.333333333333"),
        share_delta=Decimal("3.000000000000"),
        rounding_residual=Decimal("0.000000000001"),
        occurred_at=event_at,
    )
    # The persisted ledger is the replay fact; changing the ORM object must not
    # cause replay to fall back to amount / NAV recomputation.
    ledger.share_delta = Decimal("2.000000000000")
    with pytest.raises(ValueError, match="rounding residual"):
        CashService(repo)._replay_from(account, event_at.date())
    session.rollback()
    engine.dispose()


def test_cash_flow_replay_failure_rolls_back_inserted_ledger(tmp_path, monkeypatch):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("replay-rollback", Decimal("100000.00"))
    service = CashService(repo)

    monkeypatch.setattr(service, "_replay_from", lambda *_args: (_ for _ in ()).throw(ValueError("replay failed")))
    with pytest.raises(ValueError, match="replay failed"):
        service.deposit(account.id, Decimal("1"), date(2026, 7, 20))
    session.commit()

    assert len(repo.list_cash_ledger(account.id)) == 1
    engine.dispose()


def test_cash_flow_share_delta_without_residual_requires_repair(tmp_path, monkeypatch):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("missing-residual", Decimal("100000.00"))
    event_at = datetime(2026, 7, 20, 10, tzinfo=timezone.utc)
    repo.add_cash_event(
        account.id,
        "deposit",
        Decimal("10"),
        trade_date=event_at.date(),
        net_asset_value=Decimal("1"),
        share_delta=Decimal("10"),
        occurred_at=event_at,
    )
    original = repo.list_replay_events

    def without_residual(account_id, start_at=None, end_at=None):
        events = original(account_id, start_at, end_at)
        return [
            event.__class__(
                event.event_at,
                event.trade_date,
                event.event_type,
                event.source_id,
                event.source_kind,
                {key: value for key, value in event.payload.items() if key != "rounding_residual"},
                event.quality_status,
            )
            for event in events
        ]

    monkeypatch.setattr(repo, "list_replay_events", without_residual)
    with pytest.raises(ValueError, match="pricing_nav, share_delta, and rounding_residual"):
        CashService(repo)._replay_from(account, event_at.date())
    engine.dispose()


@pytest.mark.parametrize("missing", ["pricing_nav", "share_delta", "rounding_residual"])
def test_cash_flow_incomplete_persisted_allocation_requires_repair(tmp_path, monkeypatch, missing):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("incomplete-allocation", Decimal("100000.00"))
    event_at = datetime(2026, 7, 20, 10, tzinfo=timezone.utc)
    repo.add_cash_event(
        account.id,
        "deposit",
        Decimal("10"),
        trade_date=event_at.date(),
        net_asset_value=Decimal("1"),
        share_delta=Decimal("10"),
        occurred_at=event_at,
    )
    original = repo.list_replay_events

    def incomplete(account_id, start_at=None, end_at=None):
        events = original(account_id, start_at, end_at)
        return [
            event.__class__(
                event.event_at,
                event.trade_date,
                event.event_type,
                event.source_id,
                event.source_kind,
                {key: value for key, value in event.payload.items() if key != missing},
                event.quality_status,
            )
            for event in events
        ]

    monkeypatch.setattr(repo, "list_replay_events", incomplete)
    with pytest.raises(ValueError, match="pricing_nav, share_delta, and rounding_residual"):
        CashService(repo)._replay_from(account, event_at.date())
    engine.dispose()


@pytest.mark.parametrize("field", ["pricing_nav", "share_delta", "rounding_residual"])
@pytest.mark.parametrize(
    "value",
    ["NaN", "Infinity", "-Infinity", "not-a-decimal", "1.0", 1.0, 1],
)
def test_cash_flow_malformed_persisted_allocation_requires_repair(tmp_path, monkeypatch, field, value):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("malformed-allocation", Decimal("100000.00"))
    event_at = datetime(2026, 7, 20, 10, tzinfo=timezone.utc)
    repo.add_cash_event(
        account.id,
        "deposit",
        Decimal("10"),
        trade_date=event_at.date(),
        net_asset_value=Decimal("1"),
        share_delta=Decimal("10"),
        occurred_at=event_at,
    )
    original = repo.list_replay_events

    def malformed(account_id, start_at=None, end_at=None):
        events = original(account_id, start_at, end_at)
        return [
            event.__class__(
                event.event_at,
                event.trade_date,
                event.event_type,
                event.source_id,
                event.source_kind,
                {**event.payload, field: value},
                event.quality_status,
            )
            for event in events
        ]

    monkeypatch.setattr(repo, "list_replay_events", malformed)
    with pytest.raises(ValueError, match="invalid Decimal values"):
        CashService(repo)._replay_from(account, event_at.date())
    engine.dispose()


def test_backdated_withdrawal_rejects_invalid_prior_replay_state(tmp_path, monkeypatch):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("invalid-history", Decimal("100.00"))
    service = CashService(repo)
    original = repo.list_replay_events

    def invalid_history(account_id, start_at=None, end_at=None):
        events = original(account_id, start_at, end_at)
        cash_event = next(event for event in events if event.event_type.value == "cash_flow")
        return [
            event
            if event is not cash_event
            else cash_event.__class__(
                cash_event.event_at,
                cash_event.trade_date,
                cash_event.event_type,
                cash_event.source_id,
                cash_event.source_kind,
                cash_event.payload,
                SnapshotQualityStatus.INVALID,
            )
            for event in events
        ]

    service.deposit(
        account.id,
        Decimal("10"),
        date(2026, 7, 20),
        occurred_at=datetime(2026, 7, 20, 9, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(repo, "list_replay_events", invalid_history)
    with pytest.raises(ValueError, match="could not prove pre-withdrawal state"):
        service.withdraw(
            account.id,
            Decimal("1"),
            date(2026, 7, 20),
            occurred_at=datetime(2026, 7, 20, 10, tzinfo=timezone.utc),
        )
    engine.dispose()


def test_cash_flow_recalculation_failure_preserves_caller_transaction(tmp_path, monkeypatch):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("caller-transaction", Decimal("100.00"))
    snapshot_at = datetime(2026, 7, 20, 23, tzinfo=timezone.utc)
    repo.save_trading_snapshot(
        account_id=account.id,
        trade_date=snapshot_at.date(),
        event_at=snapshot_at,
        point_type=SnapshotPointType.TRADING.value,
        quality_status=SnapshotQualityStatus.VALID.value,
        cash_available=Decimal("100"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("0"),
        total_assets=Decimal("100"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=0,
        order_count=0,
        trade_count=0,
        net_asset_value=Decimal("1"),
    )
    account.name = "caller-change"
    session.flush()

    monkeypatch.setattr(
        "paper_trading.services.snapshot_recalculation_service.SnapshotRecalculationService._valuation_events",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("recalculation failed")),
    )
    with pytest.raises(RuntimeError, match="recalculation failed"):
        CashService(repo).deposit(account.id, Decimal("10"), date(2026, 7, 20))
    session.commit()

    assert repo.get_account(account.id).name == "caller-change"
    assert len(repo.list_cash_ledger(account.id)) == 1
    engine.dispose()


def test_cash_flow_request_rejects_naive_occurred_at():
    with pytest.raises(ValueError, match="offset"):
        CashFlowRequest(amount=Decimal("1"), trade_date=date(2026, 7, 20), occurred_at=datetime(2026, 7, 20))


class _NoOffsetTz(tzinfo):
    def utcoffset(self, _value):
        return None

    def dst(self, _value):
        return None

    def tzname(self, _value):
        return "no-offset"


def test_cash_flow_request_rejects_tzinfo_without_offset():
    with pytest.raises(ValueError, match="offset"):
        CashFlowRequest(
            amount=Decimal("1"),
            trade_date=date(2026, 7, 20),
            occurred_at=datetime(2026, 7, 20, tzinfo=_NoOffsetTz()),
        )


def test_cash_service_rejects_tzinfo_without_offset(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("no-offset-service", Decimal("100000.00"))

    with pytest.raises(ValueError, match="offset"):
        CashService(repo).deposit(
            account.id,
            Decimal("1"),
            date(2026, 7, 20),
            occurred_at=datetime(2026, 7, 20, tzinfo=_NoOffsetTz()),
        )

    engine.dispose()
