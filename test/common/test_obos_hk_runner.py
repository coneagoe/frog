import json
import os
import importlib.util
from types import SimpleNamespace


def load_module():
    # Ensure the worktree project root is on sys.path and import by package name so
    # we patch the same module object used elsewhere.
    import sys
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return __import__("task.obos_hk", fromlist=["*"])



def call_obos_hk(mod):
    task = mod.obos_hk
    fn = getattr(task, "run", task)
    return fn()


def test_skip_when_redis_not_success(monkeypatch):
    mod = load_module()

    # noop config parser
    monkeypatch.setattr(mod.conf, "parse_config", lambda: None)

    # fake redis client returning fail
    class FakeRedis:
        def get(self, key):
            return json.dumps({"result": "fail"})

    # patch Redis.from_url used by get_redis_client
    monkeypatch.setattr(mod.redis.Redis, "from_url", lambda url, decode_responses=True: FakeRedis())

    res = call_obos_hk(mod)
    assert "Skip: download result is fail" in res


def test_success_email_path(monkeypatch):
    mod = load_module()
    monkeypatch.setattr(mod.conf, "parse_config", lambda: None)

    class FakeRedis:
        def get(self, key):
            return json.dumps({"result": "success"})

    # patch Redis.from_url used by get_redis_client
    monkeypatch.setattr(mod.redis.Redis, "from_url", lambda url, decode_responses=True: FakeRedis())
    monkeypatch.setattr(mod, "is_hk_market_open_today", lambda: True)
    fn = getattr(mod.obos_hk, "run", mod.obos_hk)
    fn.__globals__["is_hk_market_open_today"] = lambda: True

    # capture emails
    emails = []

    def fake_send_email(subject=None, body=None):
        emails.append({"subject": subject, "body": body})

    monkeypatch.setattr(mod, "send_email", fake_send_email)

    # fake successful subprocess
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="OK", stderr=""))

    res = call_obos_hk(mod)
    assert res == "Backtest success."
    assert len(emails) == 1
    assert "obos_hk_2024-11-01" in emails[0]["subject"]
    assert "OK" in emails[0]["body"]


def test_subprocess_failure_path(monkeypatch):
    mod = load_module()
    monkeypatch.setattr(mod.conf, "parse_config", lambda: None)

    class FakeRedis:
        def get(self, key):
            return json.dumps({"result": "success"})

    # patch Redis.from_url used by get_redis_client
    monkeypatch.setattr(mod.redis.Redis, "from_url", lambda url, decode_responses=True: FakeRedis())
    monkeypatch.setattr(mod, "is_hk_market_open_today", lambda: True)
    fn = getattr(mod.obos_hk, "run", mod.obos_hk)
    fn.__globals__["is_hk_market_open_today"] = lambda: True

    emails = []

    def fake_send_email(subject=None, body=None):
        emails.append({"subject": subject, "body": body})

    monkeypatch.setattr(mod, "send_email", fake_send_email)

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="some error"))

    res = call_obos_hk(mod)
    assert "Backtest failed: some error" in res
    assert len(emails) == 1
    assert "Backtest failed with error: some error" in emails[0]["body"]
