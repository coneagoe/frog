import os
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PLACEHOLDERS = (
    "placeholder:25:placeholder:placeholder:"
    "placeholder@example.invalid:placeholder@example.invalid:placeholder:placeholder:"
    "false:https://placeholder.example.invalid:owner@example.invalid"
)


def _run_test_runner(
    arguments: list[str],
    tmp_path: Path,
    pytest_status: int,
    occupied_ports: tuple[int, ...] = (5433,),
    environment_overrides: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    command_log = tmp_path / "commands.log"
    (bin_dir / "docker").write_text(
        "#!/usr/bin/env bash\n"
        "printf 'docker %s TEST_DB_HOST_PORT=%s TEST_POSTGRESQL_URL=%s "
        "FROG_ENV=%s PAPER_TRADING_JWT_SECRET=%s PAPER_TRADING_COOKIE_SECURE=%s "
        "COMPOSE_PLACEHOLDERS=%s:%s:%s:%s:%s:%s:%s:%s:%s:%s:%s\\n' "
        '"${*}" "${TEST_DB_HOST_PORT:-}" "${TEST_POSTGRESQL_URL:-}" '
        '"${FROG_ENV:-}" "${PAPER_TRADING_JWT_SECRET:-}" "${PAPER_TRADING_COOKIE_SECURE:-}" '
        '"${SMTP_HOST:-}" "${SMTP_PORT:-}" "${SMTP_USER:-}" '
        '"${SMTP_PASSWORD:-}" "${SMTP_MAIL_FROM:-}" "${ALERT_EMAILS:-}" '
        '"${TUSHARE_TOKEN:-}" "${PAPER_TRADING_API_TOKEN:-}" '
        '"${AUTH_REGISTRATION_ENABLED:-}" "${AUTH_PUBLIC_BASE_URL:-}" "${AUTH_OWNER_EMAIL:-}" '
        '>> "$COMMAND_LOG"\n',
        encoding="utf-8",
    )
    (bin_dir / "uv").write_text(
        "#!/usr/bin/env bash\n"
        "printf 'uv %s TEST_DB_HOST_PORT=%s TEST_POSTGRESQL_URL=%s "
        "FROG_ENV=%s PAPER_TRADING_JWT_SECRET=%s PAPER_TRADING_COOKIE_SECURE=%s\\n' "
        '"$*" "$TEST_DB_HOST_PORT" "$TEST_POSTGRESQL_URL" "$FROG_ENV" '
        '"$PAPER_TRADING_JWT_SECRET" "$PAPER_TRADING_COOKIE_SECURE" >> "$COMMAND_LOG"\n'
        'exit "$PYTEST_STATUS"\n',
        encoding="utf-8",
    )
    for executable in bin_dir.iterdir():
        executable.chmod(0o755)
    occupied_case = (
        f'case "${{@: -1}}" in {"|".join(map(str, occupied_ports))}) exit 0;; esac\n'
        if len(occupied_ports) < 100
        else ""
    )
    (bin_dir / "nc").write_text(
        "#!/usr/bin/env bash\n" + occupied_case + "exit 1\n",
        encoding="utf-8",
    )
    (bin_dir / "nc").chmod(0o755)

    environment = os.environ.copy()
    environment["COMMAND_LOG"] = str(command_log)
    environment["PATH"] = f"{bin_dir}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    environment["PYTEST_STATUS"] = str(pytest_status)
    environment.pop("TEST_DB_HOST_PORT", None)
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
        "AUTH_REGISTRATION_ENABLED",
        "AUTH_PUBLIC_BASE_URL",
        "AUTH_OWNER_EMAIL",
    ):
        environment.pop(name, None)
    for name in ("FROG_ENV", "PAPER_TRADING_JWT_SECRET", "PAPER_TRADING_COOKIE_SECURE"):
        environment.pop(name, None)
    if environment_overrides:
        environment.update(environment_overrides)
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
    assert 'ports: ["127.0.0.1:${TEST_DB_HOST_PORT:-5433}:5432"]' in test_db_block
    assert "- /var/lib/postgresql/data" in test_db_block
    assert "./docker/db:/var/lib/postgresql/data" in compose_file


def test_runner_starts_test_database_runs_pytest_and_cleans_up(tmp_path: Path):
    completed, commands = _run_test_runner(["-k", "enum"], tmp_path, pytest_status=0)

    assert completed.returncode == 0
    assert commands == [
        "docker compose up -d --wait test_db TEST_DB_HOST_PORT=5434 "
        "TEST_POSTGRESQL_URL= FROG_ENV=test PAPER_TRADING_JWT_SECRET="
        "test-jwt-secret-for-runner-defaults-1234567890 PAPER_TRADING_COOKIE_SECURE=false "
        f"COMPOSE_PLACEHOLDERS={COMPOSE_PLACEHOLDERS}",
        "uv run pytest test -k enum TEST_DB_HOST_PORT=5434 "
        "TEST_POSTGRESQL_URL=postgresql://quant:quant@127.0.0.1:5434/quant "
        "FROG_ENV=test PAPER_TRADING_JWT_SECRET="
        "test-jwt-secret-for-runner-defaults-1234567890 PAPER_TRADING_COOKIE_SECURE=false",
        "docker compose rm -sfv test_db TEST_DB_HOST_PORT=5434 "
        "TEST_POSTGRESQL_URL= FROG_ENV=test PAPER_TRADING_JWT_SECRET="
        "test-jwt-secret-for-runner-defaults-1234567890 PAPER_TRADING_COOKIE_SECURE=false "
        f"COMPOSE_PLACEHOLDERS={COMPOSE_PLACEHOLDERS}",
    ]


def test_compose_contract_keeps_paper_trading_on_shared_smtp_and_redis_dependencies():
    compose_file = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    paper_trading_block = compose_file.split("  paper-trading:\n", maxsplit=1)[1].split("  paper-trading-frontend:\n", maxsplit=1)[0]

    assert "redis:\n        condition: service_started" in paper_trading_block
    assert "<<: [*db-common-env, *airflow-email-env]" in paper_trading_block
    assert "REDIS_URL: redis://redis:6379/0" in paper_trading_block
    assert "MAIL_SERVER: ${SMTP_HOST:?SMTP_HOST is required}" in compose_file
    assert "MAIL_RECEIVERS: ${ALERT_EMAILS:?ALERT_EMAILS is required}" in compose_file


def test_runner_preserves_explicit_auth_environment(tmp_path: Path):
    overrides = {
        "FROG_ENV": "ci",
        "PAPER_TRADING_JWT_SECRET": "explicit-secret-value",
        "PAPER_TRADING_COOKIE_SECURE": "true",
    }
    completed, commands = _run_test_runner([], tmp_path, pytest_status=0, environment_overrides=overrides)

    assert completed.returncode == 0
    assert all(f"{name}={value}" in command for command in commands for name, value in overrides.items())


def test_runner_preserves_pytest_failure_after_cleanup(tmp_path: Path):
    completed, commands = _run_test_runner([], tmp_path, pytest_status=1)

    assert completed.returncode == 1
    assert commands[-1] == (
        "docker compose rm -sfv test_db TEST_DB_HOST_PORT=5434 "
        "TEST_POSTGRESQL_URL= FROG_ENV=test PAPER_TRADING_JWT_SECRET="
        "test-jwt-secret-for-runner-defaults-1234567890 PAPER_TRADING_COOKIE_SECURE=false "
        f"COMPOSE_PLACEHOLDERS={COMPOSE_PLACEHOLDERS}"
    )


def test_runner_skips_consecutive_occupied_ports(tmp_path: Path):
    completed, commands = _run_test_runner([], tmp_path, pytest_status=0, occupied_ports=(5433, 5434))

    assert completed.returncode == 0
    assert "TEST_DB_HOST_PORT=5435" in commands[0]
    assert "127.0.0.1:5435/quant" in commands[1]


def test_runner_fails_when_all_ports_are_occupied(tmp_path: Path):
    result = subprocess.run(
        [
            "bash",
            "-c",
            'nc() { return 0; }; source "$1"; printf loaded; find_available_port',
            "bash",
            str(ROOT / "tools" / "run_tests.sh"),
        ],
        env={**os.environ, "LC_ALL": "C"},
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert result.stdout == "loaded"
    assert result.stderr == "No available loopback port in range 5433-65535\n"


def test_find_available_port_uses_dev_tcp_without_nc():
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(("127.0.0.1", 5433))
        except OSError:
            pass
        else:
            listener.listen()

        result = subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; find_available_port',
                "bash",
                str(ROOT / "tools" / "run_tests.sh"),
            ],
            env={"PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
        )

    assert result.returncode == 0
    selected_port = result.stdout.strip()
    assert selected_port.isdigit()
    assert int(selected_port) > 5433


def test_sourcing_runner_does_not_clean_up_with_docker(tmp_path: Path):
    docker_log = tmp_path / "docker.log"
    fake_docker = tmp_path / "docker"
    fake_docker.write_text(
        '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$DOCKER_LOG"\n',
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)

    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; find_available_port >/dev/null',
            "bash",
            str(ROOT / "tools" / "run_tests.sh"),
        ],
        env={
            **os.environ,
            "DOCKER_LOG": str(docker_log),
            "PATH": f"{tmp_path}:/usr/bin:/bin",
        },
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert not docker_log.exists()
