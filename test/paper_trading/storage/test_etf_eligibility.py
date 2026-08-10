from datetime import datetime

import pytest
from sqlalchemy import Enum, create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from paper_trading.domain.enums import ETFEligibilityStatus
from paper_trading.storage.models import ETFEligibility, tb_name_paper_etf_eligibility
from storage.model.base import Base


def test_etf_eligibility_schema_tracks_provider_and_review_lifecycle(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    table = ETFEligibility.__table__
    assert ETFEligibilityStatus._member_names_ == ["UNKNOWN", "SUPPORTED", "MONEY_MARKET", "DISABLED"]
    assert [member.value for member in ETFEligibilityStatus] == ["unknown", "supported", "money_market", "disabled"]
    assert table.primary_key.columns.keys() == ["symbol"]
    assert {column.name for column in table.columns} == {
        "symbol",
        "name",
        "exchange",
        "list_status",
        "last_seen_at",
        "last_refresh_at",
        "status",
        "reviewed_at",
        "reviewed_by",
        "created_at",
        "updated_at",
    }
    assert isinstance(table.c.status.type, Enum)
    assert table.c.status.type.name == "paper_etf_eligibility_status"
    assert table.c.status.server_default is not None
    assert {index.name for index in table.indexes} == {
        "ix_paper_etf_eligibility_status",
    }

    with Session(engine) as session:
        eligibility = ETFEligibility(
            symbol="510300",
            name="CSI 300 ETF",
            exchange="SH",
            list_status="L",
            last_seen_at=datetime(2026, 8, 10),
            last_refresh_at=datetime(2026, 8, 10),
        )
        session.add(eligibility)
        session.flush()
        assert eligibility.status == ETFEligibilityStatus.UNKNOWN.value

    inspector = inspect(engine)
    assert tb_name_paper_etf_eligibility in inspector.get_table_names()
    engine.dispose()


def test_etf_eligibility_accepts_a_bare_six_digit_symbol(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            ETFEligibility(
                symbol="510300",
                name="CSI 300 ETF",
                exchange="SH",
                list_status="L",
                last_seen_at=datetime(2026, 8, 10),
                last_refresh_at=datetime(2026, 8, 10),
            )
        )
        session.commit()

    engine.dispose()


@pytest.mark.parametrize("symbol", ["510300.SH", "SH510300", "51030", "51030A"])
def test_etf_eligibility_rejects_non_bare_six_digit_symbols(tmp_path, symbol):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            ETFEligibility(
                symbol=symbol,
                name="CSI 300 ETF",
                exchange="SH",
                list_status="L",
                last_seen_at=datetime(2026, 8, 10),
                last_refresh_at=datetime(2026, 8, 10),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()

    engine.dispose()
