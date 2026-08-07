from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from monitor.condition_validation import validate_condition
from monitor.domain_enums import ForecastSSFCandidateState, MonitorFrequency, MonitorMarket, MonitorResetMode
from storage.model import ForecastSSFCandidate, StockMonitorTarget


class MonitorEnumMigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MonitorEnumColumn:
    table_name: str
    column_name: str
    legacy_type_sql: str
    default_sql: str | None
    nullable: bool = False
    indexes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class MonitorEnumGroup:
    type_name: str
    labels: tuple[str, ...]
    columns: tuple[MonitorEnumColumn, ...]


@dataclass(frozen=True)
class MonitorEnumMigrationResult:
    dry_run: bool
    rollback: bool
    converted: bool
    rolled_back: bool
    groups: tuple[MonitorEnumGroup, ...]


def _labels(enum_type: type[StrEnum]) -> tuple[str, ...]:
    return tuple(member.value for member in enum_type)


def _index(name: str, table_name: str, column_name: str) -> tuple[str, str]:
    return name, f"CREATE INDEX {name} ON {table_name} ({column_name})"


def _column(
    table_name: str,
    column_name: str,
    legacy_type_sql: str,
    default_sql: str | None = None,
    *,
    nullable: bool = False,
    indexes: tuple[tuple[str, str], ...] = (),
) -> MonitorEnumColumn:
    if default_sql is not None and "::" not in default_sql:
        default_sql = f"{default_sql}::character varying"
    return MonitorEnumColumn(table_name, column_name, legacy_type_sql, default_sql, nullable, indexes)


MONITOR_ENUM_GROUPS = (
    MonitorEnumGroup(
        "monitor_market",
        _labels(MonitorMarket),
        (
            _column(
                "stock_monitor_targets",
                "market",
                "VARCHAR(5)",
                "'A'",
                indexes=(_index("ix_stock_monitor_targets_market", "stock_monitor_targets", "market"),),
            ),
            _column(
                "forecast_ssf_candidates",
                "market",
                "VARCHAR(5)",
                "'A'",
                indexes=(_index("ix_forecast_ssf_candidates_market", "forecast_ssf_candidates", "market"),),
            ),
        ),
    ),
    MonitorEnumGroup(
        "monitor_frequency",
        _labels(MonitorFrequency),
        (
            _column(
                "stock_monitor_targets",
                "frequency",
                "VARCHAR(10)",
                "'daily'",
                indexes=(_index("ix_stock_monitor_targets_frequency", "stock_monitor_targets", "frequency"),),
            ),
        ),
    ),
    MonitorEnumGroup(
        "monitor_reset_mode",
        _labels(MonitorResetMode),
        (
            _column(
                "stock_monitor_targets",
                "reset_mode",
                "VARCHAR(10)",
                "'auto'",
                indexes=(_index("ix_stock_monitor_targets_reset_mode", "stock_monitor_targets", "reset_mode"),),
            ),
        ),
    ),
    MonitorEnumGroup(
        "forecast_ssf_candidate_state",
        _labels(ForecastSSFCandidateState),
        (
            _column(
                "forecast_ssf_candidates",
                "state",
                "VARCHAR(32)",
                indexes=(_index("ix_forecast_ssf_candidates_state", "forecast_ssf_candidates", "state"),),
            ),
        ),
    ),
)

_GOVERNED_TABLES = (StockMonitorTarget.__table__, ForecastSSFCandidate.__table__)
_CONDITION_CHECK_NAME = "ck_stock_monitor_targets_condition_type"
_CONDITION_CHECK_SQL = (
    "CHECK (jsonb_typeof(condition) = 'object' AND condition ? 'type' "
    "AND condition->>'type' IS NOT NULL AND condition->>'type' IN "
    "('price_threshold', 'price_cross_ma', 'price_vs_ma', 'ma_cross', 'change_pct', 'rsi'))"
)
_NORMALIZED_CONDITION_CHECK = (
    "checkjsonb_typeofcondition='object'andcondition?'type'andcondition->>'type'isnotnullandcondition->>'type'=anyarray["
    "'price_threshold','price_cross_ma','price_vs_ma','ma_cross','change_pct','rsi']"
)


def migrate_monitor_enums(
    connection: Connection, *, dry_run: bool = False, rollback: bool = False
) -> MonitorEnumMigrationResult:
    """Convert legacy Monitor and Forecast SSF strings to native PostgreSQL enums.

    The caller owns transaction boundaries and must deliberately invoke this
    operator migration against a PostgreSQL connection.
    """

    def result(converted: bool = False, rolled_back: bool = False) -> MonitorEnumMigrationResult:
        return MonitorEnumMigrationResult(
            dry_run=dry_run,
            rollback=rollback,
            converted=converted,
            rolled_back=rolled_back,
            groups=MONITOR_ENUM_GROUPS,
        )

    if connection.dialect.name != "postgresql":
        return result()

    missing_tables = _preflight(connection, rollback=rollback)
    if missing_tables and len(missing_tables) != len(_GOVERNED_TABLES):
        raise MonitorEnumMigrationError(f"partially missing governed tables: {sorted(missing_tables)}")
    changed = any(
        not _column_has_type(connection, column, group.type_name)
        for group in MONITOR_ENUM_GROUPS
        for column in group.columns
    )
    if dry_run:
        return result()
    if rollback:
        if missing_tables:
            return result()
        rolled_back = _rollback(connection)
        _verify(connection, rollback=True)
        return result(rolled_back=rolled_back)

    if missing_tables:
        for group in MONITOR_ENUM_GROUPS:
            _create_type(connection, group)
        _create_missing_tables(connection, missing_tables)
        _preflight(connection, rollback=False)
        _add_condition_check(connection)
        _verify(connection, rollback=False)
        return result(converted=True)

    for group in MONITOR_ENUM_GROUPS:
        _create_type(connection, group)
    for group in MONITOR_ENUM_GROUPS:
        _alter_group(connection, group, rollback=False)
    _add_condition_check(connection)
    _verify(connection, rollback=False)
    return result(converted=changed)


def _preflight(connection: Connection, *, rollback: bool) -> set[str]:
    missing_tables = {table.name for table in _GOVERNED_TABLES if not _table_exists(connection, table.name)}
    for group in MONITOR_ENUM_GROUPS:
        labels = _enum_labels(connection, group.type_name)
        if labels and labels != group.labels:
            raise MonitorEnumMigrationError(f"{group.type_name}: unexpected enum labels {labels}")
        for column in group.columns:
            if column.table_name in missing_tables:
                continue
            facts = _column_facts(connection, column)
            if facts is None:
                raise MonitorEnumMigrationError(f"{group.type_name}: missing {column.table_name}.{column.column_name}")
            type_name, nullable = facts
            expected = _normalized_type(column.legacy_type_sql)
            valid_type = type_name in (expected, group.type_name)
            if not valid_type or nullable != column.nullable:
                raise MonitorEnumMigrationError(
                    f"{group.type_name}: incompatible {column.table_name}.{column.column_name}"
                )
            _validate_default(connection, group, column, rollback=type_name != group.type_name)
            _validate_indexes(connection, column)
            if not rollback and type_name != group.type_name:
                _validate_values(connection, group, column)
    if "stock_monitor_targets" not in missing_tables:
        _validate_legacy_conditions(connection)
    if rollback:
        check_required = any(
            _column_has_type(connection, column, group.type_name)
            for group in MONITOR_ENUM_GROUPS
            for column in group.columns
        )
        _validate_condition_check(connection, required=check_required)
    else:
        _validate_condition_check(connection, required=False)
    return missing_tables


def _create_missing_tables(connection: Connection, missing_tables: set[str]) -> None:
    tables = [table for table in _GOVERNED_TABLES if table.name in missing_tables]
    if tables:
        tables[0].metadata.create_all(connection, tables=tables, checkfirst=True)


def _validate_legacy_conditions(connection: Connection) -> None:
    rows = connection.execute(text("SELECT id, condition FROM stock_monitor_targets")).all()
    for row_id, condition in rows:
        try:
            validate_condition(condition)
        except ValueError as error:
            raise MonitorEnumMigrationError(f"condition for stock_monitor_targets.id={row_id}: {error}") from error


def _validate_values(connection: Connection, group: MonitorEnumGroup, column: MonitorEnumColumn) -> None:
    unknown = (
        connection.execute(
            text(
                f"SELECT DISTINCT {column.column_name} FROM {column.table_name} "
                f"WHERE {column.column_name} IS NULL OR {column.column_name} NOT IN :labels"
            ).bindparams(bindparam("labels", expanding=True)),
            {"labels": group.labels},
        )
        .scalars()
        .all()
    )
    if unknown and (not column.nullable or any(value is not None for value in unknown)):
        raise MonitorEnumMigrationError(f"{group.type_name}: unknown legacy values {unknown}")


def _create_type(connection: Connection, group: MonitorEnumGroup) -> None:
    if _enum_labels(connection, group.type_name):
        return
    labels = ", ".join(f"'{label}'" for label in group.labels)
    connection.execute(text(f"CREATE TYPE {group.type_name} AS ENUM ({labels})"))


def _alter_group(connection: Connection, group: MonitorEnumGroup, *, rollback: bool) -> None:
    for column in group.columns:
        if not rollback and _column_has_type(connection, column, group.type_name):
            continue
        for index_name, _ in column.indexes:
            connection.execute(text(f"DROP INDEX {index_name}"))
        if column.default_sql is not None:
            connection.execute(text(f"ALTER TABLE {column.table_name} ALTER COLUMN {column.column_name} DROP DEFAULT"))
        target = column.legacy_type_sql if rollback else group.type_name
        connection.execute(
            text(
                f"ALTER TABLE {column.table_name} ALTER COLUMN {column.column_name} TYPE {target} "
                f"USING {column.column_name}::text::{target}"
            )
        )
        if column.default_sql is not None:
            default = column.default_sql if rollback else _enum_default(column.default_sql, group.type_name)
            connection.execute(
                text(f"ALTER TABLE {column.table_name} ALTER COLUMN {column.column_name} SET DEFAULT {default}")
            )
        for _, index_sql in column.indexes:
            connection.execute(text(index_sql))


def _add_condition_check(connection: Connection) -> None:
    if _condition_check_definition(connection) is not None:
        return
    connection.execute(
        text(f"ALTER TABLE stock_monitor_targets ADD CONSTRAINT {_CONDITION_CHECK_NAME} {_CONDITION_CHECK_SQL}")
    )


def _rollback(connection: Connection) -> bool:
    changed = False
    for group in MONITOR_ENUM_GROUPS:
        if _enum_labels(connection, group.type_name):
            dependencies = _type_dependencies(connection, group.type_name)
            if dependencies:
                raise MonitorEnumMigrationError(f"{group.type_name}: dependencies remain: {dependencies}")
    for group in MONITOR_ENUM_GROUPS:
        if any(_column_has_type(connection, column, group.type_name) for column in group.columns):
            _alter_group(connection, group, rollback=True)
            changed = True
    _drop_condition_check(connection)
    for group in MONITOR_ENUM_GROUPS:
        if _enum_labels(connection, group.type_name):
            connection.execute(text(f"DROP TYPE {group.type_name}"))
    return changed


def _drop_condition_check(connection: Connection) -> None:
    if _condition_check_definition(connection) is not None:
        connection.execute(text(f"ALTER TABLE stock_monitor_targets DROP CONSTRAINT {_CONDITION_CHECK_NAME}"))


def _verify(connection: Connection, *, rollback: bool) -> None:
    for group in MONITOR_ENUM_GROUPS:
        if not rollback and _enum_labels(connection, group.type_name) != group.labels:
            raise MonitorEnumMigrationError(f"{group.type_name}: labels were not preserved")
        for column in group.columns:
            facts = _column_facts(connection, column)
            expected = _normalized_type(column.legacy_type_sql) if rollback else group.type_name
            if facts is None or facts[0] != expected:
                raise MonitorEnumMigrationError(
                    f"{group.type_name}: verification failed for {column.table_name}.{column.column_name}"
                )
            _validate_default(connection, group, column, rollback=rollback)
            _validate_indexes(connection, column)
    _validate_condition_check(connection, required=not rollback)


def _table_exists(connection: Connection, table_name: str) -> bool:
    return (
        connection.execute(text("SELECT to_regclass(:table_name)"), {"table_name": table_name}).scalar_one() is not None
    )


def _column_facts(connection: Connection, column: MonitorEnumColumn) -> tuple[str, bool] | None:
    row = connection.execute(
        text(
            "SELECT lower(format_type(a.atttypid, a.atttypmod)), NOT a.attnotnull "
            "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = current_schema() AND c.relname = :table_name AND a.attname = :column_name "
            "AND a.attnum > 0 AND NOT a.attisdropped"
        ),
        {"table_name": column.table_name, "column_name": column.column_name},
    ).one_or_none()
    return None if row is None else (str(row[0]), bool(row[1]))


def _column_has_type(connection: Connection, column: MonitorEnumColumn, type_name: str) -> bool:
    facts = _column_facts(connection, column)
    return facts is not None and facts[0] == type_name


def _normalized_type(type_sql: str) -> str:
    return type_sql.lower().replace("varchar", "character varying")


def _column_default(connection: Connection, column: MonitorEnumColumn) -> str | None:
    default = connection.execute(
        text(
            "SELECT pg_get_expr(d.adbin, d.adrelid) FROM pg_attrdef d "
            "JOIN pg_class c ON c.oid = d.adrelid JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.adnum "
            "WHERE n.nspname = current_schema() AND c.relname = :table_name AND a.attname = :column_name"
        ),
        {"table_name": column.table_name, "column_name": column.column_name},
    ).scalar_one_or_none()
    return None if default is None else str(default)


def _enum_default(legacy_default: str, type_name: str) -> str:
    return f"{legacy_default.partition('::')[0]}::{type_name}"


def _normalize_expression(expression: str) -> str:
    return re.sub(r"\s+", "", expression).lower().replace("::text::", "::")


def _validate_default(
    connection: Connection, group: MonitorEnumGroup, column: MonitorEnumColumn, *, rollback: bool
) -> None:
    actual = _column_default(connection, column)
    expected = (
        column.default_sql
        if rollback
        else (None if column.default_sql is None else _enum_default(column.default_sql, group.type_name))
    )
    if expected is None:
        if actual is not None:
            raise MonitorEnumMigrationError(
                f"{group.type_name}: unexpected default for {column.table_name}.{column.column_name}"
            )
    elif actual is None or _normalize_expression(actual) != _normalize_expression(expected):
        raise MonitorEnumMigrationError(
            f"{group.type_name}: default mismatch for {column.table_name}.{column.column_name}"
        )


def _enum_labels(connection: Connection, type_name: str) -> tuple[str, ...]:
    return tuple(
        connection.execute(
            text(
                "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = current_schema() AND t.typname = :type_name ORDER BY e.enumsortorder"
            ),
            {"type_name": type_name},
        ).scalars()
    )


def _condition_check_definition(connection: Connection) -> str | None:
    definition = connection.execute(
        text(
            "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE c.connamespace = current_schema()::regnamespace "
            "AND t.relname = 'stock_monitor_targets' AND c.conname = :constraint_name"
        ),
        {"constraint_name": _CONDITION_CHECK_NAME},
    ).scalar_one_or_none()
    return None if definition is None else str(definition)


def _validate_condition_check(connection: Connection, *, required: bool) -> None:
    definition = _condition_check_definition(connection)
    if definition is None:
        if required:
            raise MonitorEnumMigrationError(f"missing condition constraint: {_CONDITION_CHECK_NAME}")
        return
    normalized = _normalize_expression(definition).replace("::text", "").replace("(", "").replace(")", "")
    if normalized != _NORMALIZED_CONDITION_CHECK:
        raise MonitorEnumMigrationError(f"conflicting condition constraint: {_CONDITION_CHECK_NAME}")


def _validate_indexes(connection: Connection, column: MonitorEnumColumn) -> None:
    for index_name, _ in column.indexes:
        facts = connection.execute(
            text(
                "SELECT i.indisunique, array_agg(a.attname ORDER BY k.ordinality), pg_get_expr(i.indpred, i.indrelid) "
                "FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                "JOIN unnest(i.indkey) WITH ORDINALITY AS k(attnum, ordinality) ON true "
                "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum "
                "WHERE c.relnamespace = current_schema()::regnamespace AND c.relname = :index_name "
                "GROUP BY i.indisunique, i.indpred, i.indrelid"
            ),
            {"index_name": index_name},
        ).one_or_none()
        if facts is None or facts[0] or tuple(facts[1]) != (column.column_name,) or facts[2] is not None:
            raise MonitorEnumMigrationError(f"missing or invalid index {index_name}")


def _type_dependencies(connection: Connection, type_name: str) -> tuple[str, ...]:
    return tuple(
        connection.execute(
            text(
                "SELECT pg_describe_object(d.classid, d.objid, d.objsubid) "
                "FROM pg_depend d JOIN pg_type t ON t.oid = d.refobjid "
                "WHERE d.refclassid = 'pg_type'::regclass AND t.typnamespace = current_schema()::regnamespace "
                "AND t.typname = :type_name AND d.deptype NOT IN ('i', 'a') ORDER BY 1"
            ),
            {"type_name": type_name},
        ).scalars()
    )
