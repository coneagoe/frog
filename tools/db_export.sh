#!/usr/bin/env bash
set -euo pipefail

TOOLS_DIR=$(dirname "${BASH_SOURCE[0]}")
source "$TOOLS_DIR/db_common.sh"

usage() {
  cat <<'USAGE'
Export business tables from PostgreSQL as plain SQL using pg_dump.

Exports include required business enum definitions, including Paper Trading,
Monitor, and Forecast SSF enums, before dependent table dumps.

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
  --clean             Include DROP statements for the full business-database export only; cannot be combined with --table

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

if [[ $CLEAN -eq 1 && -n "$TABLE_NAME" ]]; then
  err "--clean cannot be combined with --table; selected-table clean exports are unsupported."
  exit 2
fi

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

SELECTED_ENUM_TYPES=()
CLEAN_ENUM_TYPES=()
for type_name in "${BUSINESS_ENUM_TYPES[@]}"; do
  if business_enum_is_needed "$type_name" "$TABLE_NAME"; then
    SELECTED_ENUM_TYPES+=("$type_name")
  fi
  if business_enum_can_be_dropped "$type_name" "$TABLE_NAME"; then
    CLEAN_ENUM_TYPES+=("$type_name")
  fi
done

# Build pg_dump args
DUMP_ARGS=(
  --format=plain
  --no-owner
  --no-privileges
  --verbose
)

if [[ $CLEAN -eq 1 && ${#SELECTED_ENUM_TYPES[@]} -eq 0 ]]; then
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
RECOVERY_TRIGGER_DDL_FILE=""
if [[ ${#SELECTED_ENUM_TYPES[@]} -gt 0 || -z "$TABLE_NAME" || "$TABLE_NAME" == paper_data_gap_recovery_* ]]; then
  ENUM_DDL_FILE="$(mktemp)"
  RECOVERY_TRIGGER_DDL_FILE="$(mktemp)"
  trap 'rm -f "$ENUM_DDL_FILE" "$RECOVERY_TRIGGER_DDL_FILE"' EXIT
fi

psql_args_common=(
  -v ON_ERROR_STOP=1
  -U "$DB_USER"
  -d "$DB_NAME"
)

run_catalog_query_docker() {
  local query="$1"
  local dc
  dc="$(pick_docker_compose)" || { err "docker compose (or docker-compose) not found"; exit 127; }
  # shellcheck disable=SC2086
  $dc exec -T "$SERVICE" env PGPASSWORD="${PGPASSWORD:-}" psql "${psql_args_common[@]}" -At -c "$query"
}

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

  if [[ $CLEAN -eq 1 ]]; then
    reject_full_clean_with_unmanaged_inbound_foreign_keys "$SCHEMA" run_catalog_query_docker
  fi

  if [[ ${#SELECTED_ENUM_TYPES[@]} -gt 0 ]]; then
    local enum_query
    enum_query="SELECT quote_literal(e.enumlabel) FROM pg_enum AS e JOIN pg_type AS t ON t.oid = e.enumtypid JOIN pg_namespace AS n ON n.oid = t.typnamespace WHERE n.nspname = :'schema' AND t.typname = :'type' ORDER BY e.enumsortorder;"
    if [[ $CLEAN -eq 1 ]]; then
      for ((index=${#BUSINESS_TABLES[@]} - 1; index >= 0; index--)); do
        printf 'DROP TABLE IF EXISTS "%s"."%s" CASCADE;\n' "$SCHEMA" "${BUSINESS_TABLES[index]}" >>"$ENUM_DDL_FILE"
      done
      for ((index=${#CLEAN_ENUM_TYPES[@]} - 1; index >= 0; index--)); do
        printf 'DROP TYPE IF EXISTS "%s"."%s";\n' "$SCHEMA" "${CLEAN_ENUM_TYPES[index]}" >>"$ENUM_DDL_FILE"
      done
    fi
    for type_name in "${SELECTED_ENUM_TYPES[@]}"; do
      local enum_labels_file
      enum_labels_file="$(mktemp)"
      # psql expands variables from input, but not from -c commands.
      # shellcheck disable=SC2086
      printf '%s\n' "$enum_query" | $dc exec -T "$SERVICE" env PGPASSWORD="${PGPASSWORD:-}" psql "${psql_args_common[@]}" -v "schema=$SCHEMA" -v "type=$type_name" -At >"$enum_labels_file"
      if [[ -s "$enum_labels_file" ]]; then
        printf 'DO $$ BEGIN CREATE TYPE "%s"."%s" AS ENUM (' "$SCHEMA" "$type_name" >>"$ENUM_DDL_FILE"
        paste -sd, "$enum_labels_file" >>"$ENUM_DDL_FILE"
        printf '); EXCEPTION WHEN duplicate_object THEN NULL; END $$;\n' >>"$ENUM_DDL_FILE"
      fi
      rm -f "$enum_labels_file"
    done
  fi
  if [[ -n "$ENUM_DDL_FILE" && ( -z "$TABLE_NAME" || "$TABLE_NAME" == paper_data_gap_recovery_* ) ]]; then
    write_recovery_append_only_functions "$SCHEMA" "$TABLE_NAME" run_catalog_query_docker >>"$ENUM_DDL_FILE"
    write_recovery_append_only_triggers "$SCHEMA" "$TABLE_NAME" run_catalog_query_docker >>"$RECOVERY_TRIGGER_DDL_FILE"
  fi

  if [[ $GZIP -eq 1 ]]; then
    # shellcheck disable=SC2086
    { cat "$ENUM_DDL_FILE" 2>/dev/null || true; $dc "${exec_args[@]}" "$SERVICE" env PGPASSWORD="${PGPASSWORD:-}" pg_dump -U "$DB_USER" -d "$DB_NAME" "${DUMP_ARGS[@]}"; cat "$RECOVERY_TRIGGER_DDL_FILE" 2>/dev/null || true; } | gzip -c >"$OUT_FILE"
  else
    # shellcheck disable=SC2086
    { cat "$ENUM_DDL_FILE" 2>/dev/null || true; $dc "${exec_args[@]}" "$SERVICE" env PGPASSWORD="${PGPASSWORD:-}" pg_dump -U "$DB_USER" -d "$DB_NAME" "${DUMP_ARGS[@]}"; cat "$RECOVERY_TRIGGER_DDL_FILE" 2>/dev/null || true; } >"$OUT_FILE"
  fi
}

run_export_docker

echo "[db_export] Wrote: $OUT_FILE"
