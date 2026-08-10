# ETF Eligibility Lifecycle Design

## Scope

Issue #43 adds the auditable eligibility lifecycle required before paper
trading can accept domestic ETFs. It does not add the `etf` paper-trading
market, ETF order handling, fees, daily-bar routing, or a web UI.

The lifecycle consumes the existing `etf_basic` provider table after its normal
successful refresh. It records human classification separately from provider
metadata so a later refresh cannot erase a reviewed decision.

## Persistence

Add a paper-trading-owned ETF eligibility table keyed by the bare six-digit ETF
symbol. It has a governed `ETFEligibilityStatus` enum with these states:

- `unknown`: a currently listed domestic ETF discovered by reconciliation but
  not reviewed.
- `supported`: an operator has reviewed and approved a currently eligible ETF.
- `money_market`: an operator has reviewed and excluded a money-market ETF.
- `disabled`: reconciliation has disabled an ETF that is no longer currently
  listed.

Each row persists the last observed provider name, exchange, listing status,
and refresh timestamp, plus the classification timestamp and reviewer supplied
by the operator. Provider fields are refreshed on every successful
reconciliation; classification audit fields change only through explicit review
operations or the system disabling an inactive listing.

The enum migration follows the existing paper-trading enum-governance adapter.
It creates and verifies the table and enum on upgrade and restores the prior
state on rollback only when the repository's existing dependency preflight
allows it. Add the table to the database export/import table list.

## Reconciliation

Run reconciliation only after ETF basic information has been successfully
persisted. It reads the complete current `etf_basic` snapshot and uses explicit
provider values: `SH` or `SZ` for exchange and `L` for listed status.

- A current listed Shanghai or Shenzhen ETF without an eligibility row gets a
  new `unknown` row.
- Existing rows refresh their provider lifecycle fields.
- Existing `supported` and `money_market` classifications remain unchanged for
  currently listed ETFs, including their review audit fields.
- A row whose symbol is absent from the refreshed provider snapshot or no
  longer has listed Shanghai/Shenzhen lifecycle data becomes `disabled`.
- Re-running reconciliation against the same snapshot is idempotent.

Reconciliation does not infer money-market status from TuShare's `etf_type`.
That field describes an investment channel and is retained only in the source
metadata.

## Operator Interface

Extend the authenticated paper-trading API and existing CLI wrapper with
eligibility operations:

- List records, optionally filtered by status.
- Inspect a record by bare six-digit symbol.
- Classify a current listed Shanghai/Shenzhen record explicitly as `supported`
  or `money_market`, recording the caller-supplied reviewer.

Classification rejects absent, non-listed, or non-Shanghai/Shenzhen provider
metadata. Operators cannot manually set `unknown` or `disabled`; those states
are controlled by reconciliation. No web UI or separate administrative service
is added.

## Validation Contract

Provide a narrow ETF metadata validation seam for the later ETF order workflow.
It validates a bare six-digit ETF symbol against current provider metadata and
the eligibility record, returning stable outcomes:

- No ETF basic metadata: `ETF_NOT_FOUND`.
- Missing eligibility record or `unknown` eligibility: `ETF_ELIGIBILITY_UNREVIEWED`.
- `money_market` or `disabled` eligibility: `UNSUPPORTED_ETF_TYPE`.
- Provider exchange other than `SH` or `SZ`: an invalid-exchange outcome.
- Provider listing status other than `L`: an invalid-listing-status outcome.
- A current listed Shanghai/Shenzhen `supported` ETF: eligible.

The validation seam does not add ETF order behavior in this issue. It is
covered directly so the later order path can map outcomes to its established
API error contract without reimplementing lifecycle policy.

## Testing And Verification

The primary claim is that a successful provider refresh creates and maintains
reviewable eligibility records without overwriting an operator classification,
and that callers can distinguish every eligibility failure condition.

Focused tests cover:

- Enum/table migration, verification, rollback preflight, and database
  export/import inclusion.
- Reconciliation for new, changed, missing, delisted, and unchanged provider
  records, including idempotence and review-audit preservation.
- Review service and API contracts, including allowed transitions and rejected
  stale/invalid provider records.
- CLI request construction and human/JSON output for list, get, and classify.
- Validation outcomes for absent metadata, unreviewed, money-market, disabled,
  invalid exchange, invalid listing status, and supported ETFs.
- Regression coverage that existing ETF basic download persistence continues to
  run without changing schedules, dependencies, retries, or task boundaries.

Use mocked provider data and existing paper-trading service/API fakes. Run the
focused tests first, then the paper-trading suite, formatting, lint, and type
checks appropriate to the touched modules. PostgreSQL-backed migration tests
provide the direct evidence for upgrade and rollback behavior when the local
test database is available; skipped integration tests remain explicitly
reported if it is not.

## Non-Goals

- ETF order placement, matching, pricing, valuation, fees, or sellability.
- Adding `etf` to the paper-trading market enum.
- Automatic ETF classification from code patterns, names, or provider
  `etf_type`.
- ETF listings outside Shanghai and Shenzhen.
- Web administration or a separate eligibility service.
- Changes to DAG schedules, dependencies, retries, task boundaries, or SLA.
