"""Tests for the Monitor enum migration operator command."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

import tools.migrate_monitor_enums as command


@dataclass
class FakeTransaction:
    rolled_back: bool = False

    def __enter__(self) -> "FakeTransaction":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.rolled_back = exc_type is not None


class FakeStorage:
    def __init__(self, transaction: FakeTransaction) -> None:
        self.engine = self
        self.transaction = transaction

    def begin(self) -> FakeTransaction:
        return self.transaction


@dataclass(frozen=True)
class FakeColumn:
    table_name: str
    column_name: str
    legacy_type_sql: str
    default_sql: str | None
    nullable: bool


@dataclass(frozen=True)
class FakeGroup:
    type_name: str
    labels: tuple[str, ...]
    columns: tuple[FakeColumn, ...]


@dataclass(frozen=True)
class FakeResult:
    dry_run: bool
    rollback: bool
    converted: bool
    rolled_back: bool
    groups: tuple[FakeGroup, ...]


def test_main_forwards_dry_run_and_emits_stable_json(monkeypatch, capsys):
    transaction = FakeTransaction()
    calls: list[dict[str, bool]] = []

    def fake_migration(connection, *, dry_run: bool, rollback: bool) -> FakeResult:
        calls.append({"dry_run": dry_run, "rollback": rollback})
        return FakeResult(
            dry_run=True,
            rollback=False,
            converted=False,
            rolled_back=False,
            groups=(
                FakeGroup(
                    "monitor_market",
                    ("A", "HK"),
                    (FakeColumn("stock_monitor_targets", "market", "VARCHAR(5)", "'A'", False),),
                ),
            ),
        )

    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "get_storage", lambda: FakeStorage(transaction))
    monkeypatch.setattr(command, "migrate_monitor_enums", fake_migration)

    assert command.main(["--dry-run", "--json"]) == 0

    assert calls == [{"dry_run": True, "rollback": False}]
    assert transaction.rolled_back is False
    assert json.loads(capsys.readouterr().out) == {
        "converted": False,
        "dry_run": True,
        "groups": [
            {
                "columns": [
                    {
                        "column_name": "market",
                        "default_sql": "'A'",
                        "legacy_type_sql": "VARCHAR(5)",
                        "nullable": False,
                        "table_name": "stock_monitor_targets",
                    }
                ],
                "labels": ["A", "HK"],
                "type_name": "monitor_market",
            }
        ],
        "rollback": False,
        "rolled_back": False,
    }


def test_main_prints_stable_human_group_summary(monkeypatch, capsys):
    transaction = FakeTransaction()
    result = FakeResult(
        dry_run=False,
        rollback=False,
        converted=True,
        rolled_back=False,
        groups=(
            FakeGroup(
                "monitor_market",
                ("A", "HK"),
                (
                    FakeColumn("stock_monitor_targets", "market", "VARCHAR(5)", "'A'", False),
                    FakeColumn("forecast_ssf_candidates", "market", "VARCHAR(5)", "'A'", False),
                ),
            ),
        ),
    )
    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "get_storage", lambda: FakeStorage(transaction))
    monkeypatch.setattr(command, "migrate_monitor_enums", lambda connection, **kwargs: result)

    assert command.main([]) == 0

    assert capsys.readouterr().out == (
        "dry_run=false rollback=false converted=true rolled_back=false "
        "groups=monitor_market:stock_monitor_targets.market,forecast_ssf_candidates.market\n"
    )


def test_main_forwards_rollback_and_rolls_back_transaction_on_error(monkeypatch, capsys):
    transaction = FakeTransaction()

    def raising_migration(connection, *, dry_run: bool, rollback: bool):
        assert dry_run is False
        assert rollback is True
        raise RuntimeError("migration failure")

    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "get_storage", lambda: FakeStorage(transaction))
    monkeypatch.setattr(command, "migrate_monitor_enums", raising_migration)

    assert command.main(["--rollback"]) == 1

    assert transaction.rolled_back is True
    assert "error: migration failure" in capsys.readouterr().err


@pytest.mark.parametrize("abbreviation", ["--dry", "--roll", "--j"])
def test_main_rejects_abbreviated_options(abbreviation: str):
    with pytest.raises(SystemExit) as error:
        command.main([abbreviation])

    assert error.value.code == 2


def test_script_help_works_when_invoked_outside_project_root():
    script = Path(command.__file__).resolve()
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd="/tmp",
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--dry-run" in completed.stdout
    assert "--rollback" in completed.stdout
