from datetime import date, datetime, timedelta, timezone, tzinfo
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy import String, create_engine
from sqlalchemy import cast as sa_cast
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from paper_trading.domain.enums import (
    AccountStatus,
    CashEventType,
    CorporateActionType,
    ETFEligibilityStatus,
    LedgerRebuildStatus,
    Market,
    MatchingRunStatus,
    NavReplayEventType,
    OrderSide,
    OrderStatus,
    SnapshotPointType,
    SnapshotQualityStatus,
)
from paper_trading.storage.models import (
    PaperCashLedger,
    PaperPendingSettlement,
    PaperTradeValidityCheck,
    PaperValuationGap,
)
from paper_trading.storage.repository import PaperTradingRepository
from storage.domain_enums import (
    DailyBarDiagnosticAdjust,
    DailyBarDiagnosticClassification,
    ProviderOutcomeStatus,
    validate_provider_outcomes,
)
from storage.model.base import Base
from storage.model.etf_basic import ETFBasic
from storage.model.paper_trading import DailyBarDiagnostic


def test_daily_bar_diagnostic_scalar_columns_use_value_enums():
    assert DailyBarDiagnostic.__table__.c.adjust.type.name == "daily_bar_diagnostic_adjust"
    assert DailyBarDiagnostic.__table__.c.classification.type.name == "daily_bar_diagnostic_classification"
    assert tuple(member.value for member in DailyBarDiagnosticAdjust) == ("bfq", "qfq", "hfq", "raw")
    assert tuple(member.value for member in DailyBarDiagnosticClassification) == (
        "missing_market_data",
        "missing_exact_date",
        "provider_error",
        "downloaded",
        "resolved",
    )
    assert DailyBarDiagnostic.__table__.c.adjust.type.enums == [member.value for member in DailyBarDiagnosticAdjust]
    assert DailyBarDiagnostic.__table__.c.classification.type.enums == [
        member.value for member in DailyBarDiagnosticClassification
    ]


def test_etf_eligibility_repository_upserts_gets_and_filters_status(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    refreshed_at = datetime(2026, 8, 10, tzinfo=timezone.utc)
    repo.upsert_etf_eligibility("510300", "CSI 300 ETF", "SH", "L", refreshed_at)
    repo.upsert_etf_eligibility(
        "159915", "Chinext ETF", "SZ", "L", refreshed_at, status=ETFEligibilityStatus.MONEY_MARKET
    )

    classified = repo.classify_etf_eligibility("510300", ETFEligibilityStatus.SUPPORTED, "operator")

    assert repo.get_etf_eligibility("510300") is classified
    assert [row.symbol for row in repo.list_etf_eligibility()] == ["159915", "510300"]
    assert [row.symbol for row in repo.list_etf_eligibility("supported")] == ["510300"]


@pytest.mark.parametrize("symbol", ["510300.SH", "51030", "5103000", "5103A0"])
def test_etf_eligibility_repository_rejects_non_bare_symbols(sqlite_session, symbol):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)

    with pytest.raises(ValueError, match="bare six-digit"):
        repo.get_etf_eligibility(symbol)
    with pytest.raises(ValueError, match="bare six-digit"):
        repo.upsert_etf_eligibility(symbol, "ETF", "SH", "L", datetime(2026, 8, 10, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="bare six-digit"):
        repo.classify_etf_eligibility(symbol, ETFEligibilityStatus.SUPPORTED, "operator")


def test_etf_eligibility_repository_rejects_blank_reviewer(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    repo.upsert_etf_eligibility("510300", "CSI 300 ETF", "SH", "L", datetime(2026, 8, 10, tzinfo=timezone.utc))

    with pytest.raises(ValueError, match="reviewed_by"):
        repo.classify_etf_eligibility("510300", ETFEligibilityStatus.SUPPORTED, " \t")


def test_validate_provider_outcomes_normalizes_valid_values():
    outcomes = [{"provider": "tushare", "status": "empty", "detail": None}]

    normalized = validate_provider_outcomes(outcomes)

    assert normalized == outcomes
    assert normalized is not outcomes
    assert normalized[0] is not outcomes[0]
    assert tuple(member.value for member in ProviderOutcomeStatus) == ("downloaded", "empty", "error")


@pytest.mark.parametrize("value", [None, {}, ["empty"], [{"provider": "tushare"}], [{"status": "partial"}]])
def test_validate_provider_outcomes_rejects_invalid_contract(value):
    with pytest.raises(ValueError, match="provider_outcomes"):
        validate_provider_outcomes(value)


def test_create_account_initializes_nav_share_state(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)

    account = repo.create_account("nav-demo", Decimal("100000.00"))
    ledger = repo.list_cash_ledger(account.id)

    assert account.net_asset_value == Decimal("1.000000")
    assert account.share_count == Decimal("100000.000000")
    assert account.cumulative_deposit == Decimal("100000.0000")
    assert account.cumulative_withdrawal == Decimal("0.0000")
    assert ledger[0].event_type == "deposit"
    assert ledger[0].net_asset_value == Decimal("1.000000")
    assert ledger[0].share_delta == Decimal("100000.000000")


def test_create_account_persists_etf_commission_rate(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)

    account = repo.create_account("etf-fees", Decimal("100000"), etf_commission_rate=Decimal("0.00008"))

    assert account.etf_commission_rate == Decimal("0.00008000")


def _trading_snapshot_values(account_id: int, trade_date: date, event_at: datetime) -> dict[str, Any]:
    return {
        "account_id": account_id,
        "trade_date": trade_date,
        "event_at": event_at,
        "point_type": SnapshotPointType.TRADING.value,
        "quality_status": SnapshotQualityStatus.VALID.value,
        "cash_available": Decimal("99000.0000"),
        "cash_frozen": Decimal("0.0000"),
        "market_value": Decimal("1000.0000"),
        "total_assets": Decimal("100000.0000"),
        "realized_pnl": Decimal("0.0000"),
        "unrealized_pnl": Decimal("0.0000"),
        "position_count": 1,
        "order_count": 1,
        "trade_count": 1,
        "pending_settlement": Decimal("0.0000"),
    }


@pytest.mark.parametrize("initial_cash", [Decimal("0"), Decimal("-1.00")])
def test_create_account_rejects_non_positive_initial_cash(sqlite_session, initial_cash: Decimal) -> None:
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)

    with pytest.raises(ValueError, match="initial_cash"):
        repo.create_account("bad-cash", initial_cash)


def test_create_account_persists_initial_snapshot(sqlite_session) -> None:
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)

    account = repo.create_account("initial-snapshot", Decimal("100000.00"))
    snapshots = repo.list_snapshots(account.id)

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.point_type == SnapshotPointType.INITIAL.value
    assert snapshot.quality_status == SnapshotQualityStatus.VALID.value
    assert snapshot.event_at == account.created_at
    assert snapshot.trade_date == account.created_at.date()
    assert snapshot.cash_available == Decimal("100000.0000")
    assert snapshot.cash_frozen == Decimal("0.0000")
    assert snapshot.market_value == Decimal("0.0000")
    assert snapshot.total_assets == Decimal("100000.0000")
    assert snapshot.realized_pnl == Decimal("0.0000")
    assert snapshot.unrealized_pnl == Decimal("0.0000")
    assert snapshot.position_count == 0
    assert snapshot.order_count == 0
    assert snapshot.trade_count == 0
    assert snapshot.pending_settlement == Decimal("0.0000")
    assert snapshot.share_count == account.share_count
    assert snapshot.cumulative_deposit == Decimal("100000.0000")
    assert snapshot.cumulative_withdrawal == Decimal("0.0000")
    assert snapshot.net_cash_flow == Decimal("100000.0000")
    assert snapshot.net_asset_value == Decimal("1.000000")


def test_list_snapshots_does_not_round_loaded_entities_before_commit(sqlite_session) -> None:
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("snapshot-precision", Decimal("100000"))
    precise = Decimal("123456.789012345678")
    persisted_precise = Decimal("123456.789012345675")
    snapshot = repo.save_snapshot(
        **{
            **_trading_snapshot_values(account.id, date(2026, 8, 25), datetime(2026, 8, 25, tzinfo=timezone.utc)),
            "cash_available": precise,
            "total_assets": precise,
            "net_asset_value": Decimal("1.123456789012"),
            "share_count": precise,
        }
    )

    listed = next(row for row in repo.list_snapshots(account.id) if row.id == snapshot.id)
    assert listed.cash_available == precise
    assert listed.net_asset_value == Decimal("1.123456789012")
    sqlite_session.commit()
    sqlite_session.expire_all()

    reloaded = sqlite_session.get(type(snapshot), snapshot.id)
    assert reloaded is not None
    assert reloaded.cash_available == persisted_precise
    assert reloaded.net_asset_value == Decimal("1.123456789012")


def test_list_snapshots_orders_same_day_initial_before_trading(sqlite_session) -> None:
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("same-day-order", Decimal("100000.00"))
    created_at = account.created_at

    initial = repo.list_snapshots(account.id)[0]
    trading = repo.save_snapshot(
        **_trading_snapshot_values(account.id, created_at.date(), created_at + timedelta(seconds=1))
    )

    assert initial.point_type == SnapshotPointType.INITIAL.value
    assert [row.id for row in repo.list_snapshots(account.id)] == [initial.id, trading.id]


def test_save_trading_snapshot_updates_same_account_date_in_place(sqlite_session) -> None:
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("same-day-trading", Decimal("100000.00"))
    trade_date = date(2026, 8, 25)
    first_event = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
    second_event = datetime(2026, 8, 25, 15, 0, tzinfo=timezone.utc)

    first = repo.save_trading_snapshot(**_trading_snapshot_values(account.id, trade_date, first_event))
    second = repo.save_trading_snapshot(
        **{
            **_trading_snapshot_values(account.id, trade_date, second_event),
            "cash_available": Decimal("98000.0000"),
            "market_value": Decimal("2000.0000"),
        }
    )

    snapshots = [row for row in repo.list_snapshots(account.id) if row.point_type == SnapshotPointType.TRADING.value]
    assert [row.id for row in snapshots] == [first.id]
    assert second.id == first.id
    assert snapshots[0].cash_available == Decimal("98000.0000")


def test_create_initial_snapshot_rejects_duplicate_initial_point(sqlite_session) -> None:
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("duplicate-initial", Decimal("100000.00"))

    with pytest.raises(IntegrityError):
        repo.create_initial_snapshot(account, event_at=account.created_at + timedelta(seconds=1))


def test_list_replay_events_adapts_sources_in_stable_utc_order(sqlite_session) -> None:
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("replay-events", Decimal("100000.00"))
    event_at = datetime(2026, 8, 25, 9, tzinfo=timezone.utc)
    order = repo.create_order(
        account.id, "000001", OrderSide.BUY, 100, Decimal("10"), event_at.date(), OrderStatus.FILLED
    )
    trade = repo.create_trade(
        order.id,
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10"),
        Decimal("1000"),
        Decimal("5"),
        event_at.date(),
    )
    trade.trade_time = event_at
    ledger = repo.add_cash_event(
        account.id, CashEventType.DEPOSIT, Decimal("10"), trade_date=event_at.date(), occurred_at=event_at
    )
    action = repo.create_corporate_action(
        account_id=account.id,
        symbol="000001",
        event_type=CorporateActionType.DIVIDEND,
        event_at=event_at,
        idempotency_key="replay-dividend",
        parameters={"per_share_amount": "1"},
        cash_delta=Decimal("100"),
        before_quantity=Decimal("100"),
        after_quantity=Decimal("100"),
        before_cost_amount=Decimal("1000"),
        after_cost_amount=Decimal("1000"),
        before_cash_available=Decimal("10"),
        after_cash_available=Decimal("110"),
    )
    snapshot = repo.save_trading_snapshot(**_trading_snapshot_values(account.id, event_at.date(), event_at))

    events = repo.list_replay_events(account.id, start_at=event_at, end_at=event_at)

    assert [(event.event_type, event.source_kind, event.source_id) for event in events] == [
        (NavReplayEventType.CASH_FLOW, "paper_cash_ledger", f"paper_cash_ledger:{ledger.id}"),
        (NavReplayEventType.TRADE_SETTLEMENT, "paper_trades", f"paper_trades:{trade.id}"),
        (NavReplayEventType.CORPORATE_ACTION, "paper_corporate_actions", f"paper_corporate_actions:{action.id}"),
        (NavReplayEventType.MARKET_VALUATION, "paper_account_snapshots", f"paper_account_snapshots:{snapshot.id}"),
    ]
    assert all(event.event_at.tzinfo is timezone.utc for event in events)
    assert events[0].payload["amount"] == Decimal("10.000000000000")
    assert "nav" not in events[0].payload


def test_list_replay_events_marks_legacy_missing_time_invalid(sqlite_session) -> None:
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    event_at, quality_status = repo._replay_event_time(None, date(2026, 8, 25))

    assert event_at == datetime(2026, 8, 25, tzinfo=timezone.utc)
    assert quality_status is SnapshotQualityStatus.INVALID


def test_repository_replay_has_eligible_creation_baseline(sqlite_session) -> None:
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("repository-baseline", Decimal("100000.00"))

    events = repo.list_replay_events(account.id)

    initial = next(event for event in events if event.event_type is NavReplayEventType.INITIAL)
    assert initial.source_kind == "creation"
    assert initial.payload["opening_cash"] == Decimal("100000.000000000000")
    assert initial.payload["opening_shares"] == Decimal("100000.000000000000")
    from paper_trading.services.nav_series import NavSeriesBuilder

    assert NavSeriesBuilder().baseline_eligibility({initial.source_kind: initial.payload}).value == "eligible"
    result = NavSeriesBuilder(lambda _account_id: events).build(account.id)
    assert result.points[0].event_type is NavReplayEventType.INITIAL


def test_repository_preserves_cash_ledger_event_type_and_internal_events_do_not_flow_shares(sqlite_session) -> None:
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("ledger-types", Decimal("100000.00"))
    internal = repo.add_cash_event(
        account.id,
        CashEventType.FREEZE,
        Decimal("10"),
        occurred_at=account.created_at.replace(tzinfo=timezone.utc),
    )
    events = repo.list_replay_events(account.id)

    adapted = next(event for event in events if event.source_id.endswith(f":{internal.id}"))
    assert adapted.payload["ledger_event_type"] == CashEventType.FREEZE.value
    assert adapted.event_type is NavReplayEventType.TRADE_SETTLEMENT


def test_corporate_action_ledger_is_not_replayed_as_cash_flow(sqlite_session) -> None:
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("ledger-corporate-action", Decimal("100000.00"))
    event_at = datetime(2026, 8, 25, tzinfo=timezone.utc)
    action = repo.create_corporate_action(
        account_id=account.id,
        symbol="000001",
        event_type=CorporateActionType.DIVIDEND,
        event_at=event_at,
        idempotency_key="ledger-corporate-action",
        parameters={"per_share_amount": "1"},
        cash_delta=Decimal("100"),
        before_quantity=Decimal("100"),
        after_quantity=Decimal("100"),
        before_cost_amount=Decimal("1000"),
        after_cost_amount=Decimal("1000"),
        before_cash_available=Decimal("10"),
        after_cash_available=Decimal("110"),
        affected_start_date=event_at.date(),
    )
    ledger = repo.add_cash_event(
        account.id,
        CashEventType.CORPORATE_ACTION,
        Decimal("100"),
        trade_date=event_at.date(),
        occurred_at=event_at,
        note=CorporateActionType.DIVIDEND.value,
    )

    events = repo.list_replay_events(account.id)
    ledger_event = next(event for event in events if event.source_id.endswith(f":{ledger.id}"))
    action_event = next(event for event in events if event.source_id.endswith(f":{action.id}"))
    assert ledger_event.event_type is NavReplayEventType.TRADE_SETTLEMENT
    assert ledger_event.payload["ledger_event_type"] == CashEventType.CORPORATE_ACTION.value
    assert action_event.payload["action_type"] == CorporateActionType.DIVIDEND.value
    assert action_event.payload["symbol"] == "000001"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_at", datetime(2026, 8, 25)),
        ("quality_status", "unknown"),
        ("total_assets", Decimal("NaN")),
    ],
)
def test_replace_trading_snapshots_rejects_invalid_input(sqlite_session, field, value) -> None:
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("replace-invalid", Decimal("100000.00"))
    values = _trading_snapshot_values(account.id, date(2026, 8, 25), datetime(2026, 8, 25, tzinfo=timezone.utc))
    values[field] = value

    with pytest.raises(ValueError):
        repo.replace_trading_snapshots(account.id, date(2026, 8, 25), date(2026, 8, 25), [values])


def test_replace_trading_snapshots_is_bounded_and_upserts_dates(sqlite_session) -> None:
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("replace-derived", Decimal("100000.00"))
    before = date(2026, 8, 24)
    within = date(2026, 8, 25)
    after = date(2026, 8, 26)
    repo.save_trading_snapshot(
        **_trading_snapshot_values(account.id, before, datetime(2026, 8, 24, tzinfo=timezone.utc))
    )
    repo.save_trading_snapshot(
        **_trading_snapshot_values(account.id, within, datetime(2026, 8, 25, tzinfo=timezone.utc))
    )
    repo.save_trading_snapshot(
        **_trading_snapshot_values(account.id, after, datetime(2026, 8, 26, tzinfo=timezone.utc))
    )

    repo.replace_trading_snapshots(
        account.id,
        within,
        within,
        [
            {
                **_trading_snapshot_values(account.id, within, datetime(2026, 8, 25, 16, tzinfo=timezone.utc)),
                "total_assets": Decimal("120000"),
            }
        ],
    )

    snapshots = [item for item in repo.list_snapshots(account.id) if item.point_type == SnapshotPointType.TRADING.value]
    assert [(item.trade_date, item.total_assets) for item in snapshots] == [
        (before, Decimal("100000.0000")),
        (within, Decimal("120000.0000")),
        (after, Decimal("100000.0000")),
    ]


def test_get_accounts_for_snapshot_includes_active_cash_only_accounts(sqlite_session) -> None:
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    cash_only = repo.create_account("cash-only", Decimal("100000.00"))
    future = repo.create_account("future-cash-only", Decimal("100000.00"))
    inactive = repo.create_account("inactive-cash-only", Decimal("100000.00"))
    cash_only.created_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    future.created_at = datetime(2026, 8, 26, tzinfo=timezone.utc)
    inactive.created_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    inactive.status = AccountStatus.DISABLED.value
    sqlite_session.flush()

    assert repo.get_accounts_for_snapshot(date(2026, 8, 25)) == [cash_only.id]
    assert repo.get_accounts_for_snapshot(date(2026, 8, 25), account_id=future.id) == []


def test_acquire_matching_run_uses_canonical_active_status(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    trade_date = date(2026, 7, 31)

    first, first_owner = repo.acquire_matching_run(trade_date, None)
    second, second_owner = repo.acquire_matching_run(trade_date, None)

    assert first_owner is True
    assert second_owner is False
    assert second.id == first.id
    assert first.status == MatchingRunStatus.RUNNING.value


def test_replay_cleanup_removes_matching_runs(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("replay-status", Decimal("100000.00"))
    repo.create_matching_run(date(2026, 7, 31), account.id, MatchingRunStatus.COMPLETED.value)

    repo.clear_account_rebuild_state(account.id)

    assert repo.list_matching_runs() == []


def test_upsert_daily_bar_diagnostic_reuses_business_date_symbol_adjustment(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)

    first = repo.upsert_daily_bar_diagnostic(
        business_date=date(2026, 7, 28),
        market=Market.A_SHARE,
        stock_id="300996",
        adjust="bfq",
        classification="missing_market_data",
        provider_outcomes=[{"provider": "tushare", "status": "empty", "detail": None}],
        resolved=False,
    )
    second = repo.upsert_daily_bar_diagnostic(
        business_date=date(2026, 7, 28),
        market="a_share",
        stock_id="300996",
        adjust="bfq",
        classification="downloaded",
        provider_outcomes=[{"provider": "tushare", "status": "downloaded", "detail": None}],
        resolved=True,
    )

    assert second.id == first.id
    assert second.resolved is True
    assert second.classification == "downloaded"
    assert second.provider_outcomes == [{"provider": "tushare", "status": "downloaded", "detail": None}]
    assert repo.list_daily_bar_diagnostics() == [second]


@pytest.mark.parametrize(
    ("adjust", "classification", "outcomes"),
    [
        ("bfq", "partial", []),
        ("bfq", "downloaded", [{"provider": "tushare", "status": "partial"}]),
        ("bfq", "downloaded", {"provider": "tushare", "status": "downloaded"}),
    ],
)
def test_upsert_daily_bar_diagnostic_rejects_invalid_finite_values(sqlite_session, adjust, classification, outcomes):
    Base.metadata.create_all(sqlite_session.get_bind())

    with pytest.raises(ValueError):
        PaperTradingRepository(sqlite_session).upsert_daily_bar_diagnostic(
            date(2026, 8, 8), "a_share", "000001", adjust, classification, outcomes, resolved=False
        )


def test_bfq_diagnostic_label_is_found_by_default_lookup(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)

    repo.upsert_daily_bar_diagnostic(
        business_date=date(2026, 7, 28),
        market="a_share",
        stock_id="300996",
        adjust="",
        classification="missing_market_data",
        provider_outcomes=[],
        resolved=False,
    )

    assert repo.has_unresolved_daily_bar_diagnostic(date(2026, 7, 28), "a_share", "300996") is True


def test_diagnostic_lookup_normalizes_exchange_suffixed_and_bare_stock_ids(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)

    diagnostic = repo.upsert_daily_bar_diagnostic(
        business_date=date(2026, 7, 28),
        market="a_share",
        stock_id="000002.SZ",
        adjust="bfq",
        classification="missing_market_data",
        provider_outcomes=[],
        resolved=False,
    )

    assert diagnostic.stock_id == "000002"
    assert repo.has_unresolved_daily_bar_diagnostic(date(2026, 7, 28), "a_share", "000002") is True
    assert repo.has_unresolved_daily_bar_diagnostic(date(2026, 7, 28), "a_share", "000002.SZ") is True


def test_provider_outcome_rejects_unknown_status_and_normalizes_detail():
    from paper_trading.domain.market_data_diagnostics import ProviderOutcome

    assert ProviderOutcome(provider="tushare", status="empty").detail is None
    with pytest.raises(ValueError, match="status"):
        ProviderOutcome(provider="tushare", status=cast(Any, "partial"))


def test_add_cash_event_persists_nav_share_fields(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("cash-event-demo", Decimal("100000.00"))

    event = repo.add_cash_event(
        account.id,
        CashEventType.WITHDRAWAL,
        Decimal("-5000.0000"),
        trade_date=date(2026, 7, 20),
        net_asset_value=Decimal("1.250000"),
        share_delta=Decimal("-4000.000000"),
        note="withdraw",
    )

    assert event.trade_date == date(2026, 7, 20)
    assert event.net_asset_value == Decimal("1.250000")
    assert event.share_delta == Decimal("-4000.000000")


def test_add_cash_event_defaults_rounding_residual_to_zero(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("cash-event-default-residual", Decimal("100000.00"))

    event = repo.add_cash_event(account.id, CashEventType.DEPOSIT, Decimal("1"))

    assert event.rounding_residual == Decimal("0.000000000000")


def test_add_cash_event_derives_residual_from_persisted_values(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("cash-event-derived-residual", Decimal("100000.00"))
    amount = Decimal("10.000000000001")
    nav = Decimal("1.234567890123")
    shares = Decimal("8.100000000001")

    event = repo.add_cash_event(
        account.id,
        CashEventType.DEPOSIT,
        amount,
        net_asset_value=nav,
        share_delta=shares,
        rounding_residual=Decimal("999"),
    )
    account_id = account.id
    sqlite_session.flush()
    loaded = next(ledger for ledger in repo.list_cash_ledger(account_id) if ledger.id == event.id)

    assert loaded.share_delta is not None
    assert loaded.net_asset_value is not None
    assert event.share_delta is not None
    assert event.net_asset_value is not None
    assert loaded.rounding_residual == loaded.amount - loaded.share_delta * loaded.net_asset_value
    assert event.rounding_residual == event.amount - event.share_delta * event.net_asset_value


def test_cash_ledger_orders_by_occurred_at_then_id(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("cash-order", Decimal("100000"))
    later = datetime(2026, 7, 20, 10, tzinfo=timezone.utc)
    earlier = datetime(2026, 7, 20, 9, tzinfo=timezone.utc)

    first = repo.add_cash_event(account.id, CashEventType.DEPOSIT, Decimal("1"), occurred_at=later)
    second = repo.add_cash_event(account.id, CashEventType.DEPOSIT, Decimal("1"), occurred_at=earlier)

    assert [event.id for event in repo.list_cash_ledger(account.id) if event.id in {first.id, second.id}] == [
        second.id,
        first.id,
    ]


def test_cash_ledger_orders_equal_occurred_at_by_id(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("cash-equal-order", Decimal("100000"))
    occurred_at = datetime(2026, 7, 20, 10, tzinfo=timezone.utc)

    first = repo.add_cash_event(account.id, CashEventType.DEPOSIT, Decimal("1"), occurred_at=occurred_at)
    second = repo.add_cash_event(account.id, CashEventType.DEPOSIT, Decimal("1"), occurred_at=occurred_at)

    assert [event.id for event in repo.list_cash_ledger(account.id) if event.id in {first.id, second.id}] == [
        first.id,
        second.id,
    ]


def test_corporate_actions_persist_filter_and_order(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("corporate-actions", Decimal("10000"))
    event_at = datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc)
    first = repo.create_corporate_action(
        account_id=account.id,
        market=Market.A_SHARE,
        symbol="000001",
        event_type=CorporateActionType.SPLIT,
        event_at=event_at,
        idempotency_key="split-1",
        parameters={"ratio": "2"},
        before_quantity=Decimal("100"),
        after_quantity=Decimal("200"),
        before_cost_amount=Decimal("1000"),
        after_cost_amount=Decimal("1000"),
        before_cash_available=Decimal("9000"),
        after_cash_available=Decimal("9000"),
    )
    second = repo.create_corporate_action(
        account_id=account.id,
        market=Market.A_SHARE,
        symbol="000002",
        event_type=CorporateActionType.DIVIDEND,
        event_at=event_at,
        idempotency_key="dividend-1",
        parameters={"amount": "50"},
        cash_delta=Decimal("50"),
        before_quantity=Decimal("100"),
        after_quantity=Decimal("100"),
        before_cost_amount=Decimal("1000"),
        after_cost_amount=Decimal("1000"),
        before_cash_available=Decimal("9000"),
        after_cash_available=Decimal("9050"),
    )

    assert repo.get_corporate_action_by_idempotency_key(account.id, "split-1") is first
    assert [item.id for item in repo.list_corporate_actions(account.id)] == [first.id, second.id]
    assert repo.list_corporate_actions(account.id, symbol="000002") == [second]
    assert repo.list_corporate_actions(account.id, event_type=CorporateActionType.SPLIT) == [first]
    assert first.parameters == {"ratio": "2"}
    assert first.after_quantity == Decimal("200.000000000000")


def test_corporate_action_filters_normalize_offset_bounds_to_utc(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("corporate-action-utc-bounds", Decimal("10000"))
    event = repo.create_corporate_action(
        account_id=account.id,
        market=Market.A_SHARE,
        symbol="000001",
        event_type=CorporateActionType.SPLIT,
        event_at=datetime(2026, 8, 27, 1, tzinfo=timezone.utc),
        idempotency_key="utc-bounds",
        parameters={"ratio": Decimal("2")},
        before_quantity=Decimal("1"),
        after_quantity=Decimal("2"),
        before_cost_amount=Decimal("1"),
        after_cost_amount=Decimal("1"),
        before_cash_available=Decimal("1"),
        after_cash_available=Decimal("1"),
    )
    offset = timezone(timedelta(hours=8))
    assert repo.list_corporate_actions(account.id, start_at=datetime(2026, 8, 27, 9, tzinfo=offset)) == [event]
    assert repo.list_corporate_actions(account.id, end_at=datetime(2026, 8, 27, 9, tzinfo=offset)) == [event]


def test_delete_account_removes_corporate_actions(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("corporate-actions-delete", Decimal("10000"))
    repo.create_corporate_action(
        account_id=account.id,
        symbol="000001",
        event_type=CorporateActionType.BONUS_SHARE,
        event_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
        idempotency_key="bonus-1",
        parameters={},
        before_quantity=Decimal("1"),
        after_quantity=Decimal("2"),
        before_cost_amount=Decimal("1"),
        after_cost_amount=Decimal("1"),
        before_cash_available=Decimal("1"),
        after_cash_available=Decimal("1"),
    )

    assert repo.delete_account(account.id) is True
    assert repo.list_corporate_actions(account.id) == []


def test_corporate_action_persistence_applies_shared_precision(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("corporate-actions-precision", Decimal("10000"))

    action = repo.create_corporate_action(
        account_id=account.id,
        symbol="000001",
        event_type=CorporateActionType.DIVIDEND,
        event_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
        idempotency_key="precision-1",
        parameters={"per_share_amount": Decimal("1.1234567890129")},
        cash_delta=Decimal("1.1234567890129"),
        quantity_delta=Decimal("2.1234567890129"),
        before_quantity=Decimal("3.1234567890129"),
        after_quantity=Decimal("5.2469135780258"),
        before_cost_amount=Decimal("10.1234567890129"),
        after_cost_amount=Decimal("10.1234567890129"),
        before_cash_available=Decimal("100.1234567890129"),
        after_cash_available=Decimal("101.2469135780258"),
    )

    assert action.parameters == {"per_share_amount": "1.1234567890129"}
    assert action.cash_delta == Decimal("1.123456789013")
    assert action.quantity_delta == Decimal("2.123456789013")
    assert action.before_quantity == Decimal("3.123456789013")


@pytest.mark.parametrize("field", ["parameters", "cash_delta", "before_quantity", "after_cash_available"])
def test_corporate_action_persistence_rejects_non_finite_values(sqlite_session, field):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account(f"corporate-actions-finite-{field}", Decimal("10000"))
    values: dict[str, Any] = {
        "account_id": account.id,
        "symbol": "000001",
        "event_type": CorporateActionType.DIVIDEND,
        "event_at": datetime(2026, 8, 27, tzinfo=timezone.utc),
        "idempotency_key": f"finite-{field}",
        "parameters": {"per_share_amount": Decimal("1")},
        "cash_delta": Decimal("0"),
        "quantity_delta": Decimal("0"),
        "before_quantity": Decimal("1"),
        "after_quantity": Decimal("1"),
        "before_cost_amount": Decimal("1"),
        "after_cost_amount": Decimal("1"),
        "before_cash_available": Decimal("1"),
        "after_cash_available": Decimal("1"),
    }
    values[field] = {"per_share_amount": Decimal("NaN")} if field == "parameters" else Decimal("Infinity")

    with pytest.raises(ValueError, match="finite"):
        repo.create_corporate_action(**values)


class _NoOffsetTz(tzinfo):
    def utcoffset(self, _value):
        return None

    def dst(self, _value):
        return None

    def tzname(self, _value):
        return "no-offset"


def test_add_cash_event_rejects_tzinfo_without_offset(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("no-offset-repository", Decimal("100000"))

    with pytest.raises(ValueError, match="offset"):
        repo.add_cash_event(
            account.id,
            CashEventType.DEPOSIT,
            Decimal("1"),
            occurred_at=datetime(2026, 7, 20, tzinfo=_NoOffsetTz()),
        )


def test_latest_valid_nav_before_ignores_invalid_snapshots(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("nav-lookup", Decimal("100000"))
    event_at = datetime(2026, 7, 20, 10, tzinfo=timezone.utc)
    values = _trading_snapshot_values(account.id, event_at.date(), event_at)

    repo.save_snapshot(**{**values, "net_asset_value": Decimal("1.250000")})
    later_event = event_at + timedelta(days=1)
    repo.save_snapshot(
        **{
            **values,
            "trade_date": later_event.date(),
            "event_at": later_event,
            "net_asset_value": Decimal("0"),
        }
    )

    assert repo.latest_valid_nav_before(account.id, later_event + timedelta(minutes=2)) == Decimal("1.250000")


def test_create_account_deposits_initial_cash(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'repo.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))
    session.commit()

    assert account.id is not None
    assert repo.get_cash_available(account.id) == Decimal("100000.0000")
    engine.dispose()


def test_create_order_persists_accepted_order(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'repo.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))

    order = repo.create_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 6, 16),
        status=OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.00"),
        frozen_quantity=0,
        idempotency_key="k1",
    )
    session.commit()

    assert repo.get_order(order.id).status == OrderStatus.ACCEPTED.value
    engine.dispose()


def test_list_orders_page_filters_counts_orders_and_slices_pages(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("paged-orders", Decimal("100000.00"))
    other_account = repo.create_account("other-paged-orders", Decimal("100000.00"))

    first = repo.create_order(
        account.id, "000001", OrderSide.BUY, 100, Decimal("10.00"), date(2026, 8, 1), OrderStatus.ACCEPTED
    )
    same_date = repo.create_order(
        account.id, "000002", OrderSide.BUY, 100, Decimal("20.00"), date(2026, 8, 2), OrderStatus.ACCEPTED
    )
    latest = repo.create_order(
        account.id, "000003", OrderSide.BUY, 100, Decimal("30.00"), date(2026, 8, 2), OrderStatus.ACCEPTED
    )
    repo.create_order(
        account.id, "000004", OrderSide.BUY, 100, Decimal("40.00"), date(2026, 8, 3), OrderStatus.ACCEPTED
    )
    repo.create_order(
        other_account.id, "000005", OrderSide.BUY, 100, Decimal("50.00"), date(2026, 8, 2), OrderStatus.ACCEPTED
    )

    rows, total = repo.list_orders_page(account.id, date(2026, 8, 1), date(2026, 8, 2), page=1, page_size=2)

    assert total == 3
    assert [order.id for order in rows] == [latest.id, same_date.id]
    rows, total = repo.list_orders_page(account.id, date(2026, 8, 1), date(2026, 8, 2), page=2, page_size=2)

    assert total == 3
    assert [order.id for order in rows] == [first.id]
    assert [order.id for order in repo.list_orders(account.id)] == [first.id, same_date.id, latest.id, 4]


def test_list_trades_page_filters_counts_trades_and_slices_pages(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("paged-trades", Decimal("100000.00"))
    other_account = repo.create_account("other-paged-trades", Decimal("100000.00"))

    first_order = repo.create_order(
        account.id, "000001", OrderSide.BUY, 100, Decimal("10.00"), date(2026, 8, 1), OrderStatus.FILLED
    )
    same_date_order = repo.create_order(
        account.id, "000002", OrderSide.BUY, 100, Decimal("20.00"), date(2026, 8, 2), OrderStatus.FILLED
    )
    latest_order = repo.create_order(
        account.id, "000003", OrderSide.BUY, 100, Decimal("30.00"), date(2026, 8, 2), OrderStatus.FILLED
    )
    other_order = repo.create_order(
        other_account.id, "000004", OrderSide.BUY, 100, Decimal("40.00"), date(2026, 8, 2), OrderStatus.FILLED
    )

    def create_trade_for(order, account_id, symbol, trade_date, price):
        return repo.create_trade(
            order_id=order.id,
            account_id=account_id,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=100,
            price=price,
            amount=price * 100,
            fees=Decimal("5.0000"),
            trade_date=trade_date,
        )

    first = create_trade_for(first_order, account.id, "000001", date(2026, 8, 1), Decimal("10.00"))
    same_date = create_trade_for(same_date_order, account.id, "000002", date(2026, 8, 2), Decimal("20.00"))
    latest = create_trade_for(latest_order, account.id, "000003", date(2026, 8, 2), Decimal("30.00"))
    create_trade_for(other_order, other_account.id, "000004", date(2026, 8, 2), Decimal("40.00"))

    rows, total = repo.list_trades_page(account.id, date(2026, 8, 1), date(2026, 8, 2), page=1, page_size=2)

    assert total == 3
    assert [trade.id for trade in rows] == [latest.id, same_date.id]
    rows, total = repo.list_trades_page(account.id, date(2026, 8, 1), date(2026, 8, 2), page=2, page_size=2)

    assert total == 3
    assert [trade.id for trade in rows] == [first.id]


def test_list_catalogue_etf_a_share_orders_excludes_non_candidates_and_filters_account(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("catalogue-candidate", Decimal("100000.00"))
    other_account = repo.create_account("other-account", Decimal("100000.00"))
    sqlite_session.add(ETFBasic(基金代码="510300", 中文简称="CSI 300 ETF", 交易所="SH", 存续状态="L"))
    sqlite_session.add(ETFBasic(基金代码="ABCDEF", 中文简称="Malformed ETF", 交易所="SH", 存续状态="L"))
    sqlite_session.flush()

    a_share_etf = repo.create_order(
        account.id, "510300", OrderSide.BUY, 100, Decimal("3.10"), date(2026, 8, 10), OrderStatus.ACCEPTED
    )
    repo.create_order(
        account.id,
        "510300",
        OrderSide.BUY,
        100,
        Decimal("3.10"),
        date(2026, 8, 10),
        OrderStatus.ACCEPTED,
        market=Market.ETF,
    )
    repo.create_order(
        account.id, "000001", OrderSide.BUY, 100, Decimal("10.00"), date(2026, 8, 10), OrderStatus.ACCEPTED
    )
    repo.create_order(
        account.id,
        "510300.SH",
        OrderSide.BUY,
        100,
        Decimal("3.10"),
        date(2026, 8, 10),
        OrderStatus.ACCEPTED,
    )
    repo.create_order(
        account.id, "ABCDEF", OrderSide.BUY, 100, Decimal("3.10"), date(2026, 8, 10), OrderStatus.ACCEPTED
    )

    candidates = repo.list_catalogue_etf_a_share_orders()

    assert [order.id for order in candidates] == [a_share_etf.id]
    assert repo.list_catalogue_etf_a_share_orders(other_account.id) == []


def test_update_orders_market_updates_only_targeted_orders(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("market-update", Decimal("100000.00"))
    a_share_order = repo.create_order(
        account.id, "510300", OrderSide.BUY, 100, Decimal("3.10"), date(2026, 8, 10), OrderStatus.ACCEPTED
    )
    existing_etf_order = repo.create_order(
        account.id,
        "510500",
        OrderSide.BUY,
        100,
        Decimal("3.10"),
        date(2026, 8, 10),
        OrderStatus.ACCEPTED,
        market=Market.ETF,
    )
    untargeted_a_share_order = repo.create_order(
        account.id, "000001", OrderSide.BUY, 100, Decimal("10.00"), date(2026, 8, 10), OrderStatus.ACCEPTED
    )

    changed = repo.update_orders_market([a_share_order.id], Market.ETF)

    assert changed == 1
    sqlite_session.expunge_all()
    assert repo.get_order(a_share_order.id).market == Market.ETF.value
    assert repo.get_order(existing_etf_order.id).market == Market.ETF.value
    assert repo.get_order(untargeted_a_share_order.id).market == Market.A_SHARE.value


def test_get_order_by_idempotency_key_returns_existing_order(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        OrderStatus.ACCEPTED,
        idempotency_key="order-1",
    )

    found = repo.get_order_by_idempotency_key(account.id, "order-1")
    assert found is not None
    assert found.id == order.id
    assert repo.get_order_by_idempotency_key(account.id, "missing") is None


def test_order_validity_summary_and_detail_are_persisted(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'repo.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        OrderStatus.ACCEPTED,
    )

    repo.update_order_validity(order, "valid", "VALID")
    check = repo.create_trade_validity_check(
        order_id=order.id,
        account_id=account.id,
        symbol="000001.SZ",
        trade_date=date(2026, 6, 16),
        side="buy",
        input_price=Decimal("10.00"),
        daily_low=Decimal("9.00"),
        daily_high=Decimal("10.50"),
        limit_up_price=Decimal("11.00"),
        limit_down_price=Decimal("9.00"),
        touched_limit_up=False,
        touched_limit_down=True,
        price_in_range=True,
        status="valid",
        reason_code="VALID",
        reason_detail="Price is inside daily range",
        data_granularity="daily",
    )
    session.commit()

    saved = repo.get_order(order.id)
    assert saved.validity_status == "valid"
    assert saved.validity_reason == "VALID"
    assert saved.validity_checked_at is not None
    assert repo.list_trade_validity_checks(order.id)[0].id == check.id
    engine.dispose()


def test_delete_account_deletes_trade_validity_checks_before_orders(tmp_path):
    """delete_account removes PaperTradeValidityCheck rows so FK to orders does not fail."""
    engine = create_engine(f"sqlite:///{tmp_path / 'del_account.db'}")
    Base.metadata.create_all(engine)
    session: Session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        OrderStatus.ACCEPTED,
    )
    repo.create_trade_validity_check(
        order_id=order.id,
        account_id=account.id,
        symbol="000001.SZ",
        trade_date=date(2026, 6, 16),
        side="buy",
        input_price=Decimal("10.00"),
        daily_low=None,
        daily_high=None,
        status="unchecked",
        reason_code="MARKET_DATA_UNAVAILABLE",
        reason_detail="test",
        data_granularity="daily",
    )
    session.commit()

    # Verify the check exists before deletion
    assert session.query(PaperTradeValidityCheck).filter_by(account_id=account.id).count() == 1

    # Delete the account
    deleted = repo.delete_account(account.id)
    session.commit()

    assert deleted is True
    # Verify the account and its related rows are gone
    assert repo.get_account(account.id) is None
    assert session.query(PaperTradeValidityCheck).filter_by(account_id=account.id).count() == 0
    engine.dispose()


def test_round_trip_repository_creates_and_lists_closed_cycle(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("analytics-demo", Decimal("100000.00"))

    # Create real order and trade for the round-trip open
    open_order = repo.create_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 6, 16),
        status=OrderStatus.FILLED,
        frozen_cash=Decimal("1000.0000"),
    )
    open_trade = repo.create_trade(
        order_id=open_order.id,
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        price=Decimal("10.00"),
        amount=Decimal("1000.0000"),
        fees=Decimal("5.0000"),
        trade_date=date(2026, 6, 16),
    )

    cycle = repo.create_round_trip(
        account_id=account.id,
        market="a_share",
        symbol="000001.SZ",
        open_trade_id=open_trade.id,
        open_trade_date=date(2026, 6, 16),
        entry_amount=Decimal("1000.0000"),
        fees=Decimal("5.0000"),
    )

    # Create real order and trade for the round-trip close
    close_order = repo.create_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.SELL,
        quantity=100,
        limit_price=Decimal("11.00"),
        trade_date=date(2026, 6, 20),
        status=OrderStatus.FILLED,
    )
    close_trade = repo.create_trade(
        order_id=close_order.id,
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.SELL,
        quantity=100,
        price=Decimal("11.00"),
        amount=Decimal("1100.0000"),
        fees=Decimal("10.0000"),
        trade_date=date(2026, 6, 20),
    )

    repo.update_round_trip(
        cycle,
        close_trade_id=close_trade.id,
        close_trade_date=date(2026, 6, 20),
        exit_amount=Decimal("1100.0000"),
        fees=Decimal("10.0000"),
        realized_pnl=Decimal("90.0000"),
        return_pct=Decimal("0.090000"),
        holding_days=4,
        status="closed",
    )
    sqlite_session.commit()

    rows = repo.list_round_trips(account.id)
    assert len(rows) == 1
    assert rows[0].symbol == "000001.SZ"
    assert rows[0].status == "closed"
    assert rows[0].realized_pnl == Decimal("90.0000")


def test_create_account_sets_default_fee_config(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))
    session.commit()

    assert account.fee_preset == "a_share"
    assert account.commission_rate == Decimal("0.00030000")
    assert account.min_commission == Decimal("5.0000")
    assert account.stamp_duty_rate == Decimal("0.00050000")
    assert account.transfer_fee_rate == Decimal("0.00001000")
    engine.dispose()


def test_create_account_accepts_custom_fee_config(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(
        name="custom-fee",
        initial_cash=Decimal("100000.00"),
        fee_preset="a_share",
        commission_rate=Decimal("0.00025"),
        min_commission=Decimal("3.00"),
        stamp_duty_rate=Decimal("0.0004"),
        transfer_fee_rate=Decimal("0.00002"),
    )
    session.commit()

    assert account.fee_preset == "a_share"
    assert account.commission_rate == Decimal("0.00025000")
    assert account.min_commission == Decimal("3.0000")
    assert account.stamp_duty_rate == Decimal("0.00040000")
    assert account.transfer_fee_rate == Decimal("0.00002000")
    engine.dispose()


@pytest.mark.parametrize(
    "field",
    ["commission_rate", "min_commission", "stamp_duty_rate", "transfer_fee_rate"],
)
def test_create_account_rejects_negative_fee_config(tmp_path, field):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    values = {
        "commission_rate": Decimal("0.0003"),
        "min_commission": Decimal("5.00"),
        "stamp_duty_rate": Decimal("0.0005"),
        "transfer_fee_rate": Decimal("0.00001"),
    }
    values[field] = Decimal("-0.0001")

    with pytest.raises(ValueError, match=field):
        repo.create_account(
            name="negative-fee",
            initial_cash=Decimal("100000.00"),
            commission_rate=values["commission_rate"],
            min_commission=values["min_commission"],
            stamp_duty_rate=values["stamp_duty_rate"],
            transfer_fee_rate=values["transfer_fee_rate"],
        )
    engine.dispose()


def test_create_account_preserves_zero_fee_config(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(
        name="zero-fee",
        initial_cash=Decimal("100000.00"),
        commission_rate=Decimal("0"),
        min_commission=Decimal("0"),
        stamp_duty_rate=Decimal("0"),
        transfer_fee_rate=Decimal("0"),
    )
    session.commit()

    assert account.commission_rate == Decimal("0E-8")
    assert account.min_commission == Decimal("0.0000")
    assert account.stamp_duty_rate == Decimal("0E-8")
    assert account.transfer_fee_rate == Decimal("0E-8")
    engine.dispose()


def test_update_account_fees_updates_only_provided_fields(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))
    updated = repo.update_account_fees(
        account.id,
        commission_rate=Decimal("0.0002"),
        min_commission=Decimal("3.00"),
    )
    session.commit()

    assert updated is not None
    assert updated.commission_rate == Decimal("0.00020000")
    assert updated.min_commission == Decimal("3.0000")
    assert updated.stamp_duty_rate == Decimal("0.00050000")
    assert updated.transfer_fee_rate == Decimal("0.00001000")
    engine.dispose()


def test_update_account_fees_rejects_negative_values(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))

    with pytest.raises(ValueError, match="commission_rate"):
        repo.update_account_fees(account.id, commission_rate=Decimal("-0.0001"))
    engine.dispose()


def test_update_account_fees_rejects_empty_update(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))

    with pytest.raises(ValueError, match="at least one fee field"):
        repo.update_account_fees(account.id)
    engine.dispose()


def test_update_account_fees_returns_none_for_missing_account(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    assert repo.update_account_fees(999, commission_rate=Decimal("0.0002")) is None
    engine.dispose()


def test_order_and_trade_comments_are_persisted(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper_comments.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 18),
        OrderStatus.ACCEPTED,
        comment="突破买入",
    )
    repo.create_trade(
        order.id,
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        Decimal("1000.00"),
        Decimal("5.00"),
        date(2026, 7, 18),
        comment="突破买入",
    )

    assert repo.get_order(order.id).comment == "突破买入"
    assert repo.list_trades(account.id)[0].comment == "突破买入"
    engine.dispose()


def test_update_order_comment_syncs_linked_trades_and_clears_blank(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper_comment_update.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 18),
        OrderStatus.ACCEPTED,
        comment="old",
    )
    trade = repo.create_trade(
        order.id,
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        Decimal("1000.00"),
        Decimal("5.00"),
        date(2026, 7, 18),
        comment="old",
    )

    # Keep a linked PaperTrade object loaded before the update
    loaded_trade = repo.list_trades(account.id)[0]
    assert loaded_trade.id == trade.id
    assert loaded_trade.comment == "old"

    repo.update_order_comment(order, "new reason")
    assert repo.get_order(order.id).comment == "new reason"
    # Loaded trade object observes the updated comment in-memory
    assert loaded_trade.comment == "new reason"

    repo.update_order_comment(order, "")
    assert repo.get_order(order.id).comment is None
    # Loaded trade object observes the cleared comment in-memory
    assert loaded_trade.comment is None
    engine.dispose()


def test_delete_account_removes_round_trips(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("delete-round-trips", Decimal("100000.00"))

    order = repo.create_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 6, 16),
        status=OrderStatus.FILLED,
        frozen_cash=Decimal("1000.0000"),
    )
    trade = repo.create_trade(
        order_id=order.id,
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        price=Decimal("10.00"),
        amount=Decimal("1000.0000"),
        fees=Decimal("5.0000"),
        trade_date=date(2026, 6, 16),
    )

    repo.create_round_trip(
        account_id=account.id,
        market="a_share",
        symbol="000001.SZ",
        open_trade_id=trade.id,
        open_trade_date=date(2026, 6, 16),
        entry_amount=Decimal("1000.0000"),
        fees=Decimal("5.0000"),
    )

    assert repo.delete_account(account.id) is True
    sqlite_session.commit()

    assert repo.list_round_trips(account.id) == []


def test_delete_order_returns_deleted_order_and_removes_row(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("demo", Decimal("100000"))
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 19),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    sqlite_session.commit()

    deleted = repo.delete_order(order.id)

    assert deleted is not None
    assert deleted.id == order.id
    sqlite_session.flush()
    with pytest.raises(KeyError):
        repo.get_order(order.id)


def test_ledger_rebuild_audit_lifecycle_records_trigger_counts_and_failure(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("audit-rebuild", Decimal("100000"))

    running = repo.create_ledger_rebuild_started(
        account.id,
        date(2026, 7, 19),
        trigger_evidence={"source": "api", "requested_by": "test"},
    )

    assert running.status == LedgerRebuildStatus.RUNNING.value
    assert running.trigger_evidence == {"source": "api", "requested_by": "test"}
    assert running.triggering_order_ids == []
    assert running.deleted_counts == {}
    assert running.regenerated_counts == {}
    assert running.finished_at is None

    completed = repo.complete_ledger_rebuild(
        running,
        deleted_counts={"trades": 1},
        regenerated_counts={"trades": 2, "matching_runs": 1},
    )

    assert completed.status == LedgerRebuildStatus.COMPLETED.value
    assert completed.deleted_counts == {"trades": 1}
    assert completed.regenerated_counts == {"trades": 2, "matching_runs": 1}
    assert completed.finished_at is not None

    failed = repo.create_ledger_rebuild_failed(
        account.id,
        date(2026, 7, 20),
        trigger_evidence={"source": "api"},
        error_details="boom",
        deleted_counts={"trades": 0},
        regenerated_counts={"trades": 0},
    )

    assert failed.status == LedgerRebuildStatus.FAILED.value
    assert failed.error_details == "boom"
    assert failed.finished_at is not None


def test_clear_account_rebuild_state_from_date_preserves_source_facts_and_history(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("scoped-rebuild", Decimal("100000"))
    before_date = date(2026, 7, 18)
    start_date = date(2026, 7, 19)

    before_order = repo.create_order(
        account.id, "000001", OrderSide.BUY, 100, Decimal("10.00"), before_date, OrderStatus.FILLED
    )
    after_order = repo.create_order(
        account.id, "000002", OrderSide.BUY, 100, Decimal("20.00"), start_date, OrderStatus.FILLED
    )
    cancelled_order = repo.create_order(
        account.id, "000003", OrderSide.BUY, 100, Decimal("30.00"), start_date, OrderStatus.CANCELLED
    )
    before_trade = repo.create_trade(
        before_order.id,
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        Decimal("1000"),
        Decimal("5"),
        before_date,
    )
    after_trade = repo.create_trade(
        after_order.id,
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        Decimal("2000"),
        Decimal("5"),
        start_date,
    )
    repo.add_cash_event(
        account.id,
        CashEventType.TRADE,
        Decimal("-1005"),
        order_id=before_order.id,
        trade_id=before_trade.id,
        trade_date=before_date,
    )
    repo.add_cash_event(
        account.id,
        CashEventType.TRADE,
        Decimal("-2005"),
        order_id=after_order.id,
        trade_id=after_trade.id,
        trade_date=start_date,
    )
    manual_deposit = repo.add_cash_event(
        account.id, CashEventType.DEPOSIT, Decimal("500"), trade_date=start_date, note="manual deposit"
    )
    repo.create_position_lot(account.id, "a_share", "000001", before_date, 100, 100, Decimal("10.00"), source="trade")
    repo.create_position_lot(account.id, "a_share", "000002", start_date, 100, 100, Decimal("20.00"), source="trade")
    repo.upsert_position(account.id, "a_share", "000001", 100, 0, Decimal("1000"), source="trade")
    repo.upsert_position(account.id, "a_share", "000002", 100, 0, Decimal("2000"), source="trade")
    repo.create_round_trip(account.id, "a_share", "000001", before_trade.id, before_date, Decimal("1000"), Decimal("5"))
    repo.create_round_trip(account.id, "a_share", "000002", after_trade.id, start_date, Decimal("2000"), Decimal("5"))
    repo.save_snapshot(
        account_id=account.id,
        trade_date=before_date,
        cash_available=Decimal("99000"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("1000"),
        total_assets=Decimal("100000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=1,
        order_count=1,
        trade_count=1,
    )
    repo.save_snapshot(
        account_id=account.id,
        trade_date=start_date,
        cash_available=Decimal("97000"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("3000"),
        total_assets=Decimal("100000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=2,
        order_count=2,
        trade_count=2,
    )
    repo.upsert_valuation_gap(account.id, before_date, ["000001"], [])
    repo.upsert_valuation_gap(account.id, start_date, ["000002"], [])
    repo.create_pending_settlement(account.id, Decimal("100"), start_date, trade_id=after_trade.id)
    historical_run = repo.create_matching_run(start_date, account.id, MatchingRunStatus.COMPLETED.value)
    repo.create_trade_validity_check(
        order_id=after_order.id,
        account_id=account.id,
        symbol="000002",
        trade_date=start_date,
        side=OrderSide.BUY.value,
        input_price=Decimal("20.00"),
        status="valid",
        reason_code="VALID",
    )
    sqlite_session.commit()

    counts = repo.clear_account_rebuild_state_from(account.id, start_date)
    repo.reset_orders_for_replay_from(account.id, start_date)

    assert counts["trades"] == 1
    assert counts["cash_events"] == 1
    assert [trade.id for trade in repo.list_trades(account.id)] == [before_trade.id]
    assert [event.id for event in repo.list_cash_ledger(account.id) if event.note == "manual deposit"] == [
        manual_deposit.id
    ]
    assert [order.id for order in repo.list_orders(account.id)] == [before_order.id, after_order.id, cancelled_order.id]
    assert repo.get_order(before_order.id).status == OrderStatus.FILLED.value
    assert repo.get_order(after_order.id).status == OrderStatus.ACCEPTED.value
    assert repo.get_order(cancelled_order.id).status == OrderStatus.CANCELLED.value
    assert repo.list_matching_runs()[0].id == historical_run.id
    assert repo.list_trade_validity_checks(after_order.id) != []
    assert [(snapshot.point_type, snapshot.trade_date) for snapshot in repo.list_snapshots(account.id)] == [
        (SnapshotPointType.INITIAL.value, account.created_at.date()),
        (SnapshotPointType.TRADING.value, before_date),
    ]
    assert sqlite_session.query(PaperValuationGap).filter_by(account_id=account.id).one().trade_date == before_date
    assert sqlite_session.query(PaperPendingSettlement).filter_by(account_id=account.id).count() == 0
    assert [(position.symbol, position.total_quantity) for position in repo.get_positions(account.id)] == [
        ("000001", 100)
    ]


def test_clear_account_rebuild_state_from_restores_pre_start_lots_and_realized_pnl(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("baseline-rebuild", Decimal("100000"))
    buy_date = date(2026, 7, 16)
    pre_start_sell_date = date(2026, 7, 18)
    start_date = date(2026, 7, 19)
    post_start_sell_date = date(2026, 7, 20)

    buy_order = repo.create_order(account.id, "000001", OrderSide.BUY, 100, Decimal("10"), buy_date, OrderStatus.FILLED)
    buy_trade = repo.create_trade(
        buy_order.id,
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10"),
        Decimal("1000"),
        Decimal("5"),
        buy_date,
    )
    repo.create_position_lot(account.id, "a_share", "000001", buy_date, 100, 20, Decimal("10"), source="trade")

    pre_sell_order = repo.create_order(
        account.id, "000001", OrderSide.SELL, 40, Decimal("12"), pre_start_sell_date, OrderStatus.FILLED
    )
    pre_sell_trade = repo.create_trade(
        pre_sell_order.id,
        account.id,
        "000001",
        OrderSide.SELL,
        40,
        Decimal("12"),
        Decimal("480"),
        Decimal("5"),
        pre_start_sell_date,
    )
    post_sell_order = repo.create_order(
        account.id, "000001", OrderSide.SELL, 40, Decimal("13"), post_start_sell_date, OrderStatus.FILLED
    )
    post_sell_trade = repo.create_trade(
        post_sell_order.id,
        account.id,
        "000001",
        OrderSide.SELL,
        40,
        Decimal("13"),
        Decimal("520"),
        Decimal("5"),
        post_start_sell_date,
    )
    repo.add_cash_event(
        account.id,
        CashEventType.TRADE,
        Decimal("-1005"),
        order_id=buy_order.id,
        trade_id=buy_trade.id,
        trade_date=buy_date,
    )
    repo.add_cash_event(
        account.id,
        CashEventType.TRADE,
        Decimal("475"),
        order_id=pre_sell_order.id,
        trade_id=pre_sell_trade.id,
        trade_date=pre_start_sell_date,
    )
    repo.add_cash_event(
        account.id,
        CashEventType.TRADE,
        Decimal("515"),
        order_id=post_sell_order.id,
        trade_id=post_sell_trade.id,
        trade_date=post_start_sell_date,
    )
    account.realized_pnl = Decimal("190.0000")
    sqlite_session.commit()

    repo.clear_account_rebuild_state_from(account.id, start_date)

    lot = repo.get_lots(account.id, "a_share", "000001")[0]
    assert lot.remaining_quantity == 60
    rebuilt_account = repo.get_account(account.id)
    assert rebuilt_account is not None
    assert rebuilt_account.realized_pnl == Decimal("75.0000")
    assert [trade.id for trade in repo.list_trades(account.id)] == [buy_trade.id, pre_sell_trade.id]
    position = repo.get_position(account.id, "a_share", "000001")
    assert position is not None
    assert position.total_quantity == 60
    assert position.cost_amount == Decimal("600.0000")


def test_clear_account_rebuild_state_preserves_12_decimal_cost_and_pnl(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("precision-rebuild", Decimal("100000"))
    trade_date = date(2026, 6, 16)
    repo.create_position_lot(
        account.id,
        Market.A_SHARE,
        "000001.SZ",
        trade_date,
        3,
        3,
        Decimal("1.234567891234"),
        source="imported",
    )
    order = repo.create_order(
        account.id, "000001.SZ", OrderSide.SELL, 1, Decimal("1.345678912345"), trade_date, OrderStatus.FILLED
    )
    repo.create_trade(
        order.id,
        account.id,
        "000001.SZ",
        OrderSide.SELL,
        1,
        Decimal("1.345678912345"),
        Decimal("1.345678912345"),
        Decimal("0.000023456789"),
        trade_date,
    )

    repo.clear_account_rebuild_state_from(account.id, date(2026, 6, 17))

    rebuilt_account = repo.get_account(account.id)
    positions = repo.get_positions(account.id)
    assert rebuilt_account is not None
    assert rebuilt_account.realized_pnl == Decimal("0.111087564322")
    assert positions[0].cost_amount == Decimal("2.469135782468")


def test_clear_account_rebuild_state_preserves_initial_cash(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("demo", Decimal("100000"))
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 19),
        OrderStatus.FILLED,
    )
    trade = repo.create_trade(
        order.id,
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        Decimal("1000.0000"),
        Decimal("5.0000"),
        date(2026, 7, 19),
    )
    repo.add_cash_event(account.id, CashEventType.TRADE, Decimal("-1005.0000"), order_id=order.id, trade_id=trade.id)
    # Trade-derived position/lot — should be deleted by clear_account_rebuild_state
    repo.upsert_position(
        account.id,
        "a_share",
        "000001",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("1005.0000"),
        source="trade",
    )
    repo.create_position_lot(
        account.id, "a_share", "000001", date(2026, 7, 19), 100, 100, Decimal("10.00"), source="trade"
    )
    # Imported lot with remaining_quantity < original_quantity (simulating a sell reducing it)
    # This lot must be reset to original_quantity after clear.
    repo.create_position_lot(
        account.id,
        "a_share",
        "000002",
        date(2026, 7, 1),
        original_quantity=300,
        remaining_quantity=100,
        cost_price=Decimal("9.00"),
        source="imported",
    )
    # Imported aggregate position (may have been mutated by trades) — will be rebuilt from lots
    repo.upsert_position(
        account.id,
        "a_share",
        "000002",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("900.0000"),
        source="imported",
    )
    repo.save_snapshot(
        account_id=account.id,
        trade_date=date(2026, 7, 19),
        cash_available=Decimal("98995"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("1000"),
        total_assets=Decimal("99995"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=1,
        order_count=1,
        trade_count=1,
    )
    sqlite_session.commit()

    repo.clear_account_rebuild_state(account.id)

    assert repo.list_trades(account.id) == []
    # Trade-derived lot deleted
    assert repo.count_position_lots(account.id) == 1
    # Imported lot's remaining_quantity reset to original_quantity
    lots = repo.get_lots(account.id, "a_share", "000002")
    assert len(lots) == 1
    assert lots[0].remaining_quantity == 300
    assert lots[0].original_quantity == 300
    # All positions rebuilt from imported lots only
    positions = repo.get_positions(account.id)
    assert len(positions) == 1
    assert positions[0].symbol == "000002"
    assert positions[0].source == "imported"
    assert positions[0].total_quantity == 300
    assert positions[0].cost_amount == Decimal("2700.0000")  # 300 * 9.00
    snapshots = repo.list_snapshots(account.id)
    assert [snapshot.point_type for snapshot in snapshots] == [SnapshotPointType.INITIAL.value]
    ledger = repo.list_cash_ledger(account.id)
    assert len(ledger) == 1
    assert ledger[0].note == "initial_cash"
    assert Decimal(ledger[0].amount) == Decimal("100000.0000")


def test_clear_account_rebuild_state_resets_same_symbol_imported_after_trade(sqlite_session):
    """Imported position for a symbol is rebuilt from imported lots even when
    trade-derived lots for the same symbol existed."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("demo", Decimal("100000"))

    # Imported baseline: 200 shares @ 9.00
    repo.create_position_lot(
        account.id,
        "a_share",
        "000001",
        date(2026, 7, 1),
        original_quantity=200,
        remaining_quantity=200,
        cost_price=Decimal("9.00"),
        source="imported",
    )
    repo.upsert_position(
        account.id,
        "a_share",
        "000001",
        total_quantity=200,
        frozen_quantity=0,
        cost_amount=Decimal("1800.0000"),
        source="imported",
    )
    # Trade buy on same symbol: 100 shares @ 10.00 — mutates aggregate position
    repo.create_position_lot(
        account.id,
        "a_share",
        "000001",
        date(2026, 7, 19),
        original_quantity=100,
        remaining_quantity=100,
        cost_price=Decimal("10.00"),
        source="trade",
    )
    repo.upsert_position(
        account.id,
        "a_share",
        "000001",
        total_quantity=300,
        frozen_quantity=0,
        cost_amount=Decimal("2800.0000"),
        source="trade",
    )
    sqlite_session.commit()

    repo.clear_account_rebuild_state(account.id)

    # Trade lot deleted; imported lot reset to original_quantity
    lots = repo.get_lots(account.id, "a_share", "000001")
    assert len(lots) == 1
    assert lots[0].source == "imported"
    assert lots[0].remaining_quantity == 200
    # Position rebuilt from imported lot only
    positions = repo.get_positions(account.id)
    assert len(positions) == 1
    assert positions[0].symbol == "000001"
    assert positions[0].source == "imported"
    assert positions[0].total_quantity == 200
    assert positions[0].cost_amount == Decimal("1800.0000")


def test_rebuild_preserves_imported_hk_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-import", Decimal("100000"))
    repo.create_position_lot(
        account.id,
        "hk_connect",
        "00700",
        date(2026, 7, 1),
        original_quantity=100,
        remaining_quantity=100,
        cost_price=Decimal("400.00"),
        source="imported",
    )
    repo.upsert_position(
        account.id,
        "hk_connect",
        "00700",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("40000.0000"),
        source="imported",
    )
    sqlite_session.commit()

    repo.clear_account_rebuild_state(account.id)

    position = repo.get_position(account.id, "hk_connect", "00700")
    assert position is not None
    assert position.market == "hk_connect"


def test_rebuild_restores_same_symbol_imported_lots_by_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("mixed-import", Decimal("100000"))
    for market in ("a_share", "hk_connect"):
        repo.create_position_lot(
            account.id,
            market,
            "00700",
            date(2026, 7, 1),
            original_quantity=100,
            remaining_quantity=100,
            cost_price=Decimal("400.00"),
            source="imported",
        )
    repo.upsert_position(
        account.id,
        "a_share",
        "00700",
        total_quantity=200,
        frozen_quantity=0,
        cost_amount=Decimal("80000.0000"),
        source="imported",
    )
    sqlite_session.commit()

    repo.clear_account_rebuild_state(account.id)

    a_share_position = repo.get_position(account.id, "a_share", "00700")
    hk_connect_position = repo.get_position(account.id, "hk_connect", "00700")
    assert a_share_position is not None
    assert hk_connect_position is not None
    assert a_share_position.total_quantity == 100
    assert hk_connect_position.total_quantity == 100


def test_same_symbol_positions_and_lots_are_isolated_by_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("position-isolation", Decimal("100000"))

    repo.upsert_position(account.id, "a_share", "00700", 100, 0, Decimal("900"))
    repo.upsert_position(account.id, "hk_connect", "00700", 200, 0, Decimal("80000"))
    repo.create_position_lot(account.id, "a_share", "00700", date(2026, 7, 1), 100, 100, Decimal("9"))
    repo.create_position_lot(account.id, "hk_connect", "00700", date(2026, 7, 1), 200, 200, Decimal("400"))

    a_share_position = repo.get_position(account.id, "a_share", "00700")
    hk_connect_position = repo.get_position(account.id, "hk_connect", "00700")
    assert a_share_position is not None
    assert hk_connect_position is not None
    assert a_share_position.total_quantity == 100
    assert hk_connect_position.total_quantity == 200
    assert [lot.remaining_quantity for lot in repo.get_lots(account.id, "a_share", "00700")] == [100]
    assert [lot.remaining_quantity for lot in repo.get_lots(account.id, "hk_connect", "00700")] == [200]


def test_create_position_lot_requires_and_normalizes_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("lot-market", Decimal("100000"))

    lot = repo.create_position_lot(
        account.id,
        Market.HK_CONNECT,
        "00700",
        date(2026, 7, 1),
        100,
        100,
        Decimal("400"),
    )

    assert lot.market == "hk_connect"


def test_hk_diagnostic_does_not_select_same_symbol_a_share_order_for_rebuild(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("diagnostic-market", Decimal("100000"))
    order = repo.create_order(
        account.id,
        "00700",
        OrderSide.BUY,
        100,
        Decimal("10"),
        date(2026, 7, 1),
        OrderStatus.ACCEPTED,
        market="a_share",
    )
    repo.upsert_daily_bar_diagnostic(
        date(2026, 7, 1),
        "hk_connect",
        "00700",
        "bfq",
        "missing_exact_date",
        [],
        resolved=False,
    )

    assert repo.list_eligible_daily_bar_rebuild_orders() == []
    assert order.market == "a_share"


def test_eligible_daily_bar_rebuild_orders_include_only_a_share_bfq_missing_exact_date(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    first_account = repo.create_account("a-share-retry-first", Decimal("100000"))
    second_account = repo.create_account("a-share-retry-second", Decimal("100000"))
    etf_account = repo.create_account("etf-raw-diagnostic", Decimal("100000"))
    hk_account = repo.create_account("hk-retry", Decimal("100000"))
    non_accepted_account = repo.create_account("a-share-filled", Decimal("100000"))
    later_a_share_order = repo.create_order(
        second_account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("10.000"),
        date(2026, 8, 10),
        OrderStatus.ACCEPTED,
        market=Market.A_SHARE,
    )
    earliest_a_share_order = repo.create_order(
        first_account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.000"),
        date(2026, 8, 8),
        OrderStatus.ACCEPTED,
        market=Market.A_SHARE,
    )
    hk_order = repo.create_order(
        hk_account.id,
        "00700",
        OrderSide.BUY,
        100,
        Decimal("400.000"),
        date(2026, 8, 10),
        OrderStatus.ACCEPTED,
        market=Market.HK_CONNECT,
    )
    etf_order = repo.create_order(
        etf_account.id,
        "510300",
        OrderSide.BUY,
        100,
        Decimal("3.100"),
        date(2026, 8, 10),
        OrderStatus.ACCEPTED,
        market=Market.ETF,
    )
    filled_a_share_order = repo.create_order(
        non_accepted_account.id,
        "000003",
        OrderSide.BUY,
        100,
        Decimal("10.000"),
        date(2026, 8, 10),
        OrderStatus.FILLED,
        market=Market.A_SHARE,
    )
    repo.upsert_daily_bar_diagnostic(
        later_a_share_order.trade_date,
        Market.A_SHARE,
        later_a_share_order.symbol,
        "bfq",
        "missing_exact_date",
        [],
        resolved=False,
    )
    repo.upsert_daily_bar_diagnostic(
        earliest_a_share_order.trade_date,
        Market.A_SHARE,
        earliest_a_share_order.symbol,
        "bfq",
        "missing_exact_date",
        [],
        resolved=False,
    )
    repo.upsert_daily_bar_diagnostic(
        hk_order.trade_date, Market.HK_CONNECT, hk_order.symbol, "bfq", "missing_exact_date", [], resolved=False
    )
    repo.upsert_daily_bar_diagnostic(
        etf_order.trade_date, Market.ETF, etf_order.symbol, "raw", "missing_exact_date", [], resolved=False
    )
    repo.upsert_daily_bar_diagnostic(
        filled_a_share_order.trade_date,
        Market.A_SHARE,
        filled_a_share_order.symbol,
        "bfq",
        "missing_exact_date",
        [],
        resolved=False,
    )
    repo.upsert_daily_bar_diagnostic(
        later_a_share_order.trade_date,
        Market.A_SHARE,
        "000004",
        "qfq",
        "missing_exact_date",
        [],
        resolved=False,
    )
    repo.upsert_daily_bar_diagnostic(
        later_a_share_order.trade_date,
        Market.A_SHARE,
        "000005",
        "bfq",
        "downloaded",
        [{"provider": "market_data", "status": "downloaded"}],
        resolved=False,
    )

    assert [item.id for item in repo.list_eligible_daily_bar_rebuild_orders()] == [
        earliest_a_share_order.id,
        later_a_share_order.id,
    ]


def test_same_symbol_round_trips_are_isolated_by_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("round-trip-isolation", Decimal("100000"))

    for market in ("a_share", "hk_connect"):
        order = repo.create_order(
            account.id,
            "00700",
            OrderSide.BUY,
            100,
            Decimal("10"),
            date(2026, 7, 1),
            OrderStatus.FILLED,
            market=market,
        )
        trade = repo.create_trade(
            order.id,
            account.id,
            "00700",
            OrderSide.BUY,
            100,
            Decimal("10"),
            Decimal("1000"),
            Decimal("1"),
            date(2026, 7, 1),
            market=market,
        )
        repo.create_round_trip(account.id, market, "00700", trade.id, date(2026, 7, 1), Decimal("1000"), Decimal("1"))

    a_share_round_trip = repo.get_open_round_trip(account.id, "a_share", "00700")
    hk_connect_round_trip = repo.get_open_round_trip(account.id, "hk_connect", "00700")
    assert a_share_round_trip is not None
    assert hk_connect_round_trip is not None
    assert a_share_round_trip.market == "a_share"
    assert hk_connect_round_trip.market == "hk_connect"


def test_same_symbol_diagnostics_are_isolated_by_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    a_share = repo.upsert_daily_bar_diagnostic(
        business_date=date(2026, 7, 1),
        market="a_share",
        stock_id="00700",
        adjust="bfq",
        classification="missing_exact_date",
        provider_outcomes=[],
        resolved=False,
    )
    hk_connect = repo.upsert_daily_bar_diagnostic(
        business_date=date(2026, 7, 1),
        market="hk_connect",
        stock_id="00700",
        adjust="bfq",
        classification="missing_exact_date",
        provider_outcomes=[],
        resolved=False,
    )

    assert a_share.id != hk_connect.id
    assert repo.has_unresolved_daily_bar_diagnostic(date(2026, 7, 1), "a_share", "00700") is True
    assert repo.has_unresolved_daily_bar_diagnostic(date(2026, 7, 1), "hk_connect", "00700") is True


def test_reset_orders_for_replay_resets_replayable_statuses(sqlite_session):
    """Orders with ACCEPTED, FILLED, PARTIALLY_FILLED, NEW statuses get reset."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("demo", Decimal("100000"))

    # Create orders with various replayable statuses and rejection info set
    statuses = [
        OrderStatus.ACCEPTED,
        OrderStatus.FILLED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.NEW,
    ]
    orders = {}
    for i, status in enumerate(statuses):
        orders[status] = repo.create_order(
            account.id,
            f"00000{i}",
            OrderSide.BUY,
            100,
            Decimal("10.00"),
            date(2026, 7, 19),
            status,
            frozen_cash=Decimal("1005.0000"),
            rejection_code="REJ001" if status != OrderStatus.ACCEPTED else None,
            rejection_reason="some reason" if status != OrderStatus.ACCEPTED else None,
        )
        # Set filled_quantity via raw update since create_order doesn't expose it
        if status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED):
            orders[status].filled_quantity = 50
    sqlite_session.commit()

    repo.reset_orders_for_replay(account.id)

    for status, order in orders.items():
        reloaded = repo.get_order(order.id)
        assert reloaded.status == OrderStatus.ACCEPTED.value, f"{status} should reset to ACCEPTED"
        assert reloaded.filled_quantity == 0, f"{status} filled_quantity should be 0"
        assert reloaded.rejection_code is None, f"{status} rejection_code should be None"
        assert reloaded.rejection_reason is None, f"{status} rejection_reason should be None"


def test_reset_orders_for_replay_preserves_canceled_rejected(sqlite_session):
    """Orders with CANCELLED or REJECTED status remain unchanged."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("demo", Decimal("100000"))

    rejected = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 19),
        OrderStatus.REJECTED,
        frozen_cash=Decimal("0"),
        rejection_code="BAD_SYMBOL",
        rejection_reason="unknown symbol",
    )
    rejected.filled_quantity = 0
    cancelled = repo.create_order(
        account.id,
        "000002",
        OrderSide.SELL,
        50,
        Decimal("20.00"),
        date(2026, 7, 20),
        OrderStatus.CANCELLED,
        frozen_cash=Decimal("0"),
    )
    sqlite_session.commit()

    repo.reset_orders_for_replay(account.id)

    reloaded_rejected = repo.get_order(rejected.id)
    assert reloaded_rejected.status == OrderStatus.REJECTED.value
    assert reloaded_rejected.rejection_code == "BAD_SYMBOL"
    assert reloaded_rejected.rejection_reason == "unknown symbol"

    reloaded_cancelled = repo.get_order(cancelled.id)
    assert reloaded_cancelled.status == OrderStatus.CANCELLED.value
    assert reloaded_cancelled.rejection_code is None
    assert reloaded_cancelled.rejection_reason is None


def test_list_order_trade_dates_returns_sorted_distinct_dates(sqlite_session):
    """list_order_trade_dates returns distinct trade_dates sorted ascending."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("demo", Decimal("100000"))

    # Create orders with various trade dates including duplicates
    dates = [date(2026, 7, 21), date(2026, 7, 19), date(2026, 7, 20), date(2026, 7, 19), date(2026, 7, 22)]
    for i, d in enumerate(dates):
        repo.create_order(
            account.id,
            f"00000{i}",
            OrderSide.BUY,
            100,
            Decimal("10.00"),
            d,
            OrderStatus.ACCEPTED,
            frozen_cash=Decimal("1005.0000"),
        )
    sqlite_session.commit()

    result = repo.list_order_trade_dates(account.id)

    assert result == [date(2026, 7, 19), date(2026, 7, 20), date(2026, 7, 21), date(2026, 7, 22)]


def test_create_order_persists_market_default_a_share(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("market-demo", Decimal("100000.00"))
    order = repo.create_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
    )
    assert order.market == "a_share"


def test_create_order_persists_market_hk_connect(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("market-hk", Decimal("100000.00"))
    order = repo.create_order(
        account_id=account.id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("400.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
        market="hk_connect",
    )
    assert order.market == "hk_connect"


def test_create_trade_persists_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("trade-mkt", Decimal("100000.00"))
    order = repo.create_order(
        account_id=account.id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("400.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
        market="hk_connect",
    )
    trade = repo.create_trade(
        order_id=order.id,
        account_id=account.id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        price=Decimal("400.00"),
        amount=Decimal("40000.00"),
        fees=Decimal("100.00"),
        trade_date=date(2026, 7, 21),
        market="hk_connect",
    )
    assert trade.market == "hk_connect"


def test_position_persists_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("pos-mkt", Decimal("100000.00"))
    pos = repo.upsert_position(
        account_id=account.id,
        market="hk_connect",
        symbol="00700",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("40000.00"),
    )
    assert pos.market == "hk_connect"


def test_account_hk_fee_fields_default_to_none(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-fees", Decimal("100000.00"))
    assert account.hk_commission_rate is None
    assert account.hk_min_commission is None


def test_update_account_hk_fees_persists(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-fees-upd", Decimal("100000.00"))
    updated = repo.update_account_hk_fees(
        account.id,
        hk_commission_rate=Decimal("0.0002"),
        hk_min_commission=Decimal("18.00"),
        hk_stamp_duty_rate=Decimal("0.0013"),
        hk_trading_fee_rate=Decimal("0.0000565"),
        hk_sfc_levy_rate=Decimal("0.0000027"),
        hk_afrc_levy_rate=Decimal("0.0000015"),
        hk_settlement_fee_rate=Decimal("0.00002"),
    )
    assert updated is not None
    reloaded = repo.get_account(account.id)
    assert reloaded is not None
    assert reloaded.hk_commission_rate == Decimal("0.0002")
    assert reloaded.hk_stamp_duty_rate == Decimal("0.0013")


def test_create_pending_settlement(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("settle-demo", Decimal("100000.00"))
    pending = repo.create_pending_settlement(
        account_id=account.id,
        amount=Decimal("50000.00"),
        expected_settle_date=date(2026, 7, 23),
        trade_id=1,
        source="hk_sell",
    )
    assert pending.account_id == account.id
    assert pending.settled is False


def test_internal_cash_aggregations_preserve_sqlite_decimal_text(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    amount = Decimal("123456.789012345678")
    persisted_amount = Decimal("123456.789012346000")
    account = repo.create_account("aggregation-precision", amount)
    order = repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10"),
        date(2026, 8, 28),
        OrderStatus.ACCEPTED,
        frozen_cash=amount,
    )
    pending_amount = Decimal("123456.789012345678")
    persisted_pending_amount = Decimal("123456.789012346000")
    pending = repo.create_pending_settlement(
        account.id,
        pending_amount,
        date(2026, 8, 29),
        trade_id=1,
    )
    sqlite_session.commit()
    sqlite_session.expire_all()

    assert repo.get_cash_available_internal(account.id) == persisted_amount
    assert repo.get_cash_available(account.id) == persisted_amount.quantize(Decimal("0.0001"))
    assert repo.get_cash_frozen_internal(account.id) == persisted_amount
    assert repo.get_pending_settlement_total_internal(account.id) == persisted_pending_amount
    assert order.frozen_cash == Decimal("123456.789012345675")
    assert repo.session.query(PaperPendingSettlement.amount).filter_by(id=pending.id).scalar() == Decimal(
        "123456.789012345675"
    )


def test_cash_available_as_of_internal_preserves_adjacent_decimal_boundary(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("as-of-precision", Decimal("100.000000000001"))
    repo.add_cash_event(
        account.id,
        CashEventType.TRADE,
        Decimal("0.000000000001"),
        trade_date=date(2026, 8, 28),
    )

    assert repo.get_cash_available_as_of_internal(account.id, date(2026, 8, 27)) == Decimal("100.000000000001")
    assert repo.get_cash_available_as_of_internal(account.id, date(2026, 8, 28)) == Decimal("100.000000000002")


def test_settle_pending_releases_cash(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("settle-rel", Decimal("100000.00"))
    pending = repo.create_pending_settlement(
        account_id=account.id,
        amount=Decimal("50000.00"),
        expected_settle_date=date(2026, 7, 23),
        trade_id=1,
        source="hk_sell",
    )
    repo.settle_pending(pending.id)
    assert pending.settled is True


def test_settle_pending_preserves_sqlite_high_precision_amount(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("settle-precision", Decimal("0.01"))
    logical_amount = Decimal("123456.789012346000")
    pending = repo.create_pending_settlement(
        account_id=account.id,
        amount=logical_amount,
        expected_settle_date=date(2026, 8, 29),
        trade_id=1,
        source="hk_sell",
    )
    sqlite_session.commit()
    sqlite_session.expire_all()

    repo.settle_pending(pending.id)
    ledger_amount = repo.session.query(sa_cast(PaperCashLedger.amount, String)).filter_by(trade_id=1).scalar()

    assert Decimal(str(ledger_amount)) == logical_amount
    assert repo.get_cash_available_internal(account.id) == Decimal("0.01") + logical_amount
    assert pending.settled is True
    assert repo.get_pending_settlement_total_internal(account.id) == Decimal("0")
