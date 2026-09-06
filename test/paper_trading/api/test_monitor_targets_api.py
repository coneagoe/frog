from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from monitor.monitor_target_service import MonitorTargetService
from paper_trading.api.app import create_app
from paper_trading.api.deps import get_session
from paper_trading.api.monitor_target_storage import ManualMonitorTargetStorage
from paper_trading.api.routers.monitor_targets import get_monitor_target_service
from paper_trading.auth import AuthSettings, create_session_token, hash_password
from storage.model.auth import User
from storage.model.base import Base


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


def test_monitor_target_manual_crud_filters_and_safe_schema(monkeypatch, sqlite_session):
    client, csrf_headers, _ = _client(monkeypatch, sqlite_session)

    listed = client.get("/paper/monitor-targets", params={"market": "A", "enabled": True})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [1]
    assert "workflow" not in listed.json()[0]
    assert "paused" not in listed.json()[0]

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
