import pytest

from paper_trading.storage.hk_metadata import HkConnectMetadataProvider
from storage.model.base import Base
from storage.model.general_info_ggt import GeneralInfoGGT


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
