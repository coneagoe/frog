#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Export business tables from PostgreSQL as plain SQL using pg_dump.

Default mode is Docker (docker compose exec db). Output is plain SQL suitable for psql restore.

Usage:
  bash tools/pg_export.sh [options]

Options:
  --out FILE          Output file (default: ./backups/quant_business_YYYYmmdd_HHMMSS.sql.gz)
  --out-dir DIR       Output directory (default: ./backups)
  --schema NAME       Schema for business tables (default: public)
  --no-gzip           Do not gzip output (default: gzip on)
  --gzip              Gzip output (default)
  --clean             Include DROP statements for selected tables (pg_dump --clean --if-exists)

  --docker            Use docker compose exec (default)
  --direct            Connect directly using local pg_dump
  --service NAME      Docker compose service name (default: db)

  --db NAME           Database name (default: quant)
  --user NAME         Database user (default: quant)
  --host HOST         Host (direct mode only; default: localhost)
  --port PORT         Port (direct mode only; default: 5432)

Environment variables (direct mode):
  DB_HOST / db_host, DB_PORT / db_port, DB_NAME, DB_USER / db_username, DB_PASSWORD / db_password
  PGPASSWORD can also be used.

Examples:
  # default (docker), gzip
  bash tools/pg_export.sh

  # specify schema
  bash tools/pg_export.sh --schema public

  # direct mode (requires pg_dump installed locally)
  DB_HOST=localhost DB_PASSWORD=quant bash tools/pg_export.sh --direct
USAGE
}

err() {
  echo "[pg_export] $*" >&2
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
OUT_DIR="./backups"
OUT_FILE=""
GZIP=1
CLEAN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
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
    --schema)
      SCHEMA="$2"
      shift 2
      ;;
    --out)
      OUT_FILE="$2"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="$2"
      shift 2
      ;;
    --no-gzip)
      GZIP=0
      shift
      ;;
    --gzip)
      GZIP=1
      shift
      ;;
    --clean)
      CLEAN=1
      shift
      ;;
    *)
      err "Unknown argument: $1"
      err "Run with --help for usage."
      exit 2
      ;;
  esac
 done

mkdir -p "$OUT_DIR"

if [[ -z "$OUT_FILE" ]]; then
  ts="$(date +%Y%m%d_%H%M%S)"
  base="$OUT_DIR/${DB_NAME}_business_${ts}.sql"
  if [[ $GZIP -eq 1 ]]; then
    OUT_FILE="${base}.gz"
  else
    OUT_FILE="$base"
  fi
fi

# Build pg_dump args
DUMP_ARGS=(
  --format=plain
  --no-owner
  --no-privileges
  --verbose
)

if [[ $CLEAN -eq 1 ]]; then
  DUMP_ARGS+=(--clean --if-exists)
fi

for t in "${BUSINESS_TABLES[@]}"; do
  DUMP_ARGS+=("--table=${SCHEMA}.${t}")
done

run_export_docker() {
  local dc
  dc="$(pick_docker_compose)" || { err "docker compose (or docker-compose) not found"; exit 127; }

  # In docker mode, we run inside the db container (local socket auth typically works).
  # If a password is required, you can export DB_PASSWORD/PGPASSWORD and we pass it through.
  local -a exec_args
  exec_args=(exec -T)
  if [[ -n "$DB_PASSWORD" && -z "${PGPASSWORD:-}" ]]; then
    export PGPASSWORD="$DB_PASSWORD"
  fi

  if [[ $GZIP -eq 1 ]]; then
    # shellcheck disable=SC2086
    $dc "${exec_args[@]}" "$SERVICE" env PGPASSWORD="${PGPASSWORD:-}" pg_dump -U "$DB_USER" -d "$DB_NAME" "${DUMP_ARGS[@]}" | gzip -c >"$OUT_FILE"
  else
    # shellcheck disable=SC2086
    $dc "${exec_args[@]}" "$SERVICE" env PGPASSWORD="${PGPASSWORD:-}" pg_dump -U "$DB_USER" -d "$DB_NAME" "${DUMP_ARGS[@]}" >"$OUT_FILE"
  fi
}

run_export_direct() {
  need_cmd pg_dump
  if [[ -n "$DB_PASSWORD" && -z "${PGPASSWORD:-}" ]]; then
    export PGPASSWORD="$DB_PASSWORD"
  fi

  if [[ $GZIP -eq 1 ]]; then
    pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" "${DUMP_ARGS[@]}" | gzip -c >"$OUT_FILE"
  else
    pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" "${DUMP_ARGS[@]}" >"$OUT_FILE"
  fi
}

case "$MODE" in
  docker)
    run_export_docker
    ;;
  direct)
    run_export_direct
    ;;
  *)
    err "Invalid mode: $MODE"
    exit 2
    ;;
esac

echo "[pg_export] Wrote: $OUT_FILE"