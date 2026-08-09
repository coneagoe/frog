from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.engine import Connection

from storage.enum_governance_adapter import EnumGovernanceAdapter


class EnumGovernanceError(RuntimeError):
    pass


@dataclass(frozen=True)
class EnumGovernanceDomainResult:
    name: str
    result: object


@dataclass(frozen=True)
class EnumGovernanceColumnAudit:
    table_name: str
    column_name: str
    expected_type: str
    observed_type: str | None
    expected_labels: tuple[str, ...]
    observed_values: tuple[str | None, ...]
    expected_default: str | None
    observed_default: str | None
    index_names: tuple[str, ...]
    indexes_ready: bool
    ready: bool
    reason: str | None


@dataclass(frozen=True)
class EnumGovernanceGroupAudit:
    type_name: str
    expected_labels: tuple[str, ...]
    observed_labels: tuple[str, ...]
    columns: tuple[EnumGovernanceColumnAudit, ...]
    dependencies: tuple[str, ...]
    ready: bool
    reason: str | None


@dataclass(frozen=True)
class EnumGovernanceCheckAudit:
    table_name: str
    name: str
    expected: bool
    observed_definition: str | None
    ready: bool
    reason: str | None


@dataclass(frozen=True)
class EnumGovernanceDomainAudit:
    name: str
    groups: tuple[EnumGovernanceGroupAudit, ...]
    checks: tuple[EnumGovernanceCheckAudit, ...]
    missing_tables: tuple[str, ...]
    ready: bool


@dataclass(frozen=True)
class EnumGovernanceResult:
    dry_run: bool
    rollback: bool
    converted: bool
    rolled_back: bool
    domains: tuple[EnumGovernanceDomainResult, ...]
    audits: tuple[EnumGovernanceDomainAudit, ...]


from monitor.storage.enum_migration import MONITOR_ENUM_ADAPTER  # noqa: E402
from paper_trading.storage.enum_migration import PAPER_TRADING_ENUM_ADAPTER  # noqa: E402
from storage.enum_migration import STORAGE_ENUM_ADAPTER  # noqa: E402

ENUM_GOVERNANCE_ADAPTERS = (PAPER_TRADING_ENUM_ADAPTER, MONITOR_ENUM_ADAPTER, STORAGE_ENUM_ADAPTER)


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
    audits = tuple(
        _run_phase(adapter, "audit", adapter.audit, connection, rollback=rollback)
        for adapter in adapters
        if adapter.audit is not None
    )
    if dry_run:
        return _result(adapters, dry_run=True, rollback=rollback, audits=audits)
    if rollback:
        changed = [_run_phase(adapter, "rollback", adapter.rollback, connection) for adapter in adapters]
        for adapter in adapters:
            _run_phase(adapter, "verify", adapter.verify, connection, rollback=True)
        return _result(adapters, rollback=True, rolled_back=any(changed), audits=audits)

    changed = [_run_phase(adapter, "apply", adapter.apply, connection) for adapter in adapters]
    for adapter in adapters:
        _run_phase(adapter, "verify", adapter.verify, connection, rollback=False)
    return _result(adapters, converted=any(changed), audits=audits)


def _run_phase(
    adapter: EnumGovernanceAdapter, phase: str, callback: Callable[..., Any], *args: Any, **kwargs: Any
) -> Any:
    try:
        return callback(*args, **kwargs)
    except Exception as error:
        raise EnumGovernanceError(f"{adapter.name} {phase} failed: {error}") from error


def _result(
    adapters: tuple[EnumGovernanceAdapter, ...],
    *,
    dry_run: bool = False,
    rollback: bool = False,
    converted: bool = False,
    rolled_back: bool = False,
    audits: tuple[EnumGovernanceDomainAudit, ...] = (),
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
        audits=audits,
    )
