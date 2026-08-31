from datetime import date, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_session
from paper_trading.api.routers import analytics as analytics_router
from paper_trading.domain.enums import (
    MigrationRepairReason,
    OrderSide,
    OrderStatus,
    SnapshotPointType,
    SnapshotQualityStatus,
)
from paper_trading.services.analytics_service import AnalyticsService
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def test_get_account_analytics_returns_execution_group(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("api-analytics", Decimal("100000.00"))
    sqlite_session.commit()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    client = TestClient(app)

    response = client.get(f"/paper/accounts/{account.id}/analytics", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution"]["order_count"] == 0
    assert payload["execution"]["fill_rate"]["reason"] == "insufficient_data"
    assert payload["execution"]["fill_rate"]["value"] is None
    assert payload["execution"]["rejection_rate"]["reason"] == "insufficient_data"
    assert payload["execution"]["rejection_rate"]["value"] is None
    assert payload["trade_quality"]["closed_count"] == 0
    assert payload["risk"]["sharpe"]["reason"] == "insufficient_data"
    assert payload["activity"] is None
    assert "activity_daily" not in payload
    assert "activity_weekly" not in payload
    assert "activity_monthly" not in payload


def test_get_account_analytics_returns_activity_contract_for_populated_account(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    monkeypatch.setattr(
        analytics_router,
        "AnalyticsService",
        lambda repo: AnalyticsService(repo, today_provider=lambda: date(2026, 8, 20)),
    )
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("api-analytics-populated", Decimal("100000.00"))
    repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 8, 20),
        OrderStatus.ACCEPTED,
    )
    sqlite_session.commit()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    client = TestClient(app)

    response = client.get(f"/paper/accounts/{account.id}/analytics", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    payload = response.json()
    assert set(payload["activity"]) == {"coverage_start", "coverage_end", "daily", "weekly", "monthly"}
    assert payload["activity"]["coverage_start"] == "2026-08-20"
    assert payload["activity"]["coverage_end"] == "2026-08-20"
    assert set(payload["activity"]["daily"]) == {"total_orders", "successful_orders", "failed_orders"}
    assert payload["activity"]["daily"] == {
        "total_orders": "1.000000",
        "successful_orders": "0.000000",
        "failed_orders": "0.000000",
    }


def _seed_trading_snapshot(repo, account, *, nav: Decimal | None, total_assets: Decimal, quality_status: str) -> None:
    event_at = repo.list_snapshots(account.id)[-1].event_at + timedelta(days=1)
    if event_at.tzinfo is None:
        event_at = event_at.replace(tzinfo=timezone.utc)
    repo.save_snapshot(
        account_id=account.id,
        trade_date=event_at.date(),
        event_at=event_at,
        point_type=SnapshotPointType.TRADING.value,
        quality_status=quality_status,
        invalid_reason=None if quality_status == SnapshotQualityStatus.VALID.value else "missing_nav",
        cash_available=total_assets,
        cash_frozen=Decimal("0"),
        market_value=Decimal("0"),
        total_assets=total_assets,
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=0,
        order_count=0,
        trade_count=0,
        net_asset_value=nav,
    )


def test_get_account_analytics_uses_persisted_nav_not_total_assets(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("api-nav-series", Decimal("100000.00"))
    _seed_trading_snapshot(
        repo,
        account,
        nav=Decimal("1.100000"),
        total_assets=Decimal("250000.0000"),
        quality_status=SnapshotQualityStatus.VALID.value,
    )
    sqlite_session.commit()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    client = TestClient(app)

    response = client.get(f"/paper/accounts/{account.id}/analytics", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["overview"]["total_return"]["value"] == "0.100000"
    assert payload["overview"]["simple_asset_return"]["value"] == "1.500000"
    assert payload["risk"]["max_drawdown"]["value"] == "0.000000"


def test_get_account_analytics_keeps_stale_valid_snapshot_in_nav(monkeypatch, sqlite_session):
    client, headers, repo = _analytics_client(monkeypatch, sqlite_session)
    account = repo.create_account("api-stale-valid", Decimal("100000.00"))
    snapshot = repo.list_snapshots(account.id)[0]
    snapshot.valuation_quality = "stale_suspended"
    sqlite_session.commit()

    response = client.get(f"/paper/accounts/{account.id}/analytics", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["overview"]["total_return"]["reason"] == "insufficient_data"
    assert payload["overview"]["net_asset_value"] == "1.000000"
    assert payload["risk"]["max_drawdown"]["reason"] == "insufficient_data"


def test_get_account_analytics_does_not_turn_unresolved_gap_into_nav_or_metrics(monkeypatch, sqlite_session):
    client, headers, repo = _analytics_client(monkeypatch, sqlite_session)
    account = repo.create_account("api-unresolved-gap", Decimal("100000.00"))
    repo.upsert_valuation_gap(account.id, date(2026, 8, 25), ["000001.SZ"], [{"reason": "no bar"}])
    sqlite_session.commit()

    response = client.get(f"/paper/accounts/{account.id}/analytics", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["valuation_gaps"][0]["resolved"] is False
    assert payload["overview"]["total_return"]["reason"] == "insufficient_data"
    assert payload["overview"]["net_asset_value"] == "1.000000"
    assert payload["risk"]["max_drawdown"]["reason"] == "insufficient_data"
    assert payload["risk"]["sharpe"]["value"] is None


def test_get_account_analytics_returns_date_ordered_valuation_gaps(monkeypatch, sqlite_session):
    client, headers, repo = _analytics_client(monkeypatch, sqlite_session)
    account = repo.create_account("api-valuation-gaps", Decimal("100000.00"))
    repo.upsert_valuation_gap(account.id, date(2026, 8, 26), ["000002.SZ"], [{"reason": "later"}])
    repo.upsert_valuation_gap(account.id, date(2026, 8, 25), ["000001.SZ"], [{"reason": "earlier"}])
    repo.upsert_valuation_gap(account.id, date(2026, 8, 27), [], [], resolved=True)
    sqlite_session.commit()

    response = client.get(f"/paper/accounts/{account.id}/analytics", headers=headers)

    assert response.status_code == 200
    assert response.json()["valuation_gaps"] == [
        {
            "trade_date": "2026-08-25",
            "missing_symbols": ["000001.SZ"],
            "details": [{"reason": "earlier"}],
            "resolved": False,
        },
        {
            "trade_date": "2026-08-26",
            "missing_symbols": ["000002.SZ"],
            "details": [{"reason": "later"}],
            "resolved": False,
        },
        {"trade_date": "2026-08-27", "missing_symbols": [], "details": [], "resolved": True},
    ]


def test_get_account_analytics_ignores_invalid_nav_and_does_not_derive_from_assets(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("api-invalid-nav", Decimal("100000.00"))
    _seed_trading_snapshot(
        repo,
        account,
        nav=None,
        total_assets=Decimal("80000.0000"),
        quality_status=SnapshotQualityStatus.INVALID.value,
    )
    sqlite_session.commit()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    client = TestClient(app)

    response = client.get(f"/paper/accounts/{account.id}/analytics", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["overview"]["total_return"]["reason"] == "valuation_gap"
    assert payload["overview"]["simple_asset_return"]["value"] == "-0.200000"
    assert payload["risk"]["max_drawdown"]["reason"] == "valuation_gap"
    assert payload["overview"]["net_asset_value"] is None
    assert payload["overview"]["total_assets"] == "80000.0000"
    assert payload["overview"]["cash_available"] == "80000.0000"


def _analytics_client(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    return TestClient(app), {"Authorization": "Bearer secret"}, PaperTradingRepository(sqlite_session)


def test_get_account_analytics_marks_normal_payload_available(monkeypatch, sqlite_session):
    client, headers, repo = _analytics_client(monkeypatch, sqlite_session)
    account = repo.create_account("api-available", Decimal("100000.00"))
    sqlite_session.commit()

    response = client.get(f"/paper/accounts/{account.id}/analytics", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert "overview" in payload
    assert "reason" not in payload


def test_get_account_analytics_returns_unavailable_for_repair_marked_account(monkeypatch, sqlite_session):
    client, headers, repo = _analytics_client(monkeypatch, sqlite_session)
    account = repo.create_account("api-repair-unavailable", Decimal("100000.00"))
    account.migration_repair_reason = MigrationRepairReason.LEGACY_ORDERING_UNCERTAIN.value
    sqlite_session.commit()

    response = client.get(f"/paper/accounts/{account.id}/analytics", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"available": False, "reason": "legacy_ordering_uncertain"}


def test_get_account_analytics_unknown_account_returns_404(monkeypatch, sqlite_session):
    client, headers, _ = _analytics_client(monkeypatch, sqlite_session)

    response = client.get("/paper/accounts/999/analytics", headers=headers)

    assert response.status_code == 404
    assert "paper account not found: 999" in str(response.json()["detail"])


@pytest.mark.parametrize("initial_cash", ["0", "-1"])
def test_create_account_for_analytics_rejects_non_positive_initial_cash(monkeypatch, sqlite_session, initial_cash):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    client = TestClient(app)

    response = client.post(
        "/paper/accounts",
        json={"name": "zero-cash-analytics", "initial_cash": initial_cash},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 422


def test_get_account_analytics_exposes_typed_event_series(monkeypatch, sqlite_session):
    client, headers, repo = _analytics_client(monkeypatch, sqlite_session)
    account = repo.create_account("api-event-series", Decimal("100000.00"))
    repo.add_cash_event(
        account.id,
        "deposit",
        Decimal("25000.0000"),
        trade_date=date(2026, 8, 20),
        net_asset_value=Decimal("1.000000"),
        share_delta=Decimal("25000.000000"),
        occurred_at=account.created_at.replace(tzinfo=timezone.utc) + timedelta(days=1),
    )
    sqlite_session.commit()

    response = client.get(f"/paper/accounts/{account.id}/analytics", headers=headers)

    assert response.status_code == 200
    series = response.json()["event_series"]
    assert [event["event_type"] for event in series] == ["snapshot", "deposit"]
    assert series[0]["point_type"] == "initial"
    assert series[1]["effective_nav"] == "1.000000"


def test_get_account_analytics_exposes_shared_nav_point_metadata(monkeypatch, sqlite_session):
    client, headers, repo = _analytics_client(monkeypatch, sqlite_session)
    account = repo.create_account("api-shared-nav-metadata", Decimal("100000.00"))
    initial = repo.list_snapshots(account.id)[0]
    initial.event_time_provenance = "canonical_utc"
    sqlite_session.commit()

    response = client.get(f"/paper/accounts/{account.id}/analytics", headers=headers)

    assert response.status_code == 200
    snapshot = response.json()["event_series"][0]
    assert snapshot["point_type"] == "initial"
    assert snapshot["quality"] == "valid"
    assert snapshot["timezone"] == "UTC"
    assert snapshot["nav"] == "1.000000"
    assert snapshot["share"] == "100000.000000"
