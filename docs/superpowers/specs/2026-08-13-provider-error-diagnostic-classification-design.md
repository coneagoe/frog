# Provider Error Diagnostic Classification Design

## Goal

Make `provider_error` a governed daily-bar diagnostic classification so existing
diagnostics preserve the difference between a provider failure and normal missing
market data, and the PostgreSQL enum migration can safely convert current data.

## Context

`download/download_manager.py` already writes `provider_error` when a history
download includes a provider error. The persisted `daily_bar_diagnostics`
classification column is defined as a closed business-value set, but its current
Python enum and PostgreSQL migration contract omit that value. The production
database contains six `provider_error` records, so migration preflight correctly
rejects conversion rather than silently mapping them to a different meaning.

## Design

Add `PROVIDER_ERROR = "provider_error"` to
`DailyBarDiagnosticClassification`, following `missing_exact_date` and before
`downloaded`. The SQLAlchemy mapped enum and Storage migration derive their label
lists from this type, so the canonical application and database contracts remain
aligned.

No existing record is updated, deleted, or remapped. The six stored
`provider_error` records retain their current semantic meaning. The PostgreSQL
migration creates or validates an enum containing all five labels and converts
the legacy varchar column through its existing explicit text-to-enum path.

Update the Paper Trading operational migration documentation to include
`provider_error` in the independent PostgreSQL enum-label verification query.

## Testing

Add a failing test first for the Python/SQLAlchemy enum label list. Extend the
PostgreSQL Storage migration fixture with a legacy `provider_error` diagnostic
and assert that forward migration succeeds, preserves its text label, accepts
future `provider_error` values, remains idempotent, and continues rejecting an
unknown label.

Run focused Storage and Paper Trading migration tests against PostgreSQL. Before
the production migration, run `tools/migrate_enums.py --dry-run --json`. After
the live migration, independently query PostgreSQL to verify the five
classification labels, the `daily_bar_diagnostics.market` column, and the
required indexes. Restart the Paper Trading API only after those checks pass,
then rerun matching for `2026-08-07`.

## Scope

This change only governs the existing diagnostic classification value. It does
not alter downloader failure handling, reclassify historical diagnostics, change
matching rules, or alter the `518880` order outside the existing ETF migration
and matching workflow.

## Rollback

Use the existing enum migration rollback procedure to convert the column back to
its legacy varchar representation. PostgreSQL enum labels are not removed during
rollback; this preserves compatibility and avoids dropping a type with active
dependencies.
