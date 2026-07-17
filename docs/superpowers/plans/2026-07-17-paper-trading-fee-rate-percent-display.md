# Paper Trading Fee Rate Percent Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display and accept paper trading fee rate inputs as percentages in the accounts frontend while continuing to send decimal rate strings to the backend API.

**Architecture:** Add small frontend conversion helpers beside the account fee forms, then apply them consistently in the create account form and edit fees modal. Existing API client types and backend code stay unchanged because the API contract remains decimal-rate based.

**Tech Stack:** Next.js/React client components, TypeScript, Vitest, Testing Library, `uv run` for repository commands.

## Global Constraints

- Scope is frontend paper trading accounts UI only: `Create Account` card, `Edit fees` modal, and their frontend tests.
- Backend API, database schema, CLI, fee calculation logic, and persisted values remain unchanged.
- Rate labels must be `Commission rate (%)`, `Stamp duty rate (%)`, and `Transfer fee rate (%)`.
- `Minimum commission (CNY)` remains a currency amount and must not be converted.
- Display conversion is backend decimal rate multiplied by 100.
- Submit conversion is UI percentage input divided by 100.
- Blank optional rate inputs remain blank and are omitted from payloads where existing behavior omits blank values.
- Use `uv run` for Python commands in this repository.

---

## File Structure

- Modify: `frontend/paper-trading/features/accounts/create-account-form.tsx`
  - Owns create account form state, validation, and create payload construction.
  - Adds percent labels, percent defaults/placeholders, and decimal conversion before `createAccount`.
- Modify: `frontend/paper-trading/features/accounts/edit-account-fees-modal.tsx`
  - Owns edit fee modal state, validation, changed-field detection, and update payload construction.
  - Adds percent labels, converts account decimal values to display percentages, compares changed fields against percent display values, and converts changed rate fields back to decimal strings before `updateAccountFees`.
- Modify: `frontend/paper-trading/features/accounts/accounts-page.test.tsx`
  - Integration-style tests for create form and modal behavior from the accounts page.
- Modify: `frontend/paper-trading/features/accounts/edit-account-fees-modal.test.tsx`
  - Focused modal unit tests for prefill, changed payloads, blank-field behavior, and server error behavior.

No new shared helper file is required. Keep conversion helpers local to each component unless duplication grows beyond the two small forms.

---

### Task 1: Create Account Percentage Inputs

**Files:**
- Modify: `frontend/paper-trading/features/accounts/create-account-form.tsx:7-97`
- Test: `frontend/paper-trading/features/accounts/accounts-page.test.tsx:97-158`

**Interfaces:**
- Consumes: existing `createAccount(input: CreateAccountInput)` from `@/lib/api-client`.
- Produces: create form fields labeled `Commission rate (%)`, `Stamp duty rate (%)`, `Transfer fee rate (%)`; API payload still uses decimal keys `commission_rate`, `stamp_duty_rate`, `transfer_fee_rate`.

- [ ] **Step 1: Write failing tests for percentage create input conversion**

Edit `frontend/paper-trading/features/accounts/accounts-page.test.tsx` so the existing create fee tests use percentage labels and percentage values. Replace the body of `it("creates an account with custom fee settings"...)` with:

```tsx
    listAccountsMock
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([demoAccount]);
    listPositionsMock.mockResolvedValue([]);
    listCashLedgerMock.mockResolvedValue([]);
    createAccountMock.mockResolvedValue(demoAccount);

    render(<AccountsPage />);
    await userEvent.type(await screen.findByLabelText("Account name"), "demo");
    await userEvent.clear(screen.getByLabelText("Commission rate (%)"));
    await userEvent.type(screen.getByLabelText("Commission rate (%)"), "0.02");
    await userEvent.clear(screen.getByLabelText("Minimum commission (CNY)"));
    await userEvent.type(screen.getByLabelText("Minimum commission (CNY)"), "3.00");
    await userEvent.clear(screen.getByLabelText("Stamp duty rate (%)"));
    await userEvent.type(screen.getByLabelText("Stamp duty rate (%)"), "0.05");
    await userEvent.clear(screen.getByLabelText("Transfer fee rate (%)"));
    await userEvent.type(screen.getByLabelText("Transfer fee rate (%)"), "0.001");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(createAccountMock).toHaveBeenCalledWith({
      name: "demo",
      initial_cash: "100000.00",
      fee_preset: "a_share",
      commission_rate: "0.0002",
      min_commission: "3.00",
      stamp_duty_rate: "0.0005",
      transfer_fee_rate: "0.00001"
    });
```

In the blank optional fee test, change the label lookups and expected payload to:

```tsx
    await userEvent.type(await screen.findByLabelText("Account name"), "demo");
    await userEvent.clear(screen.getByLabelText("Commission rate (%)"));
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(createAccountMock).toHaveBeenCalledWith({
      name: "demo",
      initial_cash: "100000.00",
      fee_preset: "a_share",
      min_commission: "5.00",
      stamp_duty_rate: "0.0005",
      transfer_fee_rate: "0.00001"
    });
```

In the negative validation test, change the rate label and value to:

```tsx
    await userEvent.clear(screen.getByLabelText("Commission rate (%)"));
    await userEvent.type(screen.getByLabelText("Commission rate (%)"), "-0.01");
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
uv run npm --prefix frontend/paper-trading test -- accounts-page.test.tsx
```

Expected: FAIL because `Commission rate (%)`, `Stamp duty rate (%)`, and `Transfer fee rate (%)` labels do not exist yet, or because the payload still sends unconverted values.

- [ ] **Step 3: Implement create form percentage labels and conversion**

In `frontend/paper-trading/features/accounts/create-account-form.tsx`, replace `feeFields` with metadata that distinguishes rate fields from currency fields:

```tsx
const feeFields = [
  { key: "commission_rate", label: "Commission rate (%)", defaultValue: "0.03", kind: "rate" },
  { key: "min_commission", label: "Minimum commission (CNY)", defaultValue: "5.00", kind: "money" },
  { key: "stamp_duty_rate", label: "Stamp duty rate (%)", defaultValue: "0.05", kind: "rate" },
  { key: "transfer_fee_rate", label: "Transfer fee rate (%)", defaultValue: "0.001", kind: "rate" }
] as const;
```

Add this helper below `isNonNegativeDecimal`:

```tsx
function percentToDecimalRate(value: string) {
  return (Number(value) / 100).toString();
}
```

Update the `feeValues` initial state to percentage display values for rate fields:

```tsx
  const [feeValues, setFeeValues] = useState<Record<FeeFieldKey, string>>({
    commission_rate: "0.03",
    min_commission: "5.00",
    stamp_duty_rate: "0.05",
    transfer_fee_rate: "0.001"
  });
```

Update payload construction inside `if (feeChanged)` so only rate fields are converted:

```tsx
        for (const field of feeFields) {
          const value = feeValues[field.key].trim();
          if (value !== "") {
            input[field.key] = field.kind === "rate" ? percentToDecimalRate(value) : value;
          }
        }
```

Keep the input `aria-label={field.label}` and `placeholder={field.defaultValue}` lines as they are so the new labels and placeholders flow through automatically.

- [ ] **Step 4: Run the focused create/account page tests and verify they pass**

Run:

```bash
uv run npm --prefix frontend/paper-trading test -- accounts-page.test.tsx
```

Expected: PASS for `accounts-page.test.tsx`.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add frontend/paper-trading/features/accounts/create-account-form.tsx frontend/paper-trading/features/accounts/accounts-page.test.tsx docs/superpowers/specs/2026-07-17-paper-trading-fee-rate-percent-display-design.md docs/superpowers/plans/2026-07-17-paper-trading-fee-rate-percent-display.md
git commit -m "feat: show account fee rates as percentages"
```

---

### Task 2: Edit Fees Modal Percentage Display and Save Conversion

**Files:**
- Modify: `frontend/paper-trading/features/accounts/edit-account-fees-modal.tsx:7-126`
- Test: `frontend/paper-trading/features/accounts/edit-account-fees-modal.test.tsx:31-108`
- Test: `frontend/paper-trading/features/accounts/accounts-page.test.tsx:428-515`

**Interfaces:**
- Consumes: backend account fields as decimal strings on `Account`.
- Produces: modal fields labeled `Commission rate (%)`, `Stamp duty rate (%)`, `Transfer fee rate (%)`; update payload still uses decimal strings for changed rate fields.

- [ ] **Step 1: Write failing modal unit tests for percent display and conversion**

In `frontend/paper-trading/features/accounts/edit-account-fees-modal.test.tsx`, update `prefills the current fee values when opened` assertions to:

```tsx
    expect(screen.getByLabelText("Commission rate (%)")).toHaveValue("0.03");
    expect(screen.getByLabelText("Minimum commission (CNY)")).toHaveValue("5.00");
    expect(screen.getByLabelText("Stamp duty rate (%)")).toHaveValue("0.05");
    expect(screen.getByLabelText("Transfer fee rate (%)")).toHaveValue("0.001");
```

Update `sends only changed fee fields on save` to enter a percent value while expecting a decimal payload:

```tsx
    await userEvent.clear(screen.getByLabelText("Commission rate (%)"));
    await userEvent.type(screen.getByLabelText("Commission rate (%)"), "0.02");
    await userEvent.clear(screen.getByLabelText("Minimum commission (CNY)"));
    await userEvent.type(screen.getByLabelText("Minimum commission (CNY)"), "3.00");
    await userEvent.click(screen.getByRole("button", { name: "Save fees" }));

    expect(updateAccountFeesMock).toHaveBeenCalledWith(1, {
      commission_rate: "0.0002",
      min_commission: "3.00"
    });
```

Update the remaining modal test label lookups from `Commission rate` to `Commission rate (%)`, and type `0.02` in the server error test while still expecting the server error to display.

- [ ] **Step 2: Write failing accounts page tests for modal percent behavior**

In `frontend/paper-trading/features/accounts/accounts-page.test.tsx`, update modal-related test expectations:

```tsx
    expect(within(dialog).getByLabelText("Commission rate (%)")).toHaveValue("0.03");
```

In `saves fee changes and refreshes account data`, enter percentage `0.02` and expect decimal payload `0.0002`:

```tsx
    await userEvent.clear(within(dialog).getByLabelText("Commission rate (%)"));
    await userEvent.type(within(dialog).getByLabelText("Commission rate (%)"), "0.02");
    await userEvent.click(screen.getByRole("button", { name: "Save fees" }));

    expect(updateAccountFeesMock).toHaveBeenCalledWith(1, { commission_rate: "0.0002" });
```

In `does not reload saved account details when that account is no longer selected`, make the same label and input changes:

```tsx
    await userEvent.clear(within(dialog).getByLabelText("Commission rate (%)"));
    await userEvent.type(within(dialog).getByLabelText("Commission rate (%)"), "0.02");
```

- [ ] **Step 3: Run focused modal tests and verify they fail**

Run:

```bash
uv run npm --prefix frontend/paper-trading test -- edit-account-fees-modal.test.tsx accounts-page.test.tsx
```

Expected: FAIL because the modal still labels and stores rate inputs as backend decimal strings.

- [ ] **Step 4: Implement modal percent display and decimal save conversion**

In `frontend/paper-trading/features/accounts/edit-account-fees-modal.tsx`, replace `feeFields` with:

```tsx
const feeFields = [
  { key: "commission_rate", label: "Commission rate (%)", kind: "rate" },
  { key: "min_commission", label: "Minimum commission (CNY)", kind: "money" },
  { key: "stamp_duty_rate", label: "Stamp duty rate (%)", kind: "rate" },
  { key: "transfer_fee_rate", label: "Transfer fee rate (%)", kind: "rate" }
] as const;
```

Add helpers below `isNonNegativeDecimal`:

```tsx
function decimalRateToPercent(value: string) {
  return (Number(value) * 100).toString();
}

function percentToDecimalRate(value: string) {
  return (Number(value) / 100).toString();
}

function displayValueForField(key: FeeFieldKey, value: string) {
  const field = feeFields.find((item) => item.key === key);
  return field?.kind === "rate" ? decimalRateToPercent(value) : value;
}

function apiValueForField(key: FeeFieldKey, value: string) {
  const field = feeFields.find((item) => item.key === key);
  return field?.kind === "rate" ? percentToDecimalRate(value) : value;
}
```

Update the `useEffect` form reset to display percent values for rates:

```tsx
      setFeeValues({
        commission_rate: displayValueForField("commission_rate", account.commission_rate),
        min_commission: displayValueForField("min_commission", account.min_commission),
        stamp_duty_rate: displayValueForField("stamp_duty_rate", account.stamp_duty_rate),
        transfer_fee_rate: displayValueForField("transfer_fee_rate", account.transfer_fee_rate)
      });
```

Update changed-field detection so it compares UI values to UI display baselines:

```tsx
  const hasChanges = feeFieldKeys.some((key) => {
    const trimmed = feeValues[key].trim();
    return trimmed !== "" && trimmed !== displayValueForField(key, account[key]);
  });
```

Update payload construction so changed percent fields are converted back to decimals:

```tsx
      for (const key of feeFieldKeys) {
        const trimmed = feeValues[key].trim();
        if (trimmed !== "" && trimmed !== displayValueForField(key, acct[key])) {
          input[key] = apiValueForField(key, trimmed);
        }
      }
```

Keep input `aria-label={field.label}` so the new percentage labels are accessible.

- [ ] **Step 5: Run focused tests and verify they pass**

Run:

```bash
uv run npm --prefix frontend/paper-trading test -- edit-account-fees-modal.test.tsx accounts-page.test.tsx
```

Expected: PASS for both test files.

- [ ] **Step 6: Commit Task 2**

Run:

```bash
git add frontend/paper-trading/features/accounts/edit-account-fees-modal.tsx frontend/paper-trading/features/accounts/edit-account-fees-modal.test.tsx frontend/paper-trading/features/accounts/accounts-page.test.tsx docs/superpowers/plans/2026-07-17-paper-trading-fee-rate-percent-display.md
git commit -m "feat: convert fee edit rates from percentages"
```

---

### Task 3: Final Frontend Verification

**Files:**
- Verify: `frontend/paper-trading/features/accounts/create-account-form.tsx`
- Verify: `frontend/paper-trading/features/accounts/edit-account-fees-modal.tsx`
- Verify: `frontend/paper-trading/features/accounts/accounts-page.test.tsx`
- Verify: `frontend/paper-trading/features/accounts/edit-account-fees-modal.test.tsx`

**Interfaces:**
- Consumes: completed Task 1 and Task 2 changes.
- Produces: verified frontend behavior and a clean working diff for this feature.

- [ ] **Step 1: Run focused frontend tests**

Run:

```bash
uv run npm --prefix frontend/paper-trading test -- accounts-page.test.tsx edit-account-fees-modal.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Run frontend lint or type check if available**

Inspect `frontend/paper-trading/package.json` scripts. If it has `lint`, run:

```bash
uv run npm --prefix frontend/paper-trading run lint
```

Expected: PASS. If no lint script exists, record that lint is not available and do not invent another command.

- [ ] **Step 3: Inspect diff for accidental backend or CLI changes**

Run:

```bash
git diff -- frontend/paper-trading/features/accounts/create-account-form.tsx frontend/paper-trading/features/accounts/edit-account-fees-modal.tsx frontend/paper-trading/features/accounts/accounts-page.test.tsx frontend/paper-trading/features/accounts/edit-account-fees-modal.test.tsx docs/superpowers/specs/2026-07-17-paper-trading-fee-rate-percent-display-design.md docs/superpowers/plans/2026-07-17-paper-trading-fee-rate-percent-display.md
```

Expected: diff only touches the listed frontend UI/test files and the spec/plan docs. There must be no backend API, database, CLI, or fee calculation change.

- [ ] **Step 4: Commit verification-only documentation updates if any**

If Task 3 produced only plan checkbox updates, commit them:

```bash
git add docs/superpowers/plans/2026-07-17-paper-trading-fee-rate-percent-display.md
git commit -m "docs: update fee rate percent display plan status"
```

If there are no changes after verification, do not create an empty commit.

---

## Self-Review

- Spec coverage: Task 1 covers create account labels, percent input, blank omission, and decimal API payload. Task 2 covers edit modal labels, decimal-to-percent display, percent-to-decimal save payload, unchanged detection, and blank omission. Task 3 covers verification and non-goal diff review.
- Placeholder scan: no `TBD`, `TODO`, or unspecified edge handling remains.
- Type consistency: all tasks use existing `CreateAccountInput`, `UpdateAccountFeesInput`, `Account`, `FeeFieldKey`, and existing API functions. Rate keys are unchanged.
