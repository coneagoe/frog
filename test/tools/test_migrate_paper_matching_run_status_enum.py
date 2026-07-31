from __future__ import annotations

import json
import logging

from paper_trading.storage.matching_status_migration import MatchingStatusEnumMigrationResult
from tools import migrate_paper_matching_run_status_enum as command


class FakeTransaction:
    def __init__(self, connection: object, error: Exception | None = None):
        self.connection = connection
        self.error = error
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        if self.error is not None:
            raise self.error
        return self.connection

    def __exit__(self, exception_type, exception, traceback):
        if exception_type is None:
            self.committed = True
        else:
            self.rolled_back = True
        return False


class FakeEngine:
    def __init__(self, transaction: FakeTransaction):
        self.transaction = transaction

    def begin(self):
        return self.transaction


class FakeStorage:
    def __init__(self, transaction: FakeTransaction):
        self.engine = FakeEngine(transaction)


def _result(*, dry_run: bool) -> MatchingStatusEnumMigrationResult:
    return MatchingStatusEnumMigrationResult(
        dry_run=dry_run,
        converted=not dry_run,
        labels=("running", "completed", "completed_with_warnings", "failed"),
        index_verified=True,
    )


def test_main_emits_stable_human_result(monkeypatch, capsys):
    transaction = FakeTransaction(object())
    storage = FakeStorage(transaction)
    calls: list[bool] = []
    monkeypatch.setattr(command, "parse_config", lambda: calls.append(True))
    monkeypatch.setattr(command, "get_storage", lambda: storage)
    monkeypatch.setattr(
        command,
        "migrate_paper_matching_status_enum",
        lambda connection, *, dry_run: _result(dry_run=dry_run),
    )

    assert command.main([]) == 0

    assert calls == [True]
    assert transaction.committed is True
    assert transaction.rolled_back is False
    assert capsys.readouterr().out == (
        "dry_run=false converted=true index_verified=true labels=running,completed,completed_with_warnings,failed\n"
    )


def test_main_emits_json_and_passes_dry_run(monkeypatch, capsys):
    transaction = FakeTransaction(object())
    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "get_storage", lambda: FakeStorage(transaction))
    dry_runs: list[bool] = []

    def migrate(connection, *, dry_run):
        dry_runs.append(dry_run)
        return _result(dry_run=dry_run)

    monkeypatch.setattr(command, "migrate_paper_matching_status_enum", migrate)

    assert command.main(["--dry-run", "--json"]) == 0

    assert dry_runs == [True]
    assert json.loads(capsys.readouterr().out) == {
        "converted": False,
        "dry_run": True,
        "index_verified": True,
        "labels": ["running", "completed", "completed_with_warnings", "failed"],
    }


def test_main_logs_migration_failure_and_returns_nonzero(monkeypatch, caplog, capsys):
    transaction = FakeTransaction(object())
    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "get_storage", lambda: FakeStorage(transaction))
    monkeypatch.setattr(
        command,
        "migrate_paper_matching_status_enum",
        lambda connection, *, dry_run: (_ for _ in ()).throw(RuntimeError("bad migration")),
    )

    with caplog.at_level(logging.ERROR):
        assert command.main([]) != 0

    assert transaction.rolled_back is True
    assert "bad migration" in caplog.text
    assert "bad migration" in capsys.readouterr().err


def test_main_logs_connection_failure_and_returns_nonzero(monkeypatch, caplog, capsys):
    transaction = FakeTransaction(object(), error=ConnectionError("database unavailable"))
    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "get_storage", lambda: FakeStorage(transaction))

    with caplog.at_level(logging.ERROR):
        assert command.main([]) != 0

    assert "database unavailable" in caplog.text
    assert "database unavailable" in capsys.readouterr().err
