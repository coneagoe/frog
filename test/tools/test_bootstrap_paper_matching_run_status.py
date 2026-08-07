from __future__ import annotations

import json
import logging

from paper_trading.storage.matching_status_migration import MatchingStatusBootstrapResult
from tools import bootstrap_paper_matching_run_status as command


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


def _result(*, dry_run: bool) -> MatchingStatusBootstrapResult:
    return MatchingStatusBootstrapResult(
        dry_run=dry_run,
        table_exists=True,
        table_created=False,
        converted=not dry_run,
        labels=("running", "completed", "completed_with_warnings", "failed"),
        observed_legacy_values=("completed", "running"),
        index_verified=True,
    )


def test_main_emits_json_and_forwards_dry_run(monkeypatch, capsys):
    transaction = FakeTransaction(object())
    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "get_storage", lambda: FakeStorage(transaction))
    dry_runs: list[bool] = []

    def bootstrap(connection, *, dry_run):
        dry_runs.append(dry_run)
        return _result(dry_run=dry_run)

    monkeypatch.setattr(command, "bootstrap_paper_matching_run_status", bootstrap)

    assert command.main(["--dry-run", "--json"]) == 0

    assert dry_runs == [True]
    assert json.loads(capsys.readouterr().out) == {
        "converted": False,
        "dry_run": True,
        "index_verified": True,
        "labels": ["running", "completed", "completed_with_warnings", "failed"],
        "observed_legacy_values": ["completed", "running"],
        "table_created": False,
        "table_exists": True,
    }


def test_main_rolls_back_and_returns_nonzero(monkeypatch, caplog, capsys):
    transaction = FakeTransaction(object())
    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "get_storage", lambda: FakeStorage(transaction))
    monkeypatch.setattr(
        command,
        "bootstrap_paper_matching_run_status",
        lambda connection, *, dry_run: (_ for _ in ()).throw(RuntimeError("bad bootstrap")),
    )

    with caplog.at_level(logging.ERROR):
        assert command.main([]) == 1

    assert transaction.rolled_back is True
    assert "bad bootstrap" in caplog.text
    assert "bad bootstrap" in capsys.readouterr().err
