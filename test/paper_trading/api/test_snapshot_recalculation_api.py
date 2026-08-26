from datetime import date
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_market_data_provider, get_session_factory
from paper_trading.services.snapshot_recalculation_service import SnapshotRecalculationResult
from storage.model.base import Base

AUTH_HEADERS = {"Authorization": "Bearer secret"}


def _client(monkeypatch, session_factory=None):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory or MagicMock()
    app.dependency_overrides[get_market_data_provider] = lambda: MagicMock()
    return TestClient(app)


def test_recalculation_api_requires_token():
    assert (
        TestClient(create_app())
        .post(
            "/paper/accounts/1/snapshots/recalculate",
            json={"start_date": "2026-08-25", "end_date": "2026-08-25"},
        )
        .status_code
        == 401
    )


def test_recalculation_api_rejects_inverted_range(monkeypatch):
    response = _client(monkeypatch).post(
        "/paper/accounts/1/snapshots/recalculate",
        headers=AUTH_HEADERS,
        json={"start_date": "2026-08-26", "end_date": "2026-08-25"},
    )
    assert response.status_code == 422


def test_recalculation_api_serializes_result(monkeypatch):
    result = SnapshotRecalculationResult(1, [date(2026, 8, 25)], [date(2026, 8, 26)], [], [])
    with patch(
        "paper_trading.api.routers.snapshot_recalculation.SnapshotRecalculationService.recalculate",
        return_value=result,
    ):
        response = _client(monkeypatch).post(
            "/paper/accounts/1/snapshots/recalculate",
            headers=AUTH_HEADERS,
            json={"start_date": "2026-08-25", "end_date": "2026-08-26"},
        )
    assert response.status_code == 200
    assert response.json() == {
        "account_id": 1,
        "updated_dates": ["2026-08-25"],
        "unavailable_dates": ["2026-08-26"],
        "failed_dates": [],
        "errors": [],
    }


def test_recalculation_api_returns_unknown_account_as_404_from_repository(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    try:
        response = _client(monkeypatch, factory).post(
            "/paper/accounts/1/snapshots/recalculate",
            headers=AUTH_HEADERS,
            json={"start_date": "2026-08-25", "end_date": "2026-08-25"},
        )
    finally:
        engine.dispose()
    assert response.status_code == 404
