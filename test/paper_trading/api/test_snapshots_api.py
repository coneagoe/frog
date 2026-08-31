from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_session
from paper_trading.domain.enums import MigrationRepairReason, SnapshotPointType, SnapshotQualityStatus
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def _client(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    return TestClient(app), {"Authorization": "Bearer secret"}, sqlite_session


def _seed_trading_point(
    repo: PaperTradingRepository,
    account_id: int,
    *,
    event_at: datetime,
    quality_status: str,
    invalid_reason: str | None,
    nav: Decimal | None,
    total_assets: Decimal,
    trade_date: date | None = None,
):
    return repo.save_snapshot(
        account_id=account_id,
        trade_date=event_at.date() if trade_date is None else trade_date,
        event_at=event_at,
        point_type=SnapshotPointType.TRADING.value,
        quality_status=quality_status,
        invalid_reason=invalid_reason,
        cash_available=total_assets,
        cash_frozen=Decimal("0.0000"),
        market_value=Decimal("0.0000"),
        total_assets=total_assets,
        realized_pnl=Decimal("0.0000"),
        unrealized_pnl=Decimal("0.0000"),
        position_count=0,
        order_count=0,
        trade_count=0,
        net_asset_value=nav,
    )


def _assert_iso8601_offset(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() is not None
    return parsed


def test_snapshots_api_returns_ordered_nav_point_metadata(monkeypatch, sqlite_session):
    client, headers, session = _client(monkeypatch, sqlite_session)
    repo = PaperTradingRepository(session)
    account = repo.create_account("nav-series", Decimal("100000.00"))
    initial = repo.list_snapshots(account.id)[0]
    day = datetime(2026, 8, 25, tzinfo=timezone.utc)
    initial.event_at = day.replace(hour=1)
    initial.trade_date = day.date()
    valid = _seed_trading_point(
        repo,
        account.id,
        event_at=day.replace(hour=10),
        quality_status=SnapshotQualityStatus.VALID.value,
        invalid_reason=None,
        nav=Decimal("1.100000"),
        total_assets=Decimal("110000.0000"),
        trade_date=day.date(),
    )
    invalid = _seed_trading_point(
        repo,
        account.id,
        event_at=day.replace(hour=15),
        quality_status=SnapshotQualityStatus.INVALID.value,
        invalid_reason="missing_nav",
        nav=None,
        total_assets=Decimal("250000.0000"),
        trade_date=date(2026, 8, 26),
    )
    session.commit()

    response = client.get(f"/paper/accounts/{account.id}/snapshots", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert [(item["point_type"], item["quality_status"]) for item in payload] == [
        ("initial", "valid"),
        ("trading", "valid"),
        ("trading", "invalid"),
    ]
    assert all("event_at" in item and "id" in item for item in payload)
    assert [item["id"] for item in payload] == [initial.id, valid.id, invalid.id]
    assert {item["trade_date"] for item in payload} == {"2026-08-25", "2026-08-26"}
    event_times = [_assert_iso8601_offset(item["event_at"]) for item in payload]
    assert event_times == [
        day.replace(hour=1),
        day.replace(hour=10),
        day.replace(hour=15),
    ]
    assert all(item["timezone"] == "UTC" for item in payload)
    assert payload[1]["net_asset_value"] == "1.100000"
    assert payload[2]["quality_status"] == "invalid"
    assert payload[2]["invalid_reason"] == "missing_nav"
    assert payload[2]["net_asset_value"] is None
    assert payload[2]["total_assets"] == "250000.0000"
    assert all(item["valuation_quality"] is None for item in payload)
    assert all(item["valuation_details"] is None for item in payload)


def test_snapshots_api_preserves_nullable_money_fields_for_initial_and_legacy_snapshots(monkeypatch, sqlite_session):
    client, headers, session = _client(monkeypatch, sqlite_session)
    repo = PaperTradingRepository(session)
    account = repo.create_account("nullable-snapshot-money", Decimal("100000.00"))
    initial = repo.list_snapshots(account.id)[0]
    legacy = _seed_trading_point(
        repo,
        account.id,
        event_at=datetime(2026, 8, 25, 10, tzinfo=timezone.utc),
        quality_status=SnapshotQualityStatus.VALID.value,
        invalid_reason=None,
        nav=Decimal("1.123456789"),
        total_assets=Decimal("112345.67891"),
    )
    for snapshot in (initial, legacy):
        snapshot.cumulative_deposit = None
        snapshot.cumulative_withdrawal = None
        snapshot.net_cash_flow = None
    session.commit()

    response = client.get(f"/paper/accounts/{account.id}/snapshots", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    for item in payload:
        assert item["cumulative_deposit"] is None
        assert item["cumulative_withdrawal"] is None
        assert item["net_cash_flow"] is None
    snapshots = {item["point_type"]: item for item in payload}
    assert snapshots["initial"]["total_assets"] == "100000.0000"
    assert snapshots["initial"]["net_asset_value"] == "1.000000"
    assert snapshots["trading"]["total_assets"] == "112345.6789"
    assert snapshots["trading"]["net_asset_value"] == "1.123457"


def test_snapshots_api_serializes_stale_valuation_metadata(monkeypatch, sqlite_session):
    client, headers, session = _client(monkeypatch, sqlite_session)
    repo = PaperTradingRepository(session)
    account = repo.create_account("stale-nav", Decimal("100000.00"))
    initial = repo.list_snapshots(account.id)[0]
    day = datetime(2026, 8, 25, tzinfo=timezone.utc)
    initial.event_at = day.replace(hour=1)
    initial.trade_date = day.date()
    stale = _seed_trading_point(
        repo,
        account.id,
        event_at=day.replace(hour=10),
        quality_status=SnapshotQualityStatus.VALID.value,
        invalid_reason=None,
        nav=Decimal("1.100000"),
        total_assets=Decimal("110000.0000"),
    )
    stale.valuation_quality = "stale_suspended"
    stale.valuation_details = [{"symbol": "000001.SZ", "source_date": "2026-08-22", "reason": "suspended"}]
    session.commit()

    response = client.get(f"/paper/accounts/{account.id}/snapshots", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["valuation_quality"] is None
    assert payload[0]["valuation_details"] is None
    assert payload[1]["id"] == stale.id
    assert payload[1]["valuation_quality"] == "stale_suspended"
    assert payload[1]["valuation_details"] == [
        {"symbol": "000001.SZ", "source_date": "2026-08-22", "reason": "suspended"}
    ]


def test_snapshots_api_preserves_repository_order_for_same_day_and_tied_event_at(monkeypatch, sqlite_session):
    client, headers, session = _client(monkeypatch, sqlite_session)
    repo = PaperTradingRepository(session)
    account = repo.create_account("same-time-order", Decimal("100000.00"))
    initial = repo.list_snapshots(account.id)[0]
    tied = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
    later = datetime(2026, 8, 25, 15, 0, tzinfo=timezone.utc)
    initial.event_at = datetime(2026, 8, 25, 1, 0, tzinfo=timezone.utc)
    initial.trade_date = tied.date()
    later_point = _seed_trading_point(
        repo,
        account.id,
        event_at=later,
        quality_status=SnapshotQualityStatus.VALID.value,
        invalid_reason=None,
        nav=Decimal("1.200000"),
        total_assets=Decimal("120000.0000"),
        trade_date=date(2026, 8, 27),
    )
    first_tied = _seed_trading_point(
        repo,
        account.id,
        event_at=tied,
        quality_status=SnapshotQualityStatus.VALID.value,
        invalid_reason=None,
        nav=Decimal("1.050000"),
        total_assets=Decimal("105000.0000"),
        trade_date=date(2026, 8, 25),
    )
    second_tied = _seed_trading_point(
        repo,
        account.id,
        event_at=tied,
        quality_status=SnapshotQualityStatus.INVALID.value,
        invalid_reason="missing_nav",
        nav=None,
        total_assets=Decimal("999999.0000"),
        trade_date=date(2026, 8, 26),
    )
    session.commit()

    expected_ids = [row.id for row in repo.list_snapshots(account.id)]
    response = client.get(f"/paper/accounts/{account.id}/snapshots", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert expected_ids == [initial.id, first_tied.id, second_tied.id, later_point.id]
    assert [item["id"] for item in payload] == expected_ids
    assert first_tied.id < second_tied.id
    assert payload[2]["invalid_reason"] == "missing_nav"
    assert payload[2]["net_asset_value"] is None
    assert payload[2]["total_assets"] == "999999.0000"
    assert all(_assert_iso8601_offset(item["event_at"]) for item in payload)


def test_snapshots_api_keeps_event_at_id_order_for_repair_marked_account(monkeypatch, sqlite_session):
    client, headers, session = _client(monkeypatch, sqlite_session)
    repo = PaperTradingRepository(session)
    account = repo.create_account("repair-snapshots", Decimal("100000.00"))
    initial = repo.list_snapshots(account.id)[0]
    tied = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
    later = datetime(2026, 8, 25, 15, 0, tzinfo=timezone.utc)
    initial.event_at = datetime(2026, 8, 25, 1, 0, tzinfo=timezone.utc)
    initial.trade_date = tied.date()
    later_point = _seed_trading_point(
        repo,
        account.id,
        event_at=later,
        quality_status=SnapshotQualityStatus.VALID.value,
        invalid_reason=None,
        nav=Decimal("1.200000"),
        total_assets=Decimal("120000.0000"),
        trade_date=date(2026, 8, 27),
    )
    first_tied = _seed_trading_point(
        repo,
        account.id,
        event_at=tied,
        quality_status=SnapshotQualityStatus.VALID.value,
        invalid_reason=None,
        nav=Decimal("1.050000"),
        total_assets=Decimal("105000.0000"),
        trade_date=date(2026, 8, 25),
    )
    second_tied = _seed_trading_point(
        repo,
        account.id,
        event_at=tied,
        quality_status=SnapshotQualityStatus.INVALID.value,
        invalid_reason="missing_nav",
        nav=None,
        total_assets=Decimal("999999.0000"),
        trade_date=date(2026, 8, 26),
    )
    account.migration_repair_reason = MigrationRepairReason.LEGACY_ORDERING_UNCERTAIN.value
    session.commit()

    expected_ids = [row.id for row in repo.list_snapshots(account.id)]
    response = client.get(f"/paper/accounts/{account.id}/snapshots", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert expected_ids == [initial.id, first_tied.id, second_tied.id, later_point.id]
    assert [item["id"] for item in payload] == expected_ids
    assert first_tied.id < second_tied.id
    assert all(_assert_iso8601_offset(item["event_at"]) for item in payload)
