# ruff: noqa: E501

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from storage.domain_enums import (
    BlackroomMarket,
    BlackroomSource,
    DailyBarDiagnosticAdjust,
    DailyBarDiagnosticClassification,
    ForecastSnapshotStatus,
    SSFChangeSignalStatus,
    validate_provider_outcomes,
    validate_ssf_event_types,
)
from storage.enum_governance_adapter import EnumGovernanceAdapter
from storage.model import (
    BlackroomRecord,
    DailyBarDiagnostic,
    ForecastSnapshotRecord,
    ForecastSnapshotRun,
    HkRecoveryAuthority,
    SSFChangeSignal,
    tb_name_forecast_snapshot_record,
    tb_name_forecast_snapshot_run,
)


class StorageEnumMigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class StorageEnumColumn:
    table_name: str
    column_name: str
    legacy_type_sql: str
    default_sql: str | None
    nullable: bool = False


@dataclass(frozen=True)
class StorageEnumGroup:
    type_name: str
    labels: tuple[str, ...]
    columns: tuple[StorageEnumColumn, ...]


@dataclass(frozen=True)
class StorageEnumMigrationResult:
    dry_run: bool
    rollback: bool
    converted: bool
    rolled_back: bool
    groups: tuple[StorageEnumGroup, ...]


def _labels(enum_type: type[StrEnum]) -> tuple[str, ...]:
    return tuple(member.value for member in enum_type)


def _column(
    table_name: str,
    column_name: str,
    legacy_type_sql: str,
    default_sql: str | None = None,
    *,
    nullable: bool = False,
) -> StorageEnumColumn:
    if default_sql is not None and "::" not in default_sql:
        default_sql = f"{default_sql}::character varying"
    return StorageEnumColumn(table_name, column_name, legacy_type_sql, default_sql, nullable)


STORAGE_ENUM_GROUPS = (
    StorageEnumGroup(
        "blackroom_market", _labels(BlackroomMarket), (_column("blackroom_records", "market", "VARCHAR(5)", "'A'"),)
    ),
    StorageEnumGroup(
        "blackroom_source",
        _labels(BlackroomSource),
        (_column("blackroom_records", "source", "VARCHAR(50)", "'manual'"),),
    ),
    StorageEnumGroup(
        "daily_bar_diagnostic_adjust",
        _labels(DailyBarDiagnosticAdjust),
        (_column("daily_bar_diagnostics", "adjust", "VARCHAR(10)"),),
    ),
    StorageEnumGroup(
        "daily_bar_diagnostic_classification",
        _labels(DailyBarDiagnosticClassification),
        (_column("daily_bar_diagnostics", "classification", "VARCHAR(50)"),),
    ),
    StorageEnumGroup(
        "ssf_change_signal_status",
        _labels(SSFChangeSignalStatus),
        (_column("ssf_change_signals", "status", "VARCHAR(20)", "'signal'"),),
    ),
    StorageEnumGroup(
        "forecast_snapshot_status",
        _labels(ForecastSnapshotStatus),
        (_column("forecast_snapshot_runs", "status", "VARCHAR(16)"),),
    ),
)

_GOVERNED_TABLES = (
    BlackroomRecord.__table__,
    DailyBarDiagnostic.__table__,
    ForecastSnapshotRun.__table__,
    SSFChangeSignal.__table__,
)
_PRE_RAW_DAILY_BAR_DIAGNOSTIC_ADJUST_LABELS = ("bfq", "qfq", "hfq")
_PROVIDER_CHECK_NAME = "ck_daily_bar_diagnostics_provider_outcome_status"
_PROVIDER_CHECK_SQL = (
    "CHECK (((jsonb_typeof((provider_outcomes)::jsonb) = 'array'::text) AND "
    '(NOT jsonb_path_exists((provider_outcomes)::jsonb, \'$[*]?(((@.type() != "object" || '
    '!(exists (@."status"))) || @."status".type() != "string") || !((@."status" == "downloaded" || '
    '@."status" == "empty") || @."status" == "error"))\'::jsonpath))))'
)
_SSF_CHECK_NAME = "ck_ssf_change_signals_event_types"
_SSF_CHECK_SQL = (
    "CHECK (((jsonb_typeof((event_types)::jsonb) = 'array'::text) AND "
    '(NOT jsonb_path_exists((event_types)::jsonb, \'$[*]?(@.type() != "string" || !(((@ == "increase" || '
    '@ == "decrease") || @ == "new_entry") || @ == "exit"))\'::jsonpath))))'
)
_CHECKS = (
    ("daily_bar_diagnostics", _PROVIDER_CHECK_NAME, _PROVIDER_CHECK_SQL),
    ("ssf_change_signals", _SSF_CHECK_NAME, _SSF_CHECK_SQL),
)
_SNAPSHOT_SCHEMA_CHECK_NAME = "forecast_snapshot_schema_contract"


def _result(
    *, dry_run: bool = False, rollback: bool = False, converted: bool = False, rolled_back: bool = False
) -> StorageEnumMigrationResult:
    return StorageEnumMigrationResult(dry_run, rollback, converted, rolled_back, STORAGE_ENUM_GROUPS)


def _adapter_preflight(connection: Connection, *, rollback: bool) -> None:
    _ensure_hk_recovery_authority(connection, dry_run=True)
    snapshot_tables = (ForecastSnapshotRun.__table__, ForecastSnapshotRecord.__table__)
    snapshot_table_count = sum(_table_exists(connection, table.name) for table in snapshot_tables)
    if snapshot_table_count == 1:
        raise StorageEnumMigrationError("partially missing forecast snapshot tables")
    missing = _preflight(connection, rollback=rollback)
    if not rollback and snapshot_table_count == 0 and missing == {ForecastSnapshotRun.__table__.name}:
        return
    if missing and len(missing) != len(_GOVERNED_TABLES):
        raise StorageEnumMigrationError(f"partially missing governed tables: {sorted(missing)}")


def _adapter_apply(connection: Connection) -> bool:
    hk_changed = _ensure_hk_recovery_authority(connection)
    _adapter_preflight(connection, rollback=False)
    labels_changed = _upgrade_daily_bar_diagnostic_adjust_labels(connection)
    missing = _preflight(connection, rollback=False)
    changed = (
        hk_changed
        or labels_changed
        or bool(missing)
        or any(
            not _column_has_type(connection, column, group.type_name)
            for group in STORAGE_ENUM_GROUPS
            for column in group.columns
        )
        or not _snapshot_running_range_index_matches(connection)
    )
    for group in STORAGE_ENUM_GROUPS:
        _create_type(connection, group)
    if missing:
        _create_missing_tables(connection, missing)
    else:
        for group in STORAGE_ENUM_GROUPS:
            _alter_group(connection, group, rollback=False)
    _upgrade_snapshot_schema(connection)
    _create_snapshot_indexes(connection)
    ForecastSnapshotRecord.__table__.create(connection, checkfirst=True)
    _upgrade_snapshot_schema(connection)
    _add_checks(connection)
    return changed


def _adapter_verify(connection: Connection, *, rollback: bool) -> None:
    if rollback and all(not _table_exists(connection, table.name) for table in _GOVERNED_TABLES):
        return
    _verify(connection, rollback=rollback)


def _adapter_rollback(connection: Connection) -> bool:
    _adapter_preflight(connection, rollback=True)
    if all(not _table_exists(connection, table.name) for table in _GOVERNED_TABLES):
        return False
    return _rollback(connection)


def _adapter_audit(connection: Connection, *, rollback: bool):
    from storage.enum_governance import (
        EnumGovernanceCheckAudit,
        EnumGovernanceColumnAudit,
        EnumGovernanceDomainAudit,
        EnumGovernanceGroupAudit,
    )

    missing_tables = {table.name for table in _GOVERNED_TABLES if not _table_exists(connection, table.name)}
    groups = []
    for group in STORAGE_ENUM_GROUPS:
        observed_labels = _enum_labels(connection, group.type_name)
        columns = []
        for column in group.columns:
            facts = None if column.table_name in missing_tables else _column_facts(connection, column)
            observed_type = None if facts is None else facts[0]
            observed_default = None if facts is None else _column_default(connection, column)
            observed_values = () if facts is None else _column_values(connection, column)
            enum_typed = observed_type == group.type_name
            expected_type = group.type_name
            expected_default = (
                column.default_sql
                if not enum_typed
                else _enum_default(column.default_sql, group.type_name)
                if column.default_sql
                else None
            )
            valid_type = observed_type == expected_type or (
                not rollback and observed_type == _normalized_type(column.legacy_type_sql)
            )
            values_ready = not observed_values or all(
                value is None or value in group.labels for value in observed_values
            )
            missing_table = column.table_name in missing_tables
            ready = missing_table or (
                facts is not None
                and valid_type
                and facts[1] == column.nullable
                and values_ready
                and _defaults_match(observed_default, expected_default)
            )
            columns.append(
                EnumGovernanceColumnAudit(
                    column.table_name,
                    column.column_name,
                    expected_type,
                    observed_type,
                    group.labels,
                    observed_values,
                    expected_default,
                    observed_default,
                    (),
                    True,
                    ready,
                    None if ready else "incompatible column catalog facts",
                )
            )
        dependencies = _type_dependencies(connection, group) if rollback and observed_labels else ()
        ready = observed_labels in ((), group.labels) and all(column.ready for column in columns) and not dependencies
        groups.append(
            EnumGovernanceGroupAudit(
                group.type_name,
                group.labels,
                observed_labels,
                tuple(columns),
                dependencies,
                ready,
                None if ready else "incompatible enum catalog facts",
            )
        )
    checks_required = rollback and any(
        column.observed_type == group.type_name for group in groups for column in group.columns
    )
    checks = []
    for table_name, name, definition in _CHECKS:
        observed_definition = None if table_name in missing_tables else _check_definition(connection, table_name, name)
        ready = _check_ready(connection, table_name, name, definition, required=checks_required)
        checks.append(
            EnumGovernanceCheckAudit(
                table_name,
                name,
                checks_required,
                observed_definition,
                ready,
                None if ready else "incompatible constraint",
            )
        )
    snapshot_schema_ready = _snapshot_schema_contract_matches(connection, rollback=rollback)
    checks.append(
        EnumGovernanceCheckAudit(
            tb_name_forecast_snapshot_run,
            _SNAPSHOT_SCHEMA_CHECK_NAME,
            True,
            None,
            snapshot_schema_ready,
            None if snapshot_schema_ready else "incomplete forecast snapshot schema contract",
        )
    )
    return EnumGovernanceDomainAudit(
        "storage",
        tuple(groups),
        tuple(checks),
        tuple(sorted(missing_tables)),
        all(group.ready for group in groups) and all(check.ready for check in checks),
    )


STORAGE_ENUM_ADAPTER = EnumGovernanceAdapter(
    "storage",
    _adapter_preflight,
    _adapter_apply,
    _adapter_verify,
    _adapter_rollback,
    _result,
    _adapter_audit,
)


def migrate_storage_enums(
    connection: Connection, *, dry_run: bool = False, rollback: bool = False
) -> StorageEnumMigrationResult:
    if connection.dialect.name != "postgresql":
        return _result(dry_run=dry_run, rollback=rollback)
    STORAGE_ENUM_ADAPTER.preflight(connection, rollback=rollback)
    if dry_run:
        return _result(dry_run=True, rollback=rollback)
    if rollback:
        from paper_trading.storage.enum_migration import (
            preflight_diagnostics_only_market_rollback,
            rollback_diagnostics_only_market,
        )

        paper_diagnostics_rollback = preflight_diagnostics_only_market_rollback(connection)
        rolled_back = STORAGE_ENUM_ADAPTER.rollback(connection)
        if paper_diagnostics_rollback:
            rollback_diagnostics_only_market(connection)
        STORAGE_ENUM_ADAPTER.verify(connection, rollback=True)
        return _result(rollback=True, rolled_back=rolled_back or paper_diagnostics_rollback)
    converted = STORAGE_ENUM_ADAPTER.apply(connection)
    STORAGE_ENUM_ADAPTER.verify(connection, rollback=False)
    return _result(converted=converted)


def _ensure_hk_recovery_authority(connection: Connection, *, dry_run: bool = False) -> bool:
    """Create or safely upgrade the dated HK authority table."""
    table_name = HkRecoveryAuthority.__table__.name
    type_name = "hk_suspension_state"
    expected_labels = ("active", "suspended", "unknown")
    existing_labels = _enum_labels(connection, type_name)
    if existing_labels and existing_labels != expected_labels:
        raise StorageEnumMigrationError(f"{type_name}: unexpected enum labels {existing_labels}")

    if not _table_exists(connection, table_name):
        if not dry_run:
            if not existing_labels:
                connection.execute(text("CREATE TYPE hk_suspension_state AS ENUM ('active', 'suspended', 'unknown')"))
            HkRecoveryAuthority.__table__.create(connection, checkfirst=True)
        return True
    column_type = connection.execute(
        text(
            "SELECT udt_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = :table_name "
            "AND column_name = 'suspension_state'"
        ),
        {"table_name": table_name},
    ).scalar_one_or_none()
    if column_type == type_name:
        return False
    invalid = connection.execute(
        text(
            f"SELECT suspension_state FROM {table_name} "
            "WHERE suspension_state NOT IN ('active', 'suspended', 'unknown') LIMIT 1"
        )
    ).scalar_one_or_none()
    if invalid is not None:
        raise StorageEnumMigrationError("hk_suspension_state: invalid existing value")
    if not dry_run:
        if not existing_labels:
            connection.execute(text("CREATE TYPE hk_suspension_state AS ENUM ('active', 'suspended', 'unknown')"))
        connection.execute(
            text(
                f"ALTER TABLE {table_name} ALTER COLUMN suspension_state TYPE hk_suspension_state "
                "USING suspension_state::text::hk_suspension_state"
            )
        )
    return True


def _preflight(connection: Connection, *, rollback: bool) -> set[str]:
    missing = {table.name for table in _GOVERNED_TABLES if not _table_exists(connection, table.name)}
    for group in STORAGE_ENUM_GROUPS:
        labels = _enum_labels(connection, group.type_name)
        known_legacy_adjust_labels = (
            not rollback
            and group.type_name == "daily_bar_diagnostic_adjust"
            and labels == _PRE_RAW_DAILY_BAR_DIAGNOSTIC_ADJUST_LABELS
        )
        if labels and labels != group.labels and not known_legacy_adjust_labels:
            raise StorageEnumMigrationError(f"{group.type_name}: unexpected enum labels {labels}")
        for column in group.columns:
            if column.table_name in missing:
                continue
            facts = _column_facts(connection, column)
            expected = _normalized_type(column.legacy_type_sql)
            if facts is None or facts[0] not in (expected, group.type_name) or facts[1] != column.nullable:
                raise StorageEnumMigrationError(
                    f"{group.type_name}: incompatible {column.table_name}.{column.column_name}"
                )
            _validate_default(connection, group, column, rollback=facts[0] != group.type_name)
            if not rollback and facts[0] != group.type_name:
                _validate_values(connection, group, column)
            if rollback and group.type_name == "daily_bar_diagnostic_adjust" and facts[0] == group.type_name:
                _validate_values(connection, group, column, _PRE_RAW_DAILY_BAR_DIAGNOSTIC_ADJUST_LABELS)
    if "daily_bar_diagnostics" not in missing:
        _validate_json(connection, "daily_bar_diagnostics", "provider_outcomes", validate_provider_outcomes)
    if "ssf_change_signals" not in missing:
        _validate_json(connection, "ssf_change_signals", "event_types", validate_ssf_event_types)
    checks_required = rollback and any(
        _column_has_type(connection, column, group.type_name)
        for group in STORAGE_ENUM_GROUPS
        for column in group.columns
    )
    for table_name, name, definition in _CHECKS:
        if table_name not in missing:
            _validate_check(connection, table_name, name, definition, required=checks_required)
    if rollback:
        for group in STORAGE_ENUM_GROUPS:
            if _enum_labels(connection, group.type_name):
                dependencies = _type_dependencies(connection, group)
                if dependencies:
                    raise StorageEnumMigrationError(f"{group.type_name}: dependencies remain: {dependencies}")
    return missing


def _create_missing_tables(connection: Connection, missing: set[str]) -> None:
    tables = [table for table in _GOVERNED_TABLES if table.name in missing]
    if tables:
        from paper_trading.storage.enum_migration import ensure_paper_market_type

        ensure_paper_market_type(connection)
        tables[0].metadata.create_all(connection, tables=tables, checkfirst=True)


def _create_snapshot_indexes(connection: Connection) -> None:
    for index in ForecastSnapshotRun.__table__.indexes:
        if _index_exists(connection, index.name) and not _snapshot_running_range_index_matches(connection):
            connection.execute(text(f"DROP INDEX {index.name}"))
        index.create(connection, checkfirst=True)


def _upgrade_snapshot_schema(connection: Connection) -> None:
    if not _table_exists(connection, tb_name_forecast_snapshot_run):
        return
    run_columns = {
        "requested_date_count": "integer NOT NULL DEFAULT 0",
        "covered_date_count": "integer NOT NULL DEFAULT 0",
        "source_row_count": "integer NOT NULL DEFAULT 0",
        "record_count": "integer NOT NULL DEFAULT 0",
        "duplicate_record_count": "integer NOT NULL DEFAULT 0",
        "same_day_conflict_count": "integer NOT NULL DEFAULT 0",
        "created_at": "timestamp with time zone NOT NULL DEFAULT now()",
        "completed_at": "timestamp with time zone",
        "failed_at": "timestamp with time zone",
        "failure_detail": "text",
    }
    existing_run_columns = _table_column_names(connection, tb_name_forecast_snapshot_run)
    for name, definition in run_columns.items():
        if name not in existing_run_columns:
            connection.execute(text(f"ALTER TABLE {tb_name_forecast_snapshot_run} ADD COLUMN {name} {definition}"))
    _ensure_generated_id(connection, tb_name_forecast_snapshot_run)
    if _table_exists(connection, tb_name_forecast_snapshot_record):
        _ensure_generated_id(connection, tb_name_forecast_snapshot_record)

    if _constraint_exists(
        connection, tb_name_forecast_snapshot_run, "uq_forecast_snapshot_attempt"
    ) and not _unique_constraint_matches(
        connection,
        tb_name_forecast_snapshot_run,
        "uq_forecast_snapshot_attempt",
        ("report_end_date", "announcement_start_date", "announcement_end_date", "attempt"),
    ):
        connection.execute(text("ALTER TABLE forecast_snapshot_runs DROP CONSTRAINT uq_forecast_snapshot_attempt"))
    if not _constraint_exists(connection, tb_name_forecast_snapshot_run, "uq_forecast_snapshot_attempt"):
        connection.execute(
            text(
                "ALTER TABLE forecast_snapshot_runs ADD CONSTRAINT uq_forecast_snapshot_attempt "
                "UNIQUE (report_end_date, announcement_start_date, announcement_end_date, attempt)"
            )
        )
    if not _table_exists(connection, tb_name_forecast_snapshot_record):
        return
    if _constraint_exists(
        connection, tb_name_forecast_snapshot_record, "uq_forecast_snapshot_record_source_order"
    ) and not _unique_constraint_matches(
        connection,
        tb_name_forecast_snapshot_record,
        "uq_forecast_snapshot_record_source_order",
        ("run_id", "announcement_date", "source_order"),
    ):
        connection.execute(
            text("ALTER TABLE forecast_snapshot_records DROP CONSTRAINT uq_forecast_snapshot_record_source_order")
        )
    if not _constraint_exists(connection, tb_name_forecast_snapshot_record, "uq_forecast_snapshot_record_source_order"):
        connection.execute(
            text(
                "ALTER TABLE forecast_snapshot_records ADD CONSTRAINT uq_forecast_snapshot_record_source_order "
                "UNIQUE (run_id, announcement_date, source_order)"
            )
        )


def _snapshot_schema_contract_matches(connection: Connection, *, rollback: bool) -> bool:
    if rollback:
        return True
    snapshot_table_states = tuple(
        _table_exists(connection, name) for name in (tb_name_forecast_snapshot_run, tb_name_forecast_snapshot_record)
    )
    if not any(snapshot_table_states):
        return True
    if not all(snapshot_table_states):
        return False
    expected_run_columns = {
        "id": ("integer", False, None),
        "report_end_date": ("date", False, None),
        "announcement_start_date": ("date", False, None),
        "announcement_end_date": ("date", False, None),
        "attempt": ("integer", False, None),
        "status": ("forecast_snapshot_status", False, None),
        "requested_date_count": ("integer", False, "0"),
        "covered_date_count": ("integer", False, "0"),
        "source_row_count": ("integer", False, "0"),
        "record_count": ("integer", False, "0"),
        "duplicate_record_count": ("integer", False, "0"),
        "same_day_conflict_count": ("integer", False, "0"),
        "created_at": ("timestamp with time zone", False, "now()"),
        "completed_at": ("timestamp with time zone", True, None),
        "failed_at": ("timestamp with time zone", True, None),
        "failure_detail": ("text", True, None),
    }
    expected_record_columns = {
        "id": ("integer", False, None),
        "run_id": ("integer", False, None),
        "ts_code": ("character varying(32)", False, None),
        "announcement_date": ("date", False, None),
        "report_end_date": ("date", False, None),
        "forecast_type": ("character varying(20)", False, None),
        "growth_min": ("double precision", True, None),
        "growth_max": ("double precision", True, None),
        "source_order": ("integer", False, None),
    }
    run_facts = _table_column_facts(connection, tb_name_forecast_snapshot_run)
    record_facts = _table_column_facts(connection, tb_name_forecast_snapshot_record)
    return (
        all(
            run_facts.get(name) is not None
            and run_facts[name][0] == column_type
            and run_facts[name][1] == nullable
            and (name == "id" or _defaults_match(run_facts[name][2], default))
            for name, (column_type, nullable, default) in expected_run_columns.items()
        )
        and all(
            record_facts.get(name) is not None
            and record_facts[name][:2] == expected[:2]
            and (name == "id" or _defaults_match(record_facts[name][2], expected[2]))
            for name, expected in expected_record_columns.items()
        )
        and _has_generated_id(connection, tb_name_forecast_snapshot_run)
        and _has_generated_id(connection, tb_name_forecast_snapshot_record)
        and _primary_key_matches(connection, tb_name_forecast_snapshot_run, ("id",))
        and _primary_key_matches(connection, tb_name_forecast_snapshot_record, ("id",))
        and _unique_constraint_matches(
            connection,
            tb_name_forecast_snapshot_run,
            "uq_forecast_snapshot_attempt",
            ("report_end_date", "announcement_start_date", "announcement_end_date", "attempt"),
        )
        and _unique_constraint_matches(
            connection,
            tb_name_forecast_snapshot_record,
            "uq_forecast_snapshot_record_source_order",
            ("run_id", "announcement_date", "source_order"),
        )
        and _snapshot_record_foreign_key_matches(connection)
        and _snapshot_running_range_index_matches(connection)
    )


def _ensure_generated_id(connection: Connection, table_name: str) -> None:
    if not _has_generated_id(connection, table_name):
        connection.execute(text(f"ALTER TABLE {table_name} ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY"))
    connection.execute(
        text(
            f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), "
            f"COALESCE((SELECT max(id) FROM {table_name}), 1), "
            f"(SELECT max(id) IS NOT NULL FROM {table_name}))"
        )
    )


def _has_generated_id(connection: Connection, table_name: str) -> bool:
    return bool(
        connection.execute(
            text(
                "SELECT EXISTS (SELECT FROM pg_class c JOIN pg_attribute a ON a.attrelid = c.oid "
                "LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
                "WHERE c.relnamespace = current_schema()::regnamespace AND c.relname = :table_name "
                "AND a.attname = 'id' AND (a.attidentity <> '' OR d.oid IS NOT NULL))"
            ),
            {"table_name": table_name},
        ).scalar_one()
    )


def _validate_json(connection: Connection, table_name: str, column_name: str, validator: object) -> None:
    for row_id, value in connection.execute(text(f"SELECT id, {column_name} FROM {table_name}")):
        try:
            validator(value)  # type: ignore[operator]
        except ValueError as error:
            raise StorageEnumMigrationError(f"{column_name} for {table_name}.id={row_id}: {error}") from error


def _validate_values(
    connection: Connection, group: StorageEnumGroup, column: StorageEnumColumn, labels: tuple[str, ...] | None = None
) -> None:
    labels = group.labels if labels is None else labels
    values = (
        connection.execute(
            text(
                f"SELECT DISTINCT {column.column_name}::text FROM {column.table_name} "
                f"WHERE {column.column_name} IS NULL OR {column.column_name}::text NOT IN :labels"
            ).bindparams(bindparam("labels", expanding=True)),
            {"labels": labels},
        )
        .scalars()
        .all()
    )
    if values and (not column.nullable or any(value is not None for value in values)):
        raise StorageEnumMigrationError(f"{group.type_name}: unknown legacy values {values}")


def _column_values(connection: Connection, column: StorageEnumColumn) -> tuple[str | None, ...]:
    return tuple(
        connection.execute(
            text(
                f"SELECT DISTINCT {column.column_name}::text FROM {column.table_name} "
                f"ORDER BY {column.column_name}::text NULLS FIRST"
            )
        ).scalars()
    )


def _defaults_match(observed: str | None, expected: str | None) -> bool:
    return (
        observed is None
        if expected is None
        else observed is not None and _normalize_expression(observed) == _normalize_expression(expected)
    )


def _check_ready(connection: Connection, table_name: str, name: str, definition: str, *, required: bool) -> bool:
    try:
        _validate_check(connection, table_name, name, definition, required=required)
    except StorageEnumMigrationError:
        return False
    return True


def _create_type(connection: Connection, group: StorageEnumGroup) -> None:
    if not _enum_labels(connection, group.type_name):
        connection.execute(
            text(f"CREATE TYPE {group.type_name} AS ENUM ({', '.join(repr(label) for label in group.labels)})")
        )


def ensure_daily_bar_diagnostic_adjust_type(connection: Connection) -> None:
    """Bootstrap the shared diagnostic enum without applying storage migrations."""
    group = next(group for group in STORAGE_ENUM_GROUPS if group.type_name == "daily_bar_diagnostic_adjust")
    _create_type(connection, group)


def _upgrade_daily_bar_diagnostic_adjust_labels(connection: Connection) -> bool:
    labels = _enum_labels(connection, "daily_bar_diagnostic_adjust")
    expected = _labels(DailyBarDiagnosticAdjust)
    if not labels or labels == expected:
        return False
    if labels != _PRE_RAW_DAILY_BAR_DIAGNOSTIC_ADJUST_LABELS:
        raise StorageEnumMigrationError(f"daily_bar_diagnostic_adjust: unexpected enum labels {labels}")
    connection.execute(text("ALTER TYPE daily_bar_diagnostic_adjust ADD VALUE IF NOT EXISTS 'raw'"))
    return True


def _alter_group(connection: Connection, group: StorageEnumGroup, *, rollback: bool) -> None:
    for column in group.columns:
        if not rollback and _column_has_type(connection, column, group.type_name):
            continue
        if column.default_sql is not None:
            connection.execute(text(f"ALTER TABLE {column.table_name} ALTER COLUMN {column.column_name} DROP DEFAULT"))
        target = column.legacy_type_sql if rollback else group.type_name
        connection.execute(
            text(
                f"ALTER TABLE {column.table_name} ALTER COLUMN {column.column_name} TYPE {target} USING {column.column_name}::text::{target}"
            )
        )
        if column.default_sql is not None:
            default = column.default_sql if rollback else _enum_default(column.default_sql, group.type_name)
            connection.execute(
                text(f"ALTER TABLE {column.table_name} ALTER COLUMN {column.column_name} SET DEFAULT {default}")
            )


def _add_checks(connection: Connection) -> None:
    for table_name, name, definition in _CHECKS:
        if _check_definition(connection, table_name, name) is None:
            connection.execute(text(f"ALTER TABLE {table_name} ADD CONSTRAINT {name} {definition}"))


def _rollback(connection: Connection) -> bool:
    changed = False
    if _index_exists(connection, "uq_forecast_snapshot_running_range"):
        connection.execute(text("DROP INDEX uq_forecast_snapshot_running_range"))
        changed = True
    for group in STORAGE_ENUM_GROUPS:
        if any(_column_has_type(connection, column, group.type_name) for column in group.columns):
            _alter_group(connection, group, rollback=True)
            changed = True
    for table_name, name, _ in _CHECKS:
        if _check_definition(connection, table_name, name) is not None:
            connection.execute(text(f"ALTER TABLE {table_name} DROP CONSTRAINT {name}"))
    for group in STORAGE_ENUM_GROUPS:
        if _enum_labels(connection, group.type_name):
            connection.execute(text(f"DROP TYPE {group.type_name}"))
    return changed


def _verify(connection: Connection, *, rollback: bool) -> None:
    for group in STORAGE_ENUM_GROUPS:
        if not rollback and _enum_labels(connection, group.type_name) != group.labels:
            raise StorageEnumMigrationError(f"{group.type_name}: labels were not preserved")
        for column in group.columns:
            facts = _column_facts(connection, column)
            expected = _normalized_type(column.legacy_type_sql) if rollback else group.type_name
            if facts is None or facts[0] != expected:
                raise StorageEnumMigrationError(
                    f"{group.type_name}: verification failed for {column.table_name}.{column.column_name}"
                )
            _validate_default(connection, group, column, rollback=rollback)
    for table_name, name, definition in _CHECKS:
        _validate_check(connection, table_name, name, definition, required=not rollback)
    if not _snapshot_schema_contract_matches(connection, rollback=rollback):
        raise StorageEnumMigrationError("forecast snapshot schema contract verification failed")


def _table_exists(connection: Connection, table_name: str) -> bool:
    return (
        connection.execute(text("SELECT to_regclass(:table_name)"), {"table_name": table_name}).scalar_one() is not None
    )


def _table_column_names(connection: Connection, table_name: str) -> set[str]:
    return set(_table_column_facts(connection, table_name))


def _table_column_facts(connection: Connection, table_name: str) -> dict[str, tuple[str, bool, str | None]]:
    return {
        str(name): (str(column_type), bool(nullable), None if default is None else str(default))
        for name, column_type, nullable, default in connection.execute(
            text(
                "SELECT a.attname, lower(format_type(a.atttypid, a.atttypmod)), NOT a.attnotnull, "
                "pg_get_expr(d.adbin, d.adrelid) "
                "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
                "WHERE n.nspname = current_schema() AND c.relname = :table_name "
                "AND a.attnum > 0 AND NOT a.attisdropped"
            ),
            {"table_name": table_name},
        )
    }


def _constraint_exists(connection: Connection, table_name: str, constraint_name: str) -> bool:
    return (
        connection.execute(
            text(
                "SELECT EXISTS (SELECT FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
                "WHERE c.connamespace = current_schema()::regnamespace AND t.relname = :table_name "
                "AND c.conname = :constraint_name)"
            ),
            {"table_name": table_name, "constraint_name": constraint_name},
        ).scalar_one()
        is True
    )


def _unique_constraint_matches(
    connection: Connection, table_name: str, constraint_name: str, columns: tuple[str, ...]
) -> bool:
    actual = connection.execute(
        text(
            "SELECT array_agg(a.attname ORDER BY key.ordinality) "
            "FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN unnest(c.conkey) WITH ORDINALITY AS key(attnum, ordinality) ON TRUE "
            "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = key.attnum "
            "WHERE c.connamespace = current_schema()::regnamespace AND t.relname = :table_name "
            "AND c.conname = :constraint_name AND c.contype = 'u' GROUP BY c.oid"
        ),
        {"table_name": table_name, "constraint_name": constraint_name},
    ).scalar_one_or_none()
    return actual is not None and tuple(actual) == columns


def _primary_key_matches(connection: Connection, table_name: str, columns: tuple[str, ...]) -> bool:
    actual = connection.execute(
        text(
            "SELECT array_agg(a.attname ORDER BY key.ordinality) "
            "FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN unnest(c.conkey) WITH ORDINALITY AS key(attnum, ordinality) ON TRUE "
            "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = key.attnum "
            "WHERE c.connamespace = current_schema()::regnamespace AND t.relname = :table_name "
            "AND c.contype = 'p' GROUP BY c.oid"
        ),
        {"table_name": table_name},
    ).scalar_one_or_none()
    return actual is not None and tuple(actual) == columns


def _snapshot_record_foreign_key_matches(connection: Connection) -> bool:
    return bool(
        connection.execute(
            text(
                "SELECT EXISTS (SELECT FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_class target ON target.oid = c.confrelid "
                "WHERE c.connamespace = current_schema()::regnamespace "
                "AND t.relname = 'forecast_snapshot_records' AND target.relname = 'forecast_snapshot_runs' "
                "AND c.contype = 'f' AND c.conkey = ARRAY[(SELECT attnum FROM pg_attribute "
                "WHERE attrelid = t.oid AND attname = 'run_id')] "
                "AND c.confkey = ARRAY[(SELECT attnum FROM pg_attribute "
                "WHERE attrelid = target.oid AND attname = 'id')])"
            )
        ).scalar_one()
    )


def _index_exists(connection: Connection, index_name: str) -> bool:
    return (
        connection.execute(text("SELECT to_regclass(:index_name)"), {"index_name": index_name}).scalar_one() is not None
    )


def _snapshot_running_range_index_matches(connection: Connection) -> bool:
    row = connection.execute(
        text(
            "SELECT i.indisunique, array_agg(a.attname ORDER BY key.ordinality), "
            "pg_get_expr(i.indpred, i.indrelid) "
            "FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indexrelid "
            "JOIN pg_class t ON t.oid = i.indrelid "
            "JOIN unnest(i.indkey) WITH ORDINALITY AS key(attnum, ordinality) ON key.ordinality <= i.indnkeyatts "
            "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = key.attnum "
            "WHERE c.relnamespace = current_schema()::regnamespace "
            "AND c.relname = 'uq_forecast_snapshot_running_range' "
            "GROUP BY i.indexrelid, i.indisunique, i.indpred"
        )
    ).one_or_none()
    return row == (
        True,
        ["report_end_date", "announcement_start_date", "announcement_end_date"],
        "(status = 'running'::forecast_snapshot_status)",
    )


def _column_facts(connection: Connection, column: StorageEnumColumn) -> tuple[str, bool] | None:
    row = connection.execute(
        text(
            "SELECT lower(format_type(a.atttypid, a.atttypmod)), NOT a.attnotnull FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = current_schema() AND c.relname = :table_name AND a.attname = :column_name AND a.attnum > 0 AND NOT a.attisdropped"
        ),
        {"table_name": column.table_name, "column_name": column.column_name},
    ).one_or_none()
    return None if row is None else (str(row[0]), bool(row[1]))


def _column_has_type(connection: Connection, column: StorageEnumColumn, type_name: str) -> bool:
    facts = _column_facts(connection, column)
    return facts is not None and facts[0] == type_name


def _normalized_type(type_sql: str) -> str:
    return type_sql.lower().replace("varchar", "character varying")


def _column_default(connection: Connection, column: StorageEnumColumn) -> str | None:
    result = connection.execute(
        text(
            "SELECT pg_get_expr(d.adbin, d.adrelid) FROM pg_attrdef d JOIN pg_class c ON c.oid = d.adrelid JOIN pg_namespace n ON n.oid = c.relnamespace JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.adnum WHERE n.nspname = current_schema() AND c.relname = :table_name AND a.attname = :column_name"
        ),
        {"table_name": column.table_name, "column_name": column.column_name},
    ).scalar_one_or_none()
    return None if result is None else str(result)


def _enum_default(legacy_default: str, type_name: str) -> str:
    return f"{legacy_default.partition('::')[0]}::{type_name}"


def _normalize_expression(expression: str) -> str:
    return re.sub(r"\s+", "", expression).lower().replace("::text::", "::").replace("(", "").replace(")", "")


def _validate_default(
    connection: Connection, group: StorageEnumGroup, column: StorageEnumColumn, *, rollback: bool
) -> None:
    expected = (
        column.default_sql
        if rollback
        else (None if column.default_sql is None else _enum_default(column.default_sql, group.type_name))
    )
    actual = _column_default(connection, column)
    if expected is None:
        if actual is not None:
            raise StorageEnumMigrationError(
                f"{group.type_name}: unexpected default for {column.table_name}.{column.column_name}"
            )
    elif actual is None or _normalize_expression(actual) != _normalize_expression(expected):
        raise StorageEnumMigrationError(
            f"{group.type_name}: default mismatch for {column.table_name}.{column.column_name}"
        )


def _enum_labels(connection: Connection, type_name: str) -> tuple[str, ...]:
    return tuple(
        connection.execute(
            text(
                "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid JOIN pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname = current_schema() AND t.typname = :type_name ORDER BY e.enumsortorder"
            ),
            {"type_name": type_name},
        ).scalars()
    )


def _check_definition(connection: Connection, table_name: str, name: str) -> str | None:
    definition = connection.execute(
        text(
            "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid WHERE c.connamespace = current_schema()::regnamespace AND t.relname = :table_name AND c.conname = :name"
        ),
        {"table_name": table_name, "name": name},
    ).scalar_one_or_none()
    return None if definition is None else str(definition)


def _validate_check(connection: Connection, table_name: str, name: str, definition: str, *, required: bool) -> None:
    actual = _check_definition(connection, table_name, name)
    if actual is None:
        if required:
            raise StorageEnumMigrationError(f"missing constraint: {name}")
        return
    if _normalize_expression(actual).replace("::jsonb", "") != _normalize_expression(definition).replace("::jsonb", ""):
        raise StorageEnumMigrationError(f"conflicting constraint: {name}")


def _type_dependencies(connection: Connection, group: StorageEnumGroup) -> tuple[str, ...]:
    managed = ", ".join(f"(:table_{index}, :column_{index})" for index, _ in enumerate(group.columns))
    parameters = {"type_name": group.type_name}
    parameters.update(
        {
            key: value
            for index, column in enumerate(group.columns)
            for key, value in ((f"table_{index}", column.table_name), (f"column_{index}", column.column_name))
        }
    )
    return tuple(
        connection.execute(
            text(
                "WITH managed(table_name, column_name) AS (VALUES "
                + managed
                + ") SELECT DISTINCT COALESCE('view ' || v.relname, pg_describe_object(d.classid, d.objid, d.objsubid)) FROM pg_depend d JOIN pg_type t ON t.oid = d.refobjid LEFT JOIN pg_class vc ON vc.oid = d.objid AND vc.relkind = 'v' LEFT JOIN pg_rewrite r ON d.classid = 'pg_rewrite'::regclass AND r.oid = d.objid LEFT JOIN pg_class v ON v.oid = COALESCE(vc.oid, r.ev_class) WHERE d.refclassid = 'pg_type'::regclass AND t.typnamespace = current_schema()::regnamespace AND t.typname = :type_name AND d.deptype NOT IN ('i', 'a') AND NOT (t.typname = 'forecast_snapshot_status' AND d.classid = 'pg_class'::regclass AND d.objid = to_regclass('uq_forecast_snapshot_running_range')) AND NOT EXISTS (SELECT 1 FROM managed m JOIN pg_class c ON c.relname = m.table_name JOIN pg_namespace n ON n.oid = c.relnamespace JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = m.column_name LEFT JOIN pg_attrdef ad ON ad.adrelid = c.oid AND ad.adnum = a.attnum WHERE n.nspname = current_schema() AND ((d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.objsubid = a.attnum) OR (d.classid = 'pg_attrdef'::regclass AND d.objid = ad.oid))) AND NOT (d.classid = 'pg_class'::regclass AND EXISTS (SELECT 1 FROM pg_class recovery_table JOIN pg_namespace recovery_schema ON recovery_schema.oid = recovery_table.relnamespace WHERE recovery_schema.nspname = current_schema() AND recovery_table.relname LIKE 'paper_data_gap_recovery_%' AND d.objid = recovery_table.oid)) AND NOT (d.classid = 'pg_constraint'::regclass AND EXISTS (SELECT 1 FROM pg_constraint recovery_constraint JOIN pg_class recovery_table ON recovery_table.oid = recovery_constraint.conrelid JOIN pg_namespace recovery_schema ON recovery_schema.oid = recovery_table.relnamespace WHERE recovery_schema.nspname = current_schema() AND recovery_table.relname LIKE 'paper_data_gap_recovery_%' AND d.objid = recovery_constraint.oid)) ORDER BY 1"
            ),
            parameters,
        ).scalars()
    )
