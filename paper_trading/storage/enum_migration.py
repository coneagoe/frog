from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from paper_trading.domain.enums import (
    AccountStatus,
    CashEventType,
    FeePreset,
    LedgerRebuildStatus,
    Market,
    MatchingRunStatus,
    OrderSide,
    OrderStatus,
    PendingSettlementSource,
    PositionSource,
    RoundTripStatus,
    TradeValidityGranularity,
    TradeValidityStatus,
)
from storage.model import (
    PaperAccount,
    PaperAccountSnapshot,
    PaperCashLedger,
    PaperLedgerRebuild,
    PaperMatchingRun,
    PaperOrder,
    PaperPosition,
    PaperPositionLot,
    PaperPositionRoundTrip,
    PaperTrade,
    PaperTradeValidityCheck,
    PaperValuationGap,
)
from storage.model.paper_trading import PaperPendingSettlement


class PaperTradingEnumMigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PaperTradingEnumColumn:
    table_name: str
    column_name: str
    legacy_type_sql: str
    default_sql: str | None
    nullable: bool
    indexes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class PaperTradingEnumGroup:
    type_name: str
    labels: tuple[str, ...]
    columns: tuple[PaperTradingEnumColumn, ...]


@dataclass(frozen=True)
class PaperTradingEnumMigrationResult:
    dry_run: bool
    rollback: bool
    converted: bool
    rolled_back: bool
    groups: tuple[PaperTradingEnumGroup, ...]


def _labels(enum_type: type[StrEnum]) -> tuple[str, ...]:
    return tuple(member.value for member in enum_type)


def _column(
    table_name: str,
    column_name: str,
    legacy_type_sql: str,
    default_sql: str | None = None,
    *,
    nullable: bool = False,
    indexes: tuple[tuple[str, str], ...] = (),
) -> PaperTradingEnumColumn:
    if default_sql is not None and "::" not in default_sql:
        default_sql = f"{default_sql}::character varying"
    return PaperTradingEnumColumn(table_name, column_name, legacy_type_sql, default_sql, nullable, indexes)


_MATCHING_INDEX_SQL = (
    "CREATE UNIQUE INDEX uq_matching_active_scope ON paper_matching_runs "
    "(trade_date, scope_key) WHERE status = 'running'"
)


def _index(name: str, table_name: str, column_name: str) -> tuple[str, str]:
    return name, f"CREATE INDEX {name} ON {table_name} ({column_name})"


_MATCHING_INDEX = ("uq_matching_active_scope", _MATCHING_INDEX_SQL)

PAPER_TRADING_ENUM_GROUPS = (
    PaperTradingEnumGroup(
        "paper_account_status",
        _labels(AccountStatus),
        (_column("paper_accounts", "status", "VARCHAR(20)", "'active'"),),
    ),
    PaperTradingEnumGroup(
        "paper_fee_preset", _labels(FeePreset), (_column("paper_accounts", "fee_preset", "VARCHAR(30)", "'a_share'"),)
    ),
    PaperTradingEnumGroup(
        "paper_cash_event_type", _labels(CashEventType), (_column("paper_cash_ledger", "event_type", "VARCHAR(20)"),)
    ),
    PaperTradingEnumGroup(
        "paper_order_side",
        _labels(OrderSide),
        (
            _column("paper_orders", "side", "VARCHAR(10)"),
            _column("paper_trades", "side", "VARCHAR(10)"),
            _column("paper_trade_validity_checks", "side", "VARCHAR(10)"),
        ),
    ),
    PaperTradingEnumGroup(
        "paper_order_status",
        _labels(OrderStatus),
        (
            _column(
                "paper_orders",
                "status",
                "VARCHAR(30)",
                indexes=(_index("ix_paper_orders_status", "paper_orders", "status"),),
            ),
        ),
    ),
    PaperTradingEnumGroup(
        "paper_trade_validity_status",
        _labels(TradeValidityStatus),
        (
            _column(
                "paper_orders",
                "validity_status",
                "VARCHAR(20)",
                nullable=True,
                indexes=(_index("ix_paper_orders_validity_status", "paper_orders", "validity_status"),),
            ),
            _column(
                "paper_trade_validity_checks",
                "status",
                "VARCHAR(20)",
                indexes=(_index("ix_paper_trade_validity_checks_status", "paper_trade_validity_checks", "status"),),
            ),
        ),
    ),
    PaperTradingEnumGroup(
        "paper_market",
        _labels(Market),
        (
            _column(
                "paper_orders",
                "market",
                "VARCHAR(20)",
                "'a_share'",
                indexes=(_index("ix_paper_orders_market", "paper_orders", "market"),),
            ),
            _column(
                "paper_positions",
                "market",
                "VARCHAR(20)",
                "'a_share'",
                indexes=(_index("ix_paper_positions_market", "paper_positions", "market"),),
            ),
            _column(
                "paper_position_lots",
                "market",
                "VARCHAR(20)",
                "'a_share'",
                indexes=(_index("ix_paper_position_lots_market", "paper_position_lots", "market"),),
            ),
            _column(
                "paper_trades",
                "market",
                "VARCHAR(20)",
                "'a_share'",
                indexes=(_index("ix_paper_trades_market", "paper_trades", "market"),),
            ),
            _column(
                "paper_trade_validity_checks",
                "market",
                "VARCHAR(20)",
                "'a_share'",
                indexes=(_index("ix_paper_trade_validity_checks_market", "paper_trade_validity_checks", "market"),),
            ),
        ),
    ),
    PaperTradingEnumGroup(
        "paper_position_source",
        _labels(PositionSource),
        (
            _column("paper_positions", "source", "VARCHAR(20)", "'trade'"),
            _column("paper_position_lots", "source", "VARCHAR(20)", "'trade'"),
        ),
    ),
    PaperTradingEnumGroup(
        "paper_round_trip_status",
        _labels(RoundTripStatus),
        (
            _column(
                "paper_position_round_trips",
                "status",
                "VARCHAR(20)",
                "'open'",
                indexes=(_index("ix_paper_position_round_trips_status", "paper_position_round_trips", "status"),),
            ),
        ),
    ),
    PaperTradingEnumGroup(
        "paper_trade_validity_granularity",
        _labels(TradeValidityGranularity),
        (_column("paper_trade_validity_checks", "data_granularity", "VARCHAR(20)", "'daily'"),),
    ),
    PaperTradingEnumGroup(
        "paper_pending_settlement_source",
        _labels(PendingSettlementSource),
        (_column("paper_pending_settlement", "source", "VARCHAR(20)"),),
    ),
    PaperTradingEnumGroup(
        "paper_ledger_rebuild_status",
        _labels(LedgerRebuildStatus),
        (
            _column(
                "paper_ledger_rebuilds",
                "status",
                "VARCHAR(20)",
                indexes=(_index("ix_paper_ledger_rebuilds_status", "paper_ledger_rebuilds", "status"),),
            ),
        ),
    ),
    PaperTradingEnumGroup(
        "paper_matching_run_status",
        _labels(MatchingRunStatus),
        (
            _column(
                "paper_matching_runs",
                "status",
                "VARCHAR(32)",
                indexes=(_MATCHING_INDEX,),
            ),
        ),
    ),
)

_GOVERNED_TABLES = (
    PaperAccount.__table__,
    PaperCashLedger.__table__,
    PaperPosition.__table__,
    PaperPositionLot.__table__,
    PaperOrder.__table__,
    PaperTrade.__table__,
    PaperPositionRoundTrip.__table__,
    PaperMatchingRun.__table__,
    PaperTradeValidityCheck.__table__,
    PaperPendingSettlement.__table__,
    PaperLedgerRebuild.__table__,
    PaperAccountSnapshot.__table__,
    PaperValuationGap.__table__,
)
_OPERATIONAL_TABLES = (
    PaperAccountSnapshot.__table__,
    PaperValuationGap.__table__,
)
_ENUM_PREDICATE = re.compile(r"status\s*=\s*'running'\s*::\s*paper_matching_run_status", re.IGNORECASE)
_LEGACY_PREDICATE = re.compile(r"status.*=.*'running'", re.IGNORECASE)


def migrate_paper_trading_enums(
    connection: Connection, *, dry_run: bool = False, rollback: bool = False
) -> PaperTradingEnumMigrationResult:
    return _migrate(connection, PAPER_TRADING_ENUM_GROUPS, dry_run=dry_run, rollback=rollback)


def _migrate(
    connection: Connection,
    groups: tuple[PaperTradingEnumGroup, ...],
    *,
    dry_run: bool = False,
    rollback: bool = False,
    dry_run_reports_conversion: bool = False,
) -> PaperTradingEnumMigrationResult:
    def result(converted: bool = False, rolled_back: bool = False) -> PaperTradingEnumMigrationResult:
        return PaperTradingEnumMigrationResult(
            dry_run=dry_run,
            rollback=rollback,
            converted=converted,
            rolled_back=rolled_back,
            groups=groups,
        )

    if connection.dialect.name != "postgresql":
        return result()

    missing_tables = _preflight(connection, groups, rollback=rollback)
    if missing_tables and len(missing_tables) != len(
        {column.table_name for group in groups for column in group.columns}
    ):
        raise PaperTradingEnumMigrationError(f"partially missing governed tables: {sorted(missing_tables)}")
    changed = any(
        not _column_has_type(connection, column, group.type_name) for group in groups for column in group.columns
    )
    if dry_run:
        return result(converted=changed if dry_run_reports_conversion else False)
    if missing_tables:
        if rollback:
            return result()
        for group in groups:
            _create_type(connection, group)
        _create_missing_tables(connection, missing_tables)
        _preflight(connection, groups, rollback=False)
        return result(converted=True)
    if rollback:
        changed = _rollback(connection, groups)
        _verify(connection, groups, rollback=True)
        return result(rolled_back=changed)

    if changed:
        for group in groups:
            _create_type(connection, group)
            _alter_group(connection, group, rollback=False)
    _verify(connection, groups, rollback=False)
    if groups is PAPER_TRADING_ENUM_GROUPS:
        _create_missing_tables(connection, set())
    return result(converted=changed)


def _preflight(connection: Connection, groups: tuple[PaperTradingEnumGroup, ...], *, rollback: bool) -> set[str]:
    governed_names = {column.table_name for group in groups for column in group.columns}
    missing_tables = {name for name in governed_names if not _table_exists(connection, name)}
    for group in groups:
        labels = _enum_labels(connection, group.type_name)
        if labels and labels != group.labels:
            raise PaperTradingEnumMigrationError(f"{group.type_name}: unexpected enum labels {labels}")
        for column in group.columns:
            if column.table_name in missing_tables:
                continue
            facts = _column_facts(connection, column)
            if facts is None:
                raise PaperTradingEnumMigrationError(
                    f"{group.type_name}: missing {column.table_name}.{column.column_name}"
                )
            type_name, nullable = facts
            expected = group.type_name if rollback else _normalized_type(column.legacy_type_sql)
            if rollback:
                valid = type_name == expected
            else:
                valid = type_name == expected or type_name == group.type_name
            if not valid or nullable != column.nullable:
                raise PaperTradingEnumMigrationError(
                    f"{group.type_name}: incompatible {column.table_name}.{column.column_name}"
                )
            if not rollback and type_name != group.type_name:
                _validate_values(connection, group, column)
            enum_typed = type_name == group.type_name
            _validate_indexes(connection, column, enum_typed=rollback or enum_typed)
            _validate_default(connection, group, column, rollback=not enum_typed)
    return missing_tables


def _create_missing_tables(connection: Connection, missing_tables: set[str]) -> None:
    tables = [
        table
        for table in _GOVERNED_TABLES
        if table.name in missing_tables or (table in _OPERATIONAL_TABLES and not _table_exists(connection, table.name))
    ]
    if not tables:
        return
    # Metadata creates the mapped native types and respects foreign-key order.
    tables[0].metadata.create_all(connection, tables=tables, checkfirst=True)


def _create_type(connection: Connection, group: PaperTradingEnumGroup) -> None:
    if _enum_labels(connection, group.type_name):
        return
    labels = ", ".join(f"'{label}'" for label in group.labels)
    connection.execute(text(f"CREATE TYPE {group.type_name} AS ENUM ({labels})"))


def _alter_group(connection: Connection, group: PaperTradingEnumGroup, *, rollback: bool) -> None:
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


def _rollback(connection: Connection, groups: tuple[PaperTradingEnumGroup, ...]) -> bool:
    changed = False
    for group in groups:
        if any(_column_has_type(connection, column, group.type_name) for column in group.columns):
            _alter_group(connection, group, rollback=True)
            changed = True
    _verify(connection, groups, rollback=True)
    for group in groups:
        if _enum_labels(connection, group.type_name):
            dependencies = _type_dependencies(connection, group.type_name)
            if dependencies:
                raise PaperTradingEnumMigrationError(f"{group.type_name}: dependencies remain: {dependencies}")
    for group in groups:
        if _enum_labels(connection, group.type_name):
            connection.execute(text(f"DROP TYPE {group.type_name}"))
    return changed


def _verify(connection: Connection, groups: tuple[PaperTradingEnumGroup, ...], *, rollback: bool) -> None:
    for group in groups:
        if not rollback and _enum_labels(connection, group.type_name) != group.labels:
            raise PaperTradingEnumMigrationError(f"{group.type_name}: labels were not preserved")
        for column in group.columns:
            expected = _normalized_type(column.legacy_type_sql) if rollback else group.type_name
            facts = _column_facts(connection, column)
            if facts is None or facts[0] != expected:
                raise PaperTradingEnumMigrationError(
                    f"{group.type_name}: verification failed for {column.table_name}.{column.column_name}"
                )
            _validate_default(connection, group, column, rollback=rollback)
            _validate_indexes(connection, column, enum_typed=not rollback)


def _table_exists(connection: Connection, table_name: str) -> bool:
    return (
        connection.execute(text("SELECT to_regclass(:table_name)"), {"table_name": table_name}).scalar_one() is not None
    )


def _column_facts(connection: Connection, column: PaperTradingEnumColumn) -> tuple[str, bool] | None:
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
    if row is None:
        return None
    return str(row[0]), bool(row[1])


def _normalized_type(type_sql: str) -> str:
    return type_sql.lower().replace("varchar", "character varying")


def _column_has_type(connection: Connection, column: PaperTradingEnumColumn, type_name: str) -> bool:
    facts = _column_facts(connection, column)
    return facts is not None and facts[0] == type_name


def _column_default(connection: Connection, column: PaperTradingEnumColumn) -> str | None:
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


def _expected_default(group: PaperTradingEnumGroup, column: PaperTradingEnumColumn, *, rollback: bool) -> str | None:
    if column.default_sql is None:
        return None
    return column.default_sql if rollback else _enum_default(column.default_sql, group.type_name)


def _enum_default(legacy_default: str, type_name: str) -> str:
    return f"{legacy_default.partition('::')[0]}::{type_name}"


def _normalize_expression(expression: str) -> str:
    normalized = re.sub(r"\s+", "", expression).lower()
    return normalized.replace("::text::", "::")


def _validate_default(
    connection: Connection, group: PaperTradingEnumGroup, column: PaperTradingEnumColumn, *, rollback: bool
) -> None:
    actual = _column_default(connection, column)
    expected = _expected_default(group, column, rollback=rollback)
    if expected is None:
        if actual is not None:
            raise PaperTradingEnumMigrationError(
                f"{group.type_name}: unexpected default for {column.table_name}.{column.column_name}"
            )
        return
    if actual is None or _normalize_expression(actual) != _normalize_expression(expected):
        raise PaperTradingEnumMigrationError(
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


def _validate_values(connection: Connection, group: PaperTradingEnumGroup, column: PaperTradingEnumColumn) -> None:
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
        raise PaperTradingEnumMigrationError(f"{group.type_name}: unknown legacy values {unknown}")


def _validate_matching_index(connection: Connection, index_name: str, *, enum_typed: bool) -> None:
    facts = connection.execute(
        text(
            "SELECT i.indisunique, array_agg(a.attname ORDER BY k.ordinality), pg_get_expr(i.indpred, i.indrelid) "
            "FROM pg_index i JOIN pg_class ic ON ic.oid = i.indexrelid "
            "JOIN pg_namespace n ON n.oid = ic.relnamespace JOIN pg_class tc ON tc.oid = i.indrelid "
            "JOIN unnest(i.indkey) WITH ORDINALITY AS k(attnum, ordinality) ON true "
            "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum "
            "WHERE n.nspname = current_schema() AND ic.relname = :index_name "
            "GROUP BY i.indisunique, i.indpred, i.indrelid"
        ),
        {"index_name": index_name},
    ).one_or_none()
    predicate = facts[2] if facts else ""
    pattern = _ENUM_PREDICATE if enum_typed else _LEGACY_PREDICATE
    if not facts or not facts[0] or tuple(facts[1]) != ("trade_date", "scope_key") or not pattern.search(predicate):
        raise PaperTradingEnumMigrationError(
            "paper_matching_run_status: active matching-run partial index is missing or invalid"
        )


def _validate_indexes(connection: Connection, column: PaperTradingEnumColumn, *, enum_typed: bool) -> None:
    for index_name, index_sql in column.indexes:
        if index_name == "uq_matching_active_scope":
            _validate_matching_index(connection, index_name, enum_typed=enum_typed)
            continue
        facts = connection.execute(
            text(
                "SELECT i.indisunique, array_agg(a.attname ORDER BY k.ordinality), pg_get_expr(i.indpred, i.indrelid) "
                "FROM pg_index i "
                "JOIN pg_class c ON c.oid = i.indexrelid "
                "JOIN unnest(i.indkey) WITH ORDINALITY AS k(attnum, ordinality) ON true "
                "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum "
                "WHERE c.relnamespace = current_schema()::regnamespace AND c.relname = :index_name "
                "GROUP BY i.indisunique, i.indpred, i.indrelid"
            ),
            {"index_name": index_name},
        ).one_or_none()
        expected_column = column.column_name
        if facts is None or facts[0] or tuple(facts[1]) != (expected_column,) or facts[2] is not None:
            raise PaperTradingEnumMigrationError(f"missing or invalid index {index_name}")


def _type_dependencies(connection: Connection, type_name: str) -> tuple[str, ...]:
    return tuple(
        connection.execute(
            text(
                "SELECT pg_describe_object(d.classid, d.objid, d.objsubid) "
                "FROM pg_depend d JOIN pg_type t ON t.oid = d.refobjid "
                "WHERE d.refclassid = 'pg_type'::regclass AND t.typnamespace = current_schema()::regnamespace "
                "AND t.typname = :type_name AND d.deptype NOT IN ('i', 'a') "
                "ORDER BY 1"
            ),
            {"type_name": type_name},
        ).scalars()
    )
