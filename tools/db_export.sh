#!/usr/bin/env bash
set -euo pipefail

TOOLS_DIR=$(dirname "${BASH_SOURCE[0]}")
source "$TOOLS_DIR/db_common.sh"

usage() {
  cat <<'USAGE'
Export business tables from PostgreSQL as plain SQL using pg_dump.

Exports of paper_matching_runs include the matching-run status enum definition
before the table dump.

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

EXPORTS_MATCHING_RUNS=0
if [[ -z "$TABLE_NAME" || "$TABLE_NAME" == "$PAPER_MATCHING_RUNS_TABLE" ]]; then
  EXPORTS_MATCHING_RUNS=1
fi

# Build pg_dump args
DUMP_ARGS=(
  --format=plain
  --no-owner
  --no-privileges
  --verbose
)

if [[ $CLEAN -eq 1 && $EXPORTS_MATCHING_RUNS -eq 0 ]]; then
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

ENUM_DDL_FILE=""
if [[ $EXPORTS_MATCHING_RUNS -eq 1 ]]; then
  ENUM_DDL_FILE="$(mktemp)"
  trap 'rm -f "$ENUM_DDL_FILE"' EXIT
fi

psql_args_common=(
  -v ON_ERROR_STOP=1
  -U "$DB_USER"
  -d "$DB_NAME"
)

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

  if [[ $EXPORTS_MATCHING_RUNS -eq 1 ]]; then
    local enum_query
    enum_query="SELECT quote_literal(e.enumlabel) FROM pg_enum AS e JOIN pg_type AS t ON t.oid = e.enumtypid JOIN pg_namespace AS n ON n.oid = t.typnamespace WHERE n.nspname = :'schema' AND t.typname = :'type' ORDER BY e.enumsortorder;"
    # shellcheck disable=SC2086
    $dc exec -T "$SERVICE" env PGPASSWORD="${PGPASSWORD:-}" psql "${psql_args_common[@]}" -v "schema=$SCHEMA" -v "type=$PAPER_MATCHING_RUN_STATUS_TYPE" -At -c "$enum_query" >"$ENUM_DDL_FILE"
    if [[ -s "$ENUM_DDL_FILE" ]]; then
      {
        if [[ $CLEAN -eq 1 ]]; then
          if [[ -n "$TABLE_NAME" ]]; then
            printf 'DROP TABLE IF EXISTS "%s"."%s" CASCADE;\n' "$SCHEMA" "$TABLE_NAME"
          else
            for ((index=${#BUSINESS_TABLES[@]} - 1; index >= 0; index--)); do
              printf 'DROP TABLE IF EXISTS "%s"."%s" CASCADE;\n' "$SCHEMA" "${BUSINESS_TABLES[index]}"
            done
          fi
          printf 'DROP TYPE IF EXISTS "%s"."%s" CASCADE;\n' "$SCHEMA" "$PAPER_MATCHING_RUN_STATUS_TYPE"
        fi
        printf 'CREATE TYPE "%s"."%s" AS ENUM (' "$SCHEMA" "$PAPER_MATCHING_RUN_STATUS_TYPE"
        paste -sd, "$ENUM_DDL_FILE"
        printf ');\n'
      } >"${ENUM_DDL_FILE}.sql"
      mv "${ENUM_DDL_FILE}.sql" "$ENUM_DDL_FILE"
    fi
  fi

  if [[ $GZIP -eq 1 ]]; then
    # shellcheck disable=SC2086
    { cat "$ENUM_DDL_FILE" 2>/dev/null || true; $dc "${exec_args[@]}" "$SERVICE" env PGPASSWORD="${PGPASSWORD:-}" pg_dump -U "$DB_USER" -d "$DB_NAME" "${DUMP_ARGS[@]}"; } | gzip -c >"$OUT_FILE"
  else
    # shellcheck disable=SC2086
    { cat "$ENUM_DDL_FILE" 2>/dev/null || true; $dc "${exec_args[@]}" "$SERVICE" env PGPASSWORD="${PGPASSWORD:-}" pg_dump -U "$DB_USER" -d "$DB_NAME" "${DUMP_ARGS[@]}"; } >"$OUT_FILE"
  fi
}

run_export_docker

echo "[db_export] Wrote: $OUT_FILE"
