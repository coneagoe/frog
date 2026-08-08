from dataclasses import dataclass

import pytest

from storage.enum_governance import EnumGovernanceAdapter, EnumGovernanceError, migrate_enums


@dataclass
class FakeConnection:
    dialect_name: str = "postgresql"

    @property
    def dialect(self):
        return type("Dialect", (), {"name": self.dialect_name})()


def _adapter(
    name: str,
    events: list[str],
    *,
    changed: bool = True,
    fail_preflight: bool = False,
    fail_apply: bool = False,
) -> EnumGovernanceAdapter:
    def preflight(connection: FakeConnection, *, rollback: bool) -> None:
        del connection, rollback
        events.append(f"{name}.preflight")
        if fail_preflight:
            raise RuntimeError("preflight failed")

    def apply(connection: FakeConnection) -> bool:
        del connection
        events.append(f"{name}.apply")
        if fail_apply:
            raise RuntimeError("apply failed")
        return changed

    def verify(connection: FakeConnection, *, rollback: bool) -> None:
        del connection
        events.append(f"{name}.verify_rollback" if rollback else f"{name}.verify")

    def rollback(connection: FakeConnection) -> bool:
        del connection
        events.append(f"{name}.rollback")
        return changed

    def result(*, dry_run: bool, rollback: bool, converted: bool, rolled_back: bool) -> str:
        return f"{name}:{dry_run}:{rollback}:{converted}:{rolled_back}"

    return EnumGovernanceAdapter(name, preflight, apply, verify, rollback, result)


def test_normal_migration_preflights_every_adapter_before_ddl() -> None:
    events: list[str] = []

    result = migrate_enums(
        FakeConnection(),
        adapters=(_adapter("paper", events), _adapter("monitor", events)),
    )

    assert events == [
        "paper.preflight",
        "monitor.preflight",
        "paper.apply",
        "monitor.apply",
        "paper.verify",
        "monitor.verify",
    ]
    assert result.converted is True
    assert result.rolled_back is False
    assert [(domain.name, domain.result) for domain in result.domains] == [
        ("paper", "paper:False:False:True:False"),
        ("monitor", "monitor:False:False:True:False"),
    ]


def test_dry_run_only_preflights_adapters() -> None:
    events: list[str] = []

    result = migrate_enums(
        FakeConnection(),
        dry_run=True,
        adapters=(_adapter("paper", events), _adapter("monitor", events)),
    )

    assert events == ["paper.preflight", "monitor.preflight"]
    assert result.dry_run is True
    assert result.converted is False
    assert result.rolled_back is False
    assert [(domain.name, domain.result) for domain in result.domains] == [
        ("paper", "paper:True:False:False:False"),
        ("monitor", "monitor:True:False:False:False"),
    ]


def test_rollback_verifies_each_adapter_legacy_form() -> None:
    events: list[str] = []

    result = migrate_enums(
        FakeConnection(),
        rollback=True,
        adapters=(_adapter("paper", events), _adapter("monitor", events, changed=False)),
    )

    assert events == [
        "paper.preflight",
        "monitor.preflight",
        "paper.rollback",
        "monitor.rollback",
        "paper.verify_rollback",
        "monitor.verify_rollback",
    ]
    assert result.converted is False
    assert result.rolled_back is True
    assert [(domain.name, domain.result) for domain in result.domains] == [
        ("paper", "paper:False:True:False:True"),
        ("monitor", "monitor:False:True:False:True"),
    ]


def test_preflight_failure_prevents_every_apply() -> None:
    events: list[str] = []

    with pytest.raises(EnumGovernanceError, match="monitor preflight failed"):
        migrate_enums(
            FakeConnection(),
            adapters=(_adapter("paper", events), _adapter("monitor", events, fail_preflight=True)),
        )

    assert events == ["paper.preflight", "monitor.preflight"]


def test_domain_failure_names_adapter_and_preserves_cause() -> None:
    events: list[str] = []

    with pytest.raises(EnumGovernanceError, match="monitor apply failed") as caught:
        migrate_enums(
            FakeConnection(),
            adapters=(_adapter("paper", events), _adapter("monitor", events, fail_apply=True)),
        )

    assert isinstance(caught.value.__cause__, RuntimeError)
    assert str(caught.value.__cause__) == "apply failed"


def test_non_postgresql_connection_returns_no_change_without_adapters() -> None:
    events: list[str] = []

    result = migrate_enums(
        FakeConnection(dialect_name="sqlite"),
        adapters=(_adapter("paper", events), _adapter("monitor", events)),
    )

    assert events == []
    assert result.converted is False
    assert result.rolled_back is False
    assert [(domain.name, domain.result) for domain in result.domains] == [
        ("paper", "paper:False:False:False:False"),
        ("monitor", "monitor:False:False:False:False"),
    ]
