from dataclasses import dataclass
from datetime import date
from typing import Optional, Protocol

from sqlalchemy.orm import Session

from storage.model.general_info_ggt import GeneralInfoGGT
from storage.model.hk_recovery_authority import HkRecoveryAuthority


@dataclass(frozen=True)
class HkSecurityMetadata:
    symbol: str
    name: str | None = None
    board_lot: int = 100  # default 100 for ordinary stocks
    eligible: bool = True
    effective_date: date | None = None
    source: str | None = None
    fresh: bool = False


class HkEligibilityAuthority(Protocol):
    def get_security(self, symbol: str, as_of: date | None = None) -> HkSecurityMetadata | None: ...


class HkConnectMetadataProvider:
    """Metadata source for Hong Kong Stock Connect ordinary stocks.

    Backed by the existing ``general_info_hk_ggt`` table.  Board lot size is
    100 for all ordinary stocks; this is the default.  If the symbol is not
    found in the table it is treated as ineligible.
    """

    def __init__(self, session: Session):
        self._session = session

    def get_security(self, symbol: str, as_of: date | None = None) -> Optional["HkSecurityMetadata"]:
        if not symbol:
            raise ValueError("symbol is required")
        row = self._session.query(GeneralInfoGGT).filter(GeneralInfoGGT.股票代码 == symbol).one_or_none()
        if row is None:
            return None
        authority = None
        if as_of is not None:
            authority = (
                self._session.query(HkRecoveryAuthority)
                .filter(
                    HkRecoveryAuthority.股票代码 == symbol,
                    HkRecoveryAuthority.authority_date == as_of,
                )
                .one_or_none()
            )
            if authority is None:
                return None
        effective_date = getattr(authority, "authority_date", None) if authority is not None else None
        source = getattr(authority, "source", None) if authority is not None else None
        fresh = bool(authority is not None and getattr(authority, "fresh", False))
        if effective_date != as_of:
            return None
        return HkSecurityMetadata(
            symbol=symbol,
            name=getattr(row, "股票名称", None),
            board_lot=100,
            eligible=bool(getattr(authority, "eligible", False)) if authority is not None else True,
            effective_date=effective_date,
            source=source,
            fresh=fresh,
        )
