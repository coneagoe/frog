from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from storage.enum_governance import EnumGovernanceDomainAudit


@dataclass(frozen=True)
class EnumGovernanceAdapter:
    name: str
    preflight: Callable[..., None]
    apply: Callable[..., bool]
    verify: Callable[..., None]
    rollback: Callable[..., bool]
    result: Callable[..., object]
    audit: Callable[..., EnumGovernanceDomainAudit] | None = None
