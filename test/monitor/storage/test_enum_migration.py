# ruff: noqa: E501

from __future__ import annotations

import os
import uuid
from json import dumps

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from monitor.storage.enum_migration import (
    MONITOR_ENUM_ADAPTER,
    MONITOR_ENUM_GROUPS,
    MonitorEnumMigrationError,
    migrate_monitor_enums,
)
from storage.enum_governance import migrate_enums

EXPECTED_TYPE_NAMES = {group.type_name for group in MONITOR_ENUM_GROUPS}
CONDITION_CHECK_NAME = "ck_stock_monitor_targets_condition_type"
LEGACY_CONDITION_CHECK_SQL = (
    "CHECK (jsonb_typeof(condition::jsonb) = 'object' AND condition::jsonb ? 'type' "
    "AND condition::jsonb->>'type' IS NOT NULL AND condition::jsonb->>'type' IN "
    "('price_threshold', 'price_cross_ma', 'price_vs_ma', 'ma_cross', 'change_pct', 'rsi'))"
)
MANAGED_INDEX_NAMES = (
    "ix_stock_monitor_targets_market",
    "ix_stock_monitor_targets_frequency",
    "ix_stock_monitor_targets_reset_mode",
    "ix_forecast_ssf_candidates_market",
    "ix_forecast_ssf_candidates_state",
)


def _engine() -> Engine:
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    assert url is not None
    return create_engine(url)


@pytest.fixture()
def postgres_schema():
    engine = _engine()
    schema = f"monitor_enum_migration_{uuid.uuid4().hex}"
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
    connection.execute(
        text(
            "CREATE TABLE stock_monitor_targets ("
            "id integer primary key, stock_code varchar(10) NOT NULL, market varchar(5) NOT NULL DEFAULT 'A', "
            "condition json NOT NULL, frequency varchar(10) NOT NULL DEFAULT 'daily', "
            "reset_mode varchar(10) NOT NULL DEFAULT 'auto', latest_error_kind varchar(32))"
        )
    )
    connection.execute(
        text(
            "CREATE TABLE forecast_ssf_candidates ("
            "stock_code varchar(6) primary key, market varchar(5) NOT NULL DEFAULT 'A', "
            "report_end_date date NOT NULL, state varchar(32) NOT NULL, state_reason varchar(128) NOT NULL)"
        )
    )


def _enum_types(connection: Connection) -> set[str]:
    return (
        set(
            connection.execute(
                text("SELECT typname FROM pg_type WHERE typnamespace = current_schema()::regnamespace")
            ).scalars()
        )
        & EXPECTED_TYPE_NAMES
    )


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


def _column_default(connection: Connection, table_name: str, column_name: str) -> str | None:
    return connection.execute(
        text(
            "SELECT pg_get_expr(d.adbin, d.adrelid) FROM pg_attrdef d "
            "JOIN pg_class c ON c.oid = d.adrelid "
            "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.adnum "
            "WHERE c.relnamespace = current_schema()::regnamespace "
            "AND c.relname = :table_name AND a.attname = :column_name"
        ),
        {"table_name": table_name, "column_name": column_name},
    ).scalar_one_or_none()


def _check_exists(connection: Connection) -> bool:
    return bool(
        connection.execute(
            text(
                "SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
                "WHERE c.connamespace = current_schema()::regnamespace "
                "AND t.relname = 'stock_monitor_targets' AND c.conname = :constraint_name"
            ),
            {"constraint_name": CONDITION_CHECK_NAME},
        ).scalar_one_or_none()
    )


def _index_exists(connection: Connection, index_name: str) -> bool:
    return bool(
        connection.execute(
            text(
                "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = current_schema() AND c.relname = :index_name"
            ),
            {"index_name": index_name},
        ).scalar_one_or_none()
    )


def _assert_insert_rejected(connection: Connection, statement: str) -> None:
    savepoint = connection.begin_nested()
    try:
        with pytest.raises(Exception):
            connection.execute(text(statement))
    finally:
        savepoint.rollback()


def test_adapter_preflight_validates_legacy_condition_without_ddl(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        MONITOR_ENUM_ADAPTER.preflight(connection, rollback=False)

        assert _enum_types(connection) == set()
        assert not _check_exists(connection)


def test_adapter_apply_legacy_json_condition_creates_types_and_condition_check(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        MONITOR_ENUM_ADAPTER.preflight(connection, rollback=False)
        changed, diagnostics = MONITOR_ENUM_ADAPTER.apply(connection)

        assert changed is True
        assert diagnostics == ()
        assert _enum_types(connection) == EXPECTED_TYPE_NAMES
        assert _check_exists(connection)


def test_adapter_rollback_restores_legacy_columns_and_removes_condition_check(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        MONITOR_ENUM_ADAPTER.preflight(connection, rollback=False)
        MONITOR_ENUM_ADAPTER.apply(connection)
        MONITOR_ENUM_ADAPTER.preflight(connection, rollback=True)
        changed = MONITOR_ENUM_ADAPTER.rollback(connection)

        assert changed is True
        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _column_type(connection, "forecast_ssf_candidates", "state") == "character varying(32)"
        assert _enum_types(connection) == set()
        assert not _check_exists(connection)


def test_evaluation_error_kind_converts_reruns_rejects_unknown_and_rolls_back(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode, latest_error_kind) "
                "VALUES (1, '600001', 'A', '{\"type\": \"price_threshold\", \"direction\": \"above\", \"value\": 10}'::json, 'daily', 'auto', 'market_data')"
            )
        )
        assert migrate_monitor_enums(connection).converted is True
        assert _column_type(connection, "stock_monitor_targets", "latest_error_kind") == "monitor_evaluation_error_kind"
        assert next(group.labels for group in MONITOR_ENUM_GROUPS if group.type_name == "monitor_evaluation_error_kind") == (
            "market_data", "condition", "workflow_guard", "notification", "storage", "unknown"
        )
        audit = MONITOR_ENUM_ADAPTER.audit(connection, rollback=False)
        error_kind = next(group for group in audit.groups if group.type_name == "monitor_evaluation_error_kind")
        assert error_kind.ready is True
        assert error_kind.columns[0].observed_values == ("market_data",)
        assert migrate_monitor_enums(connection).converted is False
        assert migrate_monitor_enums(connection, rollback=True).rolled_back is True
        assert _column_type(connection, "stock_monitor_targets", "latest_error_kind") == "character varying(32)"


def test_evaluation_error_kind_unknown_legacy_value_aborts_before_ddl(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode, latest_error_kind) "
                "VALUES (1, '600001', 'A', '{\"type\": \"price_threshold\", \"direction\": \"above\", \"value\": 10}'::json, 'daily', 'auto', 'provider_secret')"
            )
        )
        with pytest.raises(MonitorEnumMigrationError, match="monitor_evaluation_error_kind"):
            migrate_monitor_enums(connection)
        assert _column_type(connection, "stock_monitor_targets", "latest_error_kind") == "character varying(32)"
        assert _enum_types(connection) == set()


def test_coordinator_rollback_is_noop_when_all_governed_tables_are_absent(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(text("DROP TABLE forecast_ssf_candidates, stock_monitor_targets"))

        result = migrate_enums(connection, rollback=True, adapters=(MONITOR_ENUM_ADAPTER,))

        assert result.rollback is True
        assert result.rolled_back is False
        assert _enum_types(connection) == set()


def test_dry_run_preflights_without_ddl(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        result = migrate_monitor_enums(connection, dry_run=True)

        assert result.dry_run is True
        assert result.converted is False
        assert _enum_types(connection) == set()
        assert not _check_exists(connection)
        assert not any(_index_exists(connection, index_name) for index_name in MANAGED_INDEX_NAMES)


def test_apply_bootstraps_missing_governed_tables_after_creating_types(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(text("DROP TABLE forecast_ssf_candidates, stock_monitor_targets"))

        assert migrate_monitor_enums(connection).converted is True

        assert _enum_types(connection) == EXPECTED_TYPE_NAMES
        for group in MONITOR_ENUM_GROUPS:
            for column in group.columns:
                assert _column_type(connection, column.table_name, column.column_name) == group.type_name
        assert _column_type(connection, "stock_monitor_targets", "condition") == "jsonb"
        assert _check_exists(connection)
        assert migrate_monitor_enums(connection).converted is False
        _assert_insert_rejected(
            connection,
            "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode) "
            "VALUES (1, '600001', 'A', '[]'::jsonb, 'daily', 'auto')",
        )


def test_unknown_legacy_label_aborts_before_any_ddl(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode) "
                "VALUES (1, '600001', 'US', '{\"type\": \"price_threshold\", \"direction\": \"above\", \"value\": 10}'::jsonb, 'daily', 'auto')"
            )
        )

        with pytest.raises(MonitorEnumMigrationError, match="monitor_market"):
            migrate_monitor_enums(connection)

        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _enum_types(connection) == set()
        assert not _check_exists(connection)


def test_invalid_legacy_condition_aborts_without_ddl(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode) "
                "VALUES (1, '600001', 'A', '{\"workflow\": \"forecast_ssf_ma20\"}'::jsonb, 'daily', 'auto')"
            )
        )

        with pytest.raises(MonitorEnumMigrationError, match="condition"):
            migrate_monitor_enums(connection)

        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _enum_types(connection) == set()
        assert not _check_exists(connection)


def test_type_dependent_invalid_legacy_condition_aborts_without_ddl(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode) "
                'VALUES (1, \'600001\', \'A\', \'{"type": "ma_cross", "direction": "golden", "fast": 20, "slow": 10}\'::jsonb, \'daily\', \'auto\')'
            )
        )

        with pytest.raises(MonitorEnumMigrationError, match="condition"):
            migrate_monitor_enums(connection)

        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _enum_types(connection) == set()
        assert not _check_exists(connection)


def test_conflicting_named_condition_check_aborts_before_any_ddl(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "ALTER TABLE stock_monitor_targets ADD CONSTRAINT ck_stock_monitor_targets_condition_type "
                "CHECK (jsonb_typeof(condition::jsonb) = 'object' "
                "AND condition::jsonb->>'type' IN ('price_threshold', 'unknown'))"
            )
        )

        with pytest.raises(MonitorEnumMigrationError, match="conflicting condition constraint"):
            migrate_monitor_enums(connection)

        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _enum_types(connection) == set()


def test_incompatible_named_index_aborts_before_any_ddl(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text("CREATE UNIQUE INDEX ix_stock_monitor_targets_market ON stock_monitor_targets (market)")
        )

        with pytest.raises(MonitorEnumMigrationError, match="missing or invalid index"):
            migrate_monitor_enums(connection)

        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _enum_types(connection) == set()


def test_expression_named_index_aborts_before_any_ddl(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text("CREATE INDEX ix_stock_monitor_targets_market ON stock_monitor_targets (lower(market))")
        )

        with pytest.raises(MonitorEnumMigrationError, match="missing or invalid index"):
            migrate_monitor_enums(connection)

        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _enum_types(connection) == set()


def test_apply_converts_columns_and_rejects_direct_invalid_values(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        assert not any(_index_exists(connection, index_name) for index_name in MANAGED_INDEX_NAMES)

        result = migrate_monitor_enums(connection)

        assert result.converted is True
        assert _column_type(connection, "stock_monitor_targets", "market") == "monitor_market"
        assert _column_type(connection, "forecast_ssf_candidates", "state") == "forecast_ssf_candidate_state"
        assert _enum_types(connection) == EXPECTED_TYPE_NAMES
        assert _check_exists(connection)
        for index_name in MANAGED_INDEX_NAMES:
            assert _index_exists(connection, index_name)
        _assert_insert_rejected(
            connection,
            "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode) "
            "VALUES (1, '600001', 'US', '{\"type\": \"price_threshold\", \"direction\": \"above\", \"value\": 10}'::jsonb, 'daily', 'auto')",
        )
        _assert_insert_rejected(
            connection,
            "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode) "
            "VALUES (1, '600001', 'A', '{\"type\": \"unknown\"}'::jsonb, 'daily', 'auto')",
        )
        _assert_insert_rejected(
            connection,
            "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode) "
            "VALUES (1, '600001', 'A', '{\"direction\": \"above\", \"value\": 10}'::jsonb, 'daily', 'auto')",
        )
        _assert_insert_rejected(
            connection,
            "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode) "
            "VALUES (1, '600001', 'A', '{\"type\": null}'::jsonb, 'daily', 'auto')",
        )


def test_apply_accepts_a_share_daily_close_cross_ma_condition(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        migrate_monitor_enums(connection)

        connection.execute(
            text(
                "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode) "
                "VALUES (1, '600001', 'A', "
                '\'{"type": "close_cross_ma", "direction": "above", "period": 20}\'::jsonb, '
                "'daily', 'auto')"
            )
        )

        assert connection.execute(text("SELECT count(*) FROM stock_monitor_targets")).scalar_one() == 1


def test_apply_replaces_legacy_condition_check_and_remains_idempotent(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                f"ALTER TABLE stock_monitor_targets ADD CONSTRAINT {CONDITION_CHECK_NAME} {LEGACY_CONDITION_CHECK_SQL}"
            )
        )

        assert migrate_monitor_enums(connection).converted is True

        connection.execute(
            text(
                "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode) "
                "VALUES (1, '600001', 'A', "
                '\'{"type": "close_cross_ma", "direction": "above", "period": 20}\'::jsonb, '
                "'daily', 'auto')"
            )
        )

        assert migrate_monitor_enums(connection).converted is False
        assert connection.execute(text("SELECT count(*) FROM stock_monitor_targets")).scalar_one() == 1


def test_apply_migrates_price_vs_ma_targets_before_tightening_condition_check(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(text("ALTER TABLE stock_monitor_targets ADD COLUMN note text"))
        connection.execute(text("ALTER TABLE stock_monitor_targets ADD COLUMN workflow varchar(64)"))
        connection.execute(text("ALTER TABLE stock_monitor_targets ADD COLUMN enabled boolean NOT NULL DEFAULT true"))
        connection.execute(
            text("ALTER TABLE stock_monitor_targets ADD COLUMN last_state boolean NOT NULL DEFAULT false")
        )
        connection.execute(text("ALTER TABLE stock_monitor_targets ADD COLUMN triggered_at timestamptz"))
        connection.execute(
            text(
                "INSERT INTO stock_monitor_targets "
                "(id, stock_code, market, condition, frequency, reset_mode, note, workflow, enabled, last_state, triggered_at) "
                "VALUES "
                "(1, '600001', 'A', :a_condition, "
                "'daily', 'manual', 'keep note', 'forecast_ssf_ma20', true, true, '2026-06-03 15:30:00+08'), "
                "(2, '00700', 'HK', :hk_condition, "
                "'daily', 'auto', 'hk note', NULL, true, false, NULL)"
            ),
            {
                "a_condition": dumps(
                    {
                        "type": "price_vs_ma",
                        "direction": "above",
                        "period": 20,
                        "workflow": "forecast_ssf_ma20",
                    }
                ),
                "hk_condition": dumps({"type": "price_vs_ma", "direction": "above", "period": 20}),
            },
        )

        result = migrate_monitor_enums(connection)

        rows = connection.execute(
            text(
                "SELECT id, market, condition::jsonb AS condition, frequency, reset_mode, note, workflow, "
                "enabled, last_state, triggered_at FROM stock_monitor_targets ORDER BY id"
            )
        ).all()
        first = rows[0]._mapping
        second = rows[1]._mapping
        assert result.converted is True
        assert [diagnostic.target_id for diagnostic in result.price_vs_ma_diagnostics] == [1, 2]
        assert result.price_vs_ma_diagnostics[0].disabled is False
        assert result.price_vs_ma_diagnostics[1].market == "HK"
        assert result.price_vs_ma_diagnostics[1].disabled is True
        assert first["condition"]["type"] == "close_cross_ma"
        assert first["condition"]["workflow"] == "forecast_ssf_ma20"
        assert first["enabled"] is True
        assert first["last_state"] is True
        assert first["note"] == "keep note"
        assert first["workflow"] == "forecast_ssf_ma20"
        assert second["condition"]["type"] == "close_cross_ma"
        assert second["enabled"] is False
        assert second["last_state"] is False
        _assert_insert_rejected(
            connection,
            "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode) "
            "VALUES (3, '600002', 'A', "
            '\'{"type": "price_vs_ma", "direction": "above", "period": 20}\'::jsonb, '
            "'daily', 'auto')",
        )


def test_price_vs_ma_migration_is_rerun_safe(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(text("ALTER TABLE stock_monitor_targets ADD COLUMN enabled boolean NOT NULL DEFAULT true"))
        connection.execute(
            text("ALTER TABLE stock_monitor_targets ADD COLUMN last_state boolean NOT NULL DEFAULT false")
        )
        connection.execute(
            text(
                "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode, enabled, last_state) "
                "VALUES (1, '600001', 'A', :condition, 'daily', 'auto', true, false)"
            ),
            {"condition": dumps({"type": "price_vs_ma", "direction": "above", "period": 20})},
        )

        assert migrate_monitor_enums(connection).converted is True
        before = connection.execute(
            text("SELECT condition::jsonb, enabled, last_state FROM stock_monitor_targets")
        ).one()

        result = migrate_monitor_enums(connection)
        assert result.converted is False
        assert result.price_vs_ma_diagnostics == ()
        after = connection.execute(
            text("SELECT condition::jsonb, enabled, last_state FROM stock_monitor_targets")
        ).one()

        assert before == after


def test_price_vs_ma_below_direction_migrates_disabled_and_normalized(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(text("ALTER TABLE stock_monitor_targets ADD COLUMN enabled boolean NOT NULL DEFAULT true"))
        connection.execute(
            text(
                "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode, enabled) "
                "VALUES (1, '600001', 'A', :condition, 'daily', 'auto', true)"
            ),
            {"condition": dumps({"type": "price_vs_ma", "direction": "below", "period": 20})},
        )

        result = migrate_monitor_enums(connection)

        row = connection.execute(text("SELECT condition::jsonb, enabled FROM stock_monitor_targets WHERE id = 1")).one()
        assert len(result.price_vs_ma_diagnostics) == 1
        assert result.price_vs_ma_diagnostics[0].target_id == 1
        assert result.price_vs_ma_diagnostics[0].direction == "below"
        assert result.price_vs_ma_diagnostics[0].disabled is True
        assert row[0] == {"type": "close_cross_ma", "direction": "above", "period": 20}
        assert row[1] is False


def test_second_apply_is_idempotent(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        assert migrate_monitor_enums(connection).converted is True

        result = migrate_monitor_enums(connection)

        assert result.converted is False
        assert _enum_types(connection) == EXPECTED_TYPE_NAMES
        assert _check_exists(connection)
        assert all(_index_exists(connection, index_name) for index_name in MANAGED_INDEX_NAMES)


def test_rollback_rejects_non_column_enum_dependency_before_drop(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        migrate_monitor_enums(connection)
        connection.execute(text("CREATE VIEW monitor_market_dependency AS SELECT 'A'::monitor_market AS market"))

        with pytest.raises(MonitorEnumMigrationError, match="monitor_market: dependencies remain"):
            migrate_monitor_enums(connection, rollback=True)

        assert _column_type(connection, "stock_monitor_targets", "market") == "monitor_market"
        assert _column_type(connection, "stock_monitor_targets", "frequency") == "monitor_frequency"
        assert _column_type(connection, "stock_monitor_targets", "reset_mode") == "monitor_reset_mode"
        assert _column_type(connection, "forecast_ssf_candidates", "market") == "monitor_market"
        assert _column_type(connection, "forecast_ssf_candidates", "state") == "forecast_ssf_candidate_state"
        assert _enum_types(connection) == EXPECTED_TYPE_NAMES
        assert _check_exists(connection)


def test_rollback_audit_normalizes_view_dependency_to_one_view_name(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        migrate_monitor_enums(connection)
        connection.execute(text("CREATE VIEW monitor_market_dependency AS SELECT 'A'::monitor_market AS market"))

        audit = MONITOR_ENUM_ADAPTER.audit(connection, rollback=True)

    market = next(group for group in audit.groups if group.type_name == "monitor_market")
    assert market.dependencies == ("view monitor_market_dependency",)


def test_rollback_preflight_rejects_view_dependency_before_rollback(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        migrate_monitor_enums(connection)
        connection.execute(text("CREATE VIEW monitor_market_dependency AS SELECT 'A'::monitor_market AS market"))

        with pytest.raises(MonitorEnumMigrationError, match="monitor_market: dependencies remain"):
            MONITOR_ENUM_ADAPTER.preflight(connection, rollback=True)

        assert _column_type(connection, "stock_monitor_targets", "market") == "monitor_market"


def test_rollback_rejects_invalid_condition_before_altering_columns(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        migrate_monitor_enums(connection)
        connection.execute(
            text(
                "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode) "
                'VALUES (1, \'600001\', \'A\', \'{"type": "ma_cross", "direction": "golden", "fast": 20, "slow": 10}\'::jsonb, \'daily\', \'auto\')'
            )
        )

        with pytest.raises(MonitorEnumMigrationError, match="condition for"):
            migrate_monitor_enums(connection, rollback=True)

        assert _column_type(connection, "stock_monitor_targets", "market") == "monitor_market"
        assert _enum_types(connection) == EXPECTED_TYPE_NAMES
        assert _check_exists(connection)


def test_rollback_after_normal_apply_restores_legacy_types_defaults_and_removes_governance(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        migrate_monitor_enums(connection)

        result = migrate_monitor_enums(connection, rollback=True)

        assert result.rolled_back is True
        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _column_type(connection, "stock_monitor_targets", "frequency") == "character varying(10)"
        assert _column_type(connection, "stock_monitor_targets", "reset_mode") == "character varying(10)"
        assert _column_type(connection, "forecast_ssf_candidates", "market") == "character varying(5)"
        assert _column_type(connection, "forecast_ssf_candidates", "state") == "character varying(32)"
        assert _column_default(connection, "stock_monitor_targets", "market") == "'A'::character varying"
        assert _column_default(connection, "stock_monitor_targets", "frequency") == "'daily'::character varying"
        assert _column_default(connection, "stock_monitor_targets", "reset_mode") == "'auto'::character varying"
        assert _column_default(connection, "forecast_ssf_candidates", "market") == "'A'::character varying"
        assert _enum_types(connection) == set()
        assert not _check_exists(connection)
        for index_name in MANAGED_INDEX_NAMES:
            assert _index_exists(connection, index_name)
