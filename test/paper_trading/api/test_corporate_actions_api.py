from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_market_data_provider, get_session
from paper_trading.domain.enums import CorporateActionType
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


class _MarketData:
    def get_daily_bar(self, symbol, trade_date):
        return Decimal("10")

    def is_trade_date(self, trade_date):
        return trade_date.weekday() < 5


def _client(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    app.dependency_overrides[get_market_data_provider] = lambda: _MarketData()
    return TestClient(app), {"Authorization": "Bearer secret"}, PaperTradingRepository(sqlite_session)


def _payload(action_type: str, key: str = "key-1") -> dict:
    parameters = {
        "dividend": {"per_share_amount": "1"},
        "split": {"ratio": "2"},
        "reverse_split": {"ratio": "0.5"},
        "bonus_share": {"bonus_ratio": "0.1"},
        "rights_issue": {"subscription_ratio": "0.1", "subscription_price": "5"},
    }[action_type]
    return {
        "symbol": "000001.SZ",
        "event_type": action_type,
        "event_at": "2026-09-02T09:30:00+08:00",
        "idempotency_key": key,
        "parameters": parameters,
    }


def _set_creation_baseline(repo, account_id: int, event_at: datetime) -> None:
    account = repo.get_account(account_id)
    if account is None:
        raise AssertionError(f"account {account_id} was not created")
    account.created_at = event_at
    initial_snapshot = next(row for row in repo.list_snapshots(account_id) if row.point_type == "initial")
    initial_snapshot.event_at = event_at
    initial_snapshot.trade_date = event_at.date()
    initial_cash = repo.list_cash_ledger(account_id)[0]
    initial_cash.occurred_at = event_at
    initial_cash.trade_date = event_at.date()


@pytest.mark.parametrize("action_type", [item.value for item in CorporateActionType])
def test_create_corporate_action_returns_event_impact_and_recalculation(monkeypatch, sqlite_session, action_type):
    client, headers, repo = _client(monkeypatch, sqlite_session)
    account = repo.create_account(f"corporate-{action_type}", Decimal("100000"))
    _set_creation_baseline(repo, account.id, datetime(2026, 8, 1, 9, tzinfo=timezone.utc))
    sqlite_session.commit()

    response = client.post(
        f"/paper/accounts/{account.id}/corporate-actions",
        json=_payload(action_type),
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["event"]["event_type"] == action_type
    assert body["event"]["processing_status"] == "completed"
    assert body["event"]["account_id"] == account.id
    assert Decimal(body["impact"]["before_quantity"]) == Decimal("0")
    assert len(body["impact"]["cash_delta"].split(".")[1]) == 4
    assert set(body["recalculation"]) == {"account_id", "updated_dates", "unavailable_dates", "failed_dates", "errors"}


@pytest.mark.parametrize(
    "payload",
    [
        {"extra": True},
        {"event_at": "2026-08-20T09:30:00", "parameters": {"per_share_amount": "1"}},
        {"parameters": {"per_share_amount": "0"}},
        {"parameters": {"per_share_amount": "-1"}},
        {"parameters": {"per_share_amount": "NaN"}},
    ],
)
def test_create_corporate_action_rejects_invalid_payload(monkeypatch, sqlite_session, payload):
    client, headers, repo = _client(monkeypatch, sqlite_session)
    account = repo.create_account("corporate-invalid", Decimal("100000"))
    sqlite_session.commit()
    request = _payload("dividend")
    request.update(payload)

    response = client.post(
        f"/paper/accounts/{account.id}/corporate-actions",
        json=request,
        headers=headers,
    )

    assert response.status_code == 422


def test_corporate_action_errors_and_list_filters(monkeypatch, sqlite_session):
    client, headers, repo = _client(monkeypatch, sqlite_session)
    account = repo.create_account("corporate-list", Decimal("100000"))
    _set_creation_baseline(repo, account.id, datetime(2026, 8, 1, 9, tzinfo=timezone.utc))
    sqlite_session.commit()
    missing = client.post("/paper/accounts/999/corporate-actions", json=_payload("dividend"), headers=headers)
    assert missing.status_code == 404

    first = _payload("dividend", "same-key")
    created = client.post(f"/paper/accounts/{account.id}/corporate-actions", json=first, headers=headers)
    assert created.status_code == 200, created.text
    conflict = _payload("dividend", "same-key")
    conflict["parameters"] = {"per_share_amount": "2"}
    assert (
        client.post(f"/paper/accounts/{account.id}/corporate-actions", json=conflict, headers=headers).status_code
        == 409
    )

    second = _payload("split", "split-key")
    second["event_at"] = "2026-09-03T01:30:00Z"
    assert (
        client.post(f"/paper/accounts/{account.id}/corporate-actions", json=second, headers=headers).status_code == 200
    )
    start = "2026-09-02T01:30:00Z"
    end = "2026-09-03T01:30:00Z"
    response = client.get(
        f"/paper/accounts/{account.id}/corporate-actions",
        params={"symbol": "000001.SZ", "start_at": start, "end_at": end, "event_type": "split"},
        headers=headers,
    )
    assert response.status_code == 200
    assert [item["event_type"] for item in response.json()] == ["split"]


def test_corporate_action_before_baseline_is_rejected(monkeypatch, sqlite_session):
    client, headers, repo = _client(monkeypatch, sqlite_session)
    account = repo.create_account("corporate-before-baseline", Decimal("100000"))
    _set_creation_baseline(repo, account.id, datetime(2026, 8, 20, 9, tzinfo=timezone.utc))
    sqlite_session.commit()

    request = _payload("dividend")
    request["event_at"] = "2026-08-10T09:30:00+08:00"

    response = client.post(
        f"/paper/accounts/{account.id}/corporate-actions",
        json=request,
        headers=headers,
    )

    assert response.status_code == 422
    assert "proven baseline" in response.json()["detail"]
    assert repo.list_corporate_actions(account.id) == []


@pytest.mark.parametrize(
    ("action_type", "parameters"),
    [
        ("dividend", {"ratio": "1"}),
        ("split", {"ratio": "1", "extra": "1"}),
        ("reverse_split", {"ratio": "1"}),
        ("bonus_share", {}),
        ("rights_issue", {"subscription_ratio": "1"}),
    ],
)
def test_each_corporate_action_requires_exact_parameter_contract(monkeypatch, sqlite_session, action_type, parameters):
    client, headers, repo = _client(monkeypatch, sqlite_session)
    account = repo.create_account("corporate-parameters", Decimal("100000"))
    sqlite_session.commit()
    request = _payload(action_type)
    request["parameters"] = parameters

    response = client.post(f"/paper/accounts/{account.id}/corporate-actions", json=request, headers=headers)

    assert response.status_code == 422


@pytest.mark.parametrize("ratio", ["1", "1.000000000001", "Infinity", "NaN"])
def test_reverse_split_requires_finite_ratio_below_one(monkeypatch, sqlite_session, ratio):
    client, headers, repo = _client(monkeypatch, sqlite_session)
    account = repo.create_account("corporate-reverse-split", Decimal("100000"))
    sqlite_session.commit()
    request = _payload("reverse_split")
    request["parameters"]["ratio"] = ratio

    response = client.post(f"/paper/accounts/{account.id}/corporate-actions", json=request, headers=headers)

    assert response.status_code == 422


def test_corporate_action_rejects_unknown_types_invalid_market_and_long_idempotency_key(monkeypatch, sqlite_session):
    client, headers, repo = _client(monkeypatch, sqlite_session)
    account = repo.create_account("corporate-contracts", Decimal("100000"))
    sqlite_session.commit()
    for field, value in (("event_type", "unknown"), ("market", "unknown")):
        request = _payload("dividend")
        request[field] = value
        response = client.post(f"/paper/accounts/{account.id}/corporate-actions", json=request, headers=headers)
        assert response.status_code == 422

    request = _payload("dividend")
    request["idempotency_key"] = "x" * 101
    response = client.post(f"/paper/accounts/{account.id}/corporate-actions", json=request, headers=headers)
    assert response.status_code == 422


def test_corporate_action_list_rejects_naive_bound_timestamps(monkeypatch, sqlite_session):
    client, headers, repo = _client(monkeypatch, sqlite_session)
    account = repo.create_account("corporate-list-timezone", Decimal("100000"))
    sqlite_session.commit()

    response = client.get(
        f"/paper/accounts/{account.id}/corporate-actions",
        params={"start_at": "2026-08-20T01:30:00"},
        headers=headers,
    )

    assert response.status_code == 422
