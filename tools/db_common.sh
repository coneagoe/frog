#!/usr/bin/env bash
set -euo pipefail

# Business tables array
BUSINESS_TABLES=(
  users
  auth_tokens
  a_stock_basic
  daily_basic_a_stock
  forecasts
  forecast_ssf_candidates
  forecast_snapshot_runs
  forecast_snapshot_records
  general_info_stock
  general_info_etf
  general_info_hk_ggt
  hk_recovery_authority
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
  monitor_notifications
  blackroom_records
  paper_accounts
  paper_cash_ledger
  paper_corporate_actions
  paper_positions
  paper_position_lots
  paper_orders
  paper_order_events
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
  paper_data_gap_recovery_gaps
  paper_data_gap_recovery_candidates
  paper_data_gap_recovery_attempts
  paper_data_gap_recovery_approvals
  paper_data_gap_recovery_accounts
  paper_data_gap_recovery_batches
  paper_data_gap_recovery_alerts
)

BUSINESS_ENUM_TYPES=(
  paper_account_status
  paper_fee_preset
  paper_cash_event_type
  paper_corporate_action_type
  paper_corporate_action_processing_status
  paper_order_side
  paper_order_status
  paper_order_event_type
  paper_replay_time_provenance
  paper_trade_validity_status
  paper_trade_validity_reason
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
  paper_snapshot_valuation_quality
  paper_account_migration_repair_reason
  monitor_market
  monitor_frequency
  monitor_reset_mode
  monitor_evaluation_error_kind
  forecast_ssf_candidate_state
  monitor_notification_delivery_state
  blackroom_market
  blackroom_source
  daily_bar_diagnostic_adjust
  daily_bar_diagnostic_classification
  ssf_change_signal_status
  forecast_snapshot_status
  hk_suspension_state
  paper_data_gap_recovery_status
  paper_data_gap_recovery_attempt_outcome
  paper_data_gap_recovery_approval_decision
  paper_data_gap_recovery_account_status
  paper_data_gap_recovery_batch_status
  paper_data_gap_recovery_alert_delivery_state
)

RECOVERY_APPEND_ONLY_TABLES=(
  paper_data_gap_recovery_candidates
  paper_data_gap_recovery_attempts
  paper_data_gap_recovery_approvals
  paper_data_gap_recovery_alerts
)
# Recovery append-only functions are emitted as executable DDL by db_export.sh.
# Names include paper_data_gap_recovery_candidates_append_only and its peers.

recovery_append_only_tables() {
  local schema="$1"
  local table_name="$2"
  local query_executor="$3"
  local schema_literal="${schema//\'/\'\'}"
  local table_filter=""
  local recovery_table_literals=()
  local recovery_table_list
  local recovery_table

  for recovery_table in "${RECOVERY_APPEND_ONLY_TABLES[@]}"; do
    recovery_table_literals+=("'${recovery_table//\'/\'\'}'")
  done
  recovery_table_list=$(IFS=,; printf '%s' "${recovery_table_literals[*]}")

  if [[ -n "$table_name" ]]; then
    local table_literal="${table_name//\'/\'\'}"
    table_filter=" AND class.relname = '${table_literal}'"
  fi

  "$query_executor" "SELECT class.relname FROM pg_class AS class JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace WHERE namespace.nspname = '${schema_literal}' AND class.relkind IN ('r', 'p') AND class.relname IN (${recovery_table_list})${table_filter} ORDER BY class.relname;"
}

write_recovery_append_only_functions() {
  local schema="$1"
  local table_name="$2"
  local query_executor="$3"
  local table

  while IFS= read -r table; do
    [[ -z "$table" ]] && continue
    if [[ "$table" == "paper_data_gap_recovery_alerts" ]]; then
      printf 'CREATE OR REPLACE FUNCTION "%s"."%s_append_only"() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF TG_OP = '\''DELETE'\'' OR OLD.evidence IS DISTINCT FROM NEW.evidence THEN RAISE EXCEPTION '\''append-only evidence cannot be changed'\''; END IF; RETURN NEW; END; $$;\n' "$schema" "$table"
    else
      printf 'CREATE OR REPLACE FUNCTION "%s"."%s_append_only"() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION '\''append-only evidence cannot be changed'\''; END; $$;\n' "$schema" "$table"
    fi
  done < <(recovery_append_only_tables "$schema" "$table_name" "$query_executor")
}

write_recovery_append_only_triggers() {
  local schema="$1"
  local table_name="$2"
  local query_executor="$3"
  local table

  while IFS= read -r table; do
    [[ -z "$table" ]] && continue
    printf 'DROP TRIGGER IF EXISTS "%s_append_only" ON "%s"."%s";\n' "$table" "$schema" "$table"
    printf 'CREATE TRIGGER "%s_append_only" BEFORE UPDATE OR DELETE ON "%s"."%s" FOR EACH ROW EXECUTE FUNCTION "%s"."%s_append_only"();\n' "$table" "$schema" "$table" "$schema" "$table"
  done < <(recovery_append_only_tables "$schema" "$table_name" "$query_executor")
}

business_enum_is_needed() {
  local type_name="$1"
  local table_name="$2"

  [[ -z "$table_name" ]] && return 0

  case "$type_name:$table_name" in
    monitor_notification_delivery_state:monitor_notifications)
      return 0
      ;;
    hk_suspension_state:hk_recovery_authority|paper_data_gap_recovery_status:paper_data_gap_recovery_gaps|paper_data_gap_recovery_attempt_outcome:paper_data_gap_recovery_attempts|paper_data_gap_recovery_approval_decision:paper_data_gap_recovery_approvals|paper_data_gap_recovery_account_status:paper_data_gap_recovery_accounts|paper_data_gap_recovery_batch_status:paper_data_gap_recovery_batches|paper_data_gap_recovery_alert_delivery_state:paper_data_gap_recovery_alerts|paper_market:paper_data_gap_recovery_gaps|daily_bar_diagnostic_adjust:paper_data_gap_recovery_gaps)
      return 0
      ;;
    paper_trade_validity_reason:paper_orders|paper_trade_validity_reason:paper_trade_validity_checks)
      return 0
      ;;
    paper_account_status:paper_accounts|paper_fee_preset:paper_accounts|paper_cash_event_type:paper_cash_ledger|paper_replay_time_provenance:paper_cash_ledger|paper_corporate_action_type:paper_corporate_actions|paper_corporate_action_processing_status:paper_corporate_actions|paper_replay_time_provenance:paper_corporate_actions|paper_order_side:paper_orders|paper_order_side:paper_trades|paper_order_side:paper_trade_validity_checks|paper_order_status:paper_orders|paper_order_event_type:paper_order_events|paper_replay_time_provenance:paper_order_events|paper_trade_validity_status:paper_orders|paper_trade_validity_status:paper_trade_validity_checks|paper_market:paper_orders|paper_market:paper_positions|paper_market:paper_position_lots|paper_market:paper_trades|paper_market:paper_trade_validity_checks|paper_market:paper_corporate_actions|paper_replay_time_provenance:paper_trades|paper_position_source:paper_positions|paper_position_source:paper_position_lots|paper_round_trip_status:paper_position_round_trips|paper_trade_validity_granularity:paper_trade_validity_checks|paper_pending_settlement_source:paper_pending_settlement|paper_ledger_rebuild_status:paper_ledger_rebuilds|paper_matching_run_status:paper_matching_runs|paper_etf_eligibility_status:paper_etf_eligibility|paper_snapshot_point_type:paper_account_snapshots|paper_snapshot_quality_status:paper_account_snapshots|paper_snapshot_valuation_quality:paper_account_snapshots|paper_replay_time_provenance:paper_account_snapshots|paper_account_migration_repair_reason:paper_accounts|monitor_market:stock_monitor_targets|monitor_market:forecast_ssf_candidates|monitor_frequency:stock_monitor_targets|monitor_reset_mode:stock_monitor_targets|monitor_evaluation_error_kind:stock_monitor_targets|forecast_ssf_candidate_state:forecast_ssf_candidates|blackroom_market:blackroom_records|blackroom_source:blackroom_records|daily_bar_diagnostic_adjust:daily_bar_diagnostics|daily_bar_diagnostic_classification:daily_bar_diagnostics|ssf_change_signal_status:ssf_change_signals|forecast_snapshot_status:forecast_snapshot_runs)
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
    paper_order_side|paper_trade_validity_status|paper_trade_validity_reason|paper_market|paper_position_source|monitor_market)
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
  local managed_table_list
  local table_name

  for table_name in "${BUSINESS_TABLES[@]}"; do
    managed_table_literals+=("'${table_name//\'/\'\'}'")
  done
  managed_table_list=$(IFS=,; printf '%s' "${managed_table_literals[*]}")
  inbound_foreign_key_query="SELECT source_namespace.nspname || '.' || source_table.relname || '.' || foreign_key.conname FROM pg_constraint AS foreign_key JOIN pg_class AS source_table ON source_table.oid = foreign_key.conrelid JOIN pg_namespace AS source_namespace ON source_namespace.oid = source_table.relnamespace JOIN pg_class AS selected_table ON selected_table.oid = foreign_key.confrelid JOIN pg_namespace AS selected_namespace ON selected_namespace.oid = selected_table.relnamespace WHERE foreign_key.contype = 'f' AND selected_namespace.nspname = '${schema_literal}' AND selected_table.relname IN (${managed_table_list}) AND (source_namespace.nspname <> '${schema_literal}' OR source_table.relname NOT IN (${managed_table_list}));"
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
