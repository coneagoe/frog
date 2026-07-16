# Paper Trading Fee Edit Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a modal-based fee editing flow to the paper trading Accounts page so users can update fee fields on existing accounts and see refreshed data after save.

**Architecture:** Keep the change inside the existing paper-trading Next.js frontend. Extend the shared API types and client with a PATCH helper, add a focused fee-edit modal component, and wire the Accounts page to open the modal from the selected account header. The page remains the source of truth for refreshing the account list and detail panels after a successful update.

**Tech Stack:** Next.js App Router, React 19, TypeScript, existing frontend API proxy, Vitest, Testing Library.

## Global Constraints

- This design covers the paper trading frontend account flow only.
- It adds UI and client support for opening a fee edit form, pre-filling from the selected account, submitting changed fee fields to `PATCH /paper/accounts/{account_id}`, displaying validation and request errors, and refreshing account data after a successful update.
- It does not change order, trade, matching, snapshot, analytics, backend schema, or historical recalculation behavior.
- No support for editing `fee_preset` after account creation.
- No historical fee recalculation.
- No changes to order, trade, matching, snapshot, or analytics pages.
- No reusable fee profile management UI.
- No account edits beyond fee fields.

---

## File Structure

- Modify `frontend/paper-trading/lib/types.ts`: add `UpdateAccountFeesInput` and keep fee field names aligned with existing account types.
- Modify `frontend/paper-trading/lib/api-client.ts`: add `updateAccountFees(accountId, input)` that calls `PATCH /paper/accounts/{account_id}`.
- Create `frontend/paper-trading/features/accounts/edit-account-fees-modal.tsx`: modal form for editing fee fields, local validation, and changed-field payload creation.
- Modify `frontend/paper-trading/features/accounts/accounts-page.tsx`: add modal state, an `Edit fees` trigger in the selected-account header, and refresh/reconcile logic after save.
- Modify `frontend/paper-trading/app/globals.css`: add modal, overlay, and form-row styles that match the existing dark UI.
- Modify `frontend/paper-trading/features/accounts/accounts-page.test.tsx`: cover trigger visibility, opening the modal, saving updates, empty-submit prevention, and refresh behavior.
- Create `frontend/paper-trading/features/accounts/edit-account-fees-modal.test.tsx`: isolate the modal’s payload-building and validation behavior.

## Task 1: Extend Shared Types And API Client

**Files:**
- Modify: `frontend/paper-trading/lib/types.ts:1-191`
- Modify: `frontend/paper-trading/lib/api-client.ts:1-86`
- Test: `frontend/paper-trading/features/accounts/accounts-page.test.tsx`

**Interfaces:**
- Consumes: existing `Account` type and `apiRequest<T>()` helper.
- Produces: `UpdateAccountFeesInput` and `updateAccountFees(accountId, input): Promise<Account>` for the modal and page to use.

- [ ] **Step 1: Add the update input type**

Add this type beside `CreateAccountInput` in `frontend/paper-trading/lib/types.ts`:

```ts
export type UpdateAccountFeesInput = {
  commission_rate?: string;
  min_commission?: string;
  stamp_duty_rate?: string;
  transfer_fee_rate?: string;
};
```

Do not add `fee_preset` to this type.

- [ ] **Step 2: Add the API helper**

Add this import and function in `frontend/paper-trading/lib/api-client.ts`:

```ts
import type {
  Account,
  AnalyticsResponse,
  CashLedgerEntry,
  CreateAccountInput,
  CreateMatchingRunInput,
  CreateOrderInput,
  MatchingRun,
  Order,
  Position,
  Snapshot,
  Trade,
  UpdateAccountFeesInput
} from "./types";

export function updateAccountFees(accountId: number, input: UpdateAccountFeesInput): Promise<Account> {
  return apiRequest<Account>(`/accounts/${accountId}`, { method: "PATCH", body: JSON.stringify(input) });
}
```

Keep the helper consistent with the rest of the client: JSON body, shared error parsing, and no special-case response handling.

- [ ] **Step 3: Verify the API helper compiles**

Run: `npm run lint`

Working directory: `frontend/paper-trading`

Expected: no import or type errors from the new type and helper.

- [ ] **Step 4: Commit the shared-contract update**

```bash
git add frontend/paper-trading/lib/types.ts frontend/paper-trading/lib/api-client.ts
git commit -m "feat: add paper trading fee update client"
```

## Task 2: Build And Wire The Fee Edit Modal

**Files:**
- Create: `frontend/paper-trading/features/accounts/edit-account-fees-modal.tsx`
- Modify: `frontend/paper-trading/features/accounts/accounts-page.tsx:1-199`
- Modify: `frontend/paper-trading/app/globals.css:1-347`

**Interfaces:**
- Consumes: `Account`, `UpdateAccountFeesInput`, `updateAccountFees`, and the selected account from `AccountsPage`.
- Produces: a modal component that accepts `account`, `open`, `onClose`, and `onSaved` props and returns the updated `Account` from the API helper.

- [ ] **Step 1: Write the modal component shape first**

Create `frontend/paper-trading/features/accounts/edit-account-fees-modal.tsx` with this signature:

```tsx
type EditAccountFeesModalProps = {
  account: Account | null;
  open: boolean;
  onClose: () => void;
  onSaved: (account: Account) => Promise<void> | void;
};
```

Use the same four fee fields as the create form. Prefill them from `account` when the modal opens. If `account` is `null`, render nothing.

- [ ] **Step 2: Implement changed-field payload logic**

Inside the modal file, define the exact fee field list and compare against the opened account values:

```ts
const feeFields = [
  "commission_rate",
  "min_commission",
  "stamp_duty_rate",
  "transfer_fee_rate"
] as const;
```

Build the payload by including only fields whose trimmed value differs from the selected account's current value. If every field matches, disable the save button and avoid calling the API.

The submit payload must conform to:

```ts
{
  commission_rate?: string;
  min_commission?: string;
  stamp_duty_rate?: string;
  transfer_fee_rate?: string;
}
```

Do not send `fee_preset`.

- [ ] **Step 3: Add lightweight validation and error display**

Follow the same simple validation style used by `CreateAccountForm`:

```ts
function isNonNegativeDecimal(value: string) {
  return value.trim() === "" || (!Number.isNaN(Number(value)) && Number(value) >= 0);
}
```

If a field is invalid, show a modal-level error before calling the API. Keep the modal open on server errors and preserve user input.

Display this explanatory note in the modal body:

> Fee changes affect future orders and trades only; existing trades, cash ledger entries, and snapshots are not recalculated.

- [ ] **Step 4: Wire the modal into the Accounts page**

In `frontend/paper-trading/features/accounts/accounts-page.tsx`, add:

```tsx
const [feeEditorAccount, setFeeEditorAccount] = useState<Account | null>(null);
const [feeEditorOpen, setFeeEditorOpen] = useState(false);
```

Add an `Edit fees` button in the selected-account header area, not inside the table rows. When clicked, set `feeEditorAccount` to the selected account and open the modal.

After a successful save:

1. close the modal;
2. call `refreshAccounts()`;
3. call `loadAccountDetails(updatedAccount.id, true)` so the detail panels re-read the updated account state.

If the selected account changes while the modal is open, close the modal and clear its state when the current account is deleted or the list becomes empty.

- [ ] **Step 5: Add modal and button styles**

Extend `frontend/paper-trading/app/globals.css` with classes for:

- `.modal-backdrop`
- `.modal`
- `.modal__header`
- `.modal__body`
- `.modal__footer`
- `.modal__note`

Keep the look consistent with the existing dark panels:

- dark backdrop overlay;
- rounded panel with `--panel` or `--panel-soft` background;
- button row aligned to the right;
- mobile-friendly width and spacing.

- [ ] **Step 6: Run the page test file once the UI is wired**

Run: `npm test -- accounts-page.test.tsx`

Working directory: `frontend/paper-trading`

Expected: the file still passes before adding the new fee-edit assertions.

- [ ] **Step 7: Commit the modal wiring**

```bash
git add frontend/paper-trading/features/accounts/edit-account-fees-modal.tsx frontend/paper-trading/features/accounts/accounts-page.tsx frontend/paper-trading/app/globals.css
git commit -m "feat: add fee edit modal to paper trading accounts"
```

## Task 3: Cover The Fee Edit Flow With Tests

**Files:**
- Create: `frontend/paper-trading/features/accounts/edit-account-fees-modal.test.tsx`
- Modify: `frontend/paper-trading/features/accounts/accounts-page.test.tsx:1-416`

**Interfaces:**
- Consumes: the new modal component, `updateAccountFees`, and the existing `AccountsPage` test harness.
- Produces: test coverage for opening, prefill, changed-field PATCH submission, no-op prevention, error handling, and refresh behavior.

- [ ] **Step 1: Add focused modal tests for payload construction**

Create `frontend/paper-trading/features/accounts/edit-account-fees-modal.test.tsx` with these tests:

```tsx
it("prefills the current fee values when opened", async () => {
  render(<EditAccountFeesModal account={demoAccount} open onClose={vi.fn()} onSaved={vi.fn()} />);

  expect(screen.getByLabelText("Commission rate")).toHaveValue("0.000300");
  expect(screen.getByLabelText("Minimum commission (CNY)")).toHaveValue("5.00");
  expect(screen.getByLabelText("Stamp duty rate")).toHaveValue("0.000500");
  expect(screen.getByLabelText("Transfer fee rate")).toHaveValue("0.000010");
});

it("sends only changed fee fields on save", async () => {
  const updatedAccount = { ...demoAccount, commission_rate: "0.0002", min_commission: "3.00" };
  updateAccountFeesMock.mockResolvedValue(updatedAccount);
  const onSaved = vi.fn();

  render(<EditAccountFeesModal account={demoAccount} open onClose={vi.fn()} onSaved={onSaved} />);
  await userEvent.clear(screen.getByLabelText("Commission rate"));
  await userEvent.type(screen.getByLabelText("Commission rate"), "0.0002");
  await userEvent.clear(screen.getByLabelText("Minimum commission (CNY)"));
  await userEvent.type(screen.getByLabelText("Minimum commission (CNY)"), "3.00");
  await userEvent.click(screen.getByRole("button", { name: "Save fees" }));

  expect(updateAccountFeesMock).toHaveBeenCalledWith(1, {
    commission_rate: "0.0002",
    min_commission: "3.00"
  });
  expect(onSaved).toHaveBeenCalledWith(updatedAccount);
});

it("does not call the API when nothing changed", async () => {
  render(<EditAccountFeesModal account={demoAccount} open onClose={vi.fn()} onSaved={vi.fn()} />);

  await userEvent.click(screen.getByRole("button", { name: "Save fees" }));

  expect(updateAccountFeesMock).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toHaveTextContent("Change at least one fee field before saving.");
});

it("keeps the modal open and shows a server error", async () => {
  updateAccountFeesMock.mockRejectedValue(new Error("Invalid decimal"));

  render(<EditAccountFeesModal account={demoAccount} open onClose={vi.fn()} onSaved={vi.fn()} />);
  await userEvent.clear(screen.getByLabelText("Commission rate"));
  await userEvent.type(screen.getByLabelText("Commission rate"), "0.0002");
  await userEvent.click(screen.getByRole("button", { name: "Save fees" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Invalid decimal");
  expect(screen.getByRole("dialog", { name: "Edit fees for demo" })).toBeInTheDocument();
});
```

Use a mock account such as:

```ts
const demoAccount = {
  id: 1,
  name: "demo",
  initial_cash: "100000.00",
  status: "active",
  base_currency: "CNY",
  fee_preset: "a_share",
  commission_rate: "0.000300",
  min_commission: "5.00",
  stamp_duty_rate: "0.000500",
  transfer_fee_rate: "0.000010"
};
```

Mock `updateAccountFees` and assert the exact PATCH payload shape:

```ts
expect(updateAccountFeesMock).toHaveBeenCalledWith(1, {
  commission_rate: "0.0002",
  min_commission: "3.00"
});
```

- [ ] **Step 2: Extend the Accounts page tests for the trigger and refresh path**

Add `updateAccountFees` to the `@/lib/api-client` mock in `frontend/paper-trading/features/accounts/accounts-page.test.tsx` and cover these scenarios:

```tsx
it("opens the fee editor from the selected account header", async () => {
  listAccountsMock.mockResolvedValue([demoAccount]);
  listPositionsMock.mockResolvedValue([]);
  listCashLedgerMock.mockResolvedValue([]);

  render(<AccountsPage />);

  await userEvent.click(await screen.findByRole("button", { name: "Edit fees" }));

  expect(screen.getByRole("dialog", { name: "Edit fees for demo" })).toBeInTheDocument();
  expect(screen.getByLabelText("Commission rate")).toHaveValue("0.000300");
});

it("saves fee changes and refreshes account data", async () => {
  const updatedAccount = { ...demoAccount, commission_rate: "0.0002" };
  listAccountsMock.mockResolvedValueOnce([demoAccount]).mockResolvedValueOnce([updatedAccount]);
  listPositionsMock.mockResolvedValue([]);
  listCashLedgerMock.mockResolvedValue([]);
  updateAccountFeesMock.mockResolvedValue(updatedAccount);

  render(<AccountsPage />);
  await userEvent.click(await screen.findByRole("button", { name: "Edit fees" }));
  await userEvent.clear(screen.getByLabelText("Commission rate"));
  await userEvent.type(screen.getByLabelText("Commission rate"), "0.0002");
  await userEvent.click(screen.getByRole("button", { name: "Save fees" }));

  expect(updateAccountFeesMock).toHaveBeenCalledWith(1, { commission_rate: "0.0002" });
  await waitFor(() => expect(listAccountsMock).toHaveBeenCalledTimes(2));
  expect(screen.queryByRole("dialog", { name: "Edit fees for demo" })).not.toBeInTheDocument();
});

it("shows validation errors without sending an empty patch", async () => {
  listAccountsMock.mockResolvedValue([demoAccount]);
  listPositionsMock.mockResolvedValue([]);
  listCashLedgerMock.mockResolvedValue([]);

  render(<AccountsPage />);
  await userEvent.click(await screen.findByRole("button", { name: "Edit fees" }));
  await userEvent.click(screen.getByRole("button", { name: "Save fees" }));

  expect(updateAccountFeesMock).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toHaveTextContent("Change at least one fee field before saving.");
});
```

Assert that the visible button is `Edit fees`, that the modal pre-fills the selected account values, and that a successful save closes the modal and triggers a list refresh.

- [ ] **Step 3: Add a regression test for empty payload rejection**

Confirm that submitting without any changes does not call `updateAccountFees` and that the modal shows a clear message such as:

```text
Change at least one fee field before saving.
```

This keeps the empty-payload 422 case from reaching the backend during normal use.

- [ ] **Step 4: Run the frontend test suite for the affected files**

Run:

```bash
npm test -- edit-account-fees-modal.test.tsx accounts-page.test.tsx
```

Working directory: `frontend/paper-trading`

Expected: both test files pass, and the new assertions cover the save path and the no-op path.

- [ ] **Step 5: Run the frontend lint/test build gate**

Run:

```bash
npm run lint && npm run test && npm run build
```

Working directory: `frontend/paper-trading`

Expected: lint passes, Vitest passes, and the Next.js build succeeds.

- [ ] **Step 6: Commit the test coverage**

```bash
git add frontend/paper-trading/features/accounts/edit-account-fees-modal.test.tsx frontend/paper-trading/features/accounts/accounts-page.test.tsx
git commit -m "test: cover paper trading fee editing"
```

## Verification Checklist

- The Accounts page exposes an `Edit fees` action for the selected account.
- The modal pre-fills the current fee values from the selected account.
- Saving sends only changed fee fields to `PATCH /paper/accounts/{account_id}`.
- Empty submissions are blocked before the request is sent.
- Successful updates close the modal and refresh both account list and detail panels.
- Validation and server errors remain visible without clearing user input.

## Review Notes

- The plan is intentionally limited to the frontend flow described in the spec.
- No backend or CLI work is included here.
- The modal is the only new interaction pattern; the list and detail layout stay intact.
