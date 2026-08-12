from unittest.mock import patch

from sqlalchemy.exc import SQLAlchemyError

from paper_trading.storage.security_metadata import SecurityNameProvider
from storage.model.a_stock_basic import AStockBasic
from storage.model.base import Base
from storage.model.etf_basic import ETFBasic
from storage.model.general_info_ggt import GeneralInfoGGT


def test_resolve_names_batches_markets_filters_names_and_ignores_unknown_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    sqlite_session.add_all(
        [
            AStockBasic(股票代码="000001", 股票名称="Ping An Bank"),
            AStockBasic(股票代码="000002", 股票名称="   "),
            GeneralInfoGGT(股票代码="00700", 股票名称="Tencent Holdings"),
            GeneralInfoGGT(股票代码="00005", 股票名称=""),
        ]
    )
    sqlite_session.commit()

    result = SecurityNameProvider(sqlite_session).resolve_names(
        [
            ("a_share", "000001"),
            ("a_share", "000001"),
            ("a_share", "000002"),
            ("hk_connect", "00700"),
            ("hk_connect", "00005"),
            ("unknown", "000001"),
            ("a_share", "999999"),
        ]
    )

    assert result == {
        ("a_share", "000001"): "Ping An Bank",
        ("hk_connect", "00700"): "Tencent Holdings",
    }


def test_resolve_names_keeps_hk_results_when_a_share_loader_fails(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    sqlite_session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent Holdings"))
    sqlite_session.commit()

    provider = SecurityNameProvider(sqlite_session)
    query = sqlite_session.query

    def query_with_a_share_failure(model):
        if model is AStockBasic:
            raise SQLAlchemyError("broken")
        return query(model)

    with patch.object(sqlite_session, "query", side_effect=query_with_a_share_failure):
        result = provider.resolve_names([("a_share", "000001"), ("hk_connect", "00700")])

    assert result == {("hk_connect", "00700"): "Tencent Holdings"}


def test_resolve_names_keeps_etf_name_separate_from_a_share_symbol_collision(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    sqlite_session.add_all(
        [
            AStockBasic(股票代码="510300", 股票名称="A-share collision name"),
            ETFBasic(基金代码="510300", 中文简称="CSI 300 ETF", 交易所="SH", 存续状态="L"),
        ]
    )
    sqlite_session.commit()

    assert SecurityNameProvider(sqlite_session).resolve_names([("a_share", "510300"), ("etf", "510300")]) == {
        ("a_share", "510300"): "A-share collision name",
        ("etf", "510300"): "CSI 300 ETF",
    }
