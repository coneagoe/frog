from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_position_valuation_service, get_security_name_provider, get_session
from paper_trading.domain.enums import Market
from paper_trading.services.position_valuation_service import PositionValuation
from paper_trading.storage.models import PaperCashLedger
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base
from test.paper_trading.fakes import _FakeSecurityNameProvider


def _client(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    session = sqlite_session
    Base.metadata.create_all(session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_position_valuation_service] = lambda: _FakePositionValuationService({})
    return TestClient(app), {"Authorization": "Bearer secret"}, session


def _create_account(client, headers):
    resp = client.post(
        "/paper/accounts",
        json={"name": "demo", "initial_cash": "100000.00"},
        headers=headers,
    )
    return resp.json()["id"]


class _FakePositionValuationService:
    def __init__(self, values):
        self.values = values
        self.markets = []

    def value_many(self, positions):
        rows = list(positions)
        self.markets.extend((position.symbol, position.market) for position in rows)
        return [PositionValuation(*self.values.get(position.symbol, (None, None, None))) for position in rows]

    def value(self, position):
        return self.value_many([position])[0]


def test_api_startup_bootstraps_storage_schema(monkeypatch):
    calls: list[None] = []
    monkeypatch.setattr("paper_trading.api.app.get_storage", lambda: calls.append(None))

    with TestClient(create_app()):
        pass

    assert calls == [None]


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
            "etf_commission_rate": "0.00008",
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
    assert body["etf_commission_rate"] == "0.00008000"


def test_account_responses_include_ledger_derived_cash_available(monkeypatch, sqlite_session):
    client, headers, _ = _client(monkeypatch, sqlite_session)

    created = client.post(
        "/paper/accounts",
        json={"name": "cash-available", "initial_cash": "100000.00"},
        headers=headers,
    )

    assert created.status_code == 200
    account_id = created.json()["id"]
    assert created.json()["cash_available"] == "100000.0000"

    deposited = client.post(
        f"/paper/accounts/{account_id}/cash/deposit",
        json={"amount": "25000.00", "trade_date": "2026-07-20"},
        headers=headers,
    )
    assert deposited.status_code == 200

    listed = client.get("/paper/accounts", headers=headers)
    detailed = client.get(f"/paper/accounts/{account_id}", headers=headers)
    fee_updated = client.patch(
        f"/paper/accounts/{account_id}",
        json={"commission_rate": "0.0002"},
        headers=headers,
    )

    for response in (listed, detailed, fee_updated):
        assert response.status_code == 200
    assert listed.json()[0]["cash_available"] == "125000.0000"
    assert detailed.json()["cash_available"] == "125000.0000"
    assert fee_updated.json()["cash_available"] == "125000.0000"


@pytest.mark.parametrize("initial_cash", ["0", "-1"])
def test_create_account_rejects_non_positive_initial_cash(monkeypatch, sqlite_session, initial_cash):
    client, headers, _ = _client(monkeypatch, sqlite_session)

    response = client.post(
        "/paper/accounts",
        json={"name": "invalid", "initial_cash": initial_cash},
        headers=headers,
    )

    assert response.status_code == 422


def test_create_account_persists_one_initial_nav_snapshot(monkeypatch, sqlite_session):
    client, headers, session = _client(monkeypatch, sqlite_session)

    response = client.post(
        "/paper/accounts",
        json={"name": "primary", "initial_cash": "1000"},
        headers=headers,
    )

    assert response.status_code == 200
    account_id = response.json()["id"]
    snapshots = PaperTradingRepository(session).list_snapshots(account_id)
    assert [(row.point_type, row.net_asset_value) for row in snapshots] == [("initial", Decimal("1.000000"))]

    listed = client.get(f"/paper/accounts/{account_id}/snapshots", headers=headers)
    assert listed.status_code == 200
    payload = listed.json()
    assert len(payload) == 1
    assert payload[0]["id"] == snapshots[0].id
    assert payload[0]["point_type"] == "initial"
    assert payload[0]["quality_status"] == "valid"
    assert payload[0]["invalid_reason"] is None
    assert payload[0]["net_asset_value"] == "1.000000"
    assert "event_at" in payload[0]


def test_create_account_rolls_back_when_snapshot_insert_fails(monkeypatch, sqlite_session):
    client, headers, session = _client(monkeypatch, sqlite_session)

    def fail_snapshot(*args, **kwargs):
        raise RuntimeError("snapshot insert failed")

    monkeypatch.setattr(PaperTradingRepository, "create_initial_snapshot", fail_snapshot)

    with pytest.raises(RuntimeError, match="snapshot insert failed"):
        client.post(
            "/paper/accounts",
            json={"name": "primary", "initial_cash": "1000"},
            headers=headers,
        )
    session.rollback()

    assert PaperTradingRepository(session).list_accounts() == []
    assert session.query(PaperCashLedger).count() == 0


def test_create_account_rejects_negative_fee_config(monkeypatch, sqlite_session):
    client, headers, _ = _client(monkeypatch, sqlite_session)

    response = client.post(
        "/paper/accounts",
        json={"name": "bad-fee", "initial_cash": "100000.00", "commission_rate": "-0.0001"},
        headers=headers,
    )

    assert response.status_code == 422


def test_accounts_api_returns_etf_commission_rate(monkeypatch, sqlite_session):
    client, headers, _ = _client(monkeypatch, sqlite_session)

    response = client.post(
        "/paper/accounts",
        json={"name": "etf", "initial_cash": "100000", "etf_commission_rate": "0.00008"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["etf_commission_rate"] == "0.00008000"


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


def test_update_account_fees_updates_all_market_fee_groups(monkeypatch, sqlite_session):
    client, headers, _ = _client(monkeypatch, sqlite_session)
    created = client.post(
        "/paper/accounts",
        json={"name": "demo", "initial_cash": "100000.00"},
        headers=headers,
    ).json()

    response = client.patch(
        f"/paper/accounts/{created['id']}",
        json={
            "commission_rate": "0.0002",
            "hk_commission_rate": "0.0003",
            "etf_commission_rate": "0.00008",
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["commission_rate"] == "0.00020000"
    assert body["hk_commission_rate"] == "0.00030000"
    assert body["etf_commission_rate"] == "0.00008000"


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
    def test_list_positions_uses_real_time_price_and_calculates_unrealized_pnl(self, monkeypatch, sqlite_session):
        client, headers, session = _client(monkeypatch, sqlite_session)
        account_id = _create_account(client, headers)
        PaperTradingRepository(session).upsert_position(
            account_id, Market.A_SHARE, "000001", 100, 0, Decimal("1000.00"), realized_pnl=Decimal("75.00")
        )
        session.commit()
        client.app.dependency_overrides[get_position_valuation_service] = lambda: _FakePositionValuationService(
            {"000001": (Decimal("12.50"), "real_time", Decimal("250.00"))}
        )

        response = client.get(f"/paper/accounts/{account_id}/positions", headers=headers)

        assert response.status_code == 200
        position = response.json()[0]
        assert position["mark_price"] == "12.50"
        assert position["price_source"] == "real_time"
        assert position["unrealized_pnl"] == "250.00"

    def test_list_positions_falls_back_to_db_close_with_market_routing(self, monkeypatch, sqlite_session):
        client, headers, session = _client(monkeypatch, sqlite_session)
        account_id = _create_account(client, headers)
        repo = PaperTradingRepository(session)
        repo.upsert_position(account_id, Market.A_SHARE, "000001", 100, 0, Decimal("1000.00"))
        repo.upsert_position(account_id, Market.HK_CONNECT, "00700", 10, 0, Decimal("4000.00"))
        session.commit()
        valuation = _FakePositionValuationService(
            {
                "000001": (Decimal("11.00"), "db_close", Decimal("100.00")),
                "00700": (Decimal("410.00"), "db_close", Decimal("100.00")),
            }
        )
        client.app.dependency_overrides[get_position_valuation_service] = lambda: valuation

        response = client.get(f"/paper/accounts/{account_id}/positions", headers=headers)

        assert response.status_code == 200
        positions = {item["symbol"]: item for item in response.json()}
        assert positions["000001"]["price_source"] == "db_close"
        assert positions["00700"]["mark_price"] == "410.00"
        assert valuation.markets == [("000001", "a_share"), ("00700", "hk_connect")]

    def test_list_positions_keeps_unavailable_symbols_nullable(self, monkeypatch, sqlite_session):
        client, headers, session = _client(monkeypatch, sqlite_session)
        account_id = _create_account(client, headers)
        repo = PaperTradingRepository(session)
        repo.upsert_position(account_id, Market.A_SHARE, "000001", 100, 0, Decimal("1000.00"))
        repo.upsert_position(account_id, Market.A_SHARE, "UNKNOWN", 100, 0, Decimal("1000.00"))
        session.commit()
        client.app.dependency_overrides[get_position_valuation_service] = lambda: _FakePositionValuationService(
            {"000001": (Decimal("11.00"), "real_time", Decimal("100.00"))}
        )

        response = client.get(f"/paper/accounts/{account_id}/positions", headers=headers)

        assert response.status_code == 200
        positions = {item["symbol"]: item for item in response.json()}
        assert positions["000001"]["unrealized_pnl"] == "100.00"
        assert positions["UNKNOWN"]["mark_price"] is None
        assert positions["UNKNOWN"]["price_source"] is None
        assert positions["UNKNOWN"]["unrealized_pnl"] is None

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
        assert positions[0].market == "a_share"

    def test_list_positions_includes_stock_name(self, monkeypatch, sqlite_session):
        client, headers, session = _client(monkeypatch, sqlite_session)
        account_id = _create_account(client, headers)
        PaperTradingRepository(session).upsert_position(account_id, Market.A_SHARE, "000001", 100, 0, Decimal("1000"))
        session.commit()
        provider = _FakeSecurityNameProvider({("a_share", "000001"): "Ping An Bank"})
        client.app.dependency_overrides[get_security_name_provider] = lambda: provider

        response = client.get(f"/paper/accounts/{account_id}/positions", headers=headers)

        assert response.status_code == 200
        assert response.json()[0]["stock_name"] == "Ping An Bank"

    def test_list_positions_returns_null_for_missing_stock_name(self, monkeypatch, sqlite_session):
        client, headers, session = _client(monkeypatch, sqlite_session)
        account_id = _create_account(client, headers)
        PaperTradingRepository(session).upsert_position(account_id, Market.A_SHARE, "UNKNOWN", 100, 0, Decimal("1000"))
        session.commit()
        client.app.dependency_overrides[get_security_name_provider] = lambda: _FakeSecurityNameProvider({})

        response = client.get(f"/paper/accounts/{account_id}/positions", headers=headers)

        assert response.status_code == 200
        assert response.json()[0]["stock_name"] is None

    def test_import_positions_preserves_hk_market(self, monkeypatch, sqlite_session):
        client, headers, session = _client(monkeypatch, sqlite_session)
        account_id = _create_account(client, headers)

        response = client.post(
            f"/paper/accounts/{account_id}/positions/import",
            json={
                "positions": [
                    {
                        "symbol": "00700",
                        "quantity": 100,
                        "cost_price": "400",
                        "buy_trade_date": "2026-07-27",
                        "market": "hk_connect",
                    }
                ]
            },
            headers=headers,
        )

        assert response.status_code == 200
        positions = PaperTradingRepository(session).get_positions(account_id)
        assert positions[0].market == "hk_connect"

    def test_import_positions_creates_isolated_same_symbol_cross_market_positions(self, monkeypatch, sqlite_session):
        client, headers, session = _client(monkeypatch, sqlite_session)
        account_id = _create_account(client, headers)

        response = client.post(
            f"/paper/accounts/{account_id}/positions/import",
            json={
                "positions": [
                    {
                        "symbol": "00700",
                        "quantity": 100,
                        "cost_price": "400",
                        "buy_trade_date": "2026-07-27",
                    },
                    {
                        "symbol": "00700",
                        "quantity": 100,
                        "cost_price": "401",
                        "buy_trade_date": "2026-07-27",
                        "market": "hk_connect",
                    },
                ]
            },
            headers=headers,
        )

        assert response.status_code == 200
        repo = PaperTradingRepository(session)
        a_share_position = repo.get_position(account_id, Market.A_SHARE, "00700")
        hk_connect_position = repo.get_position(account_id, Market.HK_CONNECT, "00700")
        assert a_share_position is not None
        assert a_share_position.total_quantity == 100
        assert hk_connect_position is not None
        assert hk_connect_position.total_quantity == 100
        assert len(repo.get_lots(account_id, Market.A_SHARE, "00700")) == 1
        assert len(repo.get_lots(account_id, Market.HK_CONNECT, "00700")) == 1

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
        repo.upsert_position(account_id, Market.A_SHARE, "EXISTING", 10, 0, Decimal("100.00"))
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
            market=Market.A_SHARE,
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


# ---------------------------------------------------------------------------
# Cash Flow API
# ---------------------------------------------------------------------------


def test_deposit_endpoint_returns_cash_flow_response(monkeypatch, sqlite_session):
    client, headers, _ = _client(monkeypatch, sqlite_session)
    account_id = _create_account(client, headers)

    response = client.post(
        f"/paper/accounts/{account_id}/cash/deposit",
        json={"amount": "25000.00", "trade_date": "2026-07-20", "note": "add cash"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ledger"]["event_type"] == "deposit"
    assert body["ledger"]["share_delta"] == "25000.000000"
    assert body["cash_available"] == "125000.0000"
    assert body["share_count"] == "125000.000000"


def test_withdraw_endpoint_rejects_excess_cash(monkeypatch, sqlite_session):
    client, headers, _ = _client(monkeypatch, sqlite_session)
    account_id = _create_account(client, headers)

    response = client.post(
        f"/paper/accounts/{account_id}/cash/withdraw",
        json={"amount": "100001.00", "trade_date": "2026-07-20"},
        headers=headers,
    )

    assert response.status_code == 422
    assert "exceeds available cash" in response.json()["detail"]


# ---------------------------------------------------------------------------
# HK Fee API
# ---------------------------------------------------------------------------


def test_update_account_hk_fees(monkeypatch, sqlite_session):
    client, headers, _ = _client(monkeypatch, sqlite_session)
    account_id = _create_account(client, headers)

    response = client.patch(
        f"/paper/accounts/{account_id}",
        json={
            "hk_commission_rate": "0.0002",
            "hk_min_commission": "18.00",
            "hk_stamp_duty_rate": "0.0013",
        },
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["hk_commission_rate"] == "0.00020000"


def test_update_account_hk_fees_rejects_negative(monkeypatch, sqlite_session):
    client, headers, _ = _client(monkeypatch, sqlite_session)
    account_id = _create_account(client, headers)

    response = client.patch(
        f"/paper/accounts/{account_id}",
        json={"hk_commission_rate": "-0.01"},
        headers=headers,
    )
    assert response.status_code == 422


def test_update_account_fees_can_mix_a_share_and_hk_fields(monkeypatch, sqlite_session):
    client, headers, _ = _client(monkeypatch, sqlite_session)
    account_id = _create_account(client, headers)

    response = client.patch(
        f"/paper/accounts/{account_id}",
        json={
            "commission_rate": "0.0002",
            "min_commission": "3.00",
            "hk_commission_rate": "0.0002",
            "hk_min_commission": "18.00",
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["commission_rate"] == "0.00020000"
    assert body["min_commission"] == "3.0000"
    assert body["hk_commission_rate"] == "0.00020000"
    assert body["hk_min_commission"] == "18.0000"
