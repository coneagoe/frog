# ruff: noqa: E501

import os
import uuid
from dataclasses import dataclass
from typing import cast

import pytest
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import Connection, Engine

from monitor.storage.enum_migration import MONITOR_ENUM_GROUPS
from paper_trading.storage.enum_migration import PAPER_TRADING_ENUM_GROUPS
from storage.enum_governance import (
    ENUM_GOVERNANCE_ADAPTERS,
    EnumGovernanceAdapter,
    EnumGovernanceError,
    migrate_enums,
)
from storage.enum_migration import STORAGE_ENUM_GROUPS

MANAGED_CHECK_NAMES = {
    "ck_stock_monitor_targets_condition_type",
    "ck_daily_bar_diagnostics_provider_outcome_status",
    "ck_ssf_change_signals_event_types",
}


@dataclass
class FakeConnection:
    dialect_name: str = "postgresql"

    @property
    def dialect(self):
        return type("Dialect", (), {"name": self.dialect_name})()


def _engine() -> Engine:
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    assert url is not None
    return create_engine(url)


@pytest.fixture()
def postgres_schema():
    engine = _engine()
    schema = f"enum_governance_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET search_path TO "{schema}"'))
        _create_paper_legacy_schema(connection)
        _create_monitor_legacy_schema(connection)
        _create_storage_legacy_schema(connection)
    try:
        yield engine, schema
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def _create_paper_legacy_schema(connection: Connection) -> None:
    statements = (
        "CREATE TABLE paper_accounts (id integer primary key, status varchar(20) NOT NULL DEFAULT 'active', fee_preset varchar(30) NOT NULL DEFAULT 'a_share')",
        "CREATE TABLE paper_cash_ledger (id integer primary key, event_type varchar(20) NOT NULL)",
        "CREATE TABLE paper_positions (id integer primary key, source varchar(20) NOT NULL DEFAULT 'trade', market varchar(20) NOT NULL DEFAULT 'a_share')",
        "CREATE TABLE paper_position_lots (id integer primary key, source varchar(20) NOT NULL DEFAULT 'trade', market varchar(20) NOT NULL DEFAULT 'a_share')",
        "CREATE TABLE paper_orders (id integer primary key, side varchar(10) NOT NULL, status varchar(30) NOT NULL, validity_status varchar(20), market varchar(20) NOT NULL DEFAULT 'a_share')",
        "CREATE TABLE paper_trades (id integer primary key, side varchar(10) NOT NULL, market varchar(20) NOT NULL DEFAULT 'a_share')",
        "CREATE TABLE paper_position_round_trips (id integer primary key, status varchar(20) NOT NULL DEFAULT 'open')",
        "CREATE TABLE paper_trade_validity_checks (id integer primary key, side varchar(10) NOT NULL, status varchar(20) NOT NULL, data_granularity varchar(20) NOT NULL DEFAULT 'daily', market varchar(20) NOT NULL DEFAULT 'a_share')",
        "CREATE TABLE paper_pending_settlement (id integer primary key, source varchar(20) NOT NULL)",
        "CREATE TABLE paper_ledger_rebuilds (id integer primary key, status varchar(20) NOT NULL)",
        "CREATE TABLE paper_matching_runs (id integer primary key, trade_date date NOT NULL, scope_key varchar(40) NOT NULL, status varchar(32) NOT NULL)",
        "CREATE INDEX ix_paper_positions_market ON paper_positions (market)",
        "CREATE INDEX ix_paper_position_lots_market ON paper_position_lots (market)",
        "CREATE INDEX ix_paper_orders_status ON paper_orders (status)",
        "CREATE INDEX ix_paper_orders_validity_status ON paper_orders (validity_status)",
        "CREATE INDEX ix_paper_orders_market ON paper_orders (market)",
        "CREATE INDEX ix_paper_trades_market ON paper_trades (market)",
        "CREATE INDEX ix_paper_trade_validity_checks_status ON paper_trade_validity_checks (status)",
        "CREATE INDEX ix_paper_trade_validity_checks_market ON paper_trade_validity_checks (market)",
        "CREATE INDEX ix_paper_position_round_trips_status ON paper_position_round_trips (status)",
        "CREATE INDEX ix_paper_ledger_rebuilds_status ON paper_ledger_rebuilds (status)",
        "CREATE UNIQUE INDEX uq_matching_active_scope ON paper_matching_runs (trade_date, scope_key) WHERE status = 'running'",
    )
    for statement in statements:
        connection.execute(text(statement))


def _create_monitor_legacy_schema(connection: Connection) -> None:
    connection.execute(
        text(
            "CREATE TABLE stock_monitor_targets ("
            "id integer primary key, stock_code varchar(10) NOT NULL, market varchar(5) NOT NULL DEFAULT 'A', "
            "condition jsonb NOT NULL, frequency varchar(10) NOT NULL DEFAULT 'daily', "
            "reset_mode varchar(10) NOT NULL DEFAULT 'auto')"
        )
    )
    connection.execute(
        text(
            "CREATE TABLE forecast_ssf_candidates ("
            "stock_code varchar(6) primary key, market varchar(5) NOT NULL DEFAULT 'A', "
            "report_end_date date NOT NULL, state varchar(32) NOT NULL, state_reason varchar(128) NOT NULL)"
        )
    )


def _create_storage_legacy_schema(connection: Connection) -> None:
    statements = (
        "CREATE TABLE blackroom_records (id integer primary key, market varchar(5) NOT NULL DEFAULT 'A', source varchar(50) NOT NULL DEFAULT 'manual')",
        "CREATE TABLE daily_bar_diagnostics (id integer primary key, adjust varchar(10) NOT NULL, classification varchar(50) NOT NULL, provider_outcomes jsonb NOT NULL)",
        "CREATE TABLE ssf_change_signals (id integer primary key, status varchar(20) NOT NULL DEFAULT 'signal', event_types jsonb NOT NULL)",
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


def _index_exists(connection: Connection, index_name: str) -> bool:
    return bool(
        connection.execute(
            text("SELECT to_regclass(:index_name) IS NOT NULL"), {"index_name": index_name}
        ).scalar_one()
    )


def _normalized_legacy_type(type_sql: str) -> str:
    return type_sql.lower().replace("varchar", "character varying")


def _all_enum_groups():
    return PAPER_TRADING_ENUM_GROUPS + MONITOR_ENUM_GROUPS + STORAGE_ENUM_GROUPS


def _all_managed_enum_types(connection: Connection) -> set[str]:
    expected = {group.type_name for group in _all_enum_groups()}
    return (
        set(
            connection.execute(
                text("SELECT typname FROM pg_type WHERE typnamespace = current_schema()::regnamespace")
            ).scalars()
        )
        & expected
    )


def _managed_check_names(connection: Connection) -> set[str]:
    return set(
        connection.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE connamespace = current_schema()::regnamespace "
                "AND conname IN :names"
            ).bindparams(bindparam("names", expanding=True)),
            {"names": tuple(sorted(MANAGED_CHECK_NAMES))},
        ).scalars()
    )


def _adapter(
    name: str,
    events: list[str],
    *,
    changed: bool = True,
    fail_preflight: bool = False,
    fail_apply: bool = False,
) -> EnumGovernanceAdapter:
    def preflight(connection: FakeConnection, *, rollback: bool) -> None:
        del connection, rollback
        events.append(f"{name}.preflight")
        if fail_preflight:
            raise RuntimeError("preflight failed")

    def apply(connection: FakeConnection) -> bool:
        del connection
        events.append(f"{name}.apply")
        if fail_apply:
            raise RuntimeError("apply failed")
        return changed

    def verify(connection: FakeConnection, *, rollback: bool) -> None:
        del connection
        events.append(f"{name}.verify_rollback" if rollback else f"{name}.verify")

    def rollback(connection: FakeConnection) -> bool:
        del connection
        events.append(f"{name}.rollback")
        return changed

    def result(*, dry_run: bool, rollback: bool, converted: bool, rolled_back: bool) -> str:
        return f"{name}:{dry_run}:{rollback}:{converted}:{rolled_back}"

    return EnumGovernanceAdapter(name, preflight, apply, verify, rollback, result)


def test_normal_migration_preflights_every_adapter_before_ddl() -> None:
    events: list[str] = []

    result = migrate_enums(
        cast(Connection, FakeConnection()),
        adapters=(_adapter("paper", events), _adapter("monitor", events), _adapter("storage", events)),
    )

    assert events == [
        "paper.preflight",
        "monitor.preflight",
        "storage.preflight",
        "paper.apply",
        "monitor.apply",
        "storage.apply",
        "paper.verify",
        "monitor.verify",
        "storage.verify",
    ]
    assert result.converted is True
    assert result.rolled_back is False
    assert [(domain.name, domain.result) for domain in result.domains] == [
        ("paper", "paper:False:False:True:False"),
        ("monitor", "monitor:False:False:True:False"),
        ("storage", "storage:False:False:True:False"),
    ]


def test_dry_run_only_preflights_adapters() -> None:
    events: list[str] = []

    result = migrate_enums(
        cast(Connection, FakeConnection()),
        dry_run=True,
        adapters=(_adapter("paper", events), _adapter("monitor", events)),
    )

    assert events == ["paper.preflight", "monitor.preflight"]
    assert result.dry_run is True
    assert result.converted is False
    assert result.rolled_back is False
    assert [(domain.name, domain.result) for domain in result.domains] == [
        ("paper", "paper:True:False:False:False"),
        ("monitor", "monitor:True:False:False:False"),
    ]


def test_rollback_preflights_then_rolls_back_then_verifies_each_adapter() -> None:
    events: list[str] = []

    result = migrate_enums(
        cast(Connection, FakeConnection()),
        rollback=True,
        adapters=(
            _adapter("paper", events),
            _adapter("monitor", events, changed=False),
            _adapter("storage", events),
        ),
    )

    assert events == [
        "paper.preflight",
        "monitor.preflight",
        "storage.preflight",
        "paper.rollback",
        "monitor.rollback",
        "storage.rollback",
        "paper.verify_rollback",
        "monitor.verify_rollback",
        "storage.verify_rollback",
    ]
    assert result.converted is False
    assert result.rolled_back is True
    assert [(domain.name, domain.result) for domain in result.domains] == [
        ("paper", "paper:False:True:False:True"),
        ("monitor", "monitor:False:True:False:True"),
        ("storage", "storage:False:True:False:True"),
    ]


def test_preflight_failure_prevents_every_apply() -> None:
    events: list[str] = []

    with pytest.raises(EnumGovernanceError, match="monitor preflight failed"):
        migrate_enums(
            cast(Connection, FakeConnection()),
            adapters=(_adapter("paper", events), _adapter("monitor", events, fail_preflight=True)),
        )

    assert events == ["paper.preflight", "monitor.preflight"]


def test_domain_failure_names_adapter_and_preserves_cause() -> None:
    events: list[str] = []

    with pytest.raises(EnumGovernanceError, match="monitor apply failed") as caught:
        migrate_enums(
            cast(Connection, FakeConnection()),
            adapters=(_adapter("paper", events), _adapter("monitor", events, fail_apply=True)),
        )

    assert isinstance(caught.value.__cause__, RuntimeError)
    assert str(caught.value.__cause__) == "apply failed"


def test_non_postgresql_connection_returns_no_change_without_adapters() -> None:
    events: list[str] = []

    result = migrate_enums(
        cast(Connection, FakeConnection(dialect_name="sqlite")),
        adapters=(_adapter("paper", events), _adapter("monitor", events)),
    )

    assert events == []
    assert result.converted is False
    assert result.rolled_back is False
    assert [(domain.name, domain.result) for domain in result.domains] == [
        ("paper", "paper:False:False:False:False"),
        ("monitor", "monitor:False:False:False:False"),
    ]


def test_default_adapters_are_paper_trading_monitor_then_storage() -> None:
    assert tuple(adapter.name for adapter in ENUM_GOVERNANCE_ADAPTERS) == ("paper_trading", "monitor", "storage")


def test_atomic_migration_prevents_all_conversion_when_storage_json_is_invalid(postgres_schema) -> None:
    engine, schema = postgres_schema
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.execute(
            text(
                "INSERT INTO daily_bar_diagnostics "
                "(id, adjust, classification, provider_outcomes) VALUES "
                "(1, 'bfq', 'downloaded', '[{\"status\": \"partial\"}]'::jsonb)"
            )
        )

        with pytest.raises(EnumGovernanceError, match="storage"):
            migrate_enums(connection)

        assert _column_type(connection, "paper_matching_runs", "status") == "character varying(32)"
        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _column_type(connection, "daily_bar_diagnostics", "adjust") == "character varying(10)"
        assert _all_managed_enum_types(connection) == set()
        assert (
            connection.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE connamespace = current_schema()::regnamespace "
                    "AND conname IN ('ck_daily_bar_diagnostics_provider_outcome_status', 'ck_ssf_change_signals_event_types')"
                )
            )
            .scalars()
            .all()
            == []
        )


def test_atomic_migration_rolls_back_paper_trading_when_monitor_condition_is_invalid(postgres_schema) -> None:
    engine, schema = postgres_schema
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.execute(
            text(
                "INSERT INTO paper_matching_runs (id, trade_date, scope_key, status) VALUES (1, '2026-08-08', 'daily', 'running')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode) "
                "VALUES (1, '600001', 'A', '{\"workflow\": \"forecast_ssf_ma20\"}'::jsonb, 'daily', 'auto')"
            )
        )

        with pytest.raises(EnumGovernanceError, match="monitor"):
            migrate_enums(connection)

        assert _column_type(connection, "paper_matching_runs", "status") == "character varying(32)"
        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _all_managed_enum_types(connection) == set()


def test_atomic_migration_prevents_monitor_conversion_when_paper_trading_value_is_invalid(postgres_schema) -> None:
    engine, schema = postgres_schema
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.execute(
            text("INSERT INTO paper_orders (id, side, status, market) VALUES (1, 'borrow', 'new', 'a_share')")
        )

        with pytest.raises(EnumGovernanceError, match="paper_trading"):
            migrate_enums(connection)

        assert _column_type(connection, "paper_matching_runs", "status") == "character varying(32)"
        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _all_managed_enum_types(connection) == set()


def test_unified_rollback_restores_all_domains_and_removes_checks(postgres_schema) -> None:
    engine, schema = postgres_schema
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{schema}"'))

        assert migrate_enums(connection).converted is True
        result = migrate_enums(connection, rollback=True)

        assert result.rolled_back is True
        assert _all_managed_enum_types(connection) == set()
        assert _managed_check_names(connection) == set()
        for group in _all_enum_groups():
            for column in group.columns:
                assert _column_type(connection, column.table_name, column.column_name) == _normalized_legacy_type(
                    column.legacy_type_sql
                )
                assert _column_default(connection, column.table_name, column.column_name) == column.default_sql
                for index_name, _ in getattr(column, "indexes", ()):
                    assert _index_exists(connection, index_name)


def test_unified_rollback_wraps_storage_enum_dependency_failure(postgres_schema) -> None:
    engine, schema = postgres_schema
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{schema}"'))
        assert migrate_enums(connection).converted is True
        connection.execute(text("CREATE VIEW blackroom_market_dependency AS SELECT 'A'::blackroom_market AS market"))

        with pytest.raises(EnumGovernanceError, match="storage preflight failed") as caught:
            migrate_enums(connection, rollback=True)

        assert caught.value.__cause__ is not None
        assert "blackroom_market: dependencies remain" in str(caught.value.__cause__)
        assert _column_type(connection, "blackroom_records", "market") == "blackroom_market"
        assert _all_managed_enum_types(connection) == {group.type_name for group in _all_enum_groups()}
