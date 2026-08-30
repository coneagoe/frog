# Task 2 Report: Ordered Event Adapter and Repository Reads

## Status

Task 2 scoped review findings are resolved. The final authoritative verification is the 126-test focused run recorded below, plus the optional 23-test migration run.

## Modified files

- `paper_trading/storage/repository.py`: replay adapters, baseline retention, UTC/quality handling, bounded snapshot replacement, and active account selection.
- `test/paper_trading/storage/test_repository.py`: baseline selection, mixed repository-to-replay economic integration, payload, timezone, and replacement validation tests.

No Task 3+ files were modified. Matching and settlement code was not modified.

## Interfaces

- `PaperTradingRepository.list_replay_events(account_id, start_at=None, end_at=None) -> list[ReplayEvent]`
- `PaperTradingRepository.get_replay_events(account_id, start_at=None, end_at=None) -> list[ReplayEvent]`
- `PaperTradingRepository.replace_trading_snapshots(account_id, start_date, end_date, snapshots) -> list[PaperAccountSnapshot]`

Replay adapters preserve source table/row IDs, distinguish external deposit/withdrawal from internal ledger events, retain the latest provable creation baseline before a bounded start, and reuse `NavSeriesReplay._sort_key`.

## Superseded history

Earlier intermediate failures during review correction are superseded and are intentionally not reproduced here. The final results below are authoritative.

## Final authoritative verification

Command:

```text
uv run pytest test/paper_trading/storage/test_repository.py test/paper_trading/domain/test_nav_replay.py -v
```

### Complete final test output

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-8.4.2, pluggy-1.6.0 -- /data/frog/.worktrees/issue-82-nav-series/.venv/bin/python
cachedir: .pytest_cache
rootdir: /data/frog/.worktrees/issue-82-nav-series
configfile: pyproject.toml
plugins: anyio-4.14.0
collecting ... collected 126 items

test/paper_trading/storage/test_repository.py::test_daily_bar_diagnostic_scalar_columns_use_value_enums PASSED [  0%]
test/paper_trading/storage/test_repository.py::test_etf_eligibility_repository_upserts_gets_and_filters_status PASSED [  1%]
test/paper_trading/storage/test_repository.py::test_etf_eligibility_repository_rejects_non_bare_symbols[510300.SH] PASSED [  2%]
test/paper_trading/storage/test_repository.py::test_etf_eligibility_repository_rejects_non_bare_symbols[51030] PASSED [  3%]
test/paper_trading/storage/test_repository.py::test_etf_eligibility_repository_rejects_non_bare_symbols[5103000] PASSED [  4%]
test/paper_trading/storage/test_repository.py::test_etf_eligibility_repository_rejects_non_bare_symbols[5103A0] PASSED [  4%]
test/paper_trading/storage/test_repository.py::test_etf_eligibility_repository_rejects_blank_reviewer PASSED [  5%]
test/paper_trading/storage/test_repository.py::test_validate_provider_outcomes_normalizes_valid_values PASSED [  6%]
test/paper_trading/storage/test_repository.py::test_validate_provider_outcomes_rejects_invalid_contract[None] PASSED [  7%]
test/paper_trading/storage/test_repository.py::test_validate_provider_outcomes_rejects_invalid_contract[value1] PASSED [  8%]
test/paper_trading/storage/test_repository.py::test_validate_provider_outcomes_rejects_invalid_contract[value2] PASSED [  8%]
test/paper_trading/storage/test_repository.py::test_validate_provider_outcomes_rejects_invalid_contract[value3] PASSED [  9%]
test/paper_trading/storage/test_repository.py::test_validate_provider_outcomes_rejects_invalid_contract[value4] PASSED [ 10%]
test/paper_trading/storage/test_repository.py::test_create_account_initializes_nav_share_state PASSED [ 11%]
test/paper_trading/storage/test_repository.py::test_create_account_persists_etf_commission_rate PASSED [ 12%]
test/paper_trading/storage/test_repository.py::test_create_account_rejects_non_positive_initial_cash[initial_cash0] PASSED [ 12%]
test/paper_trading/storage/test_repository.py::test_create_account_rejects_non_positive_initial_cash[initial_cash1] PASSED [ 13%]
test/paper_trading/storage/test_repository.py::test_create_account_persists_initial_snapshot PASSED [ 14%]
test/paper_trading/storage/test_repository.py::test_list_snapshots_does_not_round_loaded_entities_before_commit PASSED [ 15%]
test/paper_trading/storage/test_repository.py::test_list_snapshots_orders_same_day_initial_before_trading PASSED [ 16%]
test/paper_trading/storage/test_repository.py::test_save_trading_snapshot_updates_same_account_date_in_place PASSED [ 16%]
test/paper_trading/storage/test_repository.py::test_create_initial_snapshot_rejects_duplicate_initial_point PASSED [ 17%]
test/paper_trading/storage/test_repository.py::test_list_replay_events_adapts_sources_in_stable_utc_order PASSED [ 18%]
test/paper_trading/storage/test_repository.py::test_list_replay_events_marks_legacy_missing_time_invalid PASSED [ 19%]
test/paper_trading/storage/test_repository.py::test_repository_replay_has_eligible_creation_baseline PASSED [ 20%]
test/paper_trading/storage/test_repository.py::test_replay_range_retains_valid_initial_baseline PASSED [ 20%]
test/paper_trading/storage/test_repository.py::test_mixed_repository_stream_replays_without_cash_flow_double_count PASSED [ 21%]
test/paper_trading/storage/test_repository.py::test_repository_preserves_cash_ledger_event_type_and_internal_events_do_not_flow_shares PASSED [ 22%]
test/paper_trading/storage/test_repository.py::test_corporate_action_ledger_is_not_replayed_as_cash_flow PASSED [ 23%]
test/paper_trading/storage/test_repository.py::test_replace_trading_snapshots_rejects_invalid_input[event_at-value0] PASSED [ 24%]
test/paper_trading/storage/test_repository.py::test_replace_trading_snapshots_rejects_invalid_input[quality_status-unknown] PASSED [ 24%]
test/paper_trading/storage/test_repository.py::test_replace_trading_snapshots_rejects_invalid_input[total_assets-value2] PASSED [ 25%]
test/paper_trading/storage/test_repository.py::test_replace_trading_snapshots_is_bounded_and_upserts_dates PASSED [ 26%]
test/paper_trading/storage/test_repository.py::test_get_accounts_for_snapshot_includes_active_cash_only_accounts PASSED [ 27%]
test/paper_trading/storage/test_repository.py::test_acquire_matching_run_uses_canonical_active_status PASSED [ 28%]
test/paper_trading/storage/test_repository.py::test_replay_cleanup_removes_matching_runs PASSED [ 28%]
test/paper_trading/storage/test_repository.py::test_upsert_daily_bar_diagnostic_reuses_business_date_symbol_adjustment PASSED [ 29%]
test/paper_trading/storage/test_repository.py::test_upsert_daily_bar_diagnostic_rejects_invalid_finite_values[bfq-partial-outcomes0] PASSED [ 30%]
test/paper_trading/storage/test_repository.py::test_upsert_daily_bar_diagnostic_rejects_invalid_finite_values[bfq-downloaded-outcomes1] PASSED [ 31%]
test/paper_trading/storage/test_repository.py::test_upsert_daily_bar_diagnostic_rejects_invalid_finite_values[bfq-downloaded-outcomes2] PASSED [ 32%]
test/paper_trading/storage/test_repository.py::test_bfq_diagnostic_label_is_found_by_default_lookup PASSED [ 32%]
test/paper_trading/storage/test_repository.py::test_diagnostic_lookup_normalizes_exchange_suffixed_and_bare_stock_ids PASSED [ 33%]
test/paper_trading/storage/test_repository.py::test_provider_outcome_rejects_unknown_status_and_normalizes_detail PASSED [ 34%]
test/paper_trading/storage/test_repository.py::test_add_cash_event_persists_nav_share_fields PASSED [ 35%]
test/paper_trading/storage/test_repository.py::test_add_cash_event_defaults_rounding_residual_to_zero PASSED [ 36%]
test/paper_trading/storage/test_repository.py::test_add_cash_event_derives_residual_from_persisted_values PASSED [ 36%]
test/paper_trading/storage/test_repository.py::test_cash_ledger_orders_by_occurred_at_then_id PASSED [ 37%]
test/paper_trading/storage/test_repository.py::test_cash_ledger_orders_equal_occurred_at_by_id PASSED [ 38%]
test/paper_trading/storage/test_repository.py::test_corporate_actions_persist_filter_and_order PASSED [ 39%]
test/paper_trading/storage/test_repository.py::test_corporate_action_filters_normalize_offset_bounds_to_utc PASSED [ 40%]
test/paper_trading/storage/test_repository.py::test_delete_account_removes_corporate_actions PASSED [ 40%]
test/paper_trading/storage/test_repository.py::test_corporate_action_persistence_applies_shared_precision PASSED [ 41%]
test/paper_trading/storage/test_repository.py::test_corporate_action_persistence_rejects_non_finite_values[parameters] PASSED [ 42%]
test/paper_trading/storage/test_repository.py::test_corporate_action_persistence_rejects_non_finite_values[cash_delta] PASSED [ 43%]
test/paper_trading/storage/test_repository.py::test_corporate_action_persistence_rejects_non_finite_values[before_quantity] PASSED [ 44%]
test/paper_trading/storage/test_repository.py::test_corporate_action_persistence_rejects_non_finite_values[after_cash_available] PASSED [ 44%]
test/paper_trading/storage/test_repository.py::test_add_cash_event_rejects_tzinfo_without_offset PASSED [ 45%]
test/paper_trading/storage/test_repository.py::test_latest_valid_nav_before_ignores_invalid_snapshots PASSED [ 46%]
test/paper_trading/storage/test_repository.py::test_create_account_deposits_initial_cash PASSED [ 47%]
test/paper_trading/storage/test_repository.py::test_create_order_persists_accepted_order PASSED [ 48%]
test/paper_trading/storage/test_repository.py::test_list_orders_page_filters_counts_orders_and_slices_pages PASSED [ 48%]
test/paper_trading/storage/test_repository.py::test_list_trades_page_filters_counts_trades_and_slices_pages PASSED [ 49%]
test/paper_trading/storage/test_repository.py::test_list_catalogue_etf_a_share_orders_excludes_non_candidates_and_filters_account PASSED [ 50%]
test/paper_trading/storage/test_repository.py::test_update_orders_market_updates_only_targeted_orders PASSED [ 51%]
test/paper_trading/storage/test_repository.py::test_get_order_by_idempotency_key_returns_existing_order PASSED [ 52%]
test/paper_trading/storage/test_repository.py::test_order_validity_summary_and_detail_are_persisted PASSED [ 52%]
test/paper_trading/storage/test_repository.py::test_delete_account_deletes_trade_validity_checks_before_orders PASSED [ 53%]
test/paper_trading/storage/test_repository.py::test_round_trip_repository_creates_and_lists_closed_cycle PASSED [ 54%]
test/paper_trading/storage/test_repository.py::test_create_account_sets_default_fee_config PASSED [ 55%]
test/paper_trading/storage/test_repository.py::test_create_account_accepts_custom_fee_config PASSED [ 56%]
test/paper_trading/storage/test_repository.py::test_create_account_rejects_negative_fee_config[commission_rate] PASSED [ 56%]
test/paper_trading/storage/test_repository.py::test_create_account_rejects_negative_fee_config[min_commission] PASSED [ 57%]
test/paper_trading/storage/test_repository.py::test_create_account_rejects_negative_fee_config[stamp_duty_rate] PASSED [ 58%]
test/paper_trading/storage/test_repository.py::test_create_account_rejects_negative_fee_config[transfer_fee_rate] PASSED [ 59%]
test/paper_trading/storage/test_repository.py::test_create_account_preserves_zero_fee_config PASSED [ 60%]
test/paper_trading/storage/test_repository.py::test_update_account_fees_updates_only_provided_fields PASSED [ 60%]
test/paper_trading/storage/test_repository.py::test_update_account_fees_rejects_negative_values PASSED [ 61%]
test/paper_trading/storage/test_repository.py::test_update_account_fees_rejects_empty_update PASSED [ 62%]
test/paper_trading/storage/test_repository.py::test_update_account_fees_returns_none_for_missing_account PASSED [ 63%]
test/paper_trading/storage/test_repository.py::test_order_and_trade_comments_are_persisted PASSED [ 64%]
test/paper_trading/storage/test_repository.py::test_update_order_comment_syncs_linked_trades_and_clears_blank PASSED [ 64%]
test/paper_trading/storage/test_repository.py::test_delete_account_removes_round_trips PASSED [ 65%]
test/paper_trading/storage/test_repository.py::test_delete_order_returns_deleted_order_and_removes_row PASSED [ 66%]
test/paper_trading/storage/test_repository.py::test_ledger_rebuild_audit_lifecycle_records_trigger_counts_and_failure PASSED [ 67%]
test/paper_trading/storage/test_repository.py::test_clear_account_rebuild_state_from_date_preserves_source_facts_and_history PASSED [ 68%]
test/paper_trading/storage/test_repository.py::test_clear_account_rebuild_state_from_restores_pre_start_lots_and_realized_pnl PASSED [ 68%]
test/paper_trading/storage/test_repository.py::test_clear_account_rebuild_state_preserves_12_decimal_cost_and_pnl PASSED [ 69%]
test/paper_trading/storage/test_repository.py::test_clear_account_rebuild_state_preserves_initial_cash PASSED [ 70%]
test/paper_trading/storage/test_repository.py::test_clear_account_rebuild_state_resets_same_symbol_imported_after_trade PASSED [ 71%]
test/paper_trading/storage/test_repository.py::test_rebuild_preserves_imported_hk_market PASSED [ 72%]
test/paper_trading/storage/test_repository.py::test_rebuild_restores_same_symbol_imported_lots_by_market PASSED [ 72%]
test/paper_trading/storage/test_repository.py::test_same_symbol_positions_and_lots_are_isolated_by_market PASSED [ 73%]
test/paper_trading/storage/test_repository.py::test_create_position_lot_requires_and_normalizes_market PASSED [ 74%]
test/paper_trading/storage/test_repository.py::test_hk_diagnostic_does_not_select_same_symbol_a_share_order_for_rebuild PASSED [ 75%]
test/paper_trading/storage/test_repository.py::test_eligible_daily_bar_rebuild_orders_include_only_a_share_bfq_missing_exact_date PASSED [ 76%]
test/paper_trading/storage/test_repository.py::test_same_symbol_round_trips_are_isolated_by_market PASSED [ 76%]
test/paper_trading/storage/test_repository.py::test_same_symbol_diagnostics_are_isolated_by_market PASSED [ 77%]
test/paper_trading/storage/test_repository.py::test_reset_orders_for_replay_resets_replayable_statuses PASSED [ 78%]
test/paper_trading/storage/test_repository.py::test_reset_orders_for_replay_preserves_canceled_rejected PASSED [ 79%]
test/paper_trading/storage/test_repository.py::test_list_order_trade_dates_returns_sorted_distinct_dates PASSED [ 80%]
test/paper_trading/storage/test_repository.py::test_create_order_persists_market_default_a_share PASSED [ 80%]
test/paper_trading/storage/test_repository.py::test_create_order_persists_market_hk_connect PASSED [ 81%]
test/paper_trading/storage/test_repository.py::test_create_trade_persists_market PASSED [ 82%]
test/paper_trading/storage/test_repository.py::test_position_persists_market PASSED [ 83%]
test/paper_trading/storage/test_repository.py::test_account_hk_fee_fields_default_to_none PASSED [ 84%]
test/paper_trading/storage/test_repository.py::test_update_account_hk_fees_persists PASSED [ 84%]
test/paper_trading/storage/test_repository.py::test_create_pending_settlement PASSED [ 85%]
test/paper_trading/storage/test_repository.py::test_internal_cash_aggregations_preserve_sqlite_decimal_text PASSED [ 86%]
test/paper_trading/storage/test_repository.py::test_cash_available_as_of_internal_preserves_adjacent_decimal_boundary PASSED [ 87%]
test/paper_trading/storage/test_repository.py::test_settle_pending_releases_cash PASSED [ 88%]
test/paper_trading/storage/test_repository.py::test_settle_pending_preserves_sqlite_high_precision_amount PASSED [ 88%]
test/paper_trading/domain/test_nav_replay.py::test_replay_orders_same_timestamp_by_fixed_precedence_then_source_id PASSED [ 89%]
test/paper_trading/domain/test_nav_replay.py::test_replay_rejects_events_with_identical_complete_ordering_key PASSED [ 90%]
test/paper_trading/domain/test_nav_replay.py::test_replay_normalizes_non_utc_event_timestamp_before_sorting PASSED [ 91%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_uses_previous_valid_nav_or_one_and_does_not_create_return PASSED [ 92%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_rejects_conflicting_pre_and_post_asset_payload PASSED [ 92%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_rejects_total_assets_that_could_be_double_counted PASSED [ 93%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_rejects_conflicting_share_count_payload PASSED [ 94%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_rejects_pre_share_count_without_replay_share_state PASSED [ 95%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_rejects_payload_nav_instead_of_overriding_replay_nav PASSED [ 96%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[None] PASSED [ 96%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value1] PASSED [ 97%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value2] PASSED [ 98%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value3] PASSED [ 99%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value4] PASSED [100%]

============================= 126 passed in 40.17s =============================

```

Final exit status: 0.

## Optional migration verification

Command: `tools/run_tests.sh test/paper_trading/storage/test_nav_series_migration.py -v`

Result: `23 passed in 47.82s` (PostgreSQL test_db started successfully).

Concern: locale warnings (`en_US.UTF-8` unavailable) were emitted by the shell/container setup; tests passed.
