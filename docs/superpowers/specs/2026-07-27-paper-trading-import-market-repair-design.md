# Paper Trading Imported Position Market Repair Design

## Goal

Prevent imported Hong Kong Connect positions from being persisted or rebuilt as A-share positions, correct explicitly identified existing records, and prevent snapshot market-data failures from surfacing as an unclassified HTTP 500 during matching.

## Scope

The repair covers:

- Per-position market selection for imported positions.
- Durable preservation of imported-position market metadata across replay and aggregate-position rebuilds.
- Backward compatibility for existing imports that omit market metadata.
- A targeted, auditable repair for known incorrectly classified existing holdings.
- Controlled matching behavior when snapshot valuation cannot obtain required daily market data.

It does not infer a market from a symbol. Historical holdings are corrected only when their intended market is explicitly known.

## Data Model and Migration

`PaperPositionLot` is the durable source for imported-position replay. Add a non-null `market` field to it, using `a_share` as the ORM and database default.

Extend the schema bootstrap migration to add `paper_position_lots.market` when absent, with `NOT NULL DEFAULT 'a_share'`. This preserves compatibility for existing lots and makes their legacy interpretation explicit; it does not attempt to classify legacy HK holdings automatically.

`PaperPosition.market` remains the aggregate position market. When a position is reconstructed from imported lots, the reconstructed aggregate uses the lot market.

An import batch may contain multiple lots for the same symbol only when every lot declares the same market. Mixed-market rows for one symbol are rejected because the aggregate position has one market field.

## Import Interfaces

Add optional `market` to the import item request model, with `a_share` as its default and the existing supported enum values: `a_share` and `hk_connect`.

The import service writes each item's market to both its imported lot and its aggregate position. Existing JSON callers that omit market retain A-share behavior.

The CSV importer accepts an optional `market` column. CSV files with the existing four required columns remain valid and default each row to A-share. The frontend import form exposes a per-row market selector with A-share selected by default and sends that value in its existing import payload.

## Replay and Rebuild

When account state is cleared and rebuilt, imported lots retain their market. Rebuilt imported aggregate positions copy that market from their lots. The implementation validates that lots for each aggregate symbol agree on market and fails clearly if persisted data is internally inconsistent.

Trade-derived positions continue to obtain market metadata from their corresponding order and are not reclassified by this work.

## Existing Data Correction

Provide a narrow, idempotent repair script or command that accepts explicit account and symbol mappings, then updates matching aggregate positions and imported lots to the requested market. The initial mapping includes only the confirmed Tencent holding, `00700`, in the affected account(s), set to `hk_connect`.

The correction produces a concise record of changed rows. It does not update holdings based on five-digit symbols or any other inferred rule.

## Matching and Snapshot Failure Handling

Snapshot valuation keeps using the persisted position market. A market-data lookup failure caused by a missing daily bar or invalid OHLC values is an unavailable-data condition, not a missing API resource.

Matching must not let such an exception escape as an unclassified HTTP 500. It retains a diagnosable matching-run result and records the failed/incomplete outcome and error detail without writing a misleading snapshot. The exact run status/error representation follows existing matching failure conventions where unavailable market data leaves an operation failed rather than incorrectly filled.

The repair does not silently retry a different market source. A wrong persisted market must be corrected as data, not masked by symbol guessing.

## Tests and Verification

Tests are written before production changes and demonstrate the intended behavior:

1. Importing `00700` with `market=hk_connect` persists HK market on both aggregate position and imported lot.
2. Imports without a market field remain valid and persist `a_share`.
3. Duplicate import rows for one symbol with conflicting markets are rejected.
4. Replay/rebuild preserves the imported HK market for `00700`.
5. The legacy schema upgrade adds the lot market column and backfills omitted legacy values as `a_share`.
6. Snapshot valuation routes an imported `00700` holding through HK data after import and rebuild.
7. A matching request whose snapshot data is absent completes with the selected controlled failure behavior rather than an uncaught 500.
8. The targeted repair command updates only the explicit holdings supplied to it and is idempotent.

Focused backend, storage migration, CLI, and frontend tests establish the behavior. After deployment, run matching for the repaired account and date, then confirm that a matching-run result is recorded and that the response is not HTTP 500.

## Non-goals

- No bulk inference or reclassification of historical holdings.
- No changes to DAG schedules, dependencies, retries, or task boundaries.
- No alteration to normal order market selection semantics.
