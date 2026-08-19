# Issue #73 Accounts Cash Available Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return authoritative available cash in paper-account responses and remove Cash Ledger loading and rendering from Accounts.

**Architecture:** Add `cash_available: Decimal` to `AccountResponse`. A shared helper in `paper_trading/api/routers/accounts.py` will enrich create, list, get, and fee-update responses with `PaperTradingRepository.get_cash_available(account_id)`. The frontend `Account` contract will consume that field; Accounts will load positions only and pass the field to the existing cash-flow modal.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, pytest, Next.js 15, React 19, TypeScript, Vitest, Testing Library.

## Global Constraints

- Reuse the existing repository cash calculation; never reconstruct cash from browser ledger entries.
- Preserve deposit, withdrawal, fee, position, matching, settlement, valuation, and account lifecycle semantics.
- Preserve the cash-ledger API and `CashLedgerTable`; remove only their use from Accounts.
- Preserve HTTP 422 insufficient-funds handling and modal error display.
- Do not modify unrelated dirty working-tree files.
- Use `uv run` for Python commands.

---

### Task 1: Backend Account Contract

**Files:**
- Modify: `paper_trading/schemas/accounts.py:61-86`
- Modify: `paper_trading/api/routers/accounts.py:38-103`
- Test: `test/paper_trading/api/test_accounts_api.py:85-193`

**Interfaces:**
- Consumes: `PaperTradingRepository.get_cash_available(account_id: int) -> Decimal`.
- Produces: `AccountResponse.cash_available: Decimal` on create, list, detail, and fee-update responses.
- Produces: `_account_response(repo, account) -> AccountResponse | None` as the single account serialization path.

- [ ] **Step 1: Add a failing contract test.** In `test_accounts_api.py`, create an account with `100000.00`, assert its create response has `cash_available == "100000.0000"`, deposit `25000.00`, then assert list, detail, and fee-update responses each return `"125000.0000"`.
- [ ] **Step 2: Run the failing test.** Run `uv run pytest test/paper_trading/api/test_accounts_api.py::test_account_responses_include_ledger_derived_cash_available -v`. It must fail because the field is absent.
- [ ] **Step 3: Implement the contract.** Add `cash_available: Decimal` to `AccountResponse`. Add `_account_response` in the router; validate the account model and copy it with `cash_available=repo.get_cash_available(account.id)`. Use one repository instance in each create/list/get/fee-update route and map list results through the helper. Preserve all current commits, status codes, and exception translation.
- [ ] **Step 4: Run the focused test.** The same pytest command must pass and show the initial and post-deposit balances above.
- [ ] **Step 5: Run backend regression tests.** Run `uv run pytest test/paper_trading/api/test_accounts_api.py -v`; all account, deposit, and withdrawal tests must pass.
- [ ] **Step 6: Commit.** Commit only the backend schema, router, and API test with subject `feat: expose paper account available cash`.

### Task 2: Accounts Frontend Workflow

**Files:**
- Modify: `frontend/paper-trading/lib/types.ts:1-16`
- Modify: `frontend/paper-trading/features/accounts/accounts-page.tsx:3-309`
- Test: `frontend/paper-trading/features/accounts/accounts-page.test.tsx:1-813`
- Test: `frontend/paper-trading/features/accounts/cash-flow-modal.test.tsx:15-30`

**Interfaces:**
- Consumes: account JSON containing `cash_available: string`.
- Produces: `Account.cash_available: string`.
- Produces: Accounts detail loading that calls `listPositions(accountId)` only.

- [ ] **Step 1: Update tests first.** Remove `listCashLedger` imports, mocks, fixtures, and expectations from `accounts-page.test.tsx`. Add `cash_available: "100000.0000"` to every account fixture. Replace ledger-specific tests with assertions that positions load, `listCashLedger` is never called, and `Cash Ledger` is absent. Keep account selection, URL selection, delete, fee, import, deposit, and withdrawal behavior assertions.
- [ ] **Step 2: Run the page test and confirm failure.** Run `npm test -- --runInBand frontend/paper-trading/features/accounts/accounts-page.test.tsx`. It must fail against the current ledger-dependent implementation.
- [ ] **Step 3: Implement the page change.** Add `cash_available: string` to `lib/types.ts`. In `accounts-page.tsx`, remove `listCashLedger`, `CashLedgerEntry`, `CashLedgerTable`, ledger state, ledger summation, and the Cash Ledger panel. Make `loadAccountDetails` request positions only while retaining stale-request protection and detail errors. Pass `selectedAccount?.cash_available ?? "0.0000"` to `CashFlowModal`. Do not change modal validation or backend-error handling.
- [ ] **Step 4: Update modal fixtures.** Add `cash_available: "100000.0000"` to the `cash-flow-modal.test.tsx` account fixture.
- [ ] **Step 5: Run focused frontend tests.** Run `npm test -- --runInBand frontend/paper-trading/features/accounts/accounts-page.test.tsx frontend/paper-trading/features/accounts/cash-flow-modal.test.tsx`; all retained workflows and cash validation/error tests must pass.
- [ ] **Step 6: Commit.** Commit only the frontend contract, page, and focused tests with subject `feat: remove accounts cash ledger display`.

### Task 3: Integrated Verification

**Files:**
- Verify the seven files changed by Tasks 1 and 2.

**Interfaces:**
- Consumes: the backend API contract and frontend consumer from Tasks 1 and 2.
- Produces: verified issue #73 behavior with the shared cash-ledger capability retained.

- [ ] **Step 1: Format and lint Python.** Run `uv run ruff format paper_trading/schemas/accounts.py paper_trading/api/routers/accounts.py test/paper_trading/api/test_accounts_api.py` and then `uv run ruff check paper_trading/schemas/accounts.py paper_trading/api/routers/accounts.py test/paper_trading/api/test_accounts_api.py`.
- [ ] **Step 2: Lint frontend.** From `frontend/paper-trading`, run `npm run lint`.
- [ ] **Step 3: Run final focused suites.** Run the backend API test file and both focused frontend test files from Tasks 1 and 2.
- [ ] **Step 4: Review the scoped diff.** Run `git diff --check` and inspect only the seven issue files. Confirm no changes to `/cash-ledger` or `CashLedgerTable`, no browser cash reconstruction, and no unrelated working-tree files.
- [ ] **Step 5: Apply the required simplify review.** Invoke the `simplify` skill after behavior is verified; apply only safe issue-scoped simplifications, then rerun affected tests.
- [ ] **Step 6: Run final verification before claiming completion.** Invoke `verification-before-completion`, confirm test output, and report any unavailable checks explicitly.
