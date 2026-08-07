from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Connection

from paper_trading.storage.enum_migration import (
    PAPER_TRADING_ENUM_GROUPS,
    PaperTradingEnumMigrationError,
    _migrate,
)

MATCHING_STATUS_LABELS = ("running", "completed", "completed_with_warnings", "failed")
_TYPE_NAME = "paper_matching_run_status"
_TABLE_NAME = "paper_matching_runs"
_INDEX_NAME = "uq_matching_active_scope"
_EXPECTED_INDEX_COLUMNS = ("trade_date", "scope_key")


class MatchingStatusEnumMigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MatchingStatusEnumMigrationResult:
    dry_run: bool
    converted: bool
    labels: tuple[str, ...]
    index_verified: bool


@dataclass(frozen=True)
class MatchingStatusBootstrapResult:
    dry_run: bool
    table_exists: bool
    table_created: bool
    status_column_type: str | None
    converted: bool
    labels: tuple[str, ...]
    observed_legacy_values: tuple[str | None, ...]
    index_verified: bool


def bootstrap_paper_matching_run_status(
    connection: Connection, *, dry_run: bool = False
) -> MatchingStatusBootstrapResult:
    if connection.dialect.name != "postgresql":
        return MatchingStatusBootstrapResult(
            dry_run=dry_run,
            table_exists=False,
            table_created=False,
            status_column_type=None,
            converted=False,
            labels=MATCHING_STATUS_LABELS,
            observed_legacy_values=(),
            index_verified=False,
        )

    table_exists = connection.execute(text("SELECT to_regclass(:table_name)"), {"table_name": _TABLE_NAME}).scalar_one()
    if not table_exists:
        if dry_run:
            return MatchingStatusBootstrapResult(
                dry_run=True,
                table_exists=False,
                table_created=False,
                status_column_type=None,
                converted=False,
                labels=MATCHING_STATUS_LABELS,
                observed_legacy_values=(),
                index_verified=False,
            )
        migrate_paper_matching_status_enum(connection)
        return MatchingStatusBootstrapResult(
            dry_run=False,
            table_exists=False,
            table_created=True,
            status_column_type=_status_column_type(connection),
            converted=False,
            labels=MATCHING_STATUS_LABELS,
            observed_legacy_values=(),
            index_verified=True,
        )

    observed_legacy_values = tuple(
        row[0]
        for row in connection.execute(
            text(f"SELECT DISTINCT status FROM {_TABLE_NAME} ORDER BY status NULLS FIRST")
        ).all()
    )
    status_column_type = _status_column_type(connection)
    migration = migrate_paper_matching_status_enum(connection, dry_run=dry_run)
    return MatchingStatusBootstrapResult(
        dry_run=dry_run,
        table_exists=True,
        table_created=False,
        status_column_type=status_column_type,
        converted=migration.converted,
        labels=migration.labels,
        observed_legacy_values=observed_legacy_values,
        index_verified=migration.index_verified,
    )


def _status_column_type(connection: Connection) -> str | None:
    return connection.execute(
        text(
            "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = current_schema() AND c.relname = :table_name "
            "AND a.attname = 'status' AND a.attnum > 0 AND NOT a.attisdropped"
        ),
        {"table_name": _TABLE_NAME},
    ).scalar_one_or_none()


def migrate_paper_matching_status_enum(
    connection: Connection, *, dry_run: bool = False
) -> MatchingStatusEnumMigrationResult:
    if connection.dialect.name != "postgresql":
        return MatchingStatusEnumMigrationResult(dry_run, False, MATCHING_STATUS_LABELS, False)
    matching_group = next(group for group in PAPER_TRADING_ENUM_GROUPS if group.type_name == _TYPE_NAME)
    try:
        result = _migrate(connection, (matching_group,), dry_run=dry_run)
    except PaperTradingEnumMigrationError as error:
        raise MatchingStatusEnumMigrationError(str(error)) from error
    converted = result.converted or (dry_run and _status_column_type(connection) != _TYPE_NAME)
    return MatchingStatusEnumMigrationResult(dry_run, converted, matching_group.labels, True)
