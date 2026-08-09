import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PLACEHOLDERS = (
    "placeholder:25:placeholder:placeholder:"
    "placeholder@example.invalid:placeholder@example.invalid:placeholder:placeholder"
)


def _run_test_runner(
    arguments: list[str], tmp_path: Path, pytest_status: int
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    command_log = tmp_path / "commands.log"
    (bin_dir / "docker").write_text(
        "#!/usr/bin/env bash\n"
        "printf 'docker %s TEST_POSTGRESQL_URL=%s COMPOSE_PLACEHOLDERS=%s:%s:%s:%s:%s:%s:%s:%s\\n' "
        '"${*}" "${TEST_POSTGRESQL_URL:-}" '
        '"${SMTP_HOST:-}" "${SMTP_PORT:-}" "${SMTP_USER:-}" '
        '"${SMTP_PASSWORD:-}" "${SMTP_MAIL_FROM:-}" "${ALERT_EMAILS:-}" '
        '"${TUSHARE_TOKEN:-}" "${PAPER_TRADING_API_TOKEN:-}" '
        '>> "$COMMAND_LOG"\n',
        encoding="utf-8",
    )
    (bin_dir / "uv").write_text(
        "#!/usr/bin/env bash\n"
        'printf \'uv %s TEST_POSTGRESQL_URL=%s\\n\' "$*" "$TEST_POSTGRESQL_URL" >> "$COMMAND_LOG"\n'
        'exit "$PYTEST_STATUS"\n',
        encoding="utf-8",
    )
    for executable in bin_dir.iterdir():
        executable.chmod(0o755)

    environment = os.environ.copy()
    environment["COMMAND_LOG"] = str(command_log)
    environment["PATH"] = f"{bin_dir}:{environment['PATH']}"
    environment["PYTEST_STATUS"] = str(pytest_status)
    environment["TEST_POSTGRESQL_URL"] = "postgresql://sentinel:sentinel@127.0.0.1:5433/sentinel"
    for name in (
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "SMTP_MAIL_FROM",
        "ALERT_EMAILS",
        "TUSHARE_TOKEN",
        "PAPER_TRADING_API_TOKEN",
    ):
        environment.pop(name, None)
    completed = subprocess.run(
        ["bash", str(ROOT / "tools" / "run_tests.sh"), *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    commands = command_log.read_text(encoding="utf-8").splitlines() if command_log.exists() else []
    return completed, commands


def test_compose_defines_isolated_test_database():
    compose_file = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    test_db_block = compose_file.split("  test_db:\n", maxsplit=1)[1].split("  db:\n", maxsplit=1)[0]

    assert "timescale/timescaledb:latest-pg16" in test_db_block
    assert 'ports: ["127.0.0.1:5433:5432"]' in test_db_block
    assert "- /var/lib/postgresql/data" in test_db_block
    assert "./docker/db:/var/lib/postgresql/data" in compose_file


def test_runner_starts_test_database_runs_pytest_and_cleans_up(tmp_path: Path):
    completed, commands = _run_test_runner(["-k", "enum"], tmp_path, pytest_status=0)

    assert completed.returncode == 0
    assert commands == [
        f"docker compose up -d --wait test_db TEST_POSTGRESQL_URL= COMPOSE_PLACEHOLDERS={COMPOSE_PLACEHOLDERS}",
        "uv run pytest test -k enum TEST_POSTGRESQL_URL=postgresql://quant:quant@127.0.0.1:5433/quant",
        f"docker compose rm -sfv test_db TEST_POSTGRESQL_URL= COMPOSE_PLACEHOLDERS={COMPOSE_PLACEHOLDERS}",
    ]


def test_runner_preserves_pytest_failure_after_cleanup(tmp_path: Path):
    completed, commands = _run_test_runner([], tmp_path, pytest_status=1)

    assert completed.returncode == 1
    assert commands[-1] == (
        f"docker compose rm -sfv test_db TEST_POSTGRESQL_URL= COMPOSE_PLACEHOLDERS={COMPOSE_PLACEHOLDERS}"
    )
