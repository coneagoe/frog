from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_session
from paper_trading.auth import AuthSettings, create_session_token, hash_password
from paper_trading.domain.enums import (
    DataGapRecoveryAccountStatus,
    DataGapRecoveryAttemptOutcome,
    DataGapRecoveryBatchStatus,
)
from paper_trading.storage.data_gap_recovery_repository import DataGapRecoveryRepository
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.auth import User
from storage.model.base import Base

AUTH_HEADERS = {"Authorization": "Bearer secret"}
GET_PATHS = [
    "/paper/data-gap-recovery/gaps",
    "/paper/data-gap-recovery/gaps/1",
    "/paper/data-gap-recovery/batches",
    "/paper/data-gap-recovery/batches/1",
]


@pytest.fixture
def data_gap_recovery_client(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    Base.metadata.create_all(sqlite_session.get_bind())
    repository = DataGapRecoveryRepository(sqlite_session)
    gap = repository.record_gap(date(2026, 8, 1), "a_share", "000001", "bfq", {"missing": 1})
    batch = repository.record_batch(DataGapRecoveryBatchStatus.COMPLETED, {"recovered": 1})
    sqlite_session.commit()

    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    return TestClient(app), gap.id, batch.id


@pytest.mark.parametrize("path", GET_PATHS)
def test_data_gap_recovery_get_routes_require_authentication(data_gap_recovery_client, path):
    client, _, _ = data_gap_recovery_client

    assert client.get(path).status_code == 401


@pytest.mark.parametrize(
    ("path", "expected_key"),
    [
        ("/paper/data-gap-recovery/gaps", "items"),
        ("/paper/data-gap-recovery/gaps/1", "id"),
        ("/paper/data-gap-recovery/batches", "items"),
        ("/paper/data-gap-recovery/batches/1", "id"),
    ],
)
def test_data_gap_recovery_get_routes_allow_bearer_read_access(data_gap_recovery_client, path, expected_key):
    client, _, _ = data_gap_recovery_client

    response = client.get(path, headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert expected_key in response.json()


@pytest.mark.parametrize(
    "path",
    [
        "/paper/data-gap-recovery/gaps",
        "/paper/data-gap-recovery/batches",
    ],
)
@pytest.mark.parametrize("query", ["offset=-1", "page_size=0", "page_size=201"])
def test_data_gap_recovery_list_routes_validate_pagination(data_gap_recovery_client, path, query):
    client, _, _ = data_gap_recovery_client

    assert client.get(f"{path}?{query}", headers=AUTH_HEADERS).status_code == 422


@pytest.mark.parametrize("path", ["/paper/data-gap-recovery/gaps/999", "/paper/data-gap-recovery/batches/999"])
def test_data_gap_recovery_get_routes_return_404_for_missing_records(data_gap_recovery_client, path):
    client, _, _ = data_gap_recovery_client

    assert client.get(path, headers=AUTH_HEADERS).status_code == 404


@pytest.mark.parametrize("path", GET_PATHS)
def test_data_gap_recovery_routes_do_not_accept_post(data_gap_recovery_client, path):
    client, _, _ = data_gap_recovery_client

    assert client.post(path, headers=AUTH_HEADERS).status_code == 405


def test_data_gap_recovery_lists_have_counts_filters_and_detail_evidence(data_gap_recovery_client):
    client, gap_id, batch_id = data_gap_recovery_client
    response = client.get("/paper/data-gap-recovery/gaps?status=open&stock_id=000001", headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()["total_count"] == 1
    detail = client.get(f"/paper/data-gap-recovery/gaps/{gap_id}", headers=AUTH_HEADERS)
    assert {"candidates", "attempts", "approvals", "accounts", "alerts"} <= detail.json().keys()
    batch = client.get(f"/paper/data-gap-recovery/batches/{batch_id}", headers=AUTH_HEADERS)
    assert {"attempts", "gaps", "alerts"} <= batch.json().keys()


def test_browser_user_only_sees_recovery_records_linked_to_owned_accounts(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    monkeypatch.setenv("PAPER_TRADING_JWT_SECRET", "test-jwt-secret")
    monkeypatch.setattr("paper_trading.api.app.get_storage", lambda: None)
    Base.metadata.create_all(sqlite_session.get_bind())
    owner = User(
        email="owner@example.com",
        password_hash=hash_password("StrongPassword1"),
        email_verified_at=datetime.now(timezone.utc),
    )
    other = User(
        email="other@example.com",
        password_hash=hash_password("StrongPassword1"),
        email_verified_at=datetime.now(timezone.utc),
    )
    sqlite_session.add_all([owner, other])
    sqlite_session.flush()
    accounts = PaperTradingRepository(sqlite_session)
    owned_account = accounts.create_account("owned", Decimal("100"), owner_user_id=owner.id)
    other_account = accounts.create_account("other", Decimal("100"), owner_user_id=other.id)
    recovery = DataGapRecoveryRepository(sqlite_session)
    visible = recovery.record_gap(date(2026, 8, 1), "a_share", "000001", "bfq", {})
    hidden = recovery.record_gap(date(2026, 8, 1), "a_share", "000002", "bfq", {})
    recovery.upsert_account_progress(visible.id, owned_account.id, DataGapRecoveryAccountStatus.PENDING, {})
    recovery.upsert_account_progress(visible.id, other_account.id, DataGapRecoveryAccountStatus.PENDING, {})
    recovery.upsert_account_progress(hidden.id, other_account.id, DataGapRecoveryAccountStatus.PENDING, {})
    batch = recovery.record_batch(DataGapRecoveryBatchStatus.COMPLETED, {})
    recovery.record_attempt(visible.id, batch.id, DataGapRecoveryAttemptOutcome.NOT_FOUND, {"visible": True})
    recovery.record_attempt(hidden.id, batch.id, DataGapRecoveryAttemptOutcome.NOT_FOUND, {"hidden": True})
    recovery.record_candidate(hidden.id, "a" * 64, {"secret": True}, {}, "test")
    sqlite_session.commit()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    client = TestClient(app)
    client.cookies.set(
        "paper_trading_session",
        create_session_token(owner.id, owner.session_version, AuthSettings.from_environment()),
    )

    listed = client.get("/paper/data-gap-recovery/gaps")
    assert listed.status_code == 200
    assert listed.json()["total_count"] == 1
    assert [item["id"] for item in listed.json()["items"]] == [visible.id]
    assert client.get(f"/paper/data-gap-recovery/gaps/{hidden.id}").status_code == 404
    batch_response = client.get(f"/paper/data-gap-recovery/batches/{batch.id}")
    assert batch_response.status_code == 200
    assert [gap["id"] for gap in batch_response.json()["gaps"]] == [visible.id]
    assert [attempt["gap_id"] for attempt in batch_response.json()["attempts"]] == [visible.id]
    assert client.get("/paper/data-gap-recovery/batches").json()["total_count"] == 1
    assert client.get(f"/paper/data-gap-recovery/gaps/{hidden.id}", headers=AUTH_HEADERS).status_code == 200
