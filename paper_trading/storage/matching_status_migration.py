from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

MATCHING_STATUS_LABELS = ("running", "completed", "completed_with_warnings", "failed")
_TYPE_NAME = "paper_matching_run_status"
_TABLE_NAME = "paper_matching_runs"
_INDEX_NAME = "uq_matching_active_scope"


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
    if dry_run:
        return MatchingStatusEnumMigrationResult(
            dry_run=True, converted=False, labels=MATCHING_STATUS_LABELS, index_verified=False
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
        text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = :type_name)"), {"type_name": _TYPE_NAME}
    ).scalar_one()
    converted = False
    if not type_exists:
        labels_sql = ", ".join(f"'{label}'" for label in MATCHING_STATUS_LABELS)
        connection.execute(text(f"CREATE TYPE {_TYPE_NAME} AS ENUM ({labels_sql})"))
        connection.execute(
            text(
                f"ALTER TABLE {_TABLE_NAME} ALTER COLUMN status TYPE {_TYPE_NAME} "
                "USING status::text::paper_matching_run_status"
            )
        )
        converted = True
    else:
        column_type = connection.execute(
            text(
                "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
                "JOIN pg_class c ON c.oid = a.attrelid "
                "WHERE c.relname = :table_name AND a.attname = 'status' AND a.attnum > 0"
            ),
            {"table_name": _TABLE_NAME},
        ).scalar_one()
        if column_type != _TYPE_NAME:
            connection.execute(
                text(
                    f"ALTER TABLE {_TABLE_NAME} ALTER COLUMN status TYPE {_TYPE_NAME} "
                    "USING status::text::paper_matching_run_status"
                )
            )
            converted = True

    actual_labels = tuple(
        row[0]
        for row in connection.execute(
            text(
                "SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_type.oid = pg_enum.enumtypid "
                "WHERE pg_type.typname = :type_name ORDER BY enumsortorder"
            ),
            {"type_name": _TYPE_NAME},
        ).all()
    )
    if actual_labels != MATCHING_STATUS_LABELS:
        raise MatchingStatusEnumMigrationError(f"Unexpected enum labels: {actual_labels}")

    predicate = connection.execute(
        text(
            "SELECT pg_get_expr(i.indpred, i.indrelid) FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indexrelid WHERE c.relname = :index_name"
        ),
        {"index_name": _INDEX_NAME},
    ).scalar_one_or_none()
    index_verified = predicate is not None and "running" in predicate.lower()
    if not index_verified:
        raise MatchingStatusEnumMigrationError("Active matching-run partial index is missing or invalid")

    return MatchingStatusEnumMigrationResult(
        dry_run=False, converted=converted, labels=actual_labels, index_verified=True
    )
