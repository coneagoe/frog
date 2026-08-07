import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAPER_ENUM_TYPES = (
    "paper_account_status",
    "paper_fee_preset",
    "paper_cash_event_type",
    "paper_order_side",
    "paper_order_status",
    "paper_trade_validity_status",
    "paper_market",
    "paper_position_source",
    "paper_round_trip_status",
    "paper_trade_validity_granularity",
    "paper_pending_settlement_source",
    "paper_ledger_rebuild_status",
    "paper_matching_run_status",
)


def _run_script(script: str, arguments: list[str], tmp_path: Path) -> tuple[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_file = tmp_path / "commands.log"
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        'printf \'%s\\n\' "$*" >> "$COMMAND_LOG"\n'
        "if [[ \"$*\" == *' psql '* && \"$*\" == *' -c '* ]]; then\n"
        '  for argument in "$@"; do\n'
        '    [[ "$argument" == type=* ]] && type_name="${argument#type=}"\n'
        "  done\n"
        '  printf "\'%s_label\'\\n" "$type_name"\n'
        "else\n"
        "  printf '%s\\n' '-- dump output'\n"
        "fi\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}:{environment['PATH']}"
    environment["COMMAND_LOG"] = str(log_file)
    result = subprocess.run(
        ["bash", str(ROOT / "tools" / script), *arguments],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout, log_file.read_text(encoding="utf-8")


def test_export_places_enum_before_matching_table_dump(tmp_path: Path):
    output_file = tmp_path / "matching.sql"
    _run_script("db_export.sh", ["--no-gzip", "--table", "paper_matching_runs", "--out", str(output_file)], tmp_path)

    dump = output_file.read_text(encoding="utf-8")
    assert dump.index("CREATE TYPE") < dump.index("-- dump output")
    assert "'paper_matching_run_status_label'" in dump
    commands = (tmp_path / "commands.log").read_text(encoding="utf-8").splitlines()
    database_commands = [command for command in commands if " psql " in command or " pg_dump " in command]
    assert database_commands[0].endswith("ORDER BY e.enumsortorder;")
    assert "pg_dump" in database_commands[1]


def test_clean_import_drops_matching_table_before_enum(tmp_path: Path):
    input_file = tmp_path / "matching.sql"
    input_file.write_text("SELECT 1;\n", encoding="utf-8")

    _run_script("db_import.sh", ["--clean", "--table", "paper_matching_runs", "--in", str(input_file)], tmp_path)

    drop_command = (tmp_path / "commands.log").read_text(encoding="utf-8")
    drop_sql = drop_command.split(" -c ", 1)[1]
    assert drop_sql.index('DROP TABLE IF EXISTS "public"."paper_matching_runs"') < drop_sql.index(
        'DROP TYPE IF EXISTS "public"."paper_matching_run_status"'
    )


def test_full_export_places_every_paper_enum_before_table_dump(tmp_path: Path):
    output_file = tmp_path / "paper.sql"
    _run_script("db_export.sh", ["--no-gzip", "--out", str(output_file)], tmp_path)

    dump = output_file.read_text(encoding="utf-8")
    for type_name in PAPER_ENUM_TYPES:
        assert f'CREATE TYPE "public"."{type_name}"' in dump
        assert dump.index(f'CREATE TYPE "public"."{type_name}"') < dump.index("-- dump output")


def test_clean_full_import_drops_tables_before_every_paper_enum(tmp_path: Path):
    input_file = tmp_path / "paper.sql"
    input_file.write_text("SELECT 1;\n", encoding="utf-8")

    _run_script("db_import.sh", ["--clean", "--in", str(input_file)], tmp_path)

    drop_sql = (tmp_path / "commands.log").read_text(encoding="utf-8").split(" -c ", 1)[1]
    for type_name in PAPER_ENUM_TYPES:
        assert drop_sql.index('DROP TABLE IF EXISTS "public"."paper_orders"') < drop_sql.index(
            f'DROP TYPE IF EXISTS "public"."{type_name}"'
        )
    drop_positions = [drop_sql.index(f'DROP TYPE IF EXISTS "public"."{type_name}"') for type_name in PAPER_ENUM_TYPES]
    assert drop_positions == sorted(drop_positions, reverse=True)


def test_clean_matching_export_drops_before_recreating_enum(tmp_path: Path):
    output_file = tmp_path / "matching.sql"
    _run_script(
        "db_export.sh",
        ["--no-gzip", "--clean", "--table", "paper_matching_runs", "--out", str(output_file)],
        tmp_path,
    )

    dump = output_file.read_text(encoding="utf-8")
    assert dump.index("DROP TABLE") < dump.index("DROP TYPE") < dump.index("CREATE TYPE")
    command = (tmp_path / "commands.log").read_text(encoding="utf-8")
    assert "--table=public.paper_matching_runs" in command
    assert "--clean" not in command


def test_clean_paper_orders_preserves_shared_enum_types(tmp_path: Path):
    output_file = tmp_path / "orders.sql"
    input_file = tmp_path / "orders-input.sql"
    input_file.write_text("SELECT 1;\n", encoding="utf-8")

    _run_script(
        "db_export.sh",
        ["--no-gzip", "--clean", "--table", "paper_orders", "--out", str(output_file)],
        tmp_path,
    )
    _run_script("db_import.sh", ["--clean", "--table", "paper_orders", "--in", str(input_file)], tmp_path)

    dump = output_file.read_text(encoding="utf-8")
    drop_sql = (tmp_path / "commands.log").read_text(encoding="utf-8").split(" -c ", 1)[1]
    assert 'DROP TYPE IF EXISTS "public"."paper_market"' not in dump
    assert 'DROP TYPE IF EXISTS "public"."paper_market"' not in drop_sql
    for type_name in ("paper_order_side", "paper_trade_validity_status", "paper_market"):
        assert f'CREATE TYPE "public"."{type_name}" AS ENUM' in dump
    assert "EXCEPTION WHEN duplicate_object THEN NULL" in dump


def test_clean_full_matching_export_retains_business_table_selection(tmp_path: Path):
    output_file = tmp_path / "matching.sql"
    _run_script("db_export.sh", ["--no-gzip", "--clean", "--out", str(output_file)], tmp_path)

    command = (tmp_path / "commands.log").read_text(encoding="utf-8")
    assert "--table=public.a_stock_basic" in command
    assert "--table=public.paper_matching_runs" in command
    assert "--table=public.paper_valuation_gaps" in command
    assert "--clean" not in command


def test_unrelated_export_does_not_query_enum(tmp_path: Path):
    output_file = tmp_path / "stock.sql"
    _run_script("db_export.sh", ["--no-gzip", "--table", "a_stock_basic", "--out", str(output_file)], tmp_path)

    commands = (tmp_path / "commands.log").read_text(encoding="utf-8")
    assert "psql" not in commands
    assert "pg_dump" in commands


def test_paper_accounts_export_queries_only_its_enum_types(tmp_path: Path):
    output_file = tmp_path / "accounts.sql"
    _run_script("db_export.sh", ["--no-gzip", "--table", "paper_accounts", "--out", str(output_file)], tmp_path)

    commands = (tmp_path / "commands.log").read_text(encoding="utf-8")
    assert "type=paper_account_status" in commands
    assert "type=paper_fee_preset" in commands
    assert "type=paper_matching_run_status" not in commands
