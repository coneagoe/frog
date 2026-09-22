from dataclasses import dataclass
from typing import Literal

from common.const import AdjustType
from paper_trading.domain.enums import Market

ProviderStatus = Literal["downloaded", "empty", "error"]


def canonical_adjust_label(adjust: AdjustType | str) -> str:
    """Return the stable label used by diagnostics and external payloads."""
    if isinstance(adjust, AdjustType):
        return adjust.name.lower()
    return "bfq" if adjust == "" else adjust.lower()


def canonical_stock_id(stock_id: str, market: str = Market.A_SHARE.value) -> str:
    """Return the ASCII numeric stock code used by daily-history storage."""
    if not isinstance(stock_id, str):
        raise ValueError("stock_id must be a string")
    value = stock_id.strip()
    if market == Market.HK_CONNECT.value:
        if value.endswith(".HK"):
            value = value[:-3]
        elif value.startswith("HK."):
            value = value[3:]
        if not value.isascii() or not value.isdecimal() or not 1 <= len(value) <= 5:
            raise ValueError("hk_connect stock_id must be one-to-five ASCII digits")
        return value.zfill(5)
    if "." in value:
        first, second = value.split(".", 1)
        if first.isascii() and first.isdecimal():
            value = first
        elif second.isascii() and second.isdecimal():
            value = second
    if not value.isascii() or not value.isdecimal():
        raise ValueError("stock_id must be ASCII digits")
    return value


def validate_recovery_identity(market: str, stock_id: str, adjust: str) -> str:
    if adjust != "bfq":
        raise ValueError("recovery adjust must be bfq")
    normalized = canonical_stock_id(stock_id, market)
    if market == Market.A_SHARE.value and len(normalized) != 6:
        raise ValueError("a_share stock_id must be six ASCII digits")
    if market not in {Market.A_SHARE.value, Market.HK_CONNECT.value}:
        raise ValueError("recovery market must be a_share or hk_connect")
    return normalized


@dataclass(frozen=True)
class ProviderOutcome:
    provider: str
    status: ProviderStatus
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"downloaded", "empty", "error"}:
            raise ValueError(f"unsupported provider status: {self.status}")
        object.__setattr__(self, "detail", self.detail or None)


@dataclass(frozen=True)
class StockHistoryOutcome:
    stock_id: str
    business_date: str
    adjust: str
    classification: str
    provider_outcomes: tuple[ProviderOutcome, ...]
    resolved: bool = False
