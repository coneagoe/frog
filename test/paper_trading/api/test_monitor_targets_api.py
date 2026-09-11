from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from monitor.monitor_health_service import MonitorTargetHealthService
from monitor.monitor_target_service import MonitorTargetService
from paper_trading.api.app import create_app
from paper_trading.api.deps import get_security_name_provider, get_session
from paper_trading.api.monitor_target_storage import ManualMonitorTargetStorage
from paper_trading.api.routers.monitor_targets import get_monitor_target_health_service, get_monitor_target_service
from paper_trading.auth import AuthSettings, create_session_token, hash_password
from storage.model.auth import User
from storage.model.base import Base
from test.paper_trading.fakes import _FakeSecurityNameProvider


class FakeMonitorStorage:
    def __init__(self):
        self.targets = [
            self._target(1, workflow=None),
            self._target(2, workflow="scheduled"),
        ]
        self.next_id = 3

    @staticmethod
    def _target(target_id, *, workflow, **updates):
        values = {
            "id": target_id,
            "stock_code": "600519",
            "market": "A",
            "condition": {"type": "price_threshold", "direction": "above", "value": 100},
            "note": "initial",
            "frequency": "daily",
            "reset_mode": "auto",
            "enabled": True,
            "last_state": False,
            "triggered_at": None,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "workflow": workflow,
            "paused": workflow is not None,
            "last_checked_at": None,
            "latest_error_kind": None,
            "latest_error_detail": None,
            "latest_error_at": None,
        }
        values.update(updates)
        return SimpleNamespace(**values)

    def list_manual_monitor_targets(self, **filters):
        targets = [target for target in self.targets if target.workflow is None]
        for field, value in filters.items():
            if value is not None:
                if field == "condition_type":
                    targets = [target for target in targets if target.condition["type"] == value]
                else:
                    targets = [target for target in targets if getattr(target, field) == value]
        return targets

    def list_monitor_target_health(self):
        return self.targets

    def list_monitor_target_health_page(self, *, page, page_size):
        total_count = len(self.targets)
        canonical_page = min(page, (total_count + page_size - 1) // page_size) if total_count else 1
        start = (canonical_page - 1) * page_size
        return self.targets[start : start + page_size], total_count

    def list_monitor_targets_unified(self, **filters):
        targets = list(self.targets)
        for field, value in filters.items():
            if field == "sort":
                continue
            if value is not None:
                if field == "condition_type":
                    targets = [
                        target for target in targets if target.workflow is None and target.condition["type"] == value
                    ]
                else:
                    targets = [target for target in targets if getattr(target, field) == value]
        return targets

    def list_monitor_targets_unified_page(self, *, page, page_size, **filters):
        targets = self.list_monitor_targets_unified(**filters)
        if filters.get("sort") == "stock_code_desc":
            targets.sort(key=lambda target: (target.stock_code, target.market, target.id), reverse=True)
        else:
            targets.sort(key=lambda target: (target.market, target.id))
        total_count = len(targets)
        start = (min(page, (total_count + page_size - 1) // page_size) - 1) * page_size if total_count else 0
        return targets[start : start + page_size], total_count

    def list_manual_monitor_targets_page(self, *, page, page_size, **filters):
        targets = self.list_manual_monitor_targets(**filters)
        total_count = len(targets)
        canonical_page = min(page, (total_count + page_size - 1) // page_size) if total_count else 1
        start = (canonical_page - 1) * page_size
        return targets[start : start + page_size], total_count

    def get_manual_monitor_target(self, target_id):
        return next((target for target in self.targets if target.id == target_id and target.workflow is None), None)

    def create_manual_monitor_target(self, **values):
        target = self._target(self.next_id, workflow=None, **values)
        self.targets.append(target)
        self.next_id += 1
        return target

    def update_manual_monitor_target(self, target_id, **updates):
        target = self.get_manual_monitor_target(target_id)
        if target is None:
            return None
        if updates.get("condition", {}).get("workflow") is not None:
            raise ValueError("workflow-owned targets cannot be updated here")
        for field, value in updates.items():
            setattr(target, field, value)
        return target

    def delete_manual_monitor_target(self, target_id):
        target = self.get_manual_monitor_target(target_id)
        if target is None:
            return False
        self.targets.remove(target)
        return True


def _client(monkeypatch, sqlite_session):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    monkeypatch.setenv("PAPER_TRADING_JWT_SECRET", "test-jwt-secret")
    monkeypatch.setattr("paper_trading.api.app.get_storage", lambda: None)
    storage = FakeMonitorStorage()
    Base.metadata.create_all(sqlite_session.get_bind())
    app = create_app()
    app.dependency_overrides[get_session] = lambda: sqlite_session
    app.dependency_overrides[get_monitor_target_service] = lambda: MonitorTargetService(
        storage=ManualMonitorTargetStorage(storage)
    )
    app.dependency_overrides[get_monitor_target_health_service] = lambda: MonitorTargetHealthService(storage=storage)
    client = TestClient(app)
    with sqlite_session.begin():
        user = User(
            email="owner@example.com",
            password_hash=hash_password("StrongPassword1"),
            email_verified_at=datetime.now(timezone.utc),
        )
        sqlite_session.add(user)
    settings = AuthSettings.from_environment()
    client.cookies.set("paper_trading_session", create_session_token(user.id, user.session_version, settings))
    client.cookies.set("paper_trading_csrf", "csrf-token")
    return client, {"X-CSRF-Token": "csrf-token"}, storage


def test_monitor_target_routes_require_auth_and_preserve_bearer_access(monkeypatch, sqlite_session):
    client, _, _ = _client(monkeypatch, sqlite_session)

    assert TestClient(create_app()).get("/paper/monitor-targets").status_code == 401
    assert client.get("/paper/monitor-targets").status_code == 200
    assert client.get("/paper/monitor-targets", headers={"Authorization": "Bearer secret"}).status_code == 200
    assert client.post("/paper/monitor-targets", json={}).status_code == 403
    assert (
        client.post(
            "/paper/monitor-targets",
            headers={"Authorization": "Bearer secret"},
            json={
                "stock_code": "000001",
                "market": "A",
                "condition": {"type": "price_threshold", "direction": "below", "value": 10},
            },
        ).status_code
        == 200
    )


def test_monitor_target_health_is_authenticated_read_only_all_target_view(monkeypatch, sqlite_session):
    client, csrf_headers, storage = _client(monkeypatch, sqlite_session)
    storage.targets[0].enabled = False
    storage.targets[0].paused = True
    storage.targets[0].last_state = True

    assert TestClient(create_app()).get("/paper/monitor-targets/health").status_code == 401
    response = client.get("/paper/monitor-targets/health")
    bearer_response = client.get("/paper/monitor-targets/health", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200, response.text
    assert bearer_response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "total": 2,
        "running": 0,
        "paused": 1,
        "disabled": 1,
        "triggered": 1,
        "daily": 2,
        "intraday": 0,
    }
    assert payload["items"][0]["operational_state"] == "disabled"
    assert payload["items"][1]["workflow"] == "scheduled"
    assert "condition" not in payload["items"][1]
    assert "note" not in payload["items"][1]

    before = list(storage.targets)
    for method in ("post", "patch"):
        assert (
            getattr(client, method)("/paper/monitor-targets/health", headers=csrf_headers, json={}).status_code >= 300
        )
    assert client.delete("/paper/monitor-targets/health", headers=csrf_headers).status_code >= 300
    assert storage.targets == before


def test_monitor_target_health_api_resanitizes_seeded_sensitive_error_detail(monkeypatch, sqlite_session):
    client, _, storage = _client(monkeypatch, sqlite_session)
    storage.targets[1].latest_error_kind = "storage"
    storage.targets[1].latest_error_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    storage.targets[1].latest_error_detail = (
        'RuntimeError: "api_key": "api-secret" X-Api-Key: header-secret '
        "Bearer token-secret https://example.com/private#fragment-secret /srv/frog/monitor.py"
    )

    response = client.get("/paper/monitor-targets/health")

    assert response.status_code == 200
    error = response.json()["items"][1]["latest_error"]
    assert error["kind"] == "storage"
    assert error["summary"] == "Monitor state persistence failed"
    for sensitive in (
        "RuntimeError:",
        "api-secret",
        "header-secret",
        "token-secret",
        "example.com",
        "fragment-secret",
        "/srv/frog/monitor.py",
    ):
        assert sensitive not in (error["detail"] or "")


def test_monitor_target_manual_crud_filters_and_safe_schema(monkeypatch, sqlite_session):
    client, csrf_headers, _ = _client(monkeypatch, sqlite_session)

    listed = client.get("/paper/monitor-targets", params={"market": "A", "enabled": True})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [1, 2]
    assert listed.json()["items"][0]["target_type"] == "manual"
    assert listed.json()["items"][1]["target_type"] == "workflow"

    created = client.post(
        "/paper/monitor-targets",
        headers=csrf_headers,
        json={
            "stock_code": "000001",
            "market": "A",
            "condition": {"type": "price_threshold", "direction": "below", "value": 10},
        },
    )
    assert created.status_code == 200
    target_id = created.json()["id"]
    assert client.get(f"/paper/monitor-targets/{target_id}").status_code == 200

    cleared = client.patch(f"/paper/monitor-targets/{target_id}", headers=csrf_headers, json={"note": None})
    assert cleared.status_code == 200
    assert cleared.json()["note"] is None
    assert client.patch(f"/paper/monitor-targets/{target_id}", headers=csrf_headers, json={}).status_code == 422

    disabled = client.patch(
        f"/paper/monitor-targets/{target_id}/enabled", headers=csrf_headers, json={"enabled": False}
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert client.delete(f"/paper/monitor-targets/{target_id}", headers=csrf_headers).status_code == 204


def test_monitor_target_list_and_health_return_enriched_page_envelopes(monkeypatch, sqlite_session):
    client, _, storage = _client(monkeypatch, sqlite_session)
    storage.targets[1].market = "HK"
    storage.targets.extend(
        [
            storage._target(3, workflow=None, stock_code="510300", market="ETF"),
            storage._target(4, workflow=None, stock_code="000002", market="A"),
        ]
    )
    client.app.dependency_overrides[get_security_name_provider] = lambda: _FakeSecurityNameProvider(
        {
            ("a_share", "600519"): "Kweichow Moutai",
            ("hk_connect", "600519"): "Tencent Holdings",
            ("etf", "510300"): "CSI 300 ETF",
        }
    )

    listed = client.get("/paper/monitor-targets?page=1&page_size=25")
    health = client.get("/paper/monitor-targets/health?page=1&page_size=2")
    second_health_page = client.get("/paper/monitor-targets/health?page=2&page_size=2")

    assert listed.status_code == 200
    assert listed.json()["pagination"] == {"page": 1, "page_size": 25, "total_count": 4, "total_pages": 1}
    assert listed.json()["items"][2]["stock_name"] == "CSI 300 ETF"
    assert health.status_code == 200
    assert health.json()["summary"]["total"] == 4
    assert health.json()["items"][0]["stock_name"] == "Kweichow Moutai"
    assert health.json()["items"][1]["stock_name"] == "Tencent Holdings"
    assert health.json()["page"] == 1
    assert health.json()["page_size"] == 2
    assert health.json()["total_count"] == 4
    assert health.json()["total_pages"] == 2
    assert second_health_page.json()["items"][0]["stock_name"] == "CSI 300 ETF"
    assert second_health_page.json()["items"][1]["stock_name"] is None


def test_unified_monitor_target_route_returns_both_target_types_and_filters_workflows(monkeypatch, sqlite_session):
    client, _, storage = _client(monkeypatch, sqlite_session)
    storage.targets.extend(
        [
            storage._target(3, workflow=None, stock_code="000002", market="A"),
            storage._target(4, workflow="scheduled", stock_code="000003", market="A"),
        ]
    )

    response = client.get(
        "/paper/monitor-targets",
        params={"sort": "stock_code_desc", "page_size": 25},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert {item["target_type"] for item in payload["items"]} == {"manual", "workflow"}
    assert all(item["can_manage"] == (item["target_type"] == "manual") for item in payload["items"])
    assert payload["pagination"] == {"page": 1, "page_size": 25, "total_count": 4, "total_pages": 1}
    assert payload["summary"]["total"] == 4

    manual_only = client.get("/paper/monitor-targets", params={"condition_type": "rsi"})
    assert manual_only.status_code == 200
    assert all(item["target_type"] == "manual" for item in manual_only.json()["items"])


def test_monitor_target_list_and_health_validate_paging_queries(monkeypatch, sqlite_session):
    client, _, _ = _client(monkeypatch, sqlite_session)

    for path in (
        "/paper/monitor-targets?page=0",
        "/paper/monitor-targets?page_size=0",
        "/paper/monitor-targets?page_size=101",
        "/paper/monitor-targets/health?page=0",
        "/paper/monitor-targets/health?page_size=0",
        "/paper/monitor-targets/health?page_size=101",
    ):
        assert client.get(path).status_code == 422


def test_monitor_target_page_envelopes_normalize_out_of_range_and_remain_valid_when_empty(monkeypatch, sqlite_session):
    client, _, storage = _client(monkeypatch, sqlite_session)

    for path, expected_page in (
        ("/paper/monitor-targets?page=99&page_size=25", 1),
        ("/paper/monitor-targets/health?page=99&page_size=1", 2),
    ):
        response = client.get(path)
        assert response.status_code == 200
        pagination = response.json().get("pagination", response.json())
        assert pagination["page"] == expected_page
        assert pagination["total_pages"] == expected_page

    storage.targets.clear()
    for path in ("/paper/monitor-targets", "/paper/monitor-targets/health"):
        response = client.get(path)
        assert response.status_code == 200
        payload = response.json()
        pagination = payload.get("pagination", payload)
        assert payload["items"] == []
        assert pagination["page"] == 1
        assert pagination["total_count"] == 0
        assert pagination["total_pages"] == 0


def test_monitor_target_name_lookup_failure_returns_null(monkeypatch, sqlite_session):
    client, _, _ = _client(monkeypatch, sqlite_session)

    class FailingNameProvider:
        def resolve_names(self, securities):
            raise RuntimeError("metadata unavailable")

    client.app.dependency_overrides[get_security_name_provider] = FailingNameProvider

    response = client.get("/paper/monitor-targets")

    assert response.status_code == 200
    assert response.json()["items"][0]["stock_name"] is None


def test_monitor_target_validation_and_workflow_targets_are_not_found(monkeypatch, sqlite_session):
    client, csrf_headers, storage = _client(monkeypatch, sqlite_session)

    invalid = client.post(
        "/paper/monitor-targets",
        headers=csrf_headers,
        json={"stock_code": "600519", "market": "A", "condition": {"type": "invalid"}},
    )
    assert invalid.status_code == 422

    for method, path, kwargs in (
        ("get", "/paper/monitor-targets/2", {}),
        ("patch", "/paper/monitor-targets/2", {"headers": csrf_headers, "json": {"note": "changed"}}),
        ("patch", "/paper/monitor-targets/2/enabled", {"headers": csrf_headers, "json": {"enabled": False}}),
        ("delete", "/paper/monitor-targets/2", {"headers": csrf_headers}),
        ("get", "/paper/monitor-targets/999", {}),
    ):
        assert getattr(client, method)(path, **kwargs).status_code == 404
    assert storage.targets[1].note == "initial"
    assert storage.targets[1].enabled is True


def test_monitor_target_create_and_update_reject_client_supplied_stock_name(monkeypatch, sqlite_session):
    client, csrf_headers, storage = _client(monkeypatch, sqlite_session)

    create = client.post(
        "/paper/monitor-targets",
        headers=csrf_headers,
        json={
            "stock_code": "000001",
            "stock_name": "Client supplied name",
            "market": "A",
            "condition": {"type": "price_threshold", "direction": "below", "value": 10},
        },
    )
    update = client.patch(
        "/paper/monitor-targets/1",
        headers=csrf_headers,
        json={"stock_name": "Client supplied name"},
    )

    assert create.status_code == 422
    assert update.status_code == 422
    assert storage.targets[0].stock_code == "600519"


def test_monitor_target_patch_rejects_workflow_condition(monkeypatch, sqlite_session):
    client, csrf_headers, storage = _client(monkeypatch, sqlite_session)

    response = client.patch(
        "/paper/monitor-targets/1",
        headers=csrf_headers,
        json={
            "condition": {
                "type": "price_threshold",
                "direction": "above",
                "value": 100,
                "workflow": "scheduled",
            }
        },
    )

    assert response.status_code == 422
    assert "workflow" not in storage.targets[0].condition
