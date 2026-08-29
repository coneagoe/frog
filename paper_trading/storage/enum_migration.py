from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from paper_trading.domain.enums import (
    AccountStatus,
    CashEventType,
    CorporateActionProcessingStatus,
    CorporateActionType,
    ETFEligibilityStatus,
    FeePreset,
    LedgerRebuildStatus,
    Market,
    MatchingRunStatus,
    MigrationRepairReason,
    OrderSide,
    OrderStatus,
    PendingSettlementSource,
    PositionSource,
    RoundTripStatus,
    SnapshotPointType,
    SnapshotQualityStatus,
    SnapshotValuationQuality,
    TradeValidityGranularity,
    TradeValidityStatus,
)
from storage.enum_governance_adapter import EnumGovernanceAdapter
from storage.model import (
    DailyBarDiagnostic,
    ETFEligibility,
    PaperAccount,
    PaperAccountSnapshot,
    PaperCashLedger,
    PaperCorporateAction,
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
from storage.model.paper_trading import (
    ETF_ELIGIBILITY_SYMBOL_CHECK_NAME,
    ETF_ELIGIBILITY_SYMBOL_CHECK_SQL,
    PaperPendingSettlement,
    tb_name_paper_corporate_actions,
    tb_name_paper_etf_eligibility,
)


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


def _legacy_market_group(group: PaperTradingEnumGroup) -> PaperTradingEnumGroup:
    return PaperTradingEnumGroup(group.type_name, ("a_share", "hk_connect"), group.columns)


_MATCHING_INDEX_SQL = (
    "CREATE UNIQUE INDEX uq_matching_active_scope ON paper_matching_runs "
    "(trade_date, scope_key) WHERE status = 'running'"
)
_SNAPSHOT_INITIAL_INDEX_SQL = (
    "CREATE UNIQUE INDEX uq_paper_account_snapshots_account_initial "
    "ON paper_account_snapshots (account_id) WHERE point_type = 'initial'"
)
_SNAPSHOT_TRADING_INDEX_SQL = (
    "CREATE UNIQUE INDEX uq_paper_account_snapshots_account_trading "
    "ON paper_account_snapshots (account_id, trade_date) WHERE point_type = 'trading'"
)


def _index(name: str, table_name: str, column_name: str) -> tuple[str, str]:
    return name, f"CREATE INDEX {name} ON {table_name} ({column_name})"


_MATCHING_INDEX = ("uq_matching_active_scope", _MATCHING_INDEX_SQL)
_SNAPSHOT_INITIAL_INDEX = ("uq_paper_account_snapshots_account_initial", _SNAPSHOT_INITIAL_INDEX_SQL)
_SNAPSHOT_TRADING_INDEX = ("uq_paper_account_snapshots_account_trading", _SNAPSHOT_TRADING_INDEX_SQL)

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
        "paper_corporate_action_type",
        _labels(CorporateActionType),
        (
            _column(
                tb_name_paper_corporate_actions,
                "event_type",
                "VARCHAR(30)",
                indexes=(
                    _index("ix_paper_corporate_actions_event_type", tb_name_paper_corporate_actions, "event_type"),
                ),
            ),
        ),
    ),
    PaperTradingEnumGroup(
        "paper_corporate_action_processing_status",
        _labels(CorporateActionProcessingStatus),
        (
            _column(
                tb_name_paper_corporate_actions,
                "processing_status",
                "VARCHAR(30)",
                "'completed'",
                indexes=(
                    _index(
                        "ix_paper_corporate_actions_processing_status",
                        tb_name_paper_corporate_actions,
                        "processing_status",
                    ),
                ),
            ),
        ),
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
            _column(
                "paper_position_round_trips",
                "market",
                "VARCHAR(20)",
                "'a_share'",
                indexes=(_index("ix_paper_position_round_trips_market", "paper_position_round_trips", "market"),),
            ),
            _column(
                "daily_bar_diagnostics",
                "market",
                "VARCHAR(20)",
                "'a_share'",
                indexes=(_index("ix_daily_bar_diagnostics_market", "daily_bar_diagnostics", "market"),),
            ),
            _column(
                tb_name_paper_corporate_actions,
                "market",
                "VARCHAR(20)",
                "'a_share'",
                indexes=(_index("ix_paper_corporate_actions_market", tb_name_paper_corporate_actions, "market"),),
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
    PaperTradingEnumGroup(
        "paper_etf_eligibility_status",
        _labels(ETFEligibilityStatus),
        (
            _column(
                "paper_etf_eligibility",
                "status",
                "VARCHAR(20)",
                "'unknown'",
                indexes=(_index("ix_paper_etf_eligibility_status", "paper_etf_eligibility", "status"),),
            ),
        ),
    ),
    PaperTradingEnumGroup(
        "paper_snapshot_point_type",
        _labels(SnapshotPointType),
        (
            _column(
                "paper_account_snapshots",
                "point_type",
                "VARCHAR(20)",
                "'trading'",
                indexes=(_SNAPSHOT_INITIAL_INDEX, _SNAPSHOT_TRADING_INDEX),
            ),
        ),
    ),
    PaperTradingEnumGroup(
        "paper_snapshot_quality_status",
        _labels(SnapshotQualityStatus),
        (_column("paper_account_snapshots", "quality_status", "VARCHAR(20)", "'valid'"),),
    ),
    PaperTradingEnumGroup(
        "paper_snapshot_valuation_quality",
        _labels(SnapshotValuationQuality),
        (_column("paper_account_snapshots", "valuation_quality", "VARCHAR(20)", nullable=True),),
    ),
    PaperTradingEnumGroup(
        "paper_account_migration_repair_reason",
        _labels(MigrationRepairReason),
        (_column("paper_accounts", "migration_repair_reason", "VARCHAR(40)", nullable=True),),
    ),
)

_GOVERNED_TABLES = (
    PaperAccount.__table__,
    PaperCashLedger.__table__,
    PaperCorporateAction.__table__,
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
    ETFEligibility.__table__,
)
_OPTIONAL_GOVERNED_TABLES = (DailyBarDiagnostic.__table__,)
_MARKET_COLUMNS_REMOVED_ON_ROLLBACK = {"paper_position_round_trips", "daily_bar_diagnostics"}
_ETF_COMMISSION_RATE_COLUMN = PaperTradingEnumColumn(
    "paper_accounts", "etf_commission_rate", "NUMERIC(20, 8)", None, True
)
_OPERATIONAL_TABLES = (
    PaperAccountSnapshot.__table__,
    PaperValuationGap.__table__,
    ETFEligibility.__table__,
)
_ADDITIVE_GOVERNED_TABLES = frozenset({tb_name_paper_corporate_actions})
_ENUM_PREDICATE = re.compile(r"status\s*=\s*'running'\s*::\s*paper_matching_run_status", re.IGNORECASE)
_LEGACY_PREDICATE = re.compile(r"status.*=.*'running'", re.IGNORECASE)
_SNAPSHOT_ENUM_TYPES = frozenset({"paper_snapshot_point_type", "paper_snapshot_quality_status"})
_SNAPSHOT_STARTUP_ENUM_TYPES = _SNAPSHOT_ENUM_TYPES | {"paper_snapshot_valuation_quality"}
_SNAPSHOT_INITIAL_ENUM_PREDICATE = re.compile(
    r"point_type\s*=\s*'initial'\s*::\s*paper_snapshot_point_type", re.IGNORECASE
)
_SNAPSHOT_INITIAL_LEGACY_PREDICATE = re.compile(r"point_type.*=.*'initial'", re.IGNORECASE)
_SNAPSHOT_TRADING_ENUM_PREDICATE = re.compile(
    r"point_type\s*=\s*'trading'\s*::\s*paper_snapshot_point_type", re.IGNORECASE
)
_SNAPSHOT_TRADING_LEGACY_PREDICATE = re.compile(r"point_type.*=.*'trading'", re.IGNORECASE)
_VALUATION_DETAILS_COLUMN = PaperTradingEnumColumn("paper_account_snapshots", "valuation_details", "json", None, True)


def _is_addable_snapshot_column(group: PaperTradingEnumGroup, column: PaperTradingEnumColumn) -> bool:
    return group.type_name in _SNAPSHOT_ENUM_TYPES and column.table_name == "paper_account_snapshots"


def _is_addable_repair_reason_column(group: PaperTradingEnumGroup, column: PaperTradingEnumColumn) -> bool:
    return (
        group.type_name == "paper_account_migration_repair_reason"
        and column.table_name == "paper_accounts"
        and column.column_name == "migration_repair_reason"
    )


def _is_addable_valuation_quality_column(group: PaperTradingEnumGroup, column: PaperTradingEnumColumn) -> bool:
    return (
        group.type_name == "paper_snapshot_valuation_quality"
        and column.table_name == "paper_account_snapshots"
        and column.column_name == "valuation_quality"
    )


def _is_addable_missing_column(group: PaperTradingEnumGroup, column: PaperTradingEnumColumn) -> bool:
    return (
        (group.type_name == "paper_market" and column.column_name == "market")
        or _is_addable_snapshot_column(group, column)
        or _is_addable_repair_reason_column(group, column)
        or _is_addable_valuation_quality_column(group, column)
    )


def ensure_snapshot_series_enum_types(connection: Connection) -> None:
    """Create snapshot series enum types when they are missing."""
    for group in PAPER_TRADING_ENUM_GROUPS:
        if group.type_name in _SNAPSHOT_STARTUP_ENUM_TYPES:
            _create_type(connection, group)


def ensure_snapshot_valuation_metadata(connection: Connection) -> bool:
    """Add valuation metadata and the trading identity index after series backfill."""
    if connection.dialect.name != "postgresql" or not _table_exists(connection, "paper_account_snapshots"):
        return False
    ensure_snapshot_series_enum_types(connection)
    _reject_duplicate_trading_snapshots(connection)
    changed = _add_valuation_quality_column(connection)
    changed = _add_valuation_details_column(connection) or changed
    return _ensure_snapshot_trading_index(connection) or changed


def _has_pending_enum_column_changes(connection: Connection, groups: tuple[PaperTradingEnumGroup, ...]) -> bool:
    for group in groups:
        for column in group.columns:
            if not _table_exists(connection, column.table_name):
                continue
            facts = _column_facts(connection, column)
            if facts is None or not _column_has_type(connection, column, group.type_name):
                return True
    return False


def _result(
    groups: tuple[PaperTradingEnumGroup, ...] = PAPER_TRADING_ENUM_GROUPS,
    *,
    dry_run: bool = False,
    rollback: bool = False,
    converted: bool = False,
    rolled_back: bool = False,
) -> PaperTradingEnumMigrationResult:
    return PaperTradingEnumMigrationResult(
        dry_run=dry_run,
        rollback=rollback,
        converted=converted,
        rolled_back=rolled_back,
        groups=groups,
    )


def _adapter_preflight(connection: Connection, *, rollback: bool) -> None:
    groups = PAPER_TRADING_ENUM_GROUPS
    missing_tables = _preflight(connection, groups, rollback=rollback)
    if not rollback and _table_exists(connection, tb_name_paper_etf_eligibility):
        _validate_etf_eligibility_symbols(connection)
    operational_tables = {table.name for table in _OPERATIONAL_TABLES}
    required_tables = (
        {column.table_name for group in groups for column in group.columns}
        - operational_tables
        - _ADDITIVE_GOVERNED_TABLES
        - {table.name for table in _OPTIONAL_GOVERNED_TABLES}
    )
    required_missing = (
        missing_tables
        - operational_tables
        - _ADDITIVE_GOVERNED_TABLES
        - {table.name for table in _OPTIONAL_GOVERNED_TABLES}
    )
    if required_missing and required_missing != required_tables:
        raise PaperTradingEnumMigrationError(f"partially missing governed tables: {sorted(missing_tables)}")
    if rollback:
        _preflight_etf_commission_rate_rollback(connection)


def _adapter_apply(connection: Connection) -> bool:
    groups = PAPER_TRADING_ENUM_GROUPS
    _adapter_preflight(connection, rollback=False)
    missing_tables = _preflight(connection, groups, rollback=False)
    changed = bool(missing_tables) or _has_pending_enum_column_changes(connection, groups)
    changed = _ensure_etf_eligibility_symbol_check(connection) or changed
    if missing_tables:
        for group in groups:
            _create_type(connection, group)
        _create_missing_tables(
            connection,
            missing_tables - {table.name for table in _OPTIONAL_GOVERNED_TABLES},
            create_operational_tables=groups is PAPER_TRADING_ENUM_GROUPS,
        )
        _add_market_columns(connection)
        _add_snapshot_columns(connection)
        _add_repair_reason_column(connection)
        for group in groups:
            _alter_group(connection, group, rollback=False)
        ensure_snapshot_valuation_metadata(connection)
        _upgrade_market_qualified_keys(connection)
        _preflight(connection, groups, rollback=False)
        return True

    if changed:
        for group in groups:
            _create_type(connection, group)
        _add_market_columns(connection)
        _add_snapshot_columns(connection)
        _add_repair_reason_column(connection)
        for group in groups:
            _alter_group(connection, group, rollback=False)
    changed = ensure_snapshot_valuation_metadata(connection) or changed
    _upgrade_market_qualified_keys(connection)
    if groups is PAPER_TRADING_ENUM_GROUPS:
        _create_missing_tables(connection, set(), create_operational_tables=True)
    return changed


def _adapter_verify(connection: Connection, *, rollback: bool) -> None:
    if rollback and all(not _table_exists(connection, table.name) for table in _GOVERNED_TABLES):
        return
    _verify(connection, PAPER_TRADING_ENUM_GROUPS, rollback=rollback)
    _verify_etf_eligibility_symbol_check(connection, rollback=rollback)
    if not rollback and _has_snapshot_trading_identity_columns(connection):
        _validate_snapshot_trading_index(connection, "uq_paper_account_snapshots_account_trading", enum_typed=True)
    if rollback and _column_facts(connection, _ETF_COMMISSION_RATE_COLUMN) is not None:
        raise PaperTradingEnumMigrationError("etf_commission_rate was not removed during rollback")
    if not rollback:
        _verify_market_qualified_keys(connection)


def _adapter_rollback(connection: Connection) -> bool:
    _adapter_preflight(connection, rollback=True)
    if all(
        not _table_exists(connection, table.name) for table in _GOVERNED_TABLES
    ) and not _diagnostics_only_market_state(connection):
        return False
    _reject_legacy_key_collisions(connection)
    changed = _rollback(connection, PAPER_TRADING_ENUM_GROUPS)
    return _drop_etf_commission_rate_column(connection) or changed


def _adapter_audit(connection: Connection, *, rollback: bool):
    from storage.enum_governance import EnumGovernanceColumnAudit, EnumGovernanceDomainAudit, EnumGovernanceGroupAudit

    missing_tables = {
        table.name
        for table in _GOVERNED_TABLES + _OPTIONAL_GOVERNED_TABLES
        if not _table_exists(connection, table.name)
    }
    groups = []
    for group in PAPER_TRADING_ENUM_GROUPS:
        observed_labels = _enum_labels(connection, group.type_name)
        columns = []
        for column in group.columns:
            facts = None if column.table_name in missing_tables else _column_facts(connection, column)
            observed_type = None if facts is None else facts[0]
            observed_default = None if facts is None else _column_default(connection, column)
            observed_values = () if facts is None else _column_values(connection, column)
            enum_typed = observed_type == group.type_name
            expected_type = group.type_name
            expected_default = _expected_default(group, column, rollback=not enum_typed)
            indexes_ready = _indexes_ready(connection, column, enum_typed=rollback or enum_typed)
            valid_type = observed_type == expected_type or (
                not rollback and observed_type == _normalized_type(column.legacy_type_sql)
            )
            values_ready = not observed_values or all(
                value is None or value in group.labels for value in observed_values
            )
            missing_table = column.table_name in missing_tables
            ready = missing_table or (
                valid_type
                and facts is not None
                and facts[1] == column.nullable
                and values_ready
                and _defaults_match(observed_default, expected_default)
                and indexes_ready
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
                    tuple(name for name, _ in column.indexes),
                    indexes_ready,
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
    return EnumGovernanceDomainAudit(
        "paper_trading", tuple(groups), (), tuple(sorted(missing_tables)), all(group.ready for group in groups)
    )


PAPER_TRADING_ENUM_ADAPTER = EnumGovernanceAdapter(
    name="paper_trading",
    preflight=_adapter_preflight,
    apply=_adapter_apply,
    verify=_adapter_verify,
    rollback=_adapter_rollback,
    result=_result,
    audit=_adapter_audit,
)


def migrate_paper_trading_enums(
    connection: Connection, *, dry_run: bool = False, rollback: bool = False
) -> PaperTradingEnumMigrationResult:
    """Compatibility wrapper for the legacy Paper Trading enum migration CLI."""

    if connection.dialect.name != "postgresql":
        return _result(dry_run=dry_run, rollback=rollback)

    PAPER_TRADING_ENUM_ADAPTER.preflight(connection, rollback=rollback)
    if dry_run:
        return _result(dry_run=True, rollback=rollback)
    if rollback:
        if all(
            not _table_exists(connection, table.name) for table in _GOVERNED_TABLES
        ) and not _diagnostics_only_market_state(connection):
            return _result(rollback=True)
        rolled_back = PAPER_TRADING_ENUM_ADAPTER.rollback(connection)
        PAPER_TRADING_ENUM_ADAPTER.verify(connection, rollback=True)
        return _result(rollback=True, rolled_back=rolled_back)

    converted = PAPER_TRADING_ENUM_ADAPTER.apply(connection)
    PAPER_TRADING_ENUM_ADAPTER.verify(connection, rollback=False)
    return _result(converted=converted)


def _migrate(
    connection: Connection,
    groups: tuple[PaperTradingEnumGroup, ...],
    *,
    dry_run: bool = False,
    rollback: bool = False,
    dry_run_reports_conversion: bool = False,
) -> PaperTradingEnumMigrationResult:
    """Run the legacy scoped migration used by matching-status bootstrap."""

    if connection.dialect.name != "postgresql":
        return _result(groups, dry_run=dry_run, rollback=rollback)

    missing_tables = _preflight(connection, groups, rollback=rollback)
    if missing_tables and len(missing_tables) != len(
        {column.table_name for group in groups for column in group.columns}
    ):
        raise PaperTradingEnumMigrationError(f"partially missing governed tables: {sorted(missing_tables)}")
    changed = any(
        not _column_has_type(connection, column, group.type_name) for group in groups for column in group.columns
    )
    if dry_run:
        return _result(
            groups, dry_run=True, rollback=rollback, converted=changed if dry_run_reports_conversion else False
        )
    if missing_tables:
        if rollback:
            return _result(groups, rollback=True)
        for group in groups:
            _create_type(connection, group)
        _create_missing_tables(connection, missing_tables)
        _preflight(connection, groups, rollback=False)
        return _result(groups, converted=True)
    if rollback:
        rolled_back = _rollback(connection, groups)
        _verify(connection, groups, rollback=True)
        return _result(groups, rollback=True, rolled_back=rolled_back)

    if changed:
        for group in groups:
            _create_type(connection, group)
            _alter_group(connection, group, rollback=False)
    _verify(connection, groups, rollback=False)
    return _result(groups, converted=changed)


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
                if not rollback and _is_addable_missing_column(group, column):
                    continue
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
            if rollback and group.type_name == "paper_market":
                _validate_values(connection, _legacy_market_group(group), column)
            enum_typed = type_name == group.type_name
            _validate_indexes(connection, column, enum_typed=rollback or enum_typed)
            _validate_default(connection, group, column, rollback=not enum_typed)
        if rollback and labels:
            dependencies = _type_dependencies(connection, group)
            if dependencies:
                raise PaperTradingEnumMigrationError(f"{group.type_name}: dependencies remain: {dependencies}")
    return missing_tables


def _create_missing_tables(
    connection: Connection, missing_tables: set[str], *, create_operational_tables: bool = False
) -> None:
    tables = [
        table
        for table in _GOVERNED_TABLES
        if table is not DailyBarDiagnostic.__table__
        and (
            table.name in missing_tables
            or (
                create_operational_tables and table in _OPERATIONAL_TABLES and not _table_exists(connection, table.name)
            )
        )
    ]
    if tables:
        # Metadata creates the mapped native types and respects foreign-key order.
        tables[0].metadata.create_all(connection, tables=tables, checkfirst=True)


def _create_type(connection: Connection, group: PaperTradingEnumGroup) -> None:
    if _enum_labels(connection, group.type_name):
        return
    labels = ", ".join(f"'{label}'" for label in group.labels)
    connection.execute(text(f"CREATE TYPE {group.type_name} AS ENUM ({labels})"))


def ensure_paper_market_type(connection: Connection) -> None:
    """Create or validate the paper-owned market type for shared tables."""
    group = next(group for group in PAPER_TRADING_ENUM_GROUPS if group.type_name == "paper_market")
    labels = _enum_labels(connection, group.type_name)
    if labels and labels != group.labels:
        raise PaperTradingEnumMigrationError(f"paper_market: unexpected enum labels {labels}")
    _create_type(connection, group)


def preflight_diagnostics_only_market_rollback(connection: Connection) -> bool:
    """Validate paper-owned market cleanup for storage-only diagnostics bootstrap."""
    if not _diagnostics_only_market_state(connection):
        return False
    PAPER_TRADING_ENUM_ADAPTER.preflight(connection, rollback=True)
    return True


def rollback_diagnostics_only_market(connection: Connection) -> bool:
    """Remove paper-owned market state when diagnostics is the only paper target."""
    if not _diagnostics_only_market_state(connection):
        return False
    rolled_back = PAPER_TRADING_ENUM_ADAPTER.rollback(connection)
    PAPER_TRADING_ENUM_ADAPTER.verify(connection, rollback=True)
    return rolled_back


def _create_column_indexes(connection: Connection, column: PaperTradingEnumColumn) -> None:
    for index_name, index_sql in column.indexes:
        if index_name == "uq_paper_account_snapshots_account_trading" and not _has_snapshot_trading_identity_columns(
            connection
        ):
            continue
        connection.execute(text(index_sql))


def _alter_group(connection: Connection, group: PaperTradingEnumGroup, *, rollback: bool) -> None:
    for column in group.columns:
        if not _table_exists(connection, column.table_name):
            continue
        if not rollback and _column_has_type(connection, column, group.type_name):
            continue
        if _column_facts(connection, column) is None:
            continue
        for index_name, _ in column.indexes:
            connection.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
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
        if not rollback and column.column_name == "point_type":
            _reject_duplicate_trading_snapshots(connection)
        _create_column_indexes(connection, column)


def _rollback(connection: Connection, groups: tuple[PaperTradingEnumGroup, ...]) -> bool:
    changed = False
    for group in groups:
        if any(_column_has_type(connection, column, group.type_name) for column in group.columns):
            _alter_group(connection, group, rollback=True)
            changed = True
    _restore_legacy_market_qualified_keys(connection)
    if any(group.type_name == "paper_etf_eligibility_status" for group in groups):
        changed = _drop_etf_eligibility_symbol_check(connection) or changed
    _verify(connection, groups, rollback=True)
    if any(group.type_name == "paper_etf_eligibility_status" for group in groups):
        _verify_etf_eligibility_symbol_check(connection, rollback=True)
    for group in groups:
        if _enum_labels(connection, group.type_name):
            connection.execute(text(f"DROP TYPE {group.type_name}"))
    return changed


def _preflight_etf_commission_rate_rollback(connection: Connection) -> None:
    facts = _column_facts(connection, _ETF_COMMISSION_RATE_COLUMN)
    if facts is None:
        return
    expected_type = _ETF_COMMISSION_RATE_COLUMN.legacy_type_sql.lower().replace(" ", "")
    if facts[0].replace(" ", "") != expected_type or not facts[1]:
        raise PaperTradingEnumMigrationError("incompatible paper_accounts.etf_commission_rate")
    if _column_default(connection, _ETF_COMMISSION_RATE_COLUMN) is not None:
        raise PaperTradingEnumMigrationError("unexpected default for paper_accounts.etf_commission_rate")
    dependencies = _column_dependencies(connection, _ETF_COMMISSION_RATE_COLUMN)
    if dependencies:
        raise PaperTradingEnumMigrationError(f"paper_accounts.etf_commission_rate: dependencies remain: {dependencies}")


def _drop_etf_commission_rate_column(connection: Connection) -> bool:
    if _column_facts(connection, _ETF_COMMISSION_RATE_COLUMN) is None:
        return False
    connection.execute(text("ALTER TABLE paper_accounts DROP COLUMN etf_commission_rate"))
    return True


def _column_dependencies(connection: Connection, column: PaperTradingEnumColumn) -> tuple[str, ...]:
    return tuple(
        connection.execute(
            text(
                "SELECT DISTINCT pg_describe_object(d.classid, d.objid, d.objsubid) "
                "FROM pg_depend d "
                "JOIN pg_class c ON c.oid = d.refobjid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.refobjsubid "
                "WHERE n.nspname = current_schema() AND c.relname = :table_name "
                "AND a.attname = :column_name AND d.deptype NOT IN ('i', 'a') ORDER BY 1"
            ),
            {"table_name": column.table_name, "column_name": column.column_name},
        ).scalars()
    )


def _verify(connection: Connection, groups: tuple[PaperTradingEnumGroup, ...], *, rollback: bool) -> None:
    for group in groups:
        if not rollback and _enum_labels(connection, group.type_name) != group.labels:
            raise PaperTradingEnumMigrationError(f"{group.type_name}: labels were not preserved")
        for column in group.columns:
            if not _table_exists(connection, column.table_name):
                continue
            expected = _normalized_type(column.legacy_type_sql) if rollback else group.type_name
            facts = _column_facts(connection, column)
            if (
                rollback
                and facts is None
                and group.type_name == "paper_market"
                and column.table_name in _MARKET_COLUMNS_REMOVED_ON_ROLLBACK
            ):
                continue
            if facts is None or facts[0] != expected:
                raise PaperTradingEnumMigrationError(
                    f"{group.type_name}: verification failed for {column.table_name}.{column.column_name}"
                )
            _validate_default(connection, group, column, rollback=rollback)
            _validate_indexes(connection, column, enum_typed=not rollback)


def _validate_etf_eligibility_symbols(connection: Connection) -> None:
    invalid = connection.execute(
        text(
            f"SELECT symbol FROM {tb_name_paper_etf_eligibility} WHERE NOT ({ETF_ELIGIBILITY_SYMBOL_CHECK_SQL}) LIMIT 1"
        )
    ).scalar_one_or_none()
    if invalid is not None:
        raise PaperTradingEnumMigrationError(f"invalid ETF eligibility symbols: {invalid}")


def _etf_eligibility_symbol_check_ready(connection: Connection) -> bool:
    definition = connection.execute(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = CAST(:table_name AS regclass) AND conname = :constraint_name AND contype = 'c'"
        ),
        {"table_name": tb_name_paper_etf_eligibility, "constraint_name": ETF_ELIGIBILITY_SYMBOL_CHECK_NAME},
    ).scalar_one_or_none()
    if definition is None:
        return False
    normalized_definition = (
        _normalize_expression(str(definition).removeprefix("CHECK"))
        .replace("::text", "")
        .replace("(", "")
        .replace(")", "")
    )
    normalized_expected = _normalize_expression(ETF_ELIGIBILITY_SYMBOL_CHECK_SQL).replace("(", "").replace(")", "")
    return normalized_definition == normalized_expected


def _ensure_etf_eligibility_symbol_check(connection: Connection) -> bool:
    if not _table_exists(connection, tb_name_paper_etf_eligibility):
        return False
    if _etf_eligibility_symbol_check_ready(connection):
        return False
    if _constraint_exists(connection, tb_name_paper_etf_eligibility, ETF_ELIGIBILITY_SYMBOL_CHECK_NAME):
        raise PaperTradingEnumMigrationError("invalid ETF eligibility symbol check constraint")
    connection.execute(
        text(
            f"ALTER TABLE {tb_name_paper_etf_eligibility} ADD CONSTRAINT {ETF_ELIGIBILITY_SYMBOL_CHECK_NAME} "
            f"CHECK ({ETF_ELIGIBILITY_SYMBOL_CHECK_SQL})"
        )
    )
    return True


def _drop_etf_eligibility_symbol_check(connection: Connection) -> bool:
    if not _table_exists(connection, tb_name_paper_etf_eligibility):
        return False
    if not _constraint_exists(connection, tb_name_paper_etf_eligibility, ETF_ELIGIBILITY_SYMBOL_CHECK_NAME):
        return False
    connection.execute(
        text(f"ALTER TABLE {tb_name_paper_etf_eligibility} DROP CONSTRAINT {ETF_ELIGIBILITY_SYMBOL_CHECK_NAME}")
    )
    return True


def _verify_etf_eligibility_symbol_check(connection: Connection, *, rollback: bool) -> None:
    if not _table_exists(connection, tb_name_paper_etf_eligibility):
        return
    ready = _etf_eligibility_symbol_check_ready(connection)
    if ready != (not rollback):
        raise PaperTradingEnumMigrationError("invalid ETF eligibility symbol check constraint")


def _add_market_columns(connection: Connection) -> None:
    market_group = next(group for group in PAPER_TRADING_ENUM_GROUPS if group.type_name == "paper_market")
    for column in market_group.columns:
        if _table_exists(connection, column.table_name) and _column_facts(connection, column) is None:
            connection.execute(
                text(
                    f"ALTER TABLE {column.table_name} ADD COLUMN {column.column_name} VARCHAR(20) NOT NULL "
                    "DEFAULT 'a_share'::character varying"
                )
            )
            for _, index_sql in column.indexes:
                connection.execute(text(index_sql))


def _add_snapshot_columns(connection: Connection) -> None:
    for group in PAPER_TRADING_ENUM_GROUPS:
        for column in group.columns:
            if not _is_addable_snapshot_column(group, column):
                continue
            if not _table_exists(connection, column.table_name) or _column_facts(connection, column) is not None:
                continue
            default_sql = column.default_sql or "'trading'::character varying"
            connection.execute(
                text(
                    f"ALTER TABLE {column.table_name} ADD COLUMN {column.column_name} VARCHAR(20) NOT NULL "
                    f"DEFAULT {default_sql}"
                )
            )
            if column.column_name == "point_type":
                _reject_duplicate_trading_snapshots(connection)
            _create_column_indexes(connection, column)


def _add_repair_reason_column(connection: Connection) -> None:
    group = next(
        group for group in PAPER_TRADING_ENUM_GROUPS if group.type_name == "paper_account_migration_repair_reason"
    )
    for column in group.columns:
        if not _table_exists(connection, column.table_name) or _column_facts(connection, column) is not None:
            continue
        connection.execute(
            text(f"ALTER TABLE {column.table_name} ADD COLUMN {column.column_name} {column.legacy_type_sql}")
        )


def _add_valuation_quality_column(connection: Connection) -> bool:
    group = next(group for group in PAPER_TRADING_ENUM_GROUPS if group.type_name == "paper_snapshot_valuation_quality")
    changed = False
    for column in group.columns:
        if not _table_exists(connection, column.table_name) or _column_facts(connection, column) is not None:
            continue
        connection.execute(text(f"ALTER TABLE {column.table_name} ADD COLUMN {column.column_name} {group.type_name}"))
        changed = True
    return changed


def _add_valuation_details_column(connection: Connection) -> bool:
    if not _table_exists(connection, _VALUATION_DETAILS_COLUMN.table_name):
        return False
    if _column_facts(connection, _VALUATION_DETAILS_COLUMN) is not None:
        return False
    connection.execute(
        text(
            f"ALTER TABLE {_VALUATION_DETAILS_COLUMN.table_name} "
            f"ADD COLUMN {_VALUATION_DETAILS_COLUMN.column_name} JSON"
        )
    )
    return True


def _has_snapshot_trading_identity_columns(connection: Connection) -> bool:
    return (
        _column_facts(connection, _column("paper_account_snapshots", "point_type", "VARCHAR(20)")) is not None
        and _column_facts(connection, _column("paper_account_snapshots", "trade_date", "DATE")) is not None
    )


def _reject_duplicate_trading_snapshots(connection: Connection) -> None:
    if not _has_snapshot_trading_identity_columns(connection):
        return
    duplicates = connection.execute(
        text(
            """
            SELECT account_id, trade_date
            FROM paper_account_snapshots
            WHERE point_type = 'trading'
            GROUP BY account_id, trade_date
            HAVING COUNT(*) > 1
            """
        )
    ).all()
    if duplicates:
        raise RuntimeError("duplicate trading snapshots")


def _ensure_snapshot_trading_index(connection: Connection) -> bool:
    if not _has_snapshot_trading_identity_columns(connection):
        return False
    if _partial_unique_index_facts(connection, "uq_paper_account_snapshots_account_trading") is not None:
        return False
    connection.execute(text(_SNAPSHOT_TRADING_INDEX_SQL))
    return True


def _diagnostics_only_market_state(connection: Connection) -> bool:
    return (
        all(not _table_exists(connection, table.name) for table in _GOVERNED_TABLES)
        and _table_exists(connection, "daily_bar_diagnostics")
        and _column_has_type(
            connection,
            PaperTradingEnumColumn("daily_bar_diagnostics", "market", "VARCHAR(20)", None, False),
            "paper_market",
        )
    )


def _replace_unique_constraint(connection: Connection, table_name: str, old_name: str, columns: str) -> None:
    if _constraint_exists(connection, table_name, old_name):
        connection.execute(text(f"ALTER TABLE {table_name} DROP CONSTRAINT {old_name}"))
    connection.execute(text(f"ALTER TABLE {table_name} ADD CONSTRAINT {old_name} UNIQUE ({columns})"))


_MARKET_QUALIFIED_KEY_COLUMNS = {
    "paper_positions": ("account_id", "market", "symbol"),
    "daily_bar_diagnostics": ("business_date", "market", "stock_id", "adjust"),
}


def _has_market_qualified_key_columns(connection: Connection, table_name: str) -> bool:
    return _table_exists(connection, table_name) and all(
        _column_facts(connection, PaperTradingEnumColumn(table_name, column_name, "", None, False)) is not None
        for column_name in _MARKET_QUALIFIED_KEY_COLUMNS[table_name]
    )


def _upgrade_market_qualified_keys(connection: Connection) -> None:
    if _has_market_qualified_key_columns(connection, "paper_positions") and not _constraint_exists(
        connection, "paper_positions", "uq_paper_positions_account_market_symbol"
    ):
        if _constraint_exists(connection, "paper_positions", "uq_paper_positions_account_symbol"):
            connection.execute(text("ALTER TABLE paper_positions DROP CONSTRAINT uq_paper_positions_account_symbol"))
        connection.execute(
            text(
                "ALTER TABLE paper_positions ADD CONSTRAINT uq_paper_positions_account_market_symbol "
                "UNIQUE (account_id, market, symbol)"
            )
        )
    if _has_market_qualified_key_columns(connection, "daily_bar_diagnostics") and _constraint_columns(
        connection, "daily_bar_diagnostics", "uq_daily_bar_diagnostics_business_key"
    ) != ("business_date", "market", "stock_id", "adjust"):
        _replace_unique_constraint(
            connection,
            "daily_bar_diagnostics",
            "uq_daily_bar_diagnostics_business_key",
            "business_date, market, stock_id, adjust",
        )


def _reject_legacy_key_collisions(connection: Connection) -> None:
    checks = (
        ("paper_positions", "account_id, symbol", "paper positions"),
        ("daily_bar_diagnostics", "business_date, stock_id, adjust", "daily bar diagnostics"),
    )
    for table_name, columns, description in checks:
        if not _has_market_qualified_key_columns(connection, table_name):
            continue
        duplicate = connection.execute(
            text(f"SELECT 1 FROM {table_name} GROUP BY {columns} HAVING count(*) > 1 LIMIT 1")
        ).scalar_one_or_none()
        if duplicate is not None:
            raise PaperTradingEnumMigrationError(f"legacy uniqueness collision in {description}")


def _restore_legacy_market_qualified_keys(connection: Connection) -> None:
    if _has_market_qualified_key_columns(connection, "paper_positions"):
        if _constraint_exists(connection, "paper_positions", "uq_paper_positions_account_market_symbol"):
            connection.execute(
                text("ALTER TABLE paper_positions DROP CONSTRAINT uq_paper_positions_account_market_symbol")
            )
            connection.execute(
                text(
                    "ALTER TABLE paper_positions ADD CONSTRAINT uq_paper_positions_account_symbol "
                    "UNIQUE (account_id, symbol)"
                )
            )
    if _has_market_qualified_key_columns(connection, "daily_bar_diagnostics"):
        connection.execute(
            text("ALTER TABLE daily_bar_diagnostics DROP CONSTRAINT uq_daily_bar_diagnostics_business_key")
        )
        connection.execute(
            text(
                "ALTER TABLE daily_bar_diagnostics ADD CONSTRAINT uq_daily_bar_diagnostics_business_key "
                "UNIQUE (business_date, stock_id, adjust)"
            )
        )
    if (
        _column_facts(connection, PaperTradingEnumColumn("daily_bar_diagnostics", "market", "VARCHAR(20)", None, False))
        is not None
    ):
        connection.execute(text("ALTER TABLE daily_bar_diagnostics DROP COLUMN market"))
    if _table_exists(connection, "paper_position_round_trips"):
        connection.execute(text("ALTER TABLE paper_position_round_trips DROP COLUMN market"))


def _constraint_exists(connection: Connection, table_name: str, constraint_name: str) -> bool:
    return _constraint_columns(connection, table_name, constraint_name) is not None


def _constraint_columns(connection: Connection, table_name: str, constraint_name: str) -> tuple[str, ...] | None:
    columns = connection.execute(
        text(
            "SELECT array_agg(a.attname ORDER BY key.ordinality) FROM pg_constraint con "
            "JOIN unnest(con.conkey) WITH ORDINALITY AS key(attnum, ordinality) ON true "
            "JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = key.attnum "
            "WHERE con.conrelid = CAST(:table_name AS regclass) AND con.conname = :constraint_name GROUP BY con.oid"
        ),
        {"table_name": table_name, "constraint_name": constraint_name},
    ).scalar_one_or_none()
    return None if columns is None else tuple(columns)


def _verify_market_qualified_keys(connection: Connection) -> None:
    expected = {
        "paper_positions": ("uq_paper_positions_account_market_symbol", ("account_id", "market", "symbol")),
        "daily_bar_diagnostics": (
            "uq_daily_bar_diagnostics_business_key",
            ("business_date", "market", "stock_id", "adjust"),
        ),
    }
    for table_name, (constraint_name, columns) in expected.items():
        if not _has_market_qualified_key_columns(connection, table_name):
            continue
        if _constraint_columns(connection, table_name, constraint_name) != columns:
            raise PaperTradingEnumMigrationError(f"missing or invalid market-qualified key {constraint_name}")


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


def _column_values(connection: Connection, column: PaperTradingEnumColumn) -> tuple[str | None, ...]:
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


def _indexes_ready(connection: Connection, column: PaperTradingEnumColumn, *, enum_typed: bool) -> bool:
    try:
        _validate_indexes(connection, column, enum_typed=enum_typed)
    except PaperTradingEnumMigrationError:
        return False
    return True


def _partial_unique_index_facts(connection: Connection, index_name: str) -> tuple[bool, tuple[str, ...], str] | None:
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
    if facts is None:
        return None
    return bool(facts[0]), tuple(facts[1]), facts[2] or ""


def _validate_partial_unique_index(
    connection: Connection,
    index_name: str,
    *,
    columns: tuple[str, ...],
    pattern: re.Pattern[str],
    error: str,
) -> None:
    facts = _partial_unique_index_facts(connection, index_name)
    if facts is None or not facts[0] or facts[1] != columns or not pattern.search(facts[2]):
        raise PaperTradingEnumMigrationError(error)


def _validate_matching_index(connection: Connection, index_name: str, *, enum_typed: bool) -> None:
    _validate_partial_unique_index(
        connection,
        index_name,
        columns=("trade_date", "scope_key"),
        pattern=_ENUM_PREDICATE if enum_typed else _LEGACY_PREDICATE,
        error="paper_matching_run_status: active matching-run partial index is missing or invalid",
    )


def _validate_snapshot_initial_index(connection: Connection, index_name: str, *, enum_typed: bool) -> None:
    _validate_partial_unique_index(
        connection,
        index_name,
        columns=("account_id",),
        pattern=_SNAPSHOT_INITIAL_ENUM_PREDICATE if enum_typed else _SNAPSHOT_INITIAL_LEGACY_PREDICATE,
        error="paper_snapshot_point_type: initial snapshot partial unique index is missing or invalid",
    )


def _validate_snapshot_trading_index(connection: Connection, index_name: str, *, enum_typed: bool) -> None:
    _validate_partial_unique_index(
        connection,
        index_name,
        columns=("account_id", "trade_date"),
        pattern=_SNAPSHOT_TRADING_ENUM_PREDICATE if enum_typed else _SNAPSHOT_TRADING_LEGACY_PREDICATE,
        error="paper_snapshot_point_type: trading snapshot partial unique index is missing or invalid",
    )


def _validate_indexes(connection: Connection, column: PaperTradingEnumColumn, *, enum_typed: bool) -> None:
    for index_name, index_sql in column.indexes:
        if index_name == "uq_matching_active_scope":
            _validate_matching_index(connection, index_name, enum_typed=enum_typed)
            continue
        if index_name == "uq_paper_account_snapshots_account_initial":
            _validate_snapshot_initial_index(connection, index_name, enum_typed=enum_typed)
            continue
        if index_name == "uq_paper_account_snapshots_account_trading":
            if _partial_unique_index_facts(connection, index_name) is None:
                continue
            _validate_snapshot_trading_index(connection, index_name, enum_typed=enum_typed)
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


def _type_dependencies(connection: Connection, group: PaperTradingEnumGroup) -> tuple[str, ...]:
    managed_columns = ", ".join(f"(:table_name_{index}, :column_name_{index})" for index, _ in enumerate(group.columns))
    declared_indexes = tuple(
        (column.table_name, index_name) for column in group.columns for index_name, _ in column.indexes
    )
    managed_indexes = (
        ", ".join(f"(:index_table_name_{index}, :index_name_{index})" for index, _ in enumerate(declared_indexes))
        or "(NULL, NULL)"
    )
    parameters = {"type_name": group.type_name}
    parameters.update(
        {
            f"{field}_{index}": getattr(column, field)
            for index, column in enumerate(group.columns)
            for field in ("table_name", "column_name")
        }
    )
    parameters.update(
        {
            f"index_{field}_{index}": value
            for index, declared_index in enumerate(declared_indexes)
            for field, value in zip(("table_name", "name"), declared_index, strict=True)
        }
    )
    return tuple(
        connection.execute(
            text(
                "WITH managed_columns(table_name, column_name) AS "
                f"(VALUES {managed_columns}) "
                ", managed_indexes(table_name, index_name) AS "
                f"(VALUES {managed_indexes}) "
                "SELECT DISTINCT COALESCE('view ' || v.relname, pg_describe_object(d.classid, d.objid, d.objsubid)) "
                "FROM pg_depend d JOIN pg_type t ON t.oid = d.refobjid "
                "LEFT JOIN pg_class vc ON vc.oid = d.objid AND vc.relkind = 'v' "
                "LEFT JOIN pg_rewrite r ON d.classid = 'pg_rewrite'::regclass AND r.oid = d.objid "
                "LEFT JOIN pg_class v ON v.oid = COALESCE(vc.oid, r.ev_class) "
                "WHERE d.refclassid = 'pg_type'::regclass AND t.typnamespace = current_schema()::regnamespace "
                "AND t.typname = :type_name AND d.deptype NOT IN ('i', 'a') "
                "AND NOT EXISTS ("
                "SELECT 1 FROM managed_columns m "
                "JOIN pg_class c ON c.relname = m.table_name "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = m.column_name "
                "LEFT JOIN pg_attrdef ad ON ad.adrelid = c.oid AND ad.adnum = a.attnum "
                "WHERE n.nspname = current_schema() AND ("
                "(d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.objsubid = a.attnum) "
                "OR (d.classid = 'pg_attrdef'::regclass AND d.objid = ad.oid)"
                ")"
                ") "
                "AND NOT EXISTS ("
                "SELECT 1 FROM managed_indexes mi "
                "JOIN pg_class tc ON tc.relname = mi.table_name "
                "JOIN pg_namespace tn ON tn.oid = tc.relnamespace "
                "JOIN pg_class ic ON ic.relname = mi.index_name "
                "JOIN pg_namespace inn ON inn.oid = ic.relnamespace "
                "JOIN pg_index i ON i.indrelid = tc.oid AND i.indexrelid = ic.oid "
                "WHERE tn.nspname = current_schema() AND inn.nspname = current_schema() "
                "AND d.classid = 'pg_class'::regclass AND d.objid = ic.oid"
                ") "
                "ORDER BY 1"
            ),
            parameters,
        ).scalars()
    )
