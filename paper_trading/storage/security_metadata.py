from collections.abc import Collection

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from storage.model.a_stock_basic import AStockBasic
from storage.model.general_info_ggt import GeneralInfoGGT


class SecurityNameProvider:
    def __init__(self, session: Session):
        self._session = session

    def resolve_names(self, securities: Collection[tuple[str, str]]) -> dict[tuple[str, str], str]:
        requested = set(securities)
        names: dict[tuple[str, str], str] = {}
        a_share_symbols = {symbol for market, symbol in requested if market == "a_share"}
        hk_symbols = {symbol for market, symbol in requested if market == "hk_connect"}

        if a_share_symbols:
            names.update(self._resolve_a_share(a_share_symbols))
        if hk_symbols:
            names.update(self._resolve_hk_connect(hk_symbols))
        return names

    def _resolve_a_share(self, symbols: Collection[str]) -> dict[tuple[str, str], str]:
        try:
            with self._session.begin_nested():
                rows = (
                    self._session.query(AStockBasic)
                    .filter(AStockBasic.股票代码.in_(symbols))
                    .all()
                )
        except SQLAlchemyError:
            return {}
        return {
            ("a_share", row.股票代码): row.股票名称
            for row in rows
            if row.股票名称 and row.股票名称.strip()
        }

    def _resolve_hk_connect(self, symbols: Collection[str]) -> dict[tuple[str, str], str]:
        try:
            with self._session.begin_nested():
                rows = (
                    self._session.query(GeneralInfoGGT)
                    .filter(GeneralInfoGGT.股票代码.in_(symbols))
                    .all()
                )
        except SQLAlchemyError:
            return {}
        return {
            ("hk_connect", row.股票代码): row.股票名称
            for row in rows
            if row.股票名称 and row.股票名称.strip()
        }
