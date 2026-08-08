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
MONITOR_ENUM_TYPES = (
    "monitor_market",
    "monitor_frequency",
    "monitor_reset_mode",
    "forecast_ssf_candidate_state",
)


def _run_script_result(
    script: str,
    arguments: list[str],
    tmp_path: Path,
    *,
    inbound_foreign_key: str = "",
    unmanaged_inbound_foreign_key: str = "",
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_file = tmp_path / "commands.log"
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        'printf \'%s\\n\' "$*" >> "$COMMAND_LOG"\n'
        "if [[ \"$*\" == *' psql '* ]]; then\n"
        "  cat >/dev/null\n"
        "  if [[ \"$*\" == *'pg_constraint'* ]]; then\n"
        "    if [[ \"$*\" == *'source_table.relname NOT IN'* ]]; then\n"
        '      [[ -n "$UNMANAGED_INBOUND_FOREIGN_KEY" ]] && printf \'%s\\n\' "$UNMANAGED_INBOUND_FOREIGN_KEY"\n'
        "    else\n"
        '      [[ -n "$INBOUND_FOREIGN_KEY" ]] && printf \'%s\\n\' "$INBOUND_FOREIGN_KEY"\n'
        "    fi\n"
        "    exit 0\n"
        "  fi\n"
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
    environment["INBOUND_FOREIGN_KEY"] = inbound_foreign_key
    environment["UNMANAGED_INBOUND_FOREIGN_KEY"] = unmanaged_inbound_foreign_key
    return subprocess.run(
        ["bash", str(ROOT / "tools" / script), *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )


def _run_script(script: str, arguments: list[str], tmp_path: Path) -> tuple[str, str]:
    result = _run_script_result(script, arguments, tmp_path)
    result.check_returncode()
    return result.stdout, (tmp_path / "commands.log").read_text(encoding="utf-8")


def test_export_places_enum_before_matching_table_dump(tmp_path: Path):
    output_file = tmp_path / "matching.sql"
    _run_script("db_export.sh", ["--no-gzip", "--table", "paper_matching_runs", "--out", str(output_file)], tmp_path)

    dump = output_file.read_text(encoding="utf-8")
    assert dump.index("CREATE TYPE") < dump.index("-- dump output")
    assert "'paper_matching_run_status_label'" in dump
    commands = (tmp_path / "commands.log").read_text(encoding="utf-8").splitlines()
    database_commands = [command for command in commands if " psql " in command or " pg_dump " in command]
    assert "type=paper_matching_run_status" in database_commands[0]
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


def test_full_export_includes_storage_enum_types_before_table_dump(tmp_path: Path):
    output_file = tmp_path / "storage.sql"
    _run_script("db_export.sh", ["--no-gzip", "--out", str(output_file)], tmp_path)

    dump = output_file.read_text(encoding="utf-8")
    for type_name in (
        "blackroom_market",
        "blackroom_source",
        "daily_bar_diagnostic_adjust",
        "daily_bar_diagnostic_classification",
        "ssf_change_signal_status",
    ):
        assert f'CREATE TYPE "public"."{type_name}"' in dump
        assert dump.index(f'CREATE TYPE "public"."{type_name}"') < dump.index("-- dump output")


def test_selected_storage_table_exports_only_required_storage_types(tmp_path: Path):
    output_file = tmp_path / "diagnostics.sql"
    _run_script(
        "db_export.sh",
        ["--no-gzip", "--table", "daily_bar_diagnostics", "--out", str(output_file)],
        tmp_path,
    )

    dump = output_file.read_text(encoding="utf-8")
    assert 'CREATE TYPE "public"."daily_bar_diagnostic_adjust"' in dump
    assert 'CREATE TYPE "public"."daily_bar_diagnostic_classification"' in dump
    assert 'CREATE TYPE "public"."blackroom_market"' not in dump
    assert 'CREATE TYPE "public"."ssf_change_signal_status"' not in dump


def test_selected_storage_table_clean_drops_private_types_only(tmp_path: Path):
    input_file = tmp_path / "diagnostics.sql"
    input_file.write_text("SELECT 1;\n", encoding="utf-8")
    _run_script(
        "db_import.sh",
        ["--clean", "--table", "daily_bar_diagnostics", "--in", str(input_file)],
        tmp_path,
    )

    drop_sql = (tmp_path / "commands.log").read_text(encoding="utf-8").split(" -c ", 1)[1]
    assert 'DROP TYPE IF EXISTS "public"."daily_bar_diagnostic_adjust"' in drop_sql
    assert 'DROP TYPE IF EXISTS "public"."daily_bar_diagnostic_classification"' in drop_sql
    assert 'DROP TYPE IF EXISTS "public"."blackroom_market"' not in drop_sql


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


def test_clean_full_import_rejects_unmanaged_inbound_foreign_key_before_drop(tmp_path: Path):
    input_file = tmp_path / "paper.sql"
    input_file.write_text("SELECT 1;\n", encoding="utf-8")

    result = _run_script_result(
        "db_import.sh",
        ["--clean", "--in", str(input_file)],
        tmp_path,
        unmanaged_inbound_foreign_key="external_audit.paper_orders_audit_order_id_fkey",
    )

    assert result.returncode != 0
    assert "unmanaged inbound foreign key" in result.stderr
    assert "DROP TABLE" not in (tmp_path / "commands.log").read_text(encoding="utf-8")


def test_clean_full_export_rejects_unmanaged_inbound_foreign_key_before_drop(tmp_path: Path):
    output_file = tmp_path / "paper.sql"
    output_file.write_text("existing dump\n", encoding="utf-8")

    result = _run_script_result(
        "db_export.sh",
        ["--clean", "--no-gzip", "--out", str(output_file)],
        tmp_path,
        unmanaged_inbound_foreign_key="external_audit.paper_orders_audit_order_id_fkey",
    )

    assert result.returncode != 0
    assert "unmanaged inbound foreign key" in result.stderr
    assert output_file.read_text(encoding="utf-8") == "existing dump\n"


def test_clean_selected_table_export_is_rejected_before_output_or_database_access(tmp_path: Path):
    output_file = tmp_path / "orders.sql"
    output_file.write_text("existing dump\n", encoding="utf-8")

    result = _run_script_result(
        "db_export.sh",
        ["--no-gzip", "--clean", "--table", "paper_orders", "--out", str(output_file)],
        tmp_path,
    )

    assert result.returncode != 0
    assert "cannot be combined with --table" in result.stderr
    assert output_file.read_text(encoding="utf-8") == "existing dump\n"
    assert not (tmp_path / "commands.log").exists()


def test_paper_orders_export_preserves_shared_enum_types(tmp_path: Path):
    output_file = tmp_path / "orders.sql"
    input_file = tmp_path / "orders-input.sql"
    input_file.write_text("SELECT 1;\n", encoding="utf-8")

    _run_script(
        "db_export.sh",
        ["--no-gzip", "--table", "paper_orders", "--out", str(output_file)],
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


def test_clean_paper_orders_import_rejects_unselected_inbound_foreign_key(tmp_path: Path):
    input_file = tmp_path / "orders.sql"
    input_file.write_text("SELECT 1;\n", encoding="utf-8")

    result = _run_script_result(
        "db_import.sh",
        ["--clean", "--table", "paper_orders", "--in", str(input_file)],
        tmp_path,
        inbound_foreign_key="paper_trades.paper_trades_order_id_fkey",
    )

    assert result.returncode != 0
    assert "unselected inbound foreign key" in result.stderr
    assert "DROP TABLE" not in (tmp_path / "commands.log").read_text(encoding="utf-8")


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


def test_selected_monitor_target_dump_creates_required_monitor_types_before_table(tmp_path: Path):
    output_file = tmp_path / "targets.sql"
    _run_script("db_export.sh", ["--no-gzip", "--table", "stock_monitor_targets", "--out", str(output_file)], tmp_path)

    dump = output_file.read_text(encoding="utf-8")
    for type_name in ("monitor_market", "monitor_frequency", "monitor_reset_mode"):
        assert dump.index(f'CREATE TYPE "public"."{type_name}"') < dump.index("-- dump output")
    assert 'CREATE TYPE "public"."forecast_ssf_candidate_state"' not in dump


def test_selected_forecast_ssf_candidate_dump_creates_required_monitor_types_before_table(tmp_path: Path):
    output_file = tmp_path / "candidates.sql"
    _run_script(
        "db_export.sh",
        ["--no-gzip", "--table", "forecast_ssf_candidates", "--out", str(output_file)],
        tmp_path,
    )

    dump = output_file.read_text(encoding="utf-8")
    for type_name in ("monitor_market", "forecast_ssf_candidate_state"):
        assert dump.index(f'CREATE TYPE "public"."{type_name}"') < dump.index("-- dump output")
    assert 'CREATE TYPE "public"."monitor_frequency"' not in dump
    assert 'CREATE TYPE "public"."monitor_reset_mode"' not in dump


def test_selected_monitor_target_clean_does_not_drop_shared_monitor_market(tmp_path: Path):
    input_file = tmp_path / "targets.sql"
    input_file.write_text("SELECT 1;\n", encoding="utf-8")

    _run_script("db_import.sh", ["--clean", "--table", "stock_monitor_targets", "--in", str(input_file)], tmp_path)

    drop_sql = (tmp_path / "commands.log").read_text(encoding="utf-8").split(" -c ", 1)[1]
    assert 'DROP TYPE IF EXISTS "public"."monitor_market"' not in drop_sql
    assert 'DROP TYPE IF EXISTS "public"."monitor_frequency"' in drop_sql
    assert 'DROP TYPE IF EXISTS "public"."monitor_reset_mode"' in drop_sql


def test_clean_full_import_drops_tables_before_every_monitor_enum(tmp_path: Path):
    input_file = tmp_path / "monitor.sql"
    input_file.write_text("SELECT 1;\n", encoding="utf-8")

    _run_script("db_import.sh", ["--clean", "--in", str(input_file)], tmp_path)

    drop_sql = (tmp_path / "commands.log").read_text(encoding="utf-8").split(" -c ", 1)[1]
    for type_name in MONITOR_ENUM_TYPES:
        assert drop_sql.index('DROP TABLE IF EXISTS "public"."stock_monitor_targets"') < drop_sql.index(
            f'DROP TYPE IF EXISTS "public"."{type_name}"'
        )
    drop_positions = [drop_sql.index(f'DROP TYPE IF EXISTS "public"."{type_name}"') for type_name in MONITOR_ENUM_TYPES]
    assert drop_positions == sorted(drop_positions, reverse=True)
