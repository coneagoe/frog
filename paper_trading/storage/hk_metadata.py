from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from storage.model.general_info_ggt import GeneralInfoGGT


@dataclass(frozen=True)
class HkSecurityMetadata:
    symbol: str
    name: str | None = None
    board_lot: int = 100  # default 100 for ordinary stocks
    eligible: bool = True


class HkConnectMetadataProvider:
    """Metadata source for Hong Kong Stock Connect ordinary stocks.

    Backed by the existing ``general_info_hk_ggt`` table.  Board lot size is
    100 for all ordinary stocks; this is the default.  If the symbol is not
    found in the table it is treated as ineligible.
    """

    def __init__(self, session: Session):
        self._session = session

    def get_security(self, symbol: str) -> Optional["HkSecurityMetadata"]:
        if not symbol:
            raise ValueError("symbol is required")
        row = self._session.query(GeneralInfoGGT).filter(GeneralInfoGGT.股票代码 == symbol).one_or_none()
        if row is None:
            return None
        return HkSecurityMetadata(
            symbol=symbol,
            name=getattr(row, "股票名称", None),
            board_lot=100,
            eligible=True,
        )
