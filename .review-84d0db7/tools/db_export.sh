#!/usr/bin/env bash
set -euo pipefail

TOOLS_DIR=$(dirname "${BASH_SOURCE[0]}")
source "$TOOLS_DIR/db_common.sh"

usage() {
  cat <<'USAGE'
Export business tables from PostgreSQL as plain SQL using pg_dump.

Uses Docker (docker compose exec db). Output is plain SQL suitable for psql restore.

Usage:
  bash tools/db_export.sh [options]

Options:
  --table NAME        Export single table (default: export all business tables)
  --out FILE          Output file (default: ./backups/quant_business_YYYYmmdd_HHMMSS.sql.gz)
  --out-dir DIR       Output directory (default: ./backups)
  --schema NAME       Schema for business tables (default: public)
  --no-gzip           Do not gzip output (default: gzip on)
  --gzip              Gzip output (default)
  --clean             Include DROP statements for selected tables (pg_dump --clean --if-exists)

  --service NAME      Docker compose service name (default: db)

  --db NAME           Database name (default: quant)
  --user NAME         Database user (default: quant)

Examples:
  # default, gzip, export all business tables
  bash tools/db_export.sh

  # export single table
  bash tools/db_export.sh --table a_stock_basic

  # specify schema
  bash tools/db_export.sh --schema public

USAGE
}

# Export-specific variables
TABLE_NAME=""
OUT_DIR="./backups"
OUT_FILE=""
GZIP=1
CLEAN=0
SERVICE="$DEFAULT_SERVICE"
DB_NAME="$DEFAULT_DB_NAME"
DB_USER="$DEFAULT_DB_USER"
DB_PASSWORD="${DB_PASSWORD:-${db_password:-}}"
SCHEMA="$DEFAULT_SCHEMA"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --table)
      TABLE_NAME="$2"
      shift 2
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
  if [[ -n "$TABLE_NAME" ]]; then
    base="$OUT_DIR/${DB_NAME}_${TABLE_NAME}_${ts}.sql"
  else
    base="$OUT_DIR/${DB_NAME}_business_${ts}.sql"
  fi
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

# Build table list - either single table or all business tables
if [[ -n "$TABLE_NAME" ]]; then
  DUMP_ARGS+=("--table=${SCHEMA}.${TABLE_NAME}")
else
  for t in "${BUSINESS_TABLES[@]}"; do
    DUMP_ARGS+=("--table=${SCHEMA}.${t}")
  done
fi

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

run_export_docker

echo "[db_export] Wrote: $OUT_FILE"
