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
        "event_at": "2026-08-20T09:30:00+08:00",
        "idempotency_key": key,
        "parameters": parameters,
    }


@pytest.mark.parametrize("action_type", [item.value for item in CorporateActionType])
def test_create_corporate_action_returns_event_impact_and_recalculation(monkeypatch, sqlite_session, action_type):
    client, headers, repo = _client(monkeypatch, sqlite_session)
    account = repo.create_account(f"corporate-{action_type}", Decimal("100000"))
    sqlite_session.commit()

    response = client.post(
        f"/paper/accounts/{account.id}/corporate-actions",
        json=_payload(action_type),
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["event"]["event_type"] == action_type
    assert body["event"]["account_id"] == account.id
    assert Decimal(body["impact"]["before_quantity"]) == Decimal("0")
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
    second["event_at"] = "2026-08-21T01:30:00Z"
    assert (
        client.post(f"/paper/accounts/{account.id}/corporate-actions", json=second, headers=headers).status_code == 200
    )
    start = "2026-08-20T01:30:00Z"
    end = "2026-08-21T01:30:00Z"
    response = client.get(
        f"/paper/accounts/{account.id}/corporate-actions",
        params={"symbol": "000001.SZ", "start_at": start, "end_at": end, "event_type": "split"},
        headers=headers,
    )
    assert response.status_code == 200
    assert [item["event_type"] for item in response.json()] == ["split"]
