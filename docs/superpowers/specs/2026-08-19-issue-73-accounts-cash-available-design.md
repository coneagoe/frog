# Issue #73: Accounts Cash Available Design

## Scope

Expose authoritative available cash in the paper-trading account API and remove
Cash Ledger loading and rendering from the Accounts workspace. Preserve the
existing cash-ledger API and reusable table component for other consumers.

The implementation must not change paper-trading business semantics, account
lifecycle behavior, fees, positions, matching, settlement, portfolio
valuation, or cash deposit and withdrawal rules.

## Architecture

`AccountResponse` gains a required decimal `cash_available` field. Account API
responses use the existing repository cash-availability calculation as their
single source of truth. A shared response-construction helper will enrich
account records so create, list, detail, and fee-update responses expose the
same contract.

The existing withdrawal service validation remains authoritative. The
withdrawal route continues to translate insufficient funds into HTTP 422, and
the frontend continues to show that backend error.

The Accounts page consumes `selectedAccount.cash_available` from the account
contract. Selecting an account loads positions only; it does not request or
sum cash-ledger history. The cash-flow modal receives the account field for
its client-side withdrawal limit check.

The `/cash-ledger` endpoint and `CashLedgerTable` remain unchanged because
this issue removes their use from Accounts, not the shared capability itself.

## Component Changes

### Backend

- Add `cash_available` to the account schema and frontend-facing contract.
- Reuse `PaperTradingRepository.get_cash_available(account_id)` when building
  account responses.
- Apply the same enrichment to create, list, get, and fee-update responses.
- Preserve all existing cash-service and router error handling.

### Frontend

- Add non-null string `cash_available` to the `Account` type.
- Remove Accounts-page imports, state, calculations, requests, and rendering
  for `CashLedgerEntry` and `CashLedgerTable`.
- Keep account selection, positions, account creation/deletion, fee editing,
  position import, deposits, and withdrawals functional.
- Pass the selected account's available cash to `CashFlowModal`.
- Retain accessible narrow-screen behavior and existing horizontal scrolling
  for wide operational tables.

## Data Flow and Error Handling

1. An account route obtains the account record.
2. The response helper obtains authoritative available cash from the
   repository and serializes it as `cash_available`.
3. The Accounts page renders the account summary and uses the field for cash
   flow validation.
4. A withdrawal is still validated by the backend at submission time; any
   HTTP 422 response remains visible in the modal.

If available-cash lookup fails, the API must surface the failure through the
existing error path. The frontend must not silently fall back to reconstructing
cash from ledger history.

## Testing and Acceptance

Backend API tests will verify that account create, list, detail, and fee-update
responses include `cash_available`, including a ledger state where the value
differs from the account's initial cash. Existing cash-service withdrawal
validation tests remain regression coverage.

Frontend page tests will verify that Accounts does not call `listCashLedger`,
does not render a Cash Ledger table, and still supports account, positions,
fees, import, deposit, and withdrawal workflows. Cash-flow modal tests will
continue to cover client-side withdrawal limits and backend error display.

Validation will include focused backend and frontend tests, formatting/lint or
type checks applicable to touched files, and a final diff review. Existing
unrelated working-tree changes will remain untouched.
