from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

MATCHING_STATUS_LABELS = ("running", "completed", "completed_with_warnings", "failed")
_TYPE_NAME = "paper_matching_run_status"
_TABLE_NAME = "paper_matching_runs"
_INDEX_NAME = "uq_matching_active_scope"
_EXPECTED_INDEX_COLUMNS = ("trade_date", "scope_key")
_ACTIVE_INDEX_PREDICATE = re.compile(
    r"\(*\s*status\s*\)*(?:\s*::\s*[\w.]+)*\s*=\s*"
    r"\(*\s*'running'\s*\)*(?:\s*::\s*[\w.]+)*\s*\)*$",
    re.IGNORECASE,
)


class MatchingStatusEnumMigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MatchingStatusEnumMigrationResult:
    dry_run: bool
    converted: bool
    labels: tuple[str, ...]
    index_verified: bool


def migrate_paper_matching_status_enum(
    connection: Connection, *, dry_run: bool = False
) -> MatchingStatusEnumMigrationResult:
    if connection.dialect.name != "postgresql":
        return MatchingStatusEnumMigrationResult(
            dry_run=dry_run, converted=False, labels=MATCHING_STATUS_LABELS, index_verified=False
        )
    unknown = connection.execute(
        text(f"SELECT DISTINCT status FROM {_TABLE_NAME} WHERE status IS NULL OR status NOT IN :labels").bindparams(
            bindparam("labels", expanding=True)
        ),
        {"labels": MATCHING_STATUS_LABELS},
    ).all()
    if unknown:
        raise MatchingStatusEnumMigrationError(f"Unknown matching run statuses: {[row[0] for row in unknown]}")

    type_exists = connection.execute(
        text(
            "SELECT EXISTS ("
            "SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = current_schema() AND t.typname = :type_name"
            ")"
        ),
        {"type_name": _TYPE_NAME},
    ).scalar_one()
    column_type_oid = connection.execute(
        text(
            "SELECT a.atttypid FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = current_schema() AND c.relname = :table_name "
            "AND a.attname = 'status' AND a.attnum > 0 AND NOT a.attisdropped"
        ),
        {"table_name": _TABLE_NAME},
    ).scalar_one()
    enum_type_oid = connection.execute(
        text(
            "SELECT t.oid FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = current_schema() AND t.typname = :type_name"
        ),
        {"type_name": _TYPE_NAME},
    ).scalar_one_or_none()
    converted = column_type_oid != enum_type_oid

    actual_labels = tuple(
        row[0]
        for row in connection.execute(
            text(
                "SELECT e.enumlabel FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = current_schema() AND t.typname = :type_name "
                "ORDER BY e.enumsortorder"
            ),
            {"type_name": _TYPE_NAME},
        ).all()
    )
    if type_exists and actual_labels != MATCHING_STATUS_LABELS:
        raise MatchingStatusEnumMigrationError(f"Unexpected enum labels: {actual_labels}")

    index_facts = connection.execute(
        text(
            "SELECT i.indisunique, "
            "array_agg(a.attname ORDER BY k.ordinality), "
            "pg_get_expr(i.indpred, i.indrelid) "
            "FROM pg_index i "
            "JOIN pg_class ic ON ic.oid = i.indexrelid "
            "JOIN pg_namespace n ON n.oid = ic.relnamespace "
            "JOIN unnest(i.indkey) WITH ORDINALITY AS k(attnum, ordinality) ON true "
            "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum "
            "WHERE n.nspname = current_schema() AND ic.relname = :index_name "
            "GROUP BY i.indisunique, i.indpred, i.indrelid"
        ),
        {"index_name": _INDEX_NAME},
    ).one_or_none()
    predicate = index_facts[2] if index_facts else None
    index_verified = bool(
        index_facts
        and index_facts[0]
        and tuple(index_facts[1]) == _EXPECTED_INDEX_COLUMNS
        and predicate
        and _ACTIVE_INDEX_PREDICATE.search(predicate.strip())
    )
    if not index_verified:
        raise MatchingStatusEnumMigrationError("Active matching-run partial index is missing or invalid")

    if dry_run:
        return MatchingStatusEnumMigrationResult(
            dry_run=True,
            converted=converted,
            labels=actual_labels,
            index_verified=True,
        )

    if converted:
        if not type_exists:
            labels_sql = ", ".join(f"'{label}'" for label in MATCHING_STATUS_LABELS)
            connection.execute(text(f"CREATE TYPE {_TYPE_NAME} AS ENUM ({labels_sql})"))
        connection.execute(
            text(
                f"ALTER TABLE {_TABLE_NAME} ALTER COLUMN status TYPE {_TYPE_NAME} "
                "USING status::text::paper_matching_run_status"
            )
        )
        actual_labels = MATCHING_STATUS_LABELS

    return MatchingStatusEnumMigrationResult(
        dry_run=False, converted=converted, labels=actual_labels, index_verified=True
    )
