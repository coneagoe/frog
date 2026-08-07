from __future__ import annotations

from sqlalchemy import create_engine

from paper_trading.storage.enum_migration import migrate_paper_trading_enums


def test_non_postgresql_migration_is_a_noop_with_the_complete_catalog():
    engine = create_engine("sqlite://")

    with engine.begin() as connection:
        result = migrate_paper_trading_enums(connection, dry_run=True)

    assert result.dry_run is True
    assert result.converted is False
    assert result.rolled_back is False
    assert {group.type_name for group in result.groups} == {
        "paper_account_status",
        "paper_fee_preset",
        "paper_cash_event_type",
        "paper_order_side",
        "paper_order_status",
        "paper_trade_validity_status",
        "paper_market",
        "paper_position_source",
        "paper_round_trip_status",
        "paper_trade_validity_granularity",
        "paper_pending_settlement_source",
        "paper_ledger_rebuild_status",
        "paper_matching_run_status",
    }
