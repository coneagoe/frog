from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_session
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def _client(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app), {"Authorization": "Bearer secret"}, session


def _create_account(client, headers):
    resp = client.post(
        "/paper/accounts",
        json={"name": "demo", "initial_cash": "100000.00"},
        headers=headers,
    )
    return resp.json()["id"]


def test_delete_account_removes_account_from_list(monkeypatch, sqlite_session):
    client, headers, _ = _client(monkeypatch, sqlite_session)
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
    client, headers, _ = _client(monkeypatch, sqlite_session)

    response = client.delete("/paper/accounts/999", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "paper account not found: 999"


def test_create_account_accepts_and_returns_fee_config(monkeypatch, sqlite_session):
    client, headers, _ = _client(monkeypatch, sqlite_session)

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
    client, headers, _ = _client(monkeypatch, sqlite_session)

    response = client.post(
        "/paper/accounts",
        json={"name": "bad-fee", "initial_cash": "100000.00", "commission_rate": "-0.0001"},
        headers=headers,
    )

    assert response.status_code == 422


def test_create_account_rejects_unknown_fee_preset(monkeypatch, sqlite_session):
    client, headers, _ = _client(monkeypatch, sqlite_session)

    response = client.post(
        "/paper/accounts",
        json={"name": "unknown-preset", "initial_cash": "100000.00", "fee_preset": "unknown_preset"},
        headers=headers,
    )

    assert response.status_code == 422


def test_update_account_fees_updates_existing_account(monkeypatch, sqlite_session):
    client, headers, _ = _client(monkeypatch, sqlite_session)
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
    client, headers, _ = _client(monkeypatch, sqlite_session)
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
    client, headers, _ = _client(monkeypatch, sqlite_session)
    created = client.post(
        "/paper/accounts",
        json={"name": "demo", "initial_cash": "100000.00"},
        headers=headers,
    ).json()

    response = client.patch(f"/paper/accounts/{created['id']}", json={}, headers=headers)

    assert response.status_code == 422


def test_update_account_fees_returns_404_for_missing_account(monkeypatch, sqlite_session):
    client, headers, _ = _client(monkeypatch, sqlite_session)

    response = client.patch(
        "/paper/accounts/999",
        json={"commission_rate": "0.0002"},
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "paper account not found: 999"


# ---------------------------------------------------------------------------
# Import Positions API
# ---------------------------------------------------------------------------


class TestImportPositionsAPI:
    def test_import_positions_returns_200(self, monkeypatch, sqlite_session):
        client, headers, session = _client(monkeypatch, sqlite_session)
        account_id = _create_account(client, headers)

        response = client.post(
            f"/paper/accounts/{account_id}/positions/import",
            json={
                "positions": [
                    {
                        "symbol": "000001",
                        "quantity": 100,
                        "cost_price": "10.50",
                        "buy_trade_date": "2026-01-15",
                    }
                ]
            },
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["imported_count"] == 1
        assert data["lots_count"] == 1
        positions = PaperTradingRepository(session).get_positions(account_id)
        assert len(positions) == 1
        assert positions[0].symbol == "000001"

    def test_import_positions_missing_account_returns_404(self, monkeypatch, sqlite_session):
        client, headers, _ = _client(monkeypatch, sqlite_session)

        response = client.post(
            "/paper/accounts/999/positions/import",
            json={
                "positions": [
                    {
                        "symbol": "000001",
                        "quantity": 100,
                        "cost_price": "10.50",
                        "buy_trade_date": "2026-01-15",
                    }
                ]
            },
            headers=headers,
        )

        assert response.status_code == 404

    def test_import_positions_rejects_missing_fields(self, monkeypatch, sqlite_session):
        client, headers, _ = _client(monkeypatch, sqlite_session)
        account_id = _create_account(client, headers)

        response = client.post(
            f"/paper/accounts/{account_id}/positions/import",
            json={
                "positions": [
                    {
                        "quantity": 100,
                        "cost_price": "10.50",
                        "buy_trade_date": "2026-01-15",
                    }
                ]
            },
            headers=headers,
        )

        assert response.status_code == 422

    def test_import_positions_rejects_negative_quantity(self, monkeypatch, sqlite_session):
        client, headers, _ = _client(monkeypatch, sqlite_session)
        account_id = _create_account(client, headers)

        response = client.post(
            f"/paper/accounts/{account_id}/positions/import",
            json={
                "positions": [
                    {
                        "symbol": "000001",
                        "quantity": -1,
                        "cost_price": "10.50",
                        "buy_trade_date": "2026-01-15",
                    }
                ]
            },
            headers=headers,
        )

        assert response.status_code == 422

    def test_import_positions_rejects_negative_cost_price(self, monkeypatch, sqlite_session):
        client, headers, _ = _client(monkeypatch, sqlite_session)
        account_id = _create_account(client, headers)

        response = client.post(
            f"/paper/accounts/{account_id}/positions/import",
            json={
                "positions": [
                    {
                        "symbol": "000001",
                        "quantity": 100,
                        "cost_price": "-1",
                        "buy_trade_date": "2026-01-15",
                    }
                ]
            },
            headers=headers,
        )

        assert response.status_code == 422

    def test_import_positions_rejects_existing_positions(self, monkeypatch, sqlite_session):
        client, headers, session = _client(monkeypatch, sqlite_session)
        account_id = _create_account(client, headers)
        # Pre-seed a position
        repo = PaperTradingRepository(session)
        repo.upsert_position(account_id, "EXISTING", 10, 0, Decimal("100.00"))
        session.commit()

        response = client.post(
            f"/paper/accounts/{account_id}/positions/import",
            json={
                "positions": [
                    {
                        "symbol": "000001",
                        "quantity": 100,
                        "cost_price": "10.50",
                        "buy_trade_date": "2026-01-15",
                    }
                ]
            },
            headers=headers,
        )

        assert response.status_code == 422

    def test_import_positions_rejects_existing_lots_only(self, monkeypatch, sqlite_session):
        """Account with lots but no positions must reject import."""
        client, headers, session = _client(monkeypatch, sqlite_session)
        account_id = _create_account(client, headers)
        repo = PaperTradingRepository(session)
        repo.create_position_lot(
            account_id=account_id,
            symbol="EXISTING",
            buy_trade_date=date(2026, 1, 15),
            original_quantity=100,
            remaining_quantity=100,
            cost_price=Decimal("10.00"),
        )
        session.commit()

        response = client.post(
            f"/paper/accounts/{account_id}/positions/import",
            json={
                "positions": [
                    {
                        "symbol": "000001",
                        "quantity": 100,
                        "cost_price": "10.50",
                        "buy_trade_date": "2026-01-15",
                    }
                ]
            },
            headers=headers,
        )

        assert response.status_code == 422

    def test_import_positions_rejects_datetime_string_date(self, monkeypatch, sqlite_session):
        """buy_trade_date must reject ISO datetime strings like '2026-01-15T00:00:00'."""
        client, headers, _ = _client(monkeypatch, sqlite_session)
        account_id = _create_account(client, headers)

        response = client.post(
            f"/paper/accounts/{account_id}/positions/import",
            json={
                "positions": [
                    {
                        "symbol": "000001",
                        "quantity": 100,
                        "cost_price": "10.50",
                        "buy_trade_date": "2026-01-15T00:00:00",
                    }
                ]
            },
            headers=headers,
        )

        assert response.status_code == 422

    def test_import_positions_rejects_timestamp_date(self, monkeypatch, sqlite_session):
        """buy_trade_date must reject numeric timestamps."""
        client, headers, _ = _client(monkeypatch, sqlite_session)
        account_id = _create_account(client, headers)

        response = client.post(
            f"/paper/accounts/{account_id}/positions/import",
            json={
                "positions": [
                    {
                        "symbol": "000001",
                        "quantity": 100,
                        "cost_price": "10.50",
                        "buy_trade_date": 1768521600,
                    }
                ]
            },
            headers=headers,
        )

        assert response.status_code == 422

    def test_import_positions_rejects_non_zero_padded_date(self, monkeypatch, sqlite_session):
        """buy_trade_date must reject non-zero-padded dates like '2026-1-5'."""
        client, headers, _ = _client(monkeypatch, sqlite_session)
        account_id = _create_account(client, headers)

        response = client.post(
            f"/paper/accounts/{account_id}/positions/import",
            json={
                "positions": [
                    {
                        "symbol": "000001",
                        "quantity": 100,
                        "cost_price": "10.50",
                        "buy_trade_date": "2026-1-5",
                    }
                ]
            },
            headers=headers,
        )

        assert response.status_code == 422
