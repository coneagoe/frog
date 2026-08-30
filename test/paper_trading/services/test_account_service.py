from datetime import date, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.domain.enums import Market, OrderSide, OrderStatus
from paper_trading.schemas.accounts import CreateAccountRequest, ImportPositionItem
from paper_trading.services.account_service import AccountService
from paper_trading.storage.models import (
    PaperAccount,
    PaperAccountSnapshot,
    PaperCashLedger,
    PaperMatchingRun,
    PaperOrder,
    PaperPosition,
    PaperPositionLot,
    PaperPositionRoundTrip,
    PaperTrade,
)
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def _repo_and_service(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'accounts.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    return engine, session, repo, AccountService(repo)


def test_create_account_returns_active_account_with_initial_cash(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'account.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = AccountService(repo).create_account("demo", Decimal("100000.00"))
    session.commit()

    assert account.name == "demo"
    assert account.status == "active"
    assert repo.get_cash_available(account.id) == Decimal("100000.0000")
    engine.dispose()


@pytest.mark.parametrize("initial_cash", [Decimal("0"), Decimal("-1")])
def test_create_account_rejects_non_positive_initial_cash(initial_cash):
    with pytest.raises(ValidationError):
        CreateAccountRequest(name="invalid", initial_cash=initial_cash)


def test_account_creation_persists_initial_nav_snapshot(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    request = CreateAccountRequest(name="primary", initial_cash=Decimal("1000"))

    account = service.create_account(request.name, request.initial_cash)
    snapshots = repo.list_snapshots(account.id)
    ledger = repo.list_cash_ledger(account.id)

    assert [(row.point_type, row.net_asset_value) for row in snapshots] == [("initial", Decimal("1.000000"))]
    assert len(ledger) == 1
    assert ledger[0].amount == Decimal("1000.0000")
    assert ledger[0].share_delta == Decimal("1000.000000")
    assert ledger[0].note == "initial_cash"
    assert ledger[0].occurred_at.replace(tzinfo=timezone.utc).tzinfo == timezone.utc
    assert ledger[0].event_time_provenance == "canonical_utc"
    assert snapshots[0].share_count == Decimal("1000.000000")
    assert snapshots[0].cash_available == Decimal("1000.0000")
    assert snapshots[0].event_at.replace(tzinfo=timezone.utc).tzinfo == timezone.utc
    assert snapshots[0].event_time_provenance == "canonical_utc"
    assert ledger[0].occurred_at.replace(tzinfo=timezone.utc) == snapshots[0].event_at.replace(tzinfo=timezone.utc)
    engine.dispose()


@pytest.mark.parametrize("initial_cash", [Decimal("0"), Decimal("-1")])
def test_create_account_service_rejects_non_positive_initial_cash(tmp_path, initial_cash):
    engine, session, repo, service = _repo_and_service(tmp_path)

    with pytest.raises(ValueError, match="initial_cash"):
        service.create_account("invalid", initial_cash)
    engine.dispose()


def test_account_creation_rolls_back_when_snapshot_insert_fails(tmp_path, monkeypatch):
    engine, session, repo, service = _repo_and_service(tmp_path)

    def fail_snapshot(*args, **kwargs):
        raise RuntimeError("snapshot insert failed")

    monkeypatch.setattr(repo, "create_initial_snapshot", fail_snapshot)

    with pytest.raises(RuntimeError, match="snapshot insert failed"):
        service.create_account("primary", Decimal("1000"))
    session.rollback()

    assert session.query(PaperAccount).count() == 0
    assert session.query(PaperCashLedger).count() == 0
    assert session.query(PaperAccountSnapshot).count() == 0
    engine.dispose()


def test_update_account_fees_via_service(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = service.create_account("demo", Decimal("100000.00"))

    updated = service.update_account_fees(
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


def test_update_account_fees_accepts_only_etf_rate(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = service.create_account("demo", Decimal("100000.00"))

    updated = service.update_account_fees(account.id, etf_commission_rate=Decimal("0"))

    assert updated is not None
    assert updated.etf_commission_rate == Decimal("0E-8")
    engine.dispose()


def test_update_account_fees_updates_all_market_fee_groups(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = service.create_account("demo", Decimal("100000.00"))

    updated = service.update_account_fees(
        account.id,
        commission_rate=Decimal("0.0002"),
        hk_commission_rate=Decimal("0.0003"),
        etf_commission_rate=Decimal("0.00008"),
    )

    assert updated is not None
    assert updated.commission_rate == Decimal("0.00020000")
    assert updated.hk_commission_rate == Decimal("0.00030000")
    assert updated.etf_commission_rate == Decimal("0.00008000")
    engine.dispose()


def test_update_account_fees_service_rejects_negative(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = service.create_account("demo", Decimal("100000.00"))

    with pytest.raises(ValueError, match="commission_rate"):
        service.update_account_fees(account.id, commission_rate=Decimal("-0.0001"))
    engine.dispose()


def test_update_account_fees_service_rejects_empty_update(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = service.create_account("demo", Decimal("100000.00"))

    with pytest.raises(ValueError, match="at least one fee field"):
        service.update_account_fees(account.id)
    engine.dispose()


def test_update_account_fees_service_returns_none_for_missing(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    assert service.update_account_fees(999, commission_rate=Decimal("0.0002")) is None
    engine.dispose()


def test_delete_account_removes_account_owned_rows(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        OrderStatus.ACCEPTED,
    )
    trade = PaperTrade(
        order_id=order.id,
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY.value,
        quantity=100,
        price=Decimal("10.00"),
        amount=Decimal("1000.00"),
        fees=Decimal("5.00"),
        trade_date=date(2026, 6, 16),
    )
    session.add(trade)
    repo.upsert_position(account.id, Market.A_SHARE, "000001.SZ", 100, 0, Decimal("1000.00"))
    repo.create_position_lot(account.id, Market.A_SHARE, "000001.SZ", date(2026, 6, 16), 100, 100, Decimal("10.00"))
    repo.save_snapshot(
        account_id=account.id,
        trade_date=date(2026, 6, 16),
        cash_available=Decimal("98995.00"),
        cash_frozen=Decimal("0.00"),
        market_value=Decimal("1000.00"),
        total_assets=Decimal("99995.00"),
        realized_pnl=Decimal("0.00"),
        unrealized_pnl=Decimal("0.00"),
        position_count=1,
        order_count=1,
        trade_count=1,
    )
    session.add(PaperMatchingRun(trade_date=date(2026, 6, 16), account_id=account.id, status="completed"))
    session.commit()

    deleted = service.delete_account(account.id)
    session.commit()

    assert deleted is True
    assert repo.get_account(account.id) is None
    assert session.query(PaperCashLedger).filter_by(account_id=account.id).count() == 0
    assert session.query(PaperTrade).filter_by(account_id=account.id).count() == 0
    assert session.query(PaperOrder).filter_by(account_id=account.id).count() == 0
    assert session.query(PaperPosition).filter_by(account_id=account.id).count() == 0
    assert session.query(PaperPositionLot).filter_by(account_id=account.id).count() == 0
    assert session.query(PaperAccountSnapshot).filter_by(account_id=account.id).count() == 0
    assert session.query(PaperMatchingRun).filter_by(account_id=account.id).count() == 0
    engine.dispose()


# ---------------------------------------------------------------------------
# import_positions
# ---------------------------------------------------------------------------


class TestImportPositions:
    def test_import_hk_position_persists_market_on_position_and_lot(self, tmp_path):
        engine, session, repo, service = _repo_and_service(tmp_path)
        account = service.create_account("demo", Decimal("100000.00"))
        session.commit()

        service.import_positions(
            account.id,
            [
                ImportPositionItem(
                    symbol="00700",
                    quantity=100,
                    cost_price=Decimal("400"),
                    buy_trade_date=date(2026, 7, 27),
                    market=Market.HK_CONNECT,
                )
            ],
        )

        assert repo.get_position(account.id, Market.HK_CONNECT, "00700").market == "hk_connect"
        assert repo.get_lots(account.id, Market.HK_CONNECT, "00700")[0].market == "hk_connect"

    def test_import_same_symbol_in_different_markets_creates_isolated_positions_and_lots(self, tmp_path):
        engine, session, repo, service = _repo_and_service(tmp_path)
        account = service.create_account("demo", Decimal("100000.00"))
        session.commit()

        a_share_00700 = ImportPositionItem(
            symbol="00700",
            quantity=100,
            cost_price=Decimal("400"),
            buy_trade_date=date(2026, 7, 27),
        )
        hk_connect_00700 = a_share_00700.model_copy(update={"market": Market.HK_CONNECT})

        service.import_positions(account.id, [a_share_00700, hk_connect_00700])
        session.commit()

        a_share_position = repo.get_position(account.id, Market.A_SHARE, "00700")
        hk_connect_position = repo.get_position(account.id, Market.HK_CONNECT, "00700")
        assert a_share_position is not None
        assert a_share_position.total_quantity == 100
        assert hk_connect_position is not None
        assert hk_connect_position.total_quantity == 100
        assert len(repo.get_lots(account.id, Market.A_SHARE, "00700")) == 1
        assert len(repo.get_lots(account.id, Market.HK_CONNECT, "00700")) == 1

    def test_import_creates_positions_and_lots(self, tmp_path):
        """Import seeds both a PaperPosition and PaperPositionLot per item."""
        engine, session, repo, service = _repo_and_service(tmp_path)
        account = service.create_account("demo", Decimal("100000.00"))
        session.commit()

        service.import_positions(
            account.id,
            [
                ImportPositionItem(
                    symbol="000001",
                    quantity=100,
                    cost_price=Decimal("10.50"),
                    buy_trade_date=date(2026, 1, 15),
                ),
            ],
        )
        session.commit()

        positions = repo.get_positions(account.id)
        assert len(positions) == 1
        assert positions[0].symbol == "000001"
        assert positions[0].total_quantity == 100
        assert positions[0].frozen_quantity == 0
        assert positions[0].cost_amount == Decimal("1050.0000")
        assert positions[0].realized_pnl == Decimal("0")

        lots = repo.get_lots(account.id, Market.A_SHARE, "000001")
        assert len(lots) == 1
        assert lots[0].original_quantity == 100
        assert lots[0].remaining_quantity == 100
        assert lots[0].cost_price == Decimal("10.5000")
        assert lots[0].buy_trade_date == date(2026, 1, 15)

    def test_import_aggregates_duplicate_symbols(self, tmp_path):
        """Multiple items with the same symbol create separate lots but one position."""
        engine, session, repo, service = _repo_and_service(tmp_path)
        account = service.create_account("demo", Decimal("100000.00"))
        session.commit()

        service.import_positions(
            account.id,
            [
                ImportPositionItem(
                    symbol="000001",
                    quantity=100,
                    cost_price=Decimal("10.00"),
                    buy_trade_date=date(2026, 1, 15),
                ),
                ImportPositionItem(
                    symbol="000001",
                    quantity=50,
                    cost_price=Decimal("12.00"),
                    buy_trade_date=date(2026, 2, 1),
                ),
            ],
        )
        session.commit()

        positions = repo.get_positions(account.id)
        assert len(positions) == 1
        assert positions[0].total_quantity == 150
        assert positions[0].cost_amount == Decimal("1600.0000")  # 100*10 + 50*12

        lots = repo.get_lots(account.id, Market.A_SHARE, "000001")
        assert len(lots) == 2

    def test_import_rejects_missing_account(self, tmp_path):
        engine, session, repo, service = _repo_and_service(tmp_path)

        with pytest.raises(ValueError, match="paper account not found"):
            service.import_positions(
                999,
                [
                    ImportPositionItem(
                        symbol="000001",
                        quantity=100,
                        cost_price=Decimal("10.00"),
                        buy_trade_date=date(2026, 1, 15),
                    ),
                ],
            )

    def test_import_rejects_account_with_existing_positions(self, tmp_path):
        engine, session, repo, service = _repo_and_service(tmp_path)
        account = service.create_account("demo", Decimal("100000.00"))
        repo.upsert_position(account.id, Market.A_SHARE, "EXISTING", 10, 0, Decimal("100.00"))
        session.commit()

        with pytest.raises(ValueError, match="account already has positions"):
            service.import_positions(
                account.id,
                [
                    ImportPositionItem(
                        symbol="000001",
                        quantity=100,
                        cost_price=Decimal("10.00"),
                        buy_trade_date=date(2026, 1, 15),
                    ),
                ],
            )

    def test_import_rejects_account_with_existing_lots_only(self, tmp_path):
        """Account with PaperPositionLot rows but no PaperPosition rows must also be rejected."""
        engine, session, repo, service = _repo_and_service(tmp_path)
        account = service.create_account("demo", Decimal("100000.00"))
        repo.create_position_lot(
            account_id=account.id,
            market=Market.A_SHARE,
            symbol="000001",
            buy_trade_date=date(2026, 1, 15),
            original_quantity=100,
            remaining_quantity=100,
            cost_price=Decimal("10.00"),
        )
        session.commit()

        with pytest.raises(ValueError, match="account already has positions"):
            service.import_positions(
                account.id,
                [
                    ImportPositionItem(
                        symbol="000002",
                        quantity=50,
                        cost_price=Decimal("20.00"),
                        buy_trade_date=date(2026, 2, 1),
                    ),
                ],
            )

    def test_import_does_not_create_cash_ledger_entries(self, tmp_path):
        """Import must not touch the cash ledger."""
        engine, session, repo, service = _repo_and_service(tmp_path)
        account = service.create_account("demo", Decimal("100000.00"))
        session.commit()

        service.import_positions(
            account.id,
            [
                ImportPositionItem(
                    symbol="000001",
                    quantity=100,
                    cost_price=Decimal("10.00"),
                    buy_trade_date=date(2026, 1, 15),
                ),
            ],
        )
        session.commit()

        # Only the initial deposit
        cash_entries = session.query(PaperCashLedger).filter_by(account_id=account.id).all()
        assert len(cash_entries) == 1
        assert cash_entries[0].event_type == "deposit"

    def test_import_does_not_create_trades_orders_or_round_trips(self, tmp_path):
        """Import must not create trades, orders, or round trips."""
        engine, session, repo, service = _repo_and_service(tmp_path)
        account = service.create_account("demo", Decimal("100000.00"))
        session.commit()

        service.import_positions(
            account.id,
            [
                ImportPositionItem(
                    symbol="000001",
                    quantity=100,
                    cost_price=Decimal("10.00"),
                    buy_trade_date=date(2026, 1, 15),
                ),
            ],
        )
        session.commit()

        assert session.query(PaperTrade).filter_by(account_id=account.id).count() == 0
        assert session.query(PaperOrder).filter_by(account_id=account.id).count() == 0
        assert session.query(PaperPositionRoundTrip).filter_by(account_id=account.id).count() == 0

    def test_import_preserves_symbol_whitespace_trimming(self, tmp_path):
        """Symbols should have whitespace trimmed before storage."""
        engine, session, repo, service = _repo_and_service(tmp_path)
        account = service.create_account("demo", Decimal("100000.00"))
        session.commit()

        service.import_positions(
            account.id,
            [
                ImportPositionItem(
                    symbol="  000001  ",
                    quantity=100,
                    cost_price=Decimal("10.00"),
                    buy_trade_date=date(2026, 1, 15),
                ),
            ],
        )
        session.commit()

        positions = repo.get_positions(account.id)
        assert positions[0].symbol == "000001"
