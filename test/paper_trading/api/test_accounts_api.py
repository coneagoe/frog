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
