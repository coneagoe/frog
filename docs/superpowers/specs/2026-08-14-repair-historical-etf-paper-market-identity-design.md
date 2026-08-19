# Repair Historical ETF Paper Market Identity Design

## Goal

Provide an authenticated Paper Trading API and CLI operation that identifies
historical Paper Trading orders stored as `a_share` even though their symbols
are present in the ETF catalogue. The operation must default to a dry run and,
when explicitly applied, correct each affected account independently and
incrementally rebuild its derived account state from the earliest corrected
order date.

This implements GitHub issue #56, a child of #53. The completed issue #54
provides raw ETF daily data routing, and issue #55 ensures new catalogue-backed
orders persist with market `etf`.

## Scope

The repair candidate rule is deliberately narrow and authoritative:

- a `PaperOrder` currently has `market="a_share"`;
- its symbol is a bare six-digit value; and
- an `ETFBasic` catalogue row exists for that symbol.

No caller-supplied symbol list, prefix inference, or ETF eligibility decision
participates in candidate selection. Catalogue membership identifies the
historical market correction only. Existing ETF eligibility policy remains the
admission policy for newly placed orders and is not re-applied by repair.

The authenticated API endpoint is `POST /paper/repairs/etf-markets`. Its
request body has an optional `apply: bool` field that defaults to `false`.
`false` performs a dry run and never writes. `true` performs the repair. The
CLI command is `repair etf-markets [--apply]`; omission of `--apply` remains a
dry run.

## Architecture

A dedicated `HistoricalEtfMarketRepairService` owns repair discovery, outcome
aggregation, and per-account isolation. It must not alter the delayed-daily-bar
rebuild endpoint or reuse its all-accounts-in-one-transaction behavior.

The API route discovers candidates using its request session. For a dry run it
serializes and returns that discovery result without flushing, committing, or
creating derived records.

For an apply operation, the service groups discovered candidates by account ID.
It processes each account with a fresh session from the normal Paper Trading
session factory, so every account has an independent database transaction. In
that transaction it:

1. re-queries qualifying candidate orders for that account, guarding against a
   concurrent or prior repair;
2. locks the account through `PaperTradingRepository.lock_account` before
   changing its orders or derived state;
3. reports the account as skipped when the re-query has no remaining
   candidates;
4. updates the remaining orders to `market="etf"`;
5. finds the minimum corrected order `trade_date`;
6. invokes `OrderDeleteService.rebuild_account_from` with that date and the
   corrected order IDs; and
7. commits the account transaction and reports its corrected order IDs and
   replay start date.

An exception during one account transaction rolls back both its market changes
and its partial rebuild. The operation records that account as failed and
continues to later accounts. Successful account repairs are never rolled back
because another account fails.

`rebuild_account_from` remains the source of replay behavior. It clears and
recreates derived records while preserving source facts, including prior
execution history before the replay date and historical daily-bar diagnostics.
With corrected ETF identity, matching reads raw `etf_daily` bars and derives
ETF-qualified trade, position, lot, cash-ledger, matching-run, snapshot,
valuation-gap, round-trip, and validity-check state.

## API And CLI Contract

`POST /paper/repairs/etf-markets` accepts:

```json
{"apply": false}
```

The response is structured for both dry-run review and applied outcomes:

```json
{
  "dry_run": true,
  "candidates": [
    {"account_id": 6, "order_id": 41, "symbol": "518880", "trade_date": "2026-08-07"}
  ],
  "corrected_orders": [],
  "repaired_accounts": [],
  "skipped_accounts": [],
  "failed_accounts": []
}
```

On apply, `corrected_orders` contains the corrected candidate records;
`repaired_accounts` contains one item per committed account with `account_id`,
`order_ids`, and `replay_start_date`; `skipped_accounts` contains account IDs
with no candidates at lock time; and `failed_accounts` contains one item per
rolled-back account with `account_id` and an error message. A zero-candidate
apply returns empty collections and makes no writes.

The CLI client sends `POST /paper/repairs/etf-markets` with `{"apply": true}`
only for `repair etf-markets --apply`; otherwise it sends `{"apply": false}`.
It follows existing `--json` behavior. Text output uses the generic structured
dictionary/list formatter so candidates and account outcomes remain readable.

## Error Handling

The API token requirement matches all existing Paper Trading operational
routes. Request-body validation is performed by a Pydantic schema and defaults
`apply` to `false`.

Account-level failures are part of a successful HTTP response because the
service is designed to complete unaffected accounts. The response must expose
only a safe exception message, not a traceback or database URL. Failure to
perform the initial catalogue candidate scan or to construct a repair session
is an unexpected endpoint failure and follows the repository's existing 500
error handling pattern.

The old A-share `missing_exact_date` diagnostic remains untouched. After order
41 is corrected to ETF, replay obtains the available raw ETF bar for
`518880` on 2026-08-07; it therefore must not create an ETF missing-date
diagnostic.

## Tests

Service-level tests will use mixed accounts and the existing Paper Trading
repository, matching, snapshot, and raw ETF market-data seams to prove:

- dry run returns only catalogue-matched A-share candidates and writes nothing;
- an apply corrects account 6 order 41 to ETF, reports 2026-08-07 as the replay
  start date, and creates ETF-consistent derived state;
- the retained A-share missing-date diagnostic survives, while no ETF
  missing-date diagnostic is created when the raw ETF bar exists;
- the service locks each affected account before updates and rebuild;
- an injected account failure rolls back that account but does not undo a
  previously committed account;
- multiple candidates in one account produce one rebuild from the earliest
  corrected date; and
- a subsequent apply finds no candidates, makes no changes, and reports a
  no-op result.

API tests will cover dry-run default behavior, explicit apply transport,
authenticated routing, and response serialization. CLI tests will cover
`repair etf-markets` defaulting to dry run, forwarding `--apply`, JSON output,
and local argument validation.

Focused test runs will use `uv run pytest`; PostgreSQL-integrated Paper Trading
coverage will use `tools/run_tests.sh` because it supplies the isolated test
database environment.

## Out Of Scope

- Changing ETF catalogue ingestion or ETF eligibility policy.
- Reclassifying positions or imported lots without an affected historical
  order.
- Deleting, rewriting, or resolving historical A-share missing-date
  diagnostics.
- Automatically correcting order identity during ordinary matching.
- Adding a browser UI, arbitrary symbol selection, schema migrations, or
  changes to A-share and Hong Kong Stock Connect behavior.
