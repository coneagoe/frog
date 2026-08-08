from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.engine import Connection


class EnumGovernanceError(RuntimeError):
    pass


@dataclass(frozen=True)
class EnumGovernanceAdapter:
    name: str
    preflight: Callable[..., None]
    apply: Callable[..., bool]
    verify: Callable[..., None]
    rollback: Callable[..., bool]
    result: Callable[..., object]


@dataclass(frozen=True)
class EnumGovernanceDomainResult:
    name: str
    result: object


@dataclass(frozen=True)
class EnumGovernanceResult:
    dry_run: bool
    rollback: bool
    converted: bool
    rolled_back: bool
    domains: tuple[EnumGovernanceDomainResult, ...]


ENUM_GOVERNANCE_ADAPTERS: tuple[EnumGovernanceAdapter, ...] = ()


def migrate_enums(
    connection: Connection,
    *,
    dry_run: bool = False,
    rollback: bool = False,
    adapters: tuple[EnumGovernanceAdapter, ...] | None = None,
) -> EnumGovernanceResult:
    adapters = ENUM_GOVERNANCE_ADAPTERS if adapters is None else adapters
    if connection.dialect.name != "postgresql":
        return _result(adapters, dry_run=dry_run, rollback=rollback)

    for adapter in adapters:
        _run_phase(adapter, "preflight", adapter.preflight, connection, rollback=rollback)
    if dry_run:
        return _result(adapters, dry_run=True, rollback=rollback)
    if rollback:
        changed = [_run_phase(adapter, "rollback", adapter.rollback, connection) for adapter in adapters]
        for adapter in adapters:
            _run_phase(adapter, "verify", adapter.verify, connection, rollback=True)
        return _result(adapters, rollback=True, rolled_back=any(changed))

    changed = [_run_phase(adapter, "apply", adapter.apply, connection) for adapter in adapters]
    for adapter in adapters:
        _run_phase(adapter, "verify", adapter.verify, connection, rollback=False)
    return _result(adapters, converted=any(changed))


def _run_phase(
    adapter: EnumGovernanceAdapter, phase: str, callback: Callable[..., Any], *args: Any, **kwargs: Any
) -> Any:
    try:
        return callback(*args, **kwargs)
    except Exception as error:
        if adapter.name in str(error):
            raise
        raise EnumGovernanceError(f"{adapter.name} {phase} failed: {error}") from error


def _result(
    adapters: tuple[EnumGovernanceAdapter, ...],
    *,
    dry_run: bool = False,
    rollback: bool = False,
    converted: bool = False,
    rolled_back: bool = False,
) -> EnumGovernanceResult:
    return EnumGovernanceResult(
        dry_run=dry_run,
        rollback=rollback,
        converted=converted,
        rolled_back=rolled_back,
        domains=tuple(
            EnumGovernanceDomainResult(
                adapter.name,
                adapter.result(
                    dry_run=dry_run,
                    rollback=rollback,
                    converted=converted,
                    rolled_back=rolled_back,
                ),
            )
            for adapter in adapters
        ),
    )
