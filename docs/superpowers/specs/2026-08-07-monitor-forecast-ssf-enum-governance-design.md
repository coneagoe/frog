# Monitor and Forecast SSF Enum Governance Design

## Goal

Make Stock Monitor and Forecast SSF persistence reject invalid finite business
values through API, CLI, workflow, storage, and PostgreSQL paths. Make typed
monitor condition JSON mandatory; do not retain compatibility for untyped
legacy condition documents.

## Scope

The implementation governs these finite column values:

- Stock Monitor target `market`: `A`, `HK`, `ETF`.
- Stock Monitor target `frequency`: `daily`, `intraday`.
- Stock Monitor target `reset_mode`: `auto`, `manual`.
- Forecast SSF candidate `market`: `A`, `HK`, `ETF`.
- Forecast SSF candidate lifecycle `state`: `eligible`, `ineligible`,
  `deferred`, `paused`, `blackroom`, `delisted_or_unlisted`.

Supported monitor condition types are `price_threshold`, `price_cross_ma`,
`price_vs_ma`, `ma_cross`, `change_pct`, and `rsi`. Comparison conditions use
`above` or `below`; `ma_cross` uses `golden` or `death`. Every condition must
include the type-specific required numeric fields. RSI defaults `period` to
14 when omitted and requires a value from 0 through 100.

## Application Boundaries

Add `monitor/condition_validation.py` as the authoritative typed-condition
contract. Its validator receives a JSON object and raises `ValueError` for an
unsupported discriminator, invalid type/direction pairing, or missing/invalid
type-specific field. Workflow markers are allowed as supplementary metadata;
their ownership and immutability remain enforced by `StorageDb`.

`MonitorTargetService` converts validator failures to its existing
`VALIDATION_ERROR` response. Direct storage writers call the same validator
before their transactions, including monitor creation, updates, workflow
upserts, and Forecast SSF combined upserts. This ensures that callers cannot
bypass the contract by avoiding the service or CLI.

Forecast SSF replaces legacy documents such as `{"workflow": "forecast_ssf_ma20"}`
with the canonical typed condition:

```json
{
  "type": "price_vs_ma",
  "direction": "above",
  "period": 20,
  "workflow": "forecast_ssf_ma20"
}
```

No automatic translation is applied to existing untyped condition rows. The
migration preflight rejects them without changing the database.

## PostgreSQL Migration

Create a dedicated Monitor/Forecast SSF enum migration and an explicit
operator command. It reuses the already-proven migration lifecycle without
refactoring the paper-trading migration: preflight, dry-run, apply, verify,
idempotent rerun, and rollback.

Python `StrEnum` definitions supply canonical labels. SQLAlchemy maps them to
named native PostgreSQL enums with string validation. The migration inspects
legacy values, defaults, indexes, nullability, and the monitor JSON contract;
it aborts before DDL for unknown legacy values or untyped/invalid conditions.
It converts eligible `VARCHAR` columns with explicit text-to-enum casts and
restores defaults and indexes. Rollback restores the original `VARCHAR`
columns and drops only enum types with no remaining dependency.

The migration adds a minimal PostgreSQL `CHECK` on
`stock_monitor_targets.condition`: it must be a JSON object whose string
`type` is one of the six supported discriminators. Type-dependent directions
and fields remain centrally application-validated, avoiding fragile SQL for a
conditional schema.

Application startup does not create, extend, or migrate enums.

## Verification

SQLite tests cover service and direct-storage validation, SQLAlchemy enum
string rejection, typed Forecast SSF workflow upserts, and unchanged canonical
lifecycle transitions.

PostgreSQL integration tests use isolated temporary schemas and prove:

- preflight rejects invalid legacy enum values and untyped/invalid condition
  JSON without mutation;
- valid legacy data converts to the expected named enum types and JSON check;
- direct SQL cannot insert invalid enum labels or an unsupported condition
  discriminator;
- rerunning migration is idempotent;
- rollback restores prior string columns and removes the check and enum types.

Focused monitor, storage, and CLI suites verify valid public behavior remains
unchanged.
