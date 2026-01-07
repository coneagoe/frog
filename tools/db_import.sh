#!/usr/bin/env bash
set -euo pipefail

TOOLS_DIR=$(dirname "${BASH_SOURCE[0]}")
source "$TOOLS_DIR/db_common.sh"

usage() {
  cat <<'USAGE'
Import business tables into PostgreSQL using psql.

Uses Docker (docker compose exec db). Input should be a plain SQL dump (optionally .gz).

Usage:
  bash tools/db_import.sh --in FILE [options]
  cat dump.sql | bash tools/db_import.sh [options]

Options:
  --in FILE           Input file (.sql or .sql.gz). If omitted, reads from stdin.
  --schema NAME       Schema for business tables (used for --clean drop list; default: public)
  --clean             Drop business tables before importing (DROP TABLE IF EXISTS ... CASCADE)

  --service NAME      Docker compose service name (default: db)

  --db NAME           Database name (default: quant)
  --user NAME         Database user (default: quant)

Examples:
  # import from file
  bash tools/db_import.sh --in ./backups/quant_business_xxx.sql.gz

  # drop business tables first
  bash tools/db_import.sh --clean --in ./backups/quant_business_xxx.sql
USAGE
}

# Import-specific variables
IN_FILE=""
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

run_import_stream_docker() {
  local dc
  dc="$(pick_docker_compose)" || { err "docker compose (or docker-compose) not found"; exit 127; }
  # shellcheck disable=SC2086
  $dc exec -T "$SERVICE" env PGPASSWORD="${PGPASSWORD:-}" psql "${psql_args_common[@]}"
}

if [[ $CLEAN -eq 1 ]]; then
  run_drop_docker
fi

# Import dump
if [[ -n "$IN_FILE" ]]; then
  if [[ ! -f "$IN_FILE" ]]; then
    err "Input file not found: $IN_FILE"
    exit 2
  fi

  if [[ "$IN_FILE" == *.gz ]]; then
    need_cmd gzip
    gzip -dc "$IN_FILE" | run_import_stream_docker
  else
    cat "$IN_FILE" | run_import_stream_docker
  fi
else
  # stdin
  run_import_stream_docker
fi

echo "[db_import] Done."
