from dataclasses import dataclass
from typing import Literal

from common.const import AdjustType

ProviderStatus = Literal["downloaded", "empty", "error"]


def canonical_adjust_label(adjust: AdjustType | str) -> str:
    """Return the stable label used by diagnostics and external payloads."""
    if isinstance(adjust, AdjustType):
        return adjust.name.lower()
    return "bfq" if adjust == "" else adjust.lower()


def canonical_stock_id(stock_id: str) -> str:
    """Return the bare numeric stock code used by daily-history storage."""
    value = stock_id.strip()
    if "." in value:
        first, second = value.split(".", 1)
        if first.isdigit():
            return first
        if second.isdigit():
            return second
    return value


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
