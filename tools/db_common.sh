#!/usr/bin/env bash
set -euo pipefail

# Business tables array
BUSINESS_TABLES=(
  a_stock_basic
  daily_basic_a_stock
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
  stk_limit_a_stock
  suspend_d_a_stock
)

# Common database configuration defaults
DEFAULT_MODE="docker"
DEFAULT_SERVICE="db"
DEFAULT_DB_NAME="quant"
DEFAULT_DB_USER="quant"
DEFAULT_DB_HOST="localhost"
DEFAULT_DB_PORT="5432"
DEFAULT_SCHEMA="public"

# Common functions
err() {
  echo "[db_common] $*" >&2
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

# Common database connection setup
setup_db_connection() {
  local mode="${1:-$DEFAULT_MODE}"
  local service="${2:-$DEFAULT_SERVICE}"
  local db_name="${3:-$DEFAULT_DB_NAME}"
  local db_user="${4:-$DEFAULT_DB_USER}"
  local db_host="${5:-$DEFAULT_DB_HOST}"
  local db_port="${6:-$DEFAULT_DB_PORT}"
  local db_password="${7:-}"
  local schema="${8:-$DEFAULT_SCHEMA}"

  # Set up environment variables with fallback support
  DB_HOST="${DB_HOST:-${db_host:-${db_host:-localhost}}}"
  DB_PORT="${DB_PORT:-${db_port:-${db_port:-5432}}}"
  DB_NAME="${DB_NAME:-$db_name}"
  DB_USER="${DB_USER:-${db_username:-$db_user}}"
  DB_PASSWORD="${DB_PASSWORD:-${db_password:-$db_password}}"
  SCHEMA="${SCHEMA:-$schema}"

  # Export PGPASSWORD if provided
  if [[ -n "$DB_PASSWORD" && -z "${PGPASSWORD:-}" ]]; then
    export PGPASSWORD="$DB_PASSWORD"
  fi

  # Return the connection parameters
  echo "$mode $service $DB_NAME $DB_USER $DB_HOST $DB_PORT $SCHEMA"
}

# Common psql arguments
get_psql_args() {
  local db_user="$1"
  local db_name="$2"

  echo "-v ON_ERROR_STOP=1 -U \"$db_user\" -d \"$db_name\""
}
