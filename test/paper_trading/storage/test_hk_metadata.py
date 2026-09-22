from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from paper_trading.services.data_gap_recovery_service import HkRecoveryAuthorityPolicy
from paper_trading.storage.hk_metadata import HkConnectMetadataProvider
from paper_trading.storage.market_data import StorageMarketDataProvider
from storage.model.base import Base
from storage.model.general_info_ggt import GeneralInfoGGT
from storage.model.hk_recovery_authority import HkRecoveryAuthority
from test.paper_trading.fakes import FakeTradeCalendar


def test_known_security_returns_metadata(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    sqlite_session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    sqlite_session.commit()

    provider = HkConnectMetadataProvider(sqlite_session)
    meta = provider.get_security("00700")
    assert meta is not None
    assert meta.symbol == "00700"
    assert meta.board_lot == 100
    assert meta.eligible is True


def test_unknown_security_returns_none(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    provider = HkConnectMetadataProvider(sqlite_session)
    meta = provider.get_security("99999")
    assert meta is None


def test_board_lot_for_different_security(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    sqlite_session.add(GeneralInfoGGT(股票代码="03690", 股票名称="Meituan"))
    sqlite_session.commit()

    provider = HkConnectMetadataProvider(sqlite_session)
    meta = provider.get_security("03690")
    assert meta is not None
    assert meta.board_lot == 100


def test_get_security_raises_for_empty_symbol(sqlite_session):
    provider = HkConnectMetadataProvider(sqlite_session)
    with pytest.raises(ValueError, match="symbol is required"):
        provider.get_security("")


@pytest.mark.parametrize("effective_date", [date(2026, 8, 6), None])
def test_date_qualified_eligibility_rejects_mismatched_or_missing_evidence(effective_date):
    session = Mock()
    session.query.return_value.filter.return_value.one_or_none.side_effect = [
        SimpleNamespace(股票代码="00700", 股票名称="Tencent", effective_date=effective_date, source="official"),
        None,
    ]

    assert HkConnectMetadataProvider(session).get_security("00700", as_of=date(2026, 8, 7)) is None


def test_date_qualified_eligibility_returns_fresh_evidence_for_matching_date():
    session = Mock()
    session.query.return_value.filter.return_value.one_or_none.side_effect = [
        SimpleNamespace(
            股票代码="00700",
            股票名称="Tencent",
            effective_date=date(2026, 8, 7),
            source="official",
        ),
        SimpleNamespace(authority_date=date(2026, 8, 7), eligible=True, source="official", fresh=True),
    ]

    metadata = HkConnectMetadataProvider(session).get_security("00700", as_of=date(2026, 8, 7))

    assert metadata is not None
    assert metadata.effective_date == date(2026, 8, 7)
    assert metadata.source == "official"
    assert metadata.fresh is True


def test_real_model_path_reads_date_qualified_authority(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    sqlite_session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    sqlite_session.add(HkRecoveryAuthority("00700", date(2026, 8, 7), True, "active", "official", True))
    sqlite_session.commit()

    metadata = HkConnectMetadataProvider(sqlite_session).get_security("00700", as_of=date(2026, 8, 7))

    assert metadata is not None
    assert metadata.effective_date == date(2026, 8, 7)
    assert metadata.source == "official"
    assert metadata.fresh is True


def test_real_model_authority_allows_matching_fresh_active_policy(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    sqlite_session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    sqlite_session.add(HkRecoveryAuthority("00700", date(2026, 8, 7), True, "active", "official", True))
    sqlite_session.commit()
    storage = SimpleNamespace(engine=sqlite_session.get_bind())
    market_data = StorageMarketDataProvider(storage, FakeTradeCalendar([]))
    policy = HkRecoveryAuthorityPolicy(
        FakeTradeCalendar([date(2026, 8, 7)]), HkConnectMetadataProvider(sqlite_session), market_data
    )

    evidence = policy.evaluate("00700", date(2026, 8, 7))

    assert evidence["decision"] is True
    assert evidence["suspension"] == "active"
    assert evidence["freshness"] is True
