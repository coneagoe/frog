"""Tests for the unified enum migration operator command."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

import tools.migrate_enums as command


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
class FakeDomainResult:
    groups: tuple[FakeGroup, ...]


@dataclass(frozen=True)
class FakeDomain:
    name: str
    result: FakeDomainResult


@dataclass(frozen=True)
class FakeResult:
    dry_run: bool
    rollback: bool
    converted: bool
    rolled_back: bool
    domains: tuple[FakeDomain, ...]


def _result_with_paper_and_monitor_groups() -> FakeResult:
    return FakeResult(
        dry_run=True,
        rollback=False,
        converted=False,
        rolled_back=False,
        domains=(
            FakeDomain(
                "paper_trading",
                FakeDomainResult((FakeGroup("paper_order_side", (FakeColumn("paper_orders", "side"),)),)),
            ),
            FakeDomain(
                "monitor",
                FakeDomainResult((FakeGroup("monitor_market", (FakeColumn("stock_monitor_targets", "market"),)),)),
            ),
        ),
    )


def test_main_emits_stable_json_for_all_domains(monkeypatch, capsys) -> None:
    transaction = FakeTransaction()
    calls: list[dict[str, bool]] = []
    config_calls: list[None] = []

    def fake_migration(connection, *, dry_run: bool, rollback: bool) -> FakeResult:
        calls.append({"dry_run": dry_run, "rollback": rollback})
        return _result_with_paper_and_monitor_groups()

    monkeypatch.setattr(command, "parse_config", lambda: config_calls.append(None))
    monkeypatch.setattr(command, "get_storage", lambda: FakeStorage(transaction))
    monkeypatch.setattr(command, "migrate_enums", fake_migration)

    assert command.main(["--dry-run", "--json"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert calls == [{"dry_run": True, "rollback": False}]
    assert config_calls == [None]
    assert transaction.rolled_back is False
    assert output["dry_run"] is True
    assert output["rollback"] is False
    assert output["converted"] is False
    assert output["rolled_back"] is False
    assert [domain["name"] for domain in output["domains"]] == ["paper_trading", "monitor"]


def test_main_prints_ordered_human_domain_groups(monkeypatch, capsys) -> None:
    transaction = FakeTransaction()
    result = _result_with_paper_and_monitor_groups()
    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "get_storage", lambda: FakeStorage(transaction))
    monkeypatch.setattr(command, "migrate_enums", lambda connection, **kwargs: result)

    assert command.main([]) == 0

    assert capsys.readouterr().out == (
        "dry_run=true rollback=false converted=false rolled_back=false "
        "domains=paper_trading[paper_order_side:paper_orders.side];"
        "monitor[monitor_market:stock_monitor_targets.market]\n"
    )


def test_main_rolls_back_transaction_when_result_output_fails(monkeypatch, capsys) -> None:
    transaction = FakeTransaction()

    def raising_print_result(result, *, json_output: bool) -> None:
        raise RuntimeError("output failure")

    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "get_storage", lambda: FakeStorage(transaction))
    monkeypatch.setattr(command, "migrate_enums", lambda connection, **kwargs: _result_with_paper_and_monitor_groups())
    monkeypatch.setattr(command, "_print_result", raising_print_result)

    assert command.main([]) == 1

    assert transaction.rolled_back is True
    assert "error: output failure" in capsys.readouterr().err


@pytest.mark.parametrize("abbreviation", ["--dry", "--roll", "--j"])
def test_main_rejects_abbreviated_options(abbreviation: str) -> None:
    with pytest.raises(SystemExit) as error:
        command.main([abbreviation])

    assert error.value.code == 2


def test_script_help_works_when_invoked_outside_project_root() -> None:
    assert command.__file__ is not None
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
    assert "--json" in completed.stdout
