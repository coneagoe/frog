#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Import business tables into PostgreSQL using psql.

Default mode is Docker (docker compose exec db). Input should be a plain SQL dump (optionally .gz).

Usage:
  bash tools/pg_import.sh --in FILE [options]
  cat dump.sql | bash tools/pg_import.sh [options]

Options:
  --in FILE           Input file (.sql or .sql.gz). If omitted, reads from stdin.
  --schema NAME       Schema for business tables (used for --clean drop list; default: public)
  --clean             Drop business tables before importing (DROP TABLE IF EXISTS ... CASCADE)

  --docker            Use docker compose exec (default)
  --direct            Connect directly using local psql
  --service NAME      Docker compose service name (default: db)

  --db NAME           Database name (default: quant)
  --user NAME         Database user (default: quant)
  --host HOST         Host (direct mode only; default: localhost)
  --port PORT         Port (direct mode only; default: 5432)

Environment variables (direct mode):
  DB_HOST / db_host, DB_PORT / db_port, DB_NAME, DB_USER / db_username, DB_PASSWORD / db_password
  PGPASSWORD can also be used.

Examples:
  # docker mode, import from file
  bash tools/pg_import.sh --in ./backups/quant_business_xxx.sql.gz

  # drop business tables first
  bash tools/pg_import.sh --clean --in ./backups/quant_business_xxx.sql

  # direct mode (requires psql installed locally)
  DB_HOST=localhost DB_PASSWORD=quant bash tools/pg_import.sh --direct --in dump.sql
USAGE
}

err() {
  echo "[pg_import] $*" >&2
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { err "Missing required command: $1"; exit 127; }
}

pick_docker_compose() {
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
    return 0
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
    return 0
  fi
  return 1
}

# Business tables defined in storage/model
BUSINESS_TABLES=(
  general_info_stock
  general_info_etf
  general_info_hk_ggt
  ingredient_300
  ingredient_500
  history_data_daily_a_stock_qfq
  history_data_daily_a_stock_hfq
  history_data_weekly_a_stock_qfq
  history_data_weekly_a_stock_hfq
  history_data_daily_etf_qfq
  history_data_daily_etf_hfq
  history_data_weekly_etf_qfq
  history_data_weekly_etf_hfq
  history_data_daily_hk_stock_hfq
  history_data_weekly_hk_stock_hfq
  history_data_monthly_hk_stock_hfq
)

MODE="docker"
SERVICE="db"
DB_NAME="quant"
DB_USER="quant"
DB_HOST="${DB_HOST:-${db_host:-localhost}}"
DB_PORT="${DB_PORT:-${db_port:-5432}}"
DB_PASSWORD="${DB_PASSWORD:-${db_password:-}}"
SCHEMA="public"
IN_FILE=""
CLEAN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --in)
      IN_FILE="$2"
      shift 2
      ;;
    --schema)
      SCHEMA="$2"
      shift 2
      ;;
    --clean)
      CLEAN=1
      shift
      ;;
    --docker)
      MODE="docker"
      shift
      ;;
    --direct)
      MODE="direct"
      shift
      ;;
    --service)
      SERVICE="$2"
      shift 2
      ;;
    --db)
      DB_NAME="$2"
      shift 2
      ;;
    --user)
      DB_USER="$2"
      shift 2
      ;;
    --host)
      DB_HOST="$2"
      shift 2
      ;;
    --port)
      DB_PORT="$2"
      shift 2
      ;;
    *)
      err "Unknown argument: $1"
      err "Run with --help for usage."
      exit 2
      ;;
  esac
 done

if [[ -n "$DB_PASSWORD" && -z "${PGPASSWORD:-}" ]]; then
  export PGPASSWORD="$DB_PASSWORD"
fi

# Build a single drop statement (only if --clean)
DROP_SQL=""
if [[ $CLEAN -eq 1 ]]; then
  DROP_SQL="BEGIN;"
  for t in "${BUSINESS_TABLES[@]}"; do
    DROP_SQL+=" DROP TABLE IF EXISTS \"${SCHEMA}\".\"${t}\" CASCADE;"
  done
  DROP_SQL+=" COMMIT;"
fi

psql_args_common=(
  -v ON_ERROR_STOP=1
  -U "$DB_USER"
  -d "$DB_NAME"
)

run_drop_docker() {
  local dc
  dc="$(pick_docker_compose)" || { err "docker compose (or docker-compose) not found"; exit 127; }
  # shellcheck disable=SC2086
  $dc exec -T "$SERVICE" env PGPASSWORD="${PGPASSWORD:-}" psql "${psql_args_common[@]}" -c "$DROP_SQL"
}

run_drop_direct() {
  need_cmd psql
  psql -h "$DB_HOST" -p "$DB_PORT" "${psql_args_common[@]}" -c "$DROP_SQL"
}

run_import_stream_docker() {
  local dc
  dc="$(pick_docker_compose)" || { err "docker compose (or docker-compose) not found"; exit 127; }
  # shellcheck disable=SC2086
  $dc exec -T "$SERVICE" env PGPASSWORD="${PGPASSWORD:-}" psql "${psql_args_common[@]}"
}

run_import_stream_direct() {
  need_cmd psql
  psql -h "$DB_HOST" -p "$DB_PORT" "${psql_args_common[@]}"
}

if [[ $CLEAN -eq 1 ]]; then
  if [[ "$MODE" == "docker" ]]; then
    run_drop_docker
  else
    run_drop_direct
  fi
fi

# Import dump
if [[ -n "$IN_FILE" ]]; then
  if [[ ! -f "$IN_FILE" ]]; then
    err "Input file not found: $IN_FILE"
    exit 2
  fi

  if [[ "$IN_FILE" == *.gz ]]; then
    if [[ "$MODE" == "docker" ]]; then
      need_cmd gzip
      gzip -dc "$IN_FILE" | run_import_stream_docker
    else
      need_cmd gzip
      gzip -dc "$IN_FILE" | run_import_stream_direct
    fi
  else
    if [[ "$MODE" == "docker" ]]; then
      cat "$IN_FILE" | run_import_stream_docker
    else
      cat "$IN_FILE" | run_import_stream_direct
    fi
  fi
else
  # stdin
  if [[ "$MODE" == "docker" ]]; then
    run_import_stream_docker
  else
    run_import_stream_direct
  fi
fi

echo "[pg_import] Done."