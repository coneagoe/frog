#!/usr/bin/env bash
set -euo pipefail

# Business tables array
BUSINESS_TABLES=(
  a_stock_basic
  daily_basic_a_stock
  forecasts
  forecast_ssf_candidates
  forecast_snapshot_runs
  forecast_snapshot_records
  general_info_stock
  general_info_etf
  general_info_hk_ggt
  ingredient_300
  ingredient_500
  history_data_daily_a_stock_bfq
  history_data_daily_a_stock_qfq
  history_data_daily_a_stock_hfq
  history_data_weekly_a_stock_qfq
  history_data_weekly_a_stock_hfq
  history_data_daily_etf_qfq
  history_data_daily_etf_hfq
  history_data_weekly_etf_qfq
  history_data_weekly_etf_hfq
  history_data_daily_fund
  history_data_daily_hk_stock_hfq
  history_data_daily_hk_stock_none
  history_data_weekly_hk_stock_hfq
  history_data_monthly_hk_stock_hfq
  stk_limit_a_stock
  stk_holdernumber
  suspend_d_a_stock
  top10_floatholders
  ssf_change_signals
  etf_basic
  etf_daily
  etf_share_size
  etf_net_flow
  index_daily_turnover
  stock_monitor_targets
  blackroom_records
  paper_accounts
  paper_cash_ledger
  paper_positions
  paper_position_lots
  paper_orders
  paper_trade_validity_checks
  paper_trades
  paper_position_round_trips
  paper_account_snapshots
  paper_matching_runs
  paper_ledger_rebuilds
  paper_pending_settlement
  daily_bar_diagnostics
  paper_valuation_gaps
  paper_etf_eligibility
)

BUSINESS_ENUM_TYPES=(
  paper_account_status
  paper_fee_preset
  paper_cash_event_type
  paper_order_side
  paper_order_status
  paper_trade_validity_status
  paper_market
  paper_position_source
  paper_round_trip_status
  paper_trade_validity_granularity
  paper_pending_settlement_source
  paper_ledger_rebuild_status
  paper_matching_run_status
  paper_etf_eligibility_status
  paper_snapshot_point_type
  paper_snapshot_quality_status
  monitor_market
  monitor_frequency
  monitor_reset_mode
  forecast_ssf_candidate_state
  blackroom_market
  blackroom_source
  daily_bar_diagnostic_adjust
  daily_bar_diagnostic_classification
  ssf_change_signal_status
  forecast_snapshot_status
)

business_enum_is_needed() {
  local type_name="$1"
  local table_name="$2"

  [[ -z "$table_name" ]] && return 0

  case "$type_name:$table_name" in
    paper_account_status:paper_accounts|paper_fee_preset:paper_accounts|paper_cash_event_type:paper_cash_ledger|paper_order_side:paper_orders|paper_order_side:paper_trades|paper_order_side:paper_trade_validity_checks|paper_order_status:paper_orders|paper_trade_validity_status:paper_orders|paper_trade_validity_status:paper_trade_validity_checks|paper_market:paper_orders|paper_market:paper_positions|paper_market:paper_position_lots|paper_market:paper_trades|paper_market:paper_trade_validity_checks|paper_position_source:paper_positions|paper_position_source:paper_position_lots|paper_round_trip_status:paper_position_round_trips|paper_trade_validity_granularity:paper_trade_validity_checks|paper_pending_settlement_source:paper_pending_settlement|paper_ledger_rebuild_status:paper_ledger_rebuilds|paper_matching_run_status:paper_matching_runs|paper_etf_eligibility_status:paper_etf_eligibility|paper_snapshot_point_type:paper_account_snapshots|paper_snapshot_quality_status:paper_account_snapshots|monitor_market:stock_monitor_targets|monitor_market:forecast_ssf_candidates|monitor_frequency:stock_monitor_targets|monitor_reset_mode:stock_monitor_targets|forecast_ssf_candidate_state:forecast_ssf_candidates|blackroom_market:blackroom_records|blackroom_source:blackroom_records|daily_bar_diagnostic_adjust:daily_bar_diagnostics|daily_bar_diagnostic_classification:daily_bar_diagnostics|ssf_change_signal_status:ssf_change_signals|forecast_snapshot_status:forecast_snapshot_runs)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

business_enum_can_be_dropped() {
  local type_name="$1"
  local table_name="$2"

  [[ -z "$table_name" ]] && return 0
  business_enum_is_needed "$type_name" "$table_name" || return 1

  case "$type_name" in
    paper_order_side|paper_trade_validity_status|paper_market|paper_position_source|monitor_market)
      return 1
      ;;
    *)
      return 0
      ;;
  esac
}

reject_selected_table_clean_with_inbound_foreign_keys() {
  local table_name="$1"
  local schema="$2"
  local query_executor="$3"
  local inbound_foreign_keys
  local inbound_foreign_key_query
  local schema_literal="${schema//\'/\'\'}"
  local table_literal="${table_name//\'/\'\'}"

  inbound_foreign_key_query="SELECT source_namespace.nspname || '.' || source_table.relname || '.' || foreign_key.conname FROM pg_constraint AS foreign_key JOIN pg_class AS source_table ON source_table.oid = foreign_key.conrelid JOIN pg_namespace AS source_namespace ON source_namespace.oid = source_table.relnamespace JOIN pg_class AS selected_table ON selected_table.oid = foreign_key.confrelid JOIN pg_namespace AS selected_namespace ON selected_namespace.oid = selected_table.relnamespace WHERE foreign_key.contype = 'f' AND selected_namespace.nspname = '${schema_literal}' AND selected_table.relname = '${table_literal}' AND foreign_key.conrelid <> foreign_key.confrelid;"
  inbound_foreign_keys="$($query_executor "$inbound_foreign_key_query")"

  if [[ -n "$inbound_foreign_keys" ]]; then
    err "Cannot safely clean selected table ${schema}.${table_name}: unselected inbound foreign key(s): ${inbound_foreign_keys//$'\n'/, }"
    return 1
  fi
}

reject_full_clean_with_unmanaged_inbound_foreign_keys() {
  local schema="$1"
  local query_executor="$2"
  local inbound_foreign_keys
  local inbound_foreign_key_query
  local schema_literal="${schema//\'/\'\'}"
  local managed_table_literals=()
  local table_name

  for table_name in "${BUSINESS_TABLES[@]}"; do
    managed_table_literals+=("'${table_name//\'/\'\'}'")
  done
  inbound_foreign_key_query="SELECT source_namespace.nspname || '.' || source_table.relname || '.' || foreign_key.conname FROM pg_constraint AS foreign_key JOIN pg_class AS source_table ON source_table.oid = foreign_key.conrelid JOIN pg_namespace AS source_namespace ON source_namespace.oid = source_table.relnamespace JOIN pg_class AS selected_table ON selected_table.oid = foreign_key.confrelid JOIN pg_namespace AS selected_namespace ON selected_namespace.oid = selected_table.relnamespace WHERE foreign_key.contype = 'f' AND selected_namespace.nspname = '${schema_literal}' AND selected_table.relname IN (${managed_table_literals[*]// /, }) AND (source_namespace.nspname <> '${schema_literal}' OR source_table.relname NOT IN (${managed_table_literals[*]// /, }));"
  inbound_foreign_keys="$($query_executor "$inbound_foreign_key_query")"

  if [[ -n "$inbound_foreign_keys" ]]; then
    err "Cannot safely clean full database ${schema}: unmanaged inbound foreign key(s): ${inbound_foreign_keys//$'\n'/, }"
    return 1
  fi
}

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
