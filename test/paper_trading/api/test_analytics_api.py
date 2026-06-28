from decimal import Decimal

from fastapi.testclient import TestClient

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_session
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
