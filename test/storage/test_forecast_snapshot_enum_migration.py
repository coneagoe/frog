from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session, sessionmaker

from storage.enum_governance import EnumGovernanceError, migrate_enums
from storage.enum_migration import STORAGE_ENUM_ADAPTER
from storage.model import ForecastSnapshotRecord, ForecastSnapshotRun
from storage.storage_db import StorageDb, StorageError


def _engine() -> Engine:
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    return create_engine(url)


@pytest.fixture()
def postgres_schema():
    engine = _engine()
    schema = f"forecast_snapshot_enum_migration_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET search_path TO "{schema}"'))
        _create_legacy_schema(connection)
    try:
        yield engine, schema
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def _connection(engine: Engine, schema: str) -> Connection:
    connection = engine.connect()
    connection.execute(text(f'SET search_path TO "{schema}"'))
    return connection


def _create_legacy_schema(connection: Connection) -> None:
    statements = (
        "CREATE TABLE blackroom_records (id integer primary key, "
        "market varchar(5) NOT NULL DEFAULT 'A', source varchar(50) NOT NULL DEFAULT 'manual')",
        "CREATE TABLE daily_bar_diagnostics (id integer primary key, "
        "adjust varchar(10) NOT NULL, classification varchar(50) NOT NULL, provider_outcomes jsonb NOT NULL)",
        "CREATE TABLE ssf_change_signals (id integer primary key, "
        "status varchar(20) NOT NULL DEFAULT 'signal', event_types jsonb NOT NULL)",
        "CREATE TABLE forecast_snapshot_runs (id integer primary key, report_end_date date NOT NULL, "
        "announcement_start_date date NOT NULL, announcement_end_date date NOT NULL, "
        "attempt integer NOT NULL, status varchar(16) NOT NULL)",
        "CREATE TABLE forecast_snapshot_records (id integer primary key, run_id integer NOT NULL "
        "REFERENCES forecast_snapshot_runs(id), ts_code varchar(32) NOT NULL, announcement_date date NOT NULL, "
        "report_end_date date NOT NULL, forecast_type varchar(20) NOT NULL, growth_min double precision, "
        "growth_max double precision, source_order integer NOT NULL)",
    )
    for statement in statements:
        connection.execute(text(statement))


def _column_type(connection: Connection, table_name: str, column_name: str) -> str:
    return str(
        connection.execute(
            text(
                "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
                "JOIN pg_class c ON c.oid = a.attrelid "
                "WHERE c.relnamespace = current_schema()::regnamespace "
                "AND c.relname = :table_name AND a.attname = :column_name"
            ),
            {"table_name": table_name, "column_name": column_name},
        ).scalar_one()
    )


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


def _index_predicate(connection: Connection, index_name: str) -> str:
    return str(
        connection.execute(
            text(
                "SELECT pg_get_expr(i.indpred, i.indrelid) FROM pg_index i "
                "JOIN pg_class c ON c.oid = i.indexrelid "
                "WHERE c.relnamespace = current_schema()::regnamespace AND c.relname = :index_name"
            ),
            {"index_name": index_name},
        ).scalar_one()
    )


def _table_exists(connection: Connection, table_name: str) -> bool:
    return connection.execute(
        text("SELECT to_regclass(:table_name) IS NOT NULL"), {"table_name": table_name}
    ).scalar_one()


def _foreign_key_target(connection: Connection, table_name: str) -> str:
    return str(
        connection.execute(
            text(
                "SELECT ccu.table_name FROM information_schema.table_constraints tc "
                "JOIN information_schema.constraint_column_usage ccu "
                "ON ccu.constraint_name = tc.constraint_name AND ccu.constraint_schema = tc.constraint_schema "
                "WHERE tc.table_schema = current_schema() AND tc.table_name = :table_name "
                "AND tc.constraint_type = 'FOREIGN KEY'"
            ),
            {"table_name": table_name},
        ).scalar_one()
    )


def _index_definition(connection: Connection, index_name: str) -> tuple[bool, tuple[str, ...], str | None]:
    row = connection.execute(
        text(
            "SELECT i.indisunique, array_agg(a.attname ORDER BY key.ordinality), "
            "pg_get_expr(i.indpred, i.indrelid) "
            "FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indexrelid "
            "JOIN pg_class t ON t.oid = i.indrelid "
            "JOIN unnest(i.indkey) WITH ORDINALITY AS key(attnum, ordinality) ON key.ordinality <= i.indnkeyatts "
            "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = key.attnum "
            "WHERE c.relnamespace = current_schema()::regnamespace AND c.relname = :index_name "
            "GROUP BY i.indexrelid, i.indisunique, i.indpred"
        ),
        {"index_name": index_name},
    ).one()
    return bool(row[0]), tuple(row[1]), None if row[2] is None else str(row[2])


def test_migration_converts_snapshot_status_and_creates_running_range_index(postgres_schema) -> None:
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        for status in ("running", "completed", "failed"):
            connection.execute(
                text(
                    "INSERT INTO forecast_snapshot_runs "
                    "(id, report_end_date, announcement_start_date, announcement_end_date, attempt, status) "
                    "VALUES (:id, '2026-06-30', '2026-07-01', '2026-07-01', :id, :status)"
                ),
                {"id": ("running", "completed", "failed").index(status) + 1, "status": status},
            )

        assert migrate_enums(connection).converted is True

        assert _column_type(connection, "forecast_snapshot_runs", "status") == "forecast_snapshot_status"
        assert _table_exists(connection, "forecast_snapshot_records")
        assert _foreign_key_target(connection, "forecast_snapshot_records") == "forecast_snapshot_runs"
        assert _enum_labels(connection, "forecast_snapshot_status") == ("running", "completed", "failed")
        assert _index_predicate(connection, "uq_forecast_snapshot_running_range") == (
            "(status = 'running'::forecast_snapshot_status)"
        )
        assert migrate_enums(connection, rollback=True).rolled_back is True
        assert _column_type(connection, "forecast_snapshot_runs", "status") == "character varying(16)"


def test_migration_creates_both_snapshot_tables_in_a_fresh_schema() -> None:
    engine = _engine()
    schema = f"forecast_snapshot_fresh_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        with _connection(engine, schema) as connection:
            assert migrate_enums(connection, adapters=(STORAGE_ENUM_ADAPTER,)).converted is True

            assert _table_exists(connection, "forecast_snapshot_runs")
            assert _table_exists(connection, "forecast_snapshot_records")
            assert _foreign_key_target(connection, "forecast_snapshot_records") == "forecast_snapshot_runs"
            assert _column_type(connection, "forecast_snapshot_runs", "status") == "forecast_snapshot_status"
            assert _index_predicate(connection, "uq_forecast_snapshot_running_range") == (
                "(status = 'running'::forecast_snapshot_status)"
            )
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_migration_rejects_run_without_snapshot_records() -> None:
    engine = _engine()
    schema = f"forecast_snapshot_run_only_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET search_path TO "{schema}"'))
        _create_legacy_schema(connection)
        connection.execute(text("DROP TABLE forecast_snapshot_records"))
    try:
        with _connection(engine, schema) as connection:
            with pytest.raises(EnumGovernanceError, match="partially missing forecast snapshot tables"):
                migrate_enums(connection, adapters=(STORAGE_ENUM_ADAPTER,))

            assert not _table_exists(connection, "forecast_snapshot_records")
            assert _column_type(connection, "forecast_snapshot_runs", "status") == "character varying(16)"
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_migration_rejects_snapshot_records_without_run() -> None:
    engine = _engine()
    schema = f"forecast_snapshot_records_only_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET search_path TO "{schema}"'))
        _create_legacy_schema(connection)
        connection.execute(text("DROP TABLE forecast_snapshot_records"))
        connection.execute(text("DROP TABLE forecast_snapshot_runs"))
        connection.execute(text("CREATE TABLE forecast_snapshot_records (id integer primary key)"))
    try:
        with _connection(engine, schema) as connection:
            with pytest.raises(EnumGovernanceError, match="partially missing forecast snapshot tables"):
                migrate_enums(connection, adapters=(STORAGE_ENUM_ADAPTER,))

            assert not _table_exists(connection, "forecast_snapshot_runs")
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_migration_rejects_unknown_snapshot_status_without_conversion(postgres_schema) -> None:
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "INSERT INTO forecast_snapshot_runs "
                "(id, report_end_date, announcement_start_date, announcement_end_date, attempt, status) "
                "VALUES (1, '2026-06-30', '2026-07-01', '2026-07-01', 1, 'unknown')"
            )
        )

        with pytest.raises(EnumGovernanceError, match="forecast_snapshot_status"):
            migrate_enums(connection)

        assert _column_type(connection, "forecast_snapshot_runs", "status") == "character varying(16)"


def test_migration_repairs_malformed_running_range_index(postgres_schema) -> None:
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(text("CREATE INDEX uq_forecast_snapshot_running_range ON forecast_snapshot_runs (attempt)"))

        assert migrate_enums(connection).converted is True

        assert _index_definition(connection, "uq_forecast_snapshot_running_range") == (
            True,
            ("report_end_date", "announcement_start_date", "announcement_end_date"),
            "(status = 'running'::forecast_snapshot_status)",
        )


def test_postgresql_allows_only_one_running_equivalent_snapshot(postgres_schema) -> None:
    engine, schema = postgres_schema
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.execute(text("DROP TABLE forecast_snapshot_records"))
        connection.execute(text("DROP TABLE forecast_snapshot_runs"))
        connection.execute(text("CREATE TYPE forecast_snapshot_status AS ENUM ('running', 'completed', 'failed')"))
        ForecastSnapshotRun.__table__.create(connection, checkfirst=True)
        ForecastSnapshotRecord.__table__.create(connection, checkfirst=True)

    first = StorageDb.__new__(StorageDb)
    first.engine = engine.execution_options(schema_translate_map={None: schema})
    first.Session = sessionmaker(bind=first.engine)
    second = StorageDb.__new__(StorageDb)
    second.engine = engine.execution_options(schema_translate_map={None: schema})
    second.Session = sessionmaker(bind=second.engine)

    def acquire(db: StorageDb) -> int | None:
        try:
            return db.acquire_forecast_snapshot_run(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 1)).id
        except StorageError:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        acquired = list(executor.map(acquire, (first, second)))

    with _connection(engine, schema) as connection:
        runs = connection.execute(text("SELECT status, attempt FROM forecast_snapshot_runs")).all()

    assert sum(run_id is not None for run_id in acquired) == 1
    assert runs == [("running", 1)]


def test_postgresql_recovers_full_attempt_collision_during_concurrent_snapshot_retry(
    postgres_schema, monkeypatch
) -> None:
    engine, schema = postgres_schema
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.execute(text("DROP TABLE forecast_snapshot_records"))
        connection.execute(text("DROP TABLE forecast_snapshot_runs"))
        connection.execute(text("CREATE TYPE forecast_snapshot_status AS ENUM ('running', 'completed', 'failed')"))
        ForecastSnapshotRun.__table__.create(connection, checkfirst=True)
        ForecastSnapshotRecord.__table__.create(connection, checkfirst=True)
        connection.execute(text("DROP INDEX uq_forecast_snapshot_running_range"))

    flush_barrier = Barrier(2)

    class RetryFlushBarrierSession(Session):
        def flush(self, *args, **kwargs):
            if any(isinstance(item, ForecastSnapshotRun) and item.attempt == 2 for item in self.new):
                flush_barrier.wait(timeout=10)
            return super().flush(*args, **kwargs)

    first = StorageDb.__new__(StorageDb)
    first.engine = engine.execution_options(schema_translate_map={None: schema})
    first.Session = sessionmaker(bind=first.engine, class_=RetryFlushBarrierSession)
    second = StorageDb.__new__(StorageDb)
    second.engine = engine.execution_options(schema_translate_map={None: schema})
    second.Session = sessionmaker(bind=second.engine, class_=RetryFlushBarrierSession)

    initial = first.acquire_forecast_snapshot_run(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 1))
    first.fail_forecast_snapshot_run(initial.id, "provider unavailable")

    completed_lookup_count = 0
    original_get_completed = StorageDb.get_completed_forecast_snapshot_run

    def get_completed(*args, **kwargs):
        nonlocal completed_lookup_count
        completed_lookup_count += 1
        return original_get_completed(*args, **kwargs)

    monkeypatch.setattr(StorageDb, "get_completed_forecast_snapshot_run", get_completed)

    def acquire(db: StorageDb) -> int | str:
        try:
            return db.acquire_forecast_snapshot_run(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 1)).id
        except StorageError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        acquired = list(executor.map(acquire, (first, second)))

    with _connection(engine, schema) as connection:
        runs = connection.execute(text("SELECT status, attempt FROM forecast_snapshot_runs ORDER BY attempt")).all()

    assert sum(isinstance(result, int) for result in acquired) == 1
    assert "forecast snapshot is already running for requested range" in acquired
    assert completed_lookup_count == 3
    assert runs == [("failed", 1), ("running", 2)]
