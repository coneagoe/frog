from fastapi.testclient import TestClient

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_session
from storage.model.base import Base


def _client(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app), {"Authorization": "Bearer secret"}


def test_delete_account_removes_account_from_list(monkeypatch, sqlite_session):
    client, headers = _client(monkeypatch, sqlite_session)
    account_response = client.post(
        "/paper/accounts",
        json={"name": "demo", "initial_cash": "100000.00"},
        headers=headers,
    )
    account_id = account_response.json()["id"]

    response = client.delete(f"/paper/accounts/{account_id}", headers=headers)

    assert response.status_code == 204
    assert response.content == b""
    list_response = client.get("/paper/accounts", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_delete_missing_account_returns_404(monkeypatch, sqlite_session):
    client, headers = _client(monkeypatch, sqlite_session)

    response = client.delete("/paper/accounts/999", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "paper account not found: 999"


def test_create_account_accepts_and_returns_fee_config(monkeypatch, sqlite_session):
    client, headers = _client(monkeypatch, sqlite_session)

    response = client.post(
        "/paper/accounts",
        json={
            "name": "custom-fee",
            "initial_cash": "100000.00",
            "fee_preset": "a_share",
            "commission_rate": "0.00025",
            "min_commission": "3.00",
            "stamp_duty_rate": "0.0004",
            "transfer_fee_rate": "0.00002",
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["fee_preset"] == "a_share"
    assert body["commission_rate"] == "0.00025000"
    assert body["min_commission"] == "3.0000"
    assert body["stamp_duty_rate"] == "0.00040000"
    assert body["transfer_fee_rate"] == "0.00002000"


def test_create_account_rejects_negative_fee_config(monkeypatch, sqlite_session):
    client, headers = _client(monkeypatch, sqlite_session)

    response = client.post(
        "/paper/accounts",
        json={"name": "bad-fee", "initial_cash": "100000.00", "commission_rate": "-0.0001"},
        headers=headers,
    )

    assert response.status_code == 422


def test_create_account_rejects_unknown_fee_preset(monkeypatch, sqlite_session):
    client, headers = _client(monkeypatch, sqlite_session)

    response = client.post(
        "/paper/accounts",
        json={"name": "unknown-preset", "initial_cash": "100000.00", "fee_preset": "unknown_preset"},
        headers=headers,
    )

    assert response.status_code == 422


def test_update_account_fees_updates_existing_account(monkeypatch, sqlite_session):
    client, headers = _client(monkeypatch, sqlite_session)
    created = client.post(
        "/paper/accounts",
        json={"name": "demo", "initial_cash": "100000.00"},
        headers=headers,
    ).json()

    response = client.patch(
        f"/paper/accounts/{created['id']}",
        json={"commission_rate": "0.0002", "min_commission": "3.00"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["commission_rate"] == "0.00020000"
    assert body["min_commission"] == "3.0000"


def test_update_account_fees_rejects_negative_fee(monkeypatch, sqlite_session):
    client, headers = _client(monkeypatch, sqlite_session)
    created = client.post(
        "/paper/accounts",
        json={"name": "demo", "initial_cash": "100000.00"},
        headers=headers,
    ).json()

    response = client.patch(
        f"/paper/accounts/{created['id']}",
        json={"commission_rate": "-0.0001"},
        headers=headers,
    )

    assert response.status_code == 422


def test_update_account_fees_rejects_empty_payload(monkeypatch, sqlite_session):
    client, headers = _client(monkeypatch, sqlite_session)
    created = client.post(
        "/paper/accounts",
        json={"name": "demo", "initial_cash": "100000.00"},
        headers=headers,
    ).json()

    response = client.patch(f"/paper/accounts/{created['id']}", json={}, headers=headers)

    assert response.status_code == 422


def test_update_account_fees_returns_404_for_missing_account(monkeypatch, sqlite_session):
    client, headers = _client(monkeypatch, sqlite_session)

    response = client.patch(
        "/paper/accounts/999",
        json={"commission_rate": "0.0002"},
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "paper account not found: 999"
