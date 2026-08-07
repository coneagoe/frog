"""Tests for the paper trading enum migration operator command."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import tools.migrate_paper_trading_enums as command


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


@dataclass(frozen=True)
class FakeGroup:
    type_name: str
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
            groups=(FakeGroup("paper_order_side", (FakeColumn("paper_orders", "side"),)),),
        )

    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "get_storage", lambda: FakeStorage(transaction))
    monkeypatch.setattr(command, "migrate_paper_trading_enums", fake_migration)

    assert command.main(["--dry-run", "--json"]) == 0

    assert calls == [{"dry_run": True, "rollback": False}]
    assert transaction.rolled_back is False
    assert json.loads(capsys.readouterr().out) == {
        "converted": False,
        "dry_run": True,
        "groups": [
            {"columns": [{"column_name": "side", "table_name": "paper_orders"}], "type_name": "paper_order_side"}
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
                "paper_market",
                (FakeColumn("paper_orders", "market"), FakeColumn("paper_trades", "market")),
            ),
        ),
    )
    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "get_storage", lambda: FakeStorage(transaction))
    monkeypatch.setattr(command, "migrate_paper_trading_enums", lambda connection, **kwargs: result)

    assert command.main([]) == 0

    assert capsys.readouterr().out == (
        "dry_run=false rollback=false converted=true rolled_back=false "
        "groups=paper_market:paper_orders.market,paper_trades.market\n"
    )


def test_main_forwards_rollback_and_rolls_back_transaction_on_error(monkeypatch, capsys):
    transaction = FakeTransaction()

    def raising_migration(connection, *, dry_run: bool, rollback: bool):
        assert dry_run is False
        assert rollback is True
        raise RuntimeError("migration failure")

    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "get_storage", lambda: FakeStorage(transaction))
    monkeypatch.setattr(command, "migrate_paper_trading_enums", raising_migration)

    assert command.main(["--rollback"]) == 1

    assert transaction.rolled_back is True
    assert "error: migration failure" in capsys.readouterr().err


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
