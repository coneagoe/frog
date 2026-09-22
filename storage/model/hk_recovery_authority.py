from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, String

from storage.domain_enums import HkSuspensionState

from .base import Base
from .orm_compat import Mapped, mapped_column

tb_name_hk_recovery_authority = "hk_recovery_authority"


class HkRecoveryAuthority(Base):
    __tablename__ = tb_name_hk_recovery_authority

    股票代码: Mapped[str] = mapped_column(String(5), primary_key=True, nullable=False)
    authority_date: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    suspension_state: Mapped[str] = mapped_column(
        Enum(
            HkSuspensionState,
            name="hk_suspension_state",
            values_callable=lambda enum_type: [member.value for member in enum_type],
        ),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    fresh: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __init__(
        self,
        symbol: str,
        authority_date: date,
        eligible: bool,
        suspension_state: str,
        source: str,
        fresh: bool,
        observed_at: datetime | None = None,
    ):
        self.股票代码 = symbol
        self.authority_date = authority_date
        self.eligible = eligible
        self.suspension_state = suspension_state
        self.source = source
        self.fresh = fresh
        self.observed_at = observed_at
