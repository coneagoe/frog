from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.domain.enums import Market
from paper_trading.storage.models import PaperAccount, PaperPosition, PaperPositionLot
from storage.model.base import Base
from tools.repair_paper_position_markets import (
    MarketRepairMapping,
    parse_mapping,
    repair_position_markets,
)


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'repair.db'}")
    Base.metadata.create_all(engine)
    db_session = sessionmaker(bind=engine)()
    try:
        yield db_session
    finally:
        db_session.close()
        engine.dispose()


def _account(session, account_id: int) -> PaperAccount:
    account = PaperAccount(
        id=account_id,
        name=f"account-{account_id}",
        initial_cash=Decimal("1000"),
    )
    session.add(account)
    return account


def _position(session, account_id: int, symbol: str, market: str, source: str = "imported"):
    position = PaperPosition(
        account_id=account_id,
        symbol=symbol,
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("1000"),
        realized_pnl=Decimal("0"),
        source=source,
        market=market,
    )
    session.add(position)
    return position


def _lot(session, account_id: int, symbol: str, market: str, source: str = "imported"):
    lot = PaperPositionLot(
        account_id=account_id,
        symbol=symbol,
        buy_trade_date=date(2026, 1, 1),
        original_quantity=100,
        remaining_quantity=100,
        cost_price=Decimal("10"),
        source=source,
        market=market,
    )
    session.add(lot)
    return lot


def test_parse_mapping_accepts_supported_market():
    assert parse_mapping("1:00700:hk_connect") == MarketRepairMapping(1, "00700", Market.HK_CONNECT)


@pytest.mark.parametrize("value", ["1:00700", "x:00700:hk_connect", "1::hk_connect", "1:00700:a_sharex"])
def test_parse_mapping_rejects_malformed_or_unsupported(value):
    with pytest.raises(ValueError):
        parse_mapping(value)


def test_repair_updates_only_explicit_imported_hk_holding(session):
    _account(session, 1)
    requested = _position(session, 1, "00700", "a_share")
    unrelated_position = _position(session, 1, "000001", "a_share")
    imported_lot = _lot(session, 1, "00700", "a_share")
    trade_lot = _lot(session, 1, "00700", "a_share", source="trade")
    session.commit()

    result = repair_position_markets(session, [MarketRepairMapping(1, "00700", Market.HK_CONNECT)])

    assert result[0].position_rows_changed == 1
    assert result[0].lot_rows_changed == 1
    assert requested.market == Market.HK_CONNECT
    assert imported_lot.market == Market.HK_CONNECT
    assert unrelated_position.market == "a_share"
    assert trade_lot.market == "a_share"


def test_repair_prevalidates_all_targets_before_writes(session):
    _account(session, 1)
    position = _position(session, 1, "00700", "a_share")
    _lot(session, 1, "00700", "a_share")
    session.commit()

    with pytest.raises(ValueError, match="position does not exist"):
        repair_position_markets(
            session,
            [
                MarketRepairMapping(1, "00700", Market.HK_CONNECT),
                MarketRepairMapping(1, "000001", Market.HK_CONNECT),
            ],
        )

    session.expire_all()
    assert session.get(PaperPosition, position.id).market == "a_share"


def test_repair_rejects_conflicting_duplicate_mappings(session):
    with pytest.raises(ValueError, match="conflicting"):
        repair_position_markets(
            session,
            [
                MarketRepairMapping(1, "00700", Market.HK_CONNECT),
                MarketRepairMapping(1, "00700", Market.A_SHARE),
            ],
        )


def test_repair_is_atomic_across_multiple_mappings(session):
    _account(session, 1)
    first = _position(session, 1, "00700", "a_share")
    second = _position(session, 1, "000002", "a_share")
    _lot(session, 1, "00700", "a_share")
    _lot(session, 1, "000002", "a_share")
    session.commit()

    result = repair_position_markets(
        session,
        [
            MarketRepairMapping(1, "00700", Market.HK_CONNECT),
            MarketRepairMapping(1, "000002", Market.HK_CONNECT),
        ],
    )

    assert [(item.position_rows_changed, item.lot_rows_changed) for item in result] == [(1, 1), (1, 1)]
    assert first.market == second.market == Market.HK_CONNECT


def test_repair_second_execution_is_idempotent(session):
    _account(session, 1)
    _position(session, 1, "00700", "a_share")
    _lot(session, 1, "00700", "a_share")
    session.commit()
    mapping = MarketRepairMapping(1, "00700", Market.HK_CONNECT)

    repair_position_markets(session, [mapping])
    result = repair_position_markets(session, [mapping])

    assert result[0].position_rows_changed == 0
    assert result[0].lot_rows_changed == 0
