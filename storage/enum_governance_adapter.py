from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from storage.enum_governance import EnumGovernanceDomainAudit


@dataclass(frozen=True)
class EnumGovernanceAdapter:
    name: str
    preflight: Callable[..., None]
    apply: Callable[..., Any]
    verify: Callable[..., None]
    rollback: Callable[..., bool]
    result: Callable[..., object]
    audit: Callable[..., EnumGovernanceDomainAudit]


def empty_enum_governance_audit(name: str) -> Callable[..., EnumGovernanceDomainAudit]:
    def audit(connection, *, rollback: bool) -> EnumGovernanceDomainAudit:
        from storage.enum_governance import EnumGovernanceDomainAudit

        del connection, rollback
        return EnumGovernanceDomainAudit(name, (), (), (), True)

    return audit
