import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run_test_runner(
    arguments: list[str], tmp_path: Path, pytest_status: int
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    command_log = tmp_path / "commands.log"
    (bin_dir / "docker").write_text(
        '#!/usr/bin/env bash\nprintf \'docker %s\\n\' "$*" >> "$COMMAND_LOG"\n',
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

    assert "  test_db:\n" in compose_file
    assert "timescale/timescaledb:latest-pg16" in compose_file
    assert 'ports: ["127.0.0.1:5433:5432"]' in compose_file
    assert "- /var/lib/postgresql/data" in compose_file
    assert "./docker/db:/var/lib/postgresql/data" in compose_file


def test_runner_starts_test_database_runs_pytest_and_cleans_up(tmp_path: Path):
    completed, commands = _run_test_runner(["-k", "enum"], tmp_path, pytest_status=0)

    assert completed.returncode == 0
    assert commands == [
        "docker compose up -d --wait test_db",
        "uv run pytest test -k enum TEST_POSTGRESQL_URL=postgresql://quant:quant@localhost:5433/quant",
        "docker compose rm -sfv test_db",
    ]


def test_runner_preserves_pytest_failure_after_cleanup(tmp_path: Path):
    completed, commands = _run_test_runner([], tmp_path, pytest_status=1)

    assert completed.returncode == 1
    assert commands[-1] == "docker compose rm -sfv test_db"
