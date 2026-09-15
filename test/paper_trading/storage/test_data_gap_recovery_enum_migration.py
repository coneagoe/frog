from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from paper_trading.domain.enums import (
    DataGapRecoveryAccountStatus,
    DataGapRecoveryAlertDeliveryState,
    DataGapRecoveryApprovalDecision,
    DataGapRecoveryAttemptOutcome,
    DataGapRecoveryBatchStatus,
    DataGapRecoveryStatus,
)
from paper_trading.storage.enum_migration import (
    PAPER_TRADING_ENUM_GROUPS,
    PaperTradingEnumMigrationError,
    migrate_paper_trading_enums,
)
from test.paper_trading.storage.test_enum_migration import _create_legacy_schema

RECOVERY_GROUPS = {
    "paper_data_gap_recovery_status": (DataGapRecoveryStatus, "paper_data_gap_recovery_gaps", "status"),
    "paper_data_gap_recovery_attempt_outcome": (
        DataGapRecoveryAttemptOutcome,
        "paper_data_gap_recovery_attempts",
        "outcome",
    ),
    "paper_data_gap_recovery_approval_decision": (
        DataGapRecoveryApprovalDecision,
        "paper_data_gap_recovery_approvals",
        "decision",
    ),
    "paper_data_gap_recovery_account_status": (
        DataGapRecoveryAccountStatus,
        "paper_data_gap_recovery_accounts",
        "status",
    ),
    "paper_data_gap_recovery_batch_status": (DataGapRecoveryBatchStatus, "paper_data_gap_recovery_batches", "status"),
    "paper_data_gap_recovery_alert_delivery_state": (
        DataGapRecoveryAlertDeliveryState,
        "paper_data_gap_recovery_alerts",
        "delivery_state",
    ),
}


def _engine() -> Engine:
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    assert url is not None
    return create_engine(url)


def _connection(engine: Engine, schema: str) -> Connection:
    connection = engine.connect()
    connection.execute(text(f'SET search_path TO "{schema}"'))
    return connection


def _enum_labels(connection: Connection, type_name: str) -> tuple[str, ...]:
    return tuple(
        connection.execute(
            text(
                "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typnamespace = current_schema()::regnamespace AND t.typname = :type_name "
                "ORDER BY e.enumsortorder"
            ),
            {"type_name": type_name},
        ).scalars()
    )


def _type_exists(connection: Connection, type_name: str) -> bool:
    return bool(
        connection.execute(text("SELECT to_regtype(:type_name) IS NOT NULL"), {"type_name": type_name}).scalar_one()
    )


def _table_exists(connection: Connection, table_name: str) -> bool:
    return bool(
        connection.execute(text("SELECT to_regclass(:table_name) IS NOT NULL"), {"table_name": table_name}).scalar_one()
    )


def _create_legacy_recovery_tables(connection: Connection) -> None:
    statements = (
        "CREATE TABLE users (id integer primary key)",
        "ALTER TABLE paper_accounts ADD CONSTRAINT paper_accounts_id_unique UNIQUE (id)",
        "CREATE TABLE paper_data_gap_recovery_gaps ("
        "id integer primary key, business_date date NOT NULL, market varchar(40) NOT NULL, "
        "stock_id varchar(6) NOT NULL, adjust varchar(40) NOT NULL, status varchar(40) NOT NULL DEFAULT 'open', "
        "first_observed_at timestamptz NOT NULL DEFAULT now(), last_observed_at timestamptz NOT NULL DEFAULT now(), "
        "resolved_at timestamptz, latest_candidate_hash varchar(64), summary jsonb NOT NULL DEFAULT '{}'::jsonb, "
        "CONSTRAINT uq_recovery_gap_identity UNIQUE (business_date, market, stock_id, adjust), "
        "CONSTRAINT ck_paper_data_gap_recovery_a_share CHECK (market = 'a_share'), "
        "CONSTRAINT ck_paper_data_gap_recovery_bfq CHECK (adjust = 'bfq'), "
        "CONSTRAINT ck_paper_data_gap_recovery_stock_id_six_ascii_digits CHECK (stock_id ~ '^[0-9]{6}$'))",
        "CREATE TABLE paper_data_gap_recovery_candidates ("
        "gap_id integer NOT NULL REFERENCES paper_data_gap_recovery_gaps(id), candidate_hash varchar(64) NOT NULL, "
        "payload jsonb NOT NULL, validation jsonb NOT NULL, source varchar(100) NOT NULL, "
        "created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (gap_id, candidate_hash))",
        "CREATE TABLE paper_data_gap_recovery_batches ("
        "id integer primary key, status varchar(40) NOT NULL, download_id varchar(100), cutoff timestamptz, "
        "finished_at timestamptz, gap_count integer NOT NULL DEFAULT 0, recovered_count integer NOT NULL DEFAULT 0, "
        "failed_count integer NOT NULL DEFAULT 0, summary jsonb NOT NULL, "
        "created_at timestamptz NOT NULL DEFAULT now())",
        "CREATE TABLE paper_data_gap_recovery_attempts ("
        "id integer primary key, gap_id integer NOT NULL REFERENCES paper_data_gap_recovery_gaps(id), "
        "batch_id integer REFERENCES paper_data_gap_recovery_batches(id), outcome varchar(40) NOT NULL, "
        "evidence jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now())",
        "CREATE TABLE paper_data_gap_recovery_approvals ("
        "id integer primary key, gap_id integer NOT NULL REFERENCES paper_data_gap_recovery_gaps(id), "
        "decision varchar(40) NOT NULL, candidate_hash varchar(64) NOT NULL, "
        "approver_user_id integer REFERENCES users(id), "
        "approver_snapshot jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), "
        "CONSTRAINT fk_recovery_approval_candidate FOREIGN KEY (gap_id, candidate_hash) "
        "REFERENCES paper_data_gap_recovery_candidates(gap_id, candidate_hash))",
        "CREATE TABLE paper_data_gap_recovery_accounts ("
        "id integer primary key, gap_id integer NOT NULL REFERENCES paper_data_gap_recovery_gaps(id), "
        "account_id integer NOT NULL REFERENCES paper_accounts(id), status varchar(40) NOT NULL DEFAULT 'pending', "
        "summary jsonb NOT NULL DEFAULT '{}'::jsonb, updated_at timestamptz NOT NULL DEFAULT now(), "
        "CONSTRAINT uq_recovery_account UNIQUE (gap_id, account_id))",
        "CREATE TABLE paper_data_gap_recovery_alerts ("
        "id integer primary key, gap_id integer NOT NULL REFERENCES paper_data_gap_recovery_gaps(id), "
        "cycle_key varchar(100) NOT NULL, evidence jsonb NOT NULL, "
        "delivery_state varchar(40) NOT NULL DEFAULT 'pending', "
        "created_at timestamptz NOT NULL DEFAULT now(), CONSTRAINT uq_recovery_alert UNIQUE (gap_id, cycle_key))",
    )
    for statement in statements:
        connection.execute(text(statement))
    connection.execute(
        text("CREATE INDEX ix_paper_data_gap_recovery_gaps_status ON paper_data_gap_recovery_gaps (status)")
    )
    connection.execute(
        text(
            "ALTER TABLE paper_data_gap_recovery_attempts ADD CONSTRAINT recovery_attempt_batch_fk "
            "FOREIGN KEY (batch_id) REFERENCES paper_data_gap_recovery_batches(id)"
        )
    )
    for table_name in (
        "paper_data_gap_recovery_candidates",
        "paper_data_gap_recovery_attempts",
        "paper_data_gap_recovery_approvals",
        "paper_data_gap_recovery_batches",
        "paper_data_gap_recovery_alerts",
    ):
        connection.execute(
            text(
                f"CREATE OR REPLACE FUNCTION {table_name}_append_only() RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN RAISE EXCEPTION 'append-only'; END; $$"
            )
        )
        connection.execute(
            text(
                f"CREATE TRIGGER {table_name}_append_only BEFORE UPDATE OR DELETE ON {table_name} "
                f"FOR EACH ROW EXECUTE FUNCTION {table_name}_append_only()"
            )
        )


@pytest.fixture()
def migration_schema():
    engine = _engine()
    schema = f"data_gap_enum_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        yield engine, schema
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_recovery_groups_declare_expected_labels_and_table_columns():
    groups = {group.type_name: group for group in PAPER_TRADING_ENUM_GROUPS}
    assert set(RECOVERY_GROUPS) <= groups.keys()
    for type_name, (enum_class, table_name, column_name) in RECOVERY_GROUPS.items():
        group = groups[type_name]
        assert group.labels == tuple(member.value for member in enum_class)
        assert [(column.table_name, column.column_name) for column in group.columns] == [(table_name, column_name)]
    assert DataGapRecoveryStatus.PENDING_APPROVAL.value in RECOVERY_GROUPS["paper_data_gap_recovery_status"][0]


def test_fresh_recovery_migration_registers_all_types_tables_and_reruns(migration_schema):
    engine, schema = migration_schema
    with _connection(engine, schema) as connection:
        connection.execute(text("CREATE TYPE daily_bar_diagnostic_adjust AS ENUM ('bfq', 'qfq')"))
        assert migrate_paper_trading_enums(connection).converted is True
        assert migrate_paper_trading_enums(connection).converted is False
        for type_name, (enum_class, table_name, _) in RECOVERY_GROUPS.items():
            assert _type_exists(connection, type_name)
            assert _enum_labels(connection, type_name) == tuple(member.value for member in enum_class)
            assert _table_exists(connection, table_name)


def test_legacy_recovery_values_are_converted_and_unknown_labels_abort(migration_schema):
    engine, schema = migration_schema
    with engine.begin() as connection:
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        _create_legacy_schema(connection)
        _create_legacy_recovery_tables(connection)
        connection.execute(
            text(
                "INSERT INTO paper_data_gap_recovery_gaps "
                "(id, business_date, market, stock_id, adjust, status, summary) "
                "VALUES (1, '2024-01-01', 'a_share', '000001', 'bfq', 'unknown', '{}'::jsonb)"
            )
        )
        with pytest.raises(PaperTradingEnumMigrationError, match="paper_data_gap_recovery_status"):
            migrate_paper_trading_enums(connection)
        assert not _type_exists(connection, "paper_data_gap_recovery_status")

    with _connection(engine, schema) as connection:
        connection.execute(text("UPDATE paper_data_gap_recovery_gaps SET status = 'open' WHERE id = 1"))
        assert migrate_paper_trading_enums(connection).converted is True
        assert migrate_paper_trading_enums(connection).converted is False
        assert _enum_labels(connection, "paper_data_gap_recovery_status") == tuple(
            member.value for member in DataGapRecoveryStatus
        )
        assert migrate_paper_trading_enums(connection, rollback=True).rolled_back is True
        assert not _type_exists(connection, "paper_data_gap_recovery_status")
        assert migrate_paper_trading_enums(connection, rollback=True).rolled_back is False


def test_existing_recovery_status_enum_gets_pending_approval_additively(migration_schema):
    engine, schema = migration_schema
    with engine.begin() as connection:
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        _create_legacy_schema(connection)
        _create_legacy_recovery_tables(connection)
        connection.execute(
            text(
                "CREATE TYPE paper_data_gap_recovery_status AS ENUM "
                "('open', 'recovered', 'escalated', 'permanently_unresolved')"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE paper_data_gap_recovery_gaps ALTER COLUMN status DROP DEFAULT"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE paper_data_gap_recovery_gaps ALTER COLUMN status TYPE paper_data_gap_recovery_status "
                "USING status::paper_data_gap_recovery_status"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE paper_data_gap_recovery_gaps ALTER COLUMN status "
                "SET DEFAULT 'open'::paper_data_gap_recovery_status"
            )
        )

        assert migrate_paper_trading_enums(connection).converted is True
        assert _enum_labels(connection, "paper_data_gap_recovery_status") == tuple(
            member.value for member in DataGapRecoveryStatus
        )
        assert migrate_paper_trading_enums(connection, rollback=True).rolled_back is True
        assert not _type_exists(connection, "paper_data_gap_recovery_status")


def test_partial_recovery_schema_without_alert_created_at_fails_closed(migration_schema):
    engine, schema = migration_schema
    with _connection(engine, schema) as connection:
        _create_legacy_schema(connection)
        _create_legacy_recovery_tables(connection)
        connection.execute(text("ALTER TABLE paper_data_gap_recovery_alerts DROP COLUMN created_at"))
        with pytest.raises(PaperTradingEnumMigrationError, match="incomplete recovery schema"):
            migrate_paper_trading_enums(connection)


def test_partial_recovery_schema_without_required_constraints_and_triggers_fails_closed(migration_schema):
    engine, schema = migration_schema
    with _connection(engine, schema) as connection:
        _create_legacy_schema(connection)
        _create_legacy_recovery_tables(connection)
        connection.execute(
            text("ALTER TABLE paper_data_gap_recovery_gaps DROP CONSTRAINT ck_paper_data_gap_recovery_bfq")
        )
        with pytest.raises(PaperTradingEnumMigrationError, match="incomplete recovery schema"):
            migrate_paper_trading_enums(connection)


def test_partial_recovery_schema_without_approval_user_fk_fails_closed(migration_schema):
    engine, schema = migration_schema
    with _connection(engine, schema) as connection:
        _create_legacy_schema(connection)
        _create_legacy_recovery_tables(connection)
        connection.execute(
            text(
                "ALTER TABLE paper_data_gap_recovery_approvals "
                "DROP CONSTRAINT paper_data_gap_recovery_approvals_approver_user_id_fkey"
            )
        )
        with pytest.raises(PaperTradingEnumMigrationError, match="incomplete recovery schema"):
            migrate_paper_trading_enums(connection)
