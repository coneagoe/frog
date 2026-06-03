# Shareholder Selling Punishment Service Rename Design

## Goal

Remove the legacy `ShareholderSellingBlackroomSyncService` name and keep only `ShareholderSellingPunishmentService` throughout the codebase.

## Scope

This change is intentionally narrow:

- remove the old compatibility alias from the service module;
- remove the old compatibility alias from the CLI module;
- update tests to stop referencing the removed name;
- update affected repository docs to stop referencing the removed name;
- keep existing runtime behavior unchanged.

This change does **not** rename broader blackroom concepts such as DAG task ids, CLI subcommands, log strings, or module filenames.

## Recommended Approach

Use a hard cut-over inside the repository:

1. `monitor/shareholder_selling_punishment.py` keeps `ShareholderSellingPunishmentService` as the only exported class name.
2. `tools/stock_monitor_cli.py` stops re-exporting `ShareholderSellingBlackroomSyncService`.
3. All repository references and tests use `ShareholderSellingPunishmentService` only.

This is the smallest change that satisfies the requirement to delete the old name instead of keeping compatibility glue.

## File-Level Design

### `monitor/shareholder_selling_punishment.py`

- Keep the existing class implementation under the name `ShareholderSellingPunishmentService`.
- Delete `ShareholderSellingBlackroomSyncService = ShareholderSellingPunishmentService`.

### `tools/stock_monitor_cli.py`

- Keep imports and dependency injection types on `ShareholderSellingPunishmentService`.
- Delete `ShareholderSellingBlackroomSyncService = ShareholderSellingPunishmentService`.

### Tests

- `test/monitor/test_shareholder_selling_punishment.py` should stop validating alias compatibility and instead validate direct construction/usage through the new class name only.
- Existing DAG and CLI tests should continue patching the new class name only.

### Documentation

- Update affected docs under `docs/superpowers/` that still mention `ShareholderSellingBlackroomSyncService` so internal written guidance matches the code after the hard cut-over.
- This includes the already-written DAG spec/plan docs and any directly affected rename-era design or plan docs that still present the old class name as current behavior.

## Error Handling and Compatibility

This is a deliberate breaking change for any external code that still imports `ShareholderSellingBlackroomSyncService`. That is acceptable for this task because the approved design explicitly removes the old name instead of keeping backward compatibility.

No runtime logic, error mapping, Tushare interaction, or blackroom business rules should change.

## Testing

Run focused tests covering the impacted areas:

- `test/monitor/test_shareholder_selling_punishment.py`
- `test/dags/test_monitor_stock_daily.py`
- `test/tools/test_stock_monitor_cli.py`

Success means:

- all in-repo references build and import using only `ShareholderSellingPunishmentService`;
- affected docs no longer present `ShareholderSellingBlackroomSyncService` as the active in-repo class name;
- the removed name no longer appears in production code;
- targeted tests pass unchanged except for the intended test updates.
