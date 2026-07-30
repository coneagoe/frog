# Paper Trading Import Positions Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add manual import of existing stock holdings to the paper trading frontend Accounts page.

**Architecture:** Keep the change localized to the Accounts workspace. Extend the shared API/types layer first, then add a dedicated modal for editable lot entry, then wire the modal into the selected-account panel and refresh the existing account detail loaders after a successful import. Reuse the current proxy path `/api/paper/*`, existing error banner patterns, and the current selected-account refresh flow.

**Tech Stack:** Next.js App Router, React 19, TypeScript, Vitest, Testing Library, existing paper trading API proxy.

## Global Constraints

- This design covers the paper trading frontend account flow only.
- It adds UI and client support for manual editable-table import, `POST /api/paper/accounts/{account_id}/positions/import`, validation and request errors, and refreshing selected account state after success.
- It does not add CSV upload, broker synchronization, backend import behavior, order, trade, matching, snapshot, or analytics changes.
- Importing is for one-time initialization of existing holdings.
- Importing does not change account cash.
- Accounts with existing positions or lots cannot be imported again.
- No backend API changes.
- No changes to order, trade, matching, snapshot, or analytics pages.

---

## File Map

- `frontend/paper-trading/lib/types.ts`
  - Add import request/response types.
- `frontend/paper-trading/lib/api-client.ts`
  - Add `importPositions()` helper that posts through the existing proxy.
- `frontend/paper-trading/lib/api-client.test.ts`
  - Add request/body coverage for the new API helper.
- `frontend/paper-trading/features/accounts/import-positions-modal.tsx`
  - New modal with editable lot rows, validation, submit state, and success/error handling.
- `frontend/paper-trading/features/accounts/accounts-page.tsx`
  - Add the entry button, modal wiring, and post-success refresh behavior.
- `frontend/paper-trading/features/accounts/accounts-page.test.tsx`
  - Cover entry point, modal flow, validation, success refresh, and backend failure behavior.

## Task 1: Add import types and API client helper

**Files:**
- Modify: `frontend/paper-trading/lib/types.ts`
- Modify: `frontend/paper-trading/lib/api-client.ts`
- Test: `frontend/paper-trading/lib/api-client.test.ts`

**Interfaces:**
- Consumes: `apiRequest<T>()` in `lib/api-client.ts`, existing `Account`/`Position` type style in `lib/types.ts`
- Produces: `ImportPositionInput`, `ImportPositionsInput`, `ImportPositionsResult`, and `importPositions(accountId, input)`

- [ ] **Step 1: Write the failing test**

Add a test in `frontend/paper-trading/lib/api-client.test.ts` that stubs `fetch`, calls `importPositions(7, { positions: [{ symbol: "000001", quantity: 100, cost_price: "10.23", buy_trade_date: "2026-01-15" }] })`, and asserts the request goes to `/api/paper/accounts/7/positions/import` with `method: "POST"` and the exact JSON body.

```ts
import { importPositions } from "./api-client";

it("posts import positions payloads", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ imported_count: 1, lots_count: 1 }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);

  await importPositions(7, {
    positions: [{ symbol: "000001", quantity: 100, cost_price: "10.23", buy_trade_date: "2026-01-15" }]
  });

  expect(fetchMock).toHaveBeenCalledWith(
    "/api/paper/accounts/7/positions/import",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        positions: [{ symbol: "000001", quantity: 100, cost_price: "10.23", buy_trade_date: "2026-01-15" }]
      })
    })
  );
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/paper-trading && npm run test -- lib/api-client.test.ts`

Expected: fail because `importPositions` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

In `lib/types.ts`, add:

```ts
export type ImportPositionInput = {
  symbol: string;
  quantity: number;
  cost_price: string;
  buy_trade_date: string;
};

export type ImportPositionsInput = {
  positions: ImportPositionInput[];
};

export type ImportPositionsResult = {
  imported_count: number;
  lots_count: number;
};
```

In `lib/api-client.ts`, extend the import list and add:

```ts
export function importPositions(accountId: number, input: ImportPositionsInput): Promise<ImportPositionsResult> {
  return apiRequest<ImportPositionsResult>(`/accounts/${accountId}/positions/import`, {
    method: "POST",
    body: JSON.stringify(input)
  });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend/paper-trading && npm run test -- lib/api-client.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

If you are working in a git lane, commit only these files with a message like:

```bash
git add frontend/paper-trading/lib/types.ts frontend/paper-trading/lib/api-client.ts frontend/paper-trading/lib/api-client.test.ts
git commit -m "feat(paper-trading): add import positions client"
```

## Task 2: Build the import positions modal

**Files:**
- Create: `frontend/paper-trading/features/accounts/import-positions-modal.tsx`
- Test: `frontend/paper-trading/features/accounts/import-positions-modal.test.tsx`

**Interfaces:**
- Consumes: `importPositions()` from `@/lib/api-client`, `ImportPositionsInput`/`ImportPositionsResult` from `@/lib/types`
- Produces: `ImportPositionsModal` with props `{ account: Account | null; open: boolean; onClose: () => void; onImported: (result: ImportPositionsResult) => Promise<void> | void }`

- [ ] **Step 1: Write the failing test**

Create a focused modal test file that renders the modal open for a demo account and asserts:

1. It shows the title `Import positions for demo`.
2. It starts with one editable row.
3. It shows the note that import is one-time and does not change cash.
4. Adding a row increases the number of row groups.
5. Removing a row does not leave the table visually empty.
6. Valid input calls `importPositions()` with the expected body.
7. Invalid quantity or invalid date shows a validation alert and does not submit.

```tsx
it("submits a valid import payload", async () => {
  importPositionsMock.mockResolvedValue({ imported_count: 1, lots_count: 1 });

  render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

  const dialog = screen.getByRole("dialog", { name: "Import positions for demo" });
  await userEvent.type(within(dialog).getByLabelText("Symbol"), "000001");
  await userEvent.type(within(dialog).getByLabelText("Quantity"), "100");
  await userEvent.type(within(dialog).getByLabelText("Cost price"), "10.23");
  await userEvent.type(within(dialog).getByLabelText("Buy trade date"), "2026-01-15");

  await userEvent.click(screen.getByRole("button", { name: "Import positions" }));

  expect(importPositionsMock).toHaveBeenCalledWith(1, {
    positions: [{ symbol: "000001", quantity: 100, cost_price: "10.23", buy_trade_date: "2026-01-15" }]
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/paper-trading && npm run test -- features/accounts/import-positions-modal.test.tsx`

Expected: fail because the component does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implement the modal as a client component with these behaviors:

```tsx
type ImportRow = {
  symbol: string;
  quantity: string;
  cost_price: string;
  buy_trade_date: string;
};
```

Use local state for rows, `submitting`, and `error`.

Validation rules:

- symbol is non-empty after trim;
- quantity parses to an integer `> 0`;
- cost price parses to a number `>= 0`;
- buy date matches `/^\d{4}-\d{2}-\d{2}$/`.

Submission rules:

- trim symbol before submit;
- convert quantity to `number` in the payload;
- keep cost price as a string in the payload;
- call `importPositions(account.id, { positions })`;
- call `onImported(result)` after success;
- close through `onClose()` only after success handling completes.

Modal copy rules:

- title: `Import positions for ${account.name}`;
- note: `Importing initializes existing holdings only and does not change cash.`;
- backend rejection note: `This account already has positions. Import is only available for empty accounts.`

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend/paper-trading && npm run test -- features/accounts/import-positions-modal.test.tsx`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/paper-trading/features/accounts/import-positions-modal.tsx frontend/paper-trading/features/accounts/import-positions-modal.test.tsx
git commit -m "feat(paper-trading): add import positions modal"
```

## Task 3: Wire import into Accounts page and refresh data

**Files:**
- Modify: `frontend/paper-trading/features/accounts/accounts-page.tsx`
- Modify: `frontend/paper-trading/features/accounts/accounts-page.test.tsx`

**Interfaces:**
- Consumes: `ImportPositionsModal`, `importPositions()` via modal callback, existing `loadAccountDetails(accountId, true)` pattern
- Produces: `Import positions` entry point on the selected account panel and post-import refresh behavior

- [ ] **Step 1: Write the failing test**

Add tests in `accounts-page.test.tsx` covering:

1. The selected account panel shows `Import positions`.
2. Opening the modal shows the one-time import/cash note.
3. Importing a valid row calls the API helper, closes the modal, and refreshes `listPositions()` and `listCashLedger()` for the selected account.
4. Backend validation errors keep the modal open and show the error text.

Use the existing mocking style already present in this file:

```ts
vi.mock("@/lib/api-client", () => ({
  createAccount: vi.fn(),
  deleteAccount: vi.fn(),
  listAccounts: vi.fn(),
  listPositions: vi.fn(),
  listCashLedger: vi.fn(),
  updateAccountFees: vi.fn(),
  importPositions: vi.fn()
}));
```

For the success path, assert the selected account details refresh after import by checking the refreshed `listPositions` and `listCashLedger` calls.

```tsx
await userEvent.click(screen.getByRole("button", { name: "Import positions" }));
const dialog = screen.getByRole("dialog", { name: "Import positions for demo" });
await userEvent.type(within(dialog).getByLabelText("Symbol"), "000001");
await userEvent.type(within(dialog).getByLabelText("Quantity"), "100");
await userEvent.type(within(dialog).getByLabelText("Cost price"), "10.23");
await userEvent.type(within(dialog).getByLabelText("Buy trade date"), "2026-01-15");
await userEvent.click(screen.getByRole("button", { name: "Import positions" }));

expect(importPositionsMock).toHaveBeenCalledWith(1, {
  positions: [{ symbol: "000001", quantity: 100, cost_price: "10.23", buy_trade_date: "2026-01-15" }]
});
await waitFor(() => expect(listPositionsMock).toHaveBeenCalledTimes(2));
await waitFor(() => expect(listCashLedgerMock).toHaveBeenCalledTimes(2));
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/paper-trading && npm run test -- features/accounts/accounts-page.test.tsx`

Expected: fail because the new action/modal are not wired yet.

- [ ] **Step 3: Write minimal implementation**

In `accounts-page.tsx`:

1. Import `importPositions` only if the page needs to forward a helper directly; otherwise keep the API call inside the modal and pass a callback into the modal.
2. Add new local state for the import modal, similar to the fee editor:

```ts
const [importModalOpen, setImportModalOpen] = useState(false);
```

3. Render an `Import positions` button next to `Edit fees` in the selected account header.
4. Add the new modal directly under `EditAccountFeesModal`.
5. On successful import, close the modal and call `loadAccountDetails(selectedAccountId, true)` so positions and cash ledger refresh together.
6. Reuse the existing `detailError` and `ErrorBanner` pattern for request errors if the modal reports an error upward.

Keep the page change small. Do not move selected-account logic out of the page.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd frontend/paper-trading && npm run test -- features/accounts/accounts-page.test.tsx lib/api-client.test.ts features/accounts/import-positions-modal.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/paper-trading/features/accounts/accounts-page.tsx frontend/paper-trading/features/accounts/accounts-page.test.tsx
git commit -m "feat(paper-trading): wire import positions into accounts"
```

## Task 4: Final verification and doc sync

**Files:**
- Modify only if needed: frontend paper-trading docs or test files discovered during verification

**Interfaces:**
- Consumes: completed frontend feature and tests
- Produces: verified working change set

- [ ] **Step 1: Run the frontend test suite**

Run: `cd frontend/paper-trading && npm run test`

Expected: PASS.

- [ ] **Step 2: Run lint**

Run: `cd frontend/paper-trading && npm run lint`

Expected: PASS.

- [ ] **Step 3: Fix any test or lint fallout**

If the new modal copy, accessibility labels, or test selectors need adjustment, fix them in the owning file from Tasks 2-3 and re-run the same command that failed.

- [ ] **Step 4: Review whether docs need a frontend-facing note**

If the implementation introduces any user-visible copy or workflow clarification not already covered by `docs/paper_trading.md` and the API reference, update the smallest relevant doc file and keep the wording aligned with the implemented UI.

## Spec Coverage Check

- Manual editable-table import from Accounts page: Task 2 and Task 3.
- No CSV upload: covered by Global Constraints and Task 2 non-goals.
- One-time initialization only: Task 2 copy and validation.
- Does not change cash: Task 2 copy and Task 3 refresh behavior.
- Reject already-populated accounts: Task 2 error handling.
- API proxy path `/api/paper/accounts/{account_id}/positions/import`: Task 1.
- Refresh positions and cash ledger after success: Task 3.
- Tests for API, modal, and page integration: Tasks 1-3.

## Self-Review Notes

- No placeholders remain.
- Type names are consistent across tasks: `ImportPositionInput`, `ImportPositionsInput`, `ImportPositionsResult`.
- The plan stays within a single frontend feature slice and does not mix backend work.
