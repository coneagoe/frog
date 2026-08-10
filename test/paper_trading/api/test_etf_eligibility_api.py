from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_session
from paper_trading.domain.enums import ETFEligibilityStatus
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base
from storage.model.etf_basic import ETFBasic


def _client(monkeypatch, sqlite_session) -> TestClient:
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    ETFBasic.__table__.create(sqlite_session.get_bind(), checkfirst=True)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    return TestClient(app)


def _add_etf(repo, session, symbol, name, exchange="SH", list_status="L", status=ETFEligibilityStatus.UNKNOWN):
    Base.metadata.create_all(session.get_bind())
    ETFBasic.__table__.create(session.get_bind(), checkfirst=True)
    session.add(ETFBasic(基金代码=symbol, 中文简称=name, 交易所=exchange, 存续状态=list_status))
    return repo.upsert_etf_eligibility(
        symbol,
        name,
        exchange,
        list_status,
        datetime(2026, 8, 10, 9, 30, tzinfo=timezone.utc),
        status=status,
    )


def test_etf_eligibility_api_requires_bearer_token(monkeypatch, sqlite_session):
    response = _client(monkeypatch, sqlite_session).get("/paper/etf-eligibility")

    assert response.status_code == 401


def test_list_etf_eligibility_filters_status_and_serializes_audit_fields(monkeypatch, sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    supported = _add_etf(repo, sqlite_session, "510300", "CSI 300 ETF", status=ETFEligibilityStatus.SUPPORTED)
    supported.reviewed_by = "operator"
    supported.reviewed_at = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
    _add_etf(repo, sqlite_session, "159915", "Chinext ETF", exchange="SZ")
    sqlite_session.commit()

    response = _client(monkeypatch, sqlite_session).get(
        "/paper/etf-eligibility", params={"status": "supported"}, headers={"Authorization": "Bearer secret"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "symbol": "510300",
                "name": "CSI 300 ETF",
                "exchange": "SH",
                "list_status": "L",
                "last_seen_at": "2026-08-10T09:30:00",
                "last_refresh_at": "2026-08-10T09:30:00",
                "status": "supported",
                "reviewed_at": "2026-08-10T10:00:00",
                "reviewed_by": "operator",
            }
        ]
    }


def test_get_etf_eligibility_returns_record(monkeypatch, sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    _add_etf(repo, sqlite_session, "510300", "CSI 300 ETF")
    sqlite_session.commit()

    response = _client(monkeypatch, sqlite_session).get(
        "/paper/etf-eligibility/510300", headers={"Authorization": "Bearer secret"}
    )

    assert response.status_code == 200
    assert response.json()["symbol"] == "510300"
    assert response.json()["status"] == "unknown"
    assert response.json()["reviewed_at"] is None


def test_get_etf_eligibility_returns_not_found_for_missing_record(monkeypatch, sqlite_session):
    response = _client(monkeypatch, sqlite_session).get(
        "/paper/etf-eligibility/510300", headers={"Authorization": "Bearer secret"}
    )

    assert response.status_code == 404


def test_list_etf_eligibility_rejects_invalid_filter_with_structured_error(monkeypatch, sqlite_session):
    response = _client(monkeypatch, sqlite_session).get(
        "/paper/etf-eligibility", params={"status": "invalid"}, headers={"Authorization": "Bearer secret"}
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "INVALID_ETF_ELIGIBILITY_STATUS",
            "message": "'invalid' is not a valid ETFEligibilityStatus",
            "details": {},
        }
    }


def test_get_etf_eligibility_rejects_invalid_symbol_with_structured_error(monkeypatch, sqlite_session):
    response = _client(monkeypatch, sqlite_session).get(
        "/paper/etf-eligibility/510300.SH", headers={"Authorization": "Bearer secret"}
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "INVALID_ETF_SYMBOL",
            "message": "ETF symbol must be a bare six-digit value",
            "details": {},
        }
    }


def test_classify_etf_eligibility_persists_review_audit(monkeypatch, sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    _add_etf(repo, sqlite_session, "510300", "CSI 300 ETF")
    sqlite_session.commit()

    response = _client(monkeypatch, sqlite_session).post(
        "/paper/etf-eligibility/510300/classify",
        json={"status": "money_market", "reviewed_by": "reviewer"},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "money_market"
    assert response.json()["reviewed_by"] == "reviewer"
    assert response.json()["reviewed_at"] is not None
    eligibility = repo.get_etf_eligibility("510300")
    assert eligibility is not None
    assert eligibility.status == "money_market"


@pytest.mark.parametrize("invalid_status", ["unknown", "disabled", "arbitrary"])
def test_classify_etf_eligibility_rejects_non_operator_statuses(monkeypatch, sqlite_session, invalid_status):
    repo = PaperTradingRepository(sqlite_session)
    _add_etf(repo, sqlite_session, "510300", "CSI 300 ETF")
    sqlite_session.commit()

    response = _client(monkeypatch, sqlite_session).post(
        "/paper/etf-eligibility/510300/classify",
        json={"status": invalid_status, "reviewed_by": "reviewer"},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "status"]


def test_classify_etf_eligibility_returns_not_found_for_missing_record(monkeypatch, sqlite_session):
    response = _client(monkeypatch, sqlite_session).post(
        "/paper/etf-eligibility/510300/classify",
        json={"status": "supported", "reviewed_by": "reviewer"},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 404


def test_classify_etf_eligibility_rejects_invalid_symbol_with_structured_error(monkeypatch, sqlite_session):
    response = _client(monkeypatch, sqlite_session).post(
        "/paper/etf-eligibility/510300.SH/classify",
        json={"status": "supported", "reviewed_by": "reviewer"},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "INVALID_ETF_SYMBOL",
            "message": "ETF symbol must be a bare six-digit value",
            "details": {},
        }
    }


def test_classify_etf_eligibility_returns_not_found_for_missing_provider(monkeypatch, sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    Base.metadata.create_all(sqlite_session.get_bind())
    repo.upsert_etf_eligibility(
        "510300",
        "CSI 300 ETF",
        "SH",
        "L",
        datetime(2026, 8, 10, 9, 30, tzinfo=timezone.utc),
    )
    sqlite_session.commit()

    response = _client(monkeypatch, sqlite_session).post(
        "/paper/etf-eligibility/510300/classify",
        json={"status": "supported", "reviewed_by": "reviewer"},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 404


def test_classify_etf_eligibility_rejects_invalid_provider_metadata(monkeypatch, sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    _add_etf(repo, sqlite_session, "510300", "Foreign ETF", exchange="HK")
    sqlite_session.commit()

    response = _client(monkeypatch, sqlite_session).post(
        "/paper/etf-eligibility/510300/classify",
        json={"status": "supported", "reviewed_by": "reviewer"},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "INVALID_ETF_EXCHANGE",
            "message": "ETF exchange must be SH or SZ",
            "details": {},
        }
    }


def test_classify_etf_eligibility_rejects_invalid_listing_status(monkeypatch, sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    _add_etf(repo, sqlite_session, "510300", "Delisted ETF", list_status="D")
    sqlite_session.commit()

    response = _client(monkeypatch, sqlite_session).post(
        "/paper/etf-eligibility/510300/classify",
        json={"status": "supported", "reviewed_by": "reviewer"},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "INVALID_ETF_LISTING_STATUS",
            "message": "ETF listing status must be L",
            "details": {},
        }
    }


def test_classify_etf_eligibility_rejects_extra_request_fields(monkeypatch, sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    _add_etf(repo, sqlite_session, "510300", "CSI 300 ETF")
    sqlite_session.commit()

    response = _client(monkeypatch, sqlite_session).post(
        "/paper/etf-eligibility/510300/classify",
        json={"status": "supported", "reviewed_by": "reviewer", "admin": True},
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "admin"]
