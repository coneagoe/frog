# Paper Trading Import Positions Modal Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Paper Trading Accounts `Import positions` modal into a structured import workspace with aligned columns, visible date-format guidance, clearer copy, and preserved import behavior.

**Architecture:** Keep the existing `ImportPositionsModal` component and API flow. Replace the current HTML table with semantic grid-based row groups so the header and editable rows share one CSS grid template, then add modal-specific CSS classes in `app/globals.css` without changing backend or account-page data flow.

**Tech Stack:** Next.js 15, React 19, TypeScript, Vitest, Testing Library, global CSS in `frontend/paper-trading/app/globals.css`.

## Global Constraints

- Scope is limited to the existing import positions modal and affected frontend tests.
- No backend schema changes.
- No CSV, paste, or broker import.
- No change to import payload shape.
- No change to account cash behavior.
- No redesign of the full Accounts page outside the modal trigger and modal integration.
- The alignment fix must use one shared grid template for headers and rows.
- The date-format fix must provide visible `YYYY-MM-DD` guidance while preserving accessible labels.
- Keep strict `YYYY-MM-DD` validation.
- Use project command conventions: frontend commands run from `frontend/paper-trading`; Python repo commands, if needed, must use `uv run`.

---

## File Structure

- Modify `frontend/paper-trading/features/accounts/import-positions-modal.tsx`
  - Owns modal state, validation, submission, accessible labels, copy, and redesigned JSX structure.
- Modify `frontend/paper-trading/app/globals.css`
  - Owns modal workspace layout, aligned import grid, guidance strip, footer summary, responsive fallback.
- Modify `frontend/paper-trading/features/accounts/import-positions-modal.test.tsx`
  - Covers modal copy, date placeholder, grid structure, validation, row behavior, payload, and backend error handling.

No new source files are required.

---

### Task 1: Lock in modal UX tests

**Files:**
- Modify: `frontend/paper-trading/features/accounts/import-positions-modal.test.tsx`
- Test: `frontend/paper-trading/features/accounts/import-positions-modal.test.tsx`

**Interfaces:**
- Consumes: existing `ImportPositionsModal` props: `{ account, open, onClose, onImported }`.
- Produces: failing tests that require the redesigned heading, guidance copy, date placeholder, and grid row structure.

- [ ] **Step 1: Update title and guidance tests**

Replace the existing title/note tests near the top of `import-positions-modal.test.tsx` with these tests:

```tsx
  it("shows the import workspace title and selected account context", () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    expect(screen.getByRole("dialog", { name: "Import initial positions for demo" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Import initial positions" })).toBeInTheDocument();
    expect(screen.getByText("Account: demo")).toBeInTheDocument();
  });

  it("shows concise import guidance before the editable grid", () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    expect(screen.getByText("Set starting holdings for this account. Cash will not change.")).toBeInTheDocument();
    expect(screen.getByText("Use this once for an empty account.")).toBeInTheDocument();
    expect(screen.getByText("Lots with the same symbol are allowed.")).toBeInTheDocument();
    expect(screen.getByText("Importing positions does not add or remove cash.")).toBeInTheDocument();
  });
```

Remove the old tests named:

```tsx
it("shows the title Import positions for demo", ...)
it("shows the note that import is one-time and does not change cash", ...)
it("shows the visible heading Import positions for demo", ...)
```

- [ ] **Step 2: Add date guidance and grid structure tests**

Add these tests after `starts with one editable row`:

```tsx
  it("shows visible YYYY-MM-DD guidance on the buy date input", () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    expect(screen.getByLabelText("Buy trade date")).toHaveAttribute("placeholder", "YYYY-MM-DD");
    expect(screen.getByText("YYYY-MM-DD")).toBeInTheDocument();
  });

  it("renders one aligned import grid header and row", () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    const grid = screen.getByTestId("import-positions-grid");
    expect(within(grid).getByText("Symbol")).toBeInTheDocument();
    expect(within(grid).getByText("Quantity")).toBeInTheDocument();
    expect(within(grid).getByText("Cost price")).toBeInTheDocument();
    expect(within(grid).getByText("Buy date")).toBeInTheDocument();
    expect(within(grid).getAllByTestId("import-position-row")).toHaveLength(1);
  });
```

- [ ] **Step 3: Update dialog-name references in existing tests**

Replace all existing test lookups using:

```tsx
screen.getByRole("dialog", { name: "Import positions for demo" })
```

with:

```tsx
screen.getByRole("dialog", { name: "Import initial positions for demo" })
```

- [ ] **Step 4: Add footer summary test**

Add this test after the add-row test:

```tsx
  it("updates the footer row count as rows are added", async () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    expect(screen.getByText("1 row ready for input")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add row" }));
    expect(screen.getByText("2 rows ready for input")).toBeInTheDocument();
  });
```

- [ ] **Step 5: Run tests to verify they fail for the expected reasons**

Run:

```bash
cd frontend/paper-trading && npm run test -- features/accounts/import-positions-modal.test.tsx
```

Expected: FAIL because the current modal still uses the old title/copy, lacks `data-testid="import-positions-grid"`, lacks `data-testid="import-position-row"`, and lacks the `YYYY-MM-DD` placeholder/helper text.

- [ ] **Step 6: Commit failing tests**

```bash
git add frontend/paper-trading/features/accounts/import-positions-modal.test.tsx
git commit -m "test: cover import positions modal redesign"
```

---

### Task 2: Redesign the modal component structure

**Files:**
- Modify: `frontend/paper-trading/features/accounts/import-positions-modal.tsx`
- Test: `frontend/paper-trading/features/accounts/import-positions-modal.test.tsx`

**Interfaces:**
- Consumes: tests from Task 1; existing `importPositions(account.id, { positions })` helper.
- Produces: JSX classes and test IDs used by CSS and tests:
  - `.import-modal`
  - `.import-modal__intro`
  - `.import-modal__rules`
  - `.import-grid`
  - `.import-grid__header`
  - `.import-grid__row`
  - `.import-grid__field`
  - `.import-modal__grid-actions`
  - `.import-modal__footer-note`
  - `data-testid="import-positions-grid"`
  - `data-testid="import-position-row"`

- [ ] **Step 1: Add a row-count helper**

In `import-positions-modal.tsx`, add this helper below `removeRow`:

```tsx
  const rowSummary = `${rows.length} ${rows.length === 1 ? "row" : "rows"} ready for input`;
```

- [ ] **Step 2: Replace modal label and header JSX**

In the returned JSX, change the dialog label and header from:

```tsx
        aria-label={"Import positions for " + account.name}
      >
        <div className="modal__header">
          <h2>Import positions for {account.name}</h2>
        </div>
```

to:

```tsx
        aria-label={"Import initial positions for " + account.name}
      >
        <div className="modal__header import-modal__header">
          <div>
            <p className="import-modal__eyebrow">Account: {account.name}</p>
            <h2>Import initial positions</h2>
            <p className="import-modal__intro">Set starting holdings for this account. Cash will not change.</p>
          </div>
        </div>
```

- [ ] **Step 3: Replace the table body with the grid workspace**

Replace the whole current `modal__body` content from `<table className="form">` through the current note/error block with this JSX:

```tsx
          <div className="modal__body import-modal__body">
            <div className="import-modal__rules" aria-label="Import rules">
              <span>Use this once for an empty account.</span>
              <span>Lots with the same symbol are allowed.</span>
              <span>Importing positions does not add or remove cash.</span>
            </div>

            {error ? (
              <div role="alert" className="error-banner">
                {error}
              </div>
            ) : null}

            <div className="import-grid" data-testid="import-positions-grid">
              <div className="import-grid__header" aria-hidden="true">
                <span>Symbol</span>
                <span>Quantity</span>
                <span>Cost price</span>
                <span>Buy date</span>
                <span>Action</span>
              </div>

              {rows.map((row, index) => (
                <div className="import-grid__row" data-testid="import-position-row" key={index}>
                  <label className="import-grid__field">
                    <span>Symbol</span>
                    <input
                      aria-label="Symbol"
                      autoComplete="off"
                      placeholder="000001"
                      value={row.symbol}
                      onChange={(e) => updateRow(index, "symbol", e.target.value)}
                    />
                  </label>

                  <label className="import-grid__field">
                    <span>Quantity</span>
                    <input
                      aria-label="Quantity"
                      inputMode="numeric"
                      placeholder="100"
                      value={row.quantity}
                      onChange={(e) => updateRow(index, "quantity", e.target.value)}
                    />
                  </label>

                  <label className="import-grid__field">
                    <span>Cost price</span>
                    <input
                      aria-label="Cost price"
                      inputMode="decimal"
                      placeholder="10.23"
                      value={row.cost_price}
                      onChange={(e) => updateRow(index, "cost_price", e.target.value)}
                    />
                  </label>

                  <label className="import-grid__field">
                    <span>Buy date</span>
                    <input
                      aria-label="Buy trade date"
                      inputMode="numeric"
                      placeholder="YYYY-MM-DD"
                      value={row.buy_trade_date}
                      onChange={(e) => updateRow(index, "buy_trade_date", e.target.value)}
                    />
                    <small>YYYY-MM-DD</small>
                  </label>

                  <div className="import-grid__action">
                    <button type="button" aria-label="Remove row" onClick={() => removeRow(index)}>
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <div className="import-modal__grid-actions">
              <button className="button button--secondary" type="button" onClick={addRow}>
                Add row
              </button>
            </div>
          </div>
```

- [ ] **Step 4: Replace footer JSX with summary plus actions**

Replace the existing footer block with:

```tsx
          <div className="modal__footer import-modal__footer">
            <p className="import-modal__footer-note">{rowSummary}</p>
            <div className="import-modal__footer-actions">
              <button className="button button--secondary" onClick={onClose} type="button">
                Cancel
              </button>
              <button className="button" disabled={submitting} type="submit">
                {submitting ? "Importing…" : "Import positions"}
              </button>
            </div>
          </div>
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd frontend/paper-trading && npm run test -- features/accounts/import-positions-modal.test.tsx
```

Expected: tests may still FAIL visually unrelated CSS assertions are absent, but behavior tests should pass once JSX is correct. If Testing Library reports multiple `YYYY-MM-DD` matches for `getByText`, change the test assertion from `screen.getByText("YYYY-MM-DD")` to `screen.getByText("YYYY-MM-DD", { selector: "small" })`.

- [ ] **Step 6: Commit component redesign**

```bash
git add frontend/paper-trading/features/accounts/import-positions-modal.tsx frontend/paper-trading/features/accounts/import-positions-modal.test.tsx
git commit -m "feat: restructure import positions modal"
```

---

### Task 3: Add modal workspace styling

**Files:**
- Modify: `frontend/paper-trading/app/globals.css`
- Test: `frontend/paper-trading/features/accounts/import-positions-modal.test.tsx`

**Interfaces:**
- Consumes: class names produced in Task 2.
- Produces: aligned desktop grid and mobile card fallback.

- [ ] **Step 1: Widen the modal safely for the import workspace**

In `globals.css`, change `.modal` from:

```css
.modal {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 14px;
  max-height: 90vh;
  max-width: 480px;
  overflow-y: auto;
  padding: 0;
  width: 100%;
}
```

to:

```css
.modal {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 14px;
  max-height: 90vh;
  max-width: 760px;
  overflow-y: auto;
  padding: 0;
  width: min(100%, calc(100vw - 32px));
}
```

- [ ] **Step 2: Add import modal CSS after `.modal__note`**

Add this CSS after the existing `.modal__note` block:

```css
.import-modal__header {
  align-items: flex-start;
}

.import-modal__eyebrow {
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  margin: 0 0 6px;
  text-transform: uppercase;
}

.import-modal__intro {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.5;
  margin: 6px 0 0;
}

.import-modal__body {
  display: grid;
  gap: 14px;
}

.import-modal__rules {
  background: rgba(56, 189, 248, 0.08);
  border: 1px solid rgba(56, 189, 248, 0.28);
  border-radius: 12px;
  color: #bae6fd;
  display: grid;
  gap: 8px;
  padding: 12px;
}

.import-modal__rules span {
  line-height: 1.4;
}

.import-grid {
  display: grid;
  gap: 8px;
  overflow-x: auto;
}

.import-grid__header,
.import-grid__row {
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(120px, 1fr) minmax(100px, 0.8fr) minmax(120px, 0.9fr) minmax(150px, 1fr) minmax(88px, auto);
  min-width: 660px;
}

.import-grid__header {
  color: var(--muted);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  padding: 0 2px;
  text-transform: uppercase;
}

.import-grid__row {
  align-items: start;
  background: rgba(31, 41, 55, 0.72);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px;
}

.import-grid__field {
  display: grid;
  gap: 6px;
}

.import-grid__field > span {
  display: none;
}

.import-grid__field small {
  color: var(--muted);
  font-size: 11px;
}

.import-grid__field input {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  color: var(--text);
  min-width: 0;
  padding: 10px 12px;
  width: 100%;
}

.import-grid__field input::placeholder {
  color: #64748b;
}

.import-grid__action {
  display: flex;
  justify-content: flex-end;
}

.import-grid__action button {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 10px;
  color: var(--muted);
  cursor: pointer;
  padding: 10px 12px;
}

.import-grid__action button:hover,
.import-grid__action button:focus-visible {
  border-color: var(--danger);
  color: #fecaca;
}

.import-modal__grid-actions {
  display: flex;
  justify-content: flex-start;
}

.import-modal__footer {
  align-items: center;
  justify-content: space-between;
}

.import-modal__footer-note {
  color: var(--muted);
  font-size: 13px;
  margin: 0;
}

.import-modal__footer-actions {
  display: flex;
  gap: 10px;
}
```

- [ ] **Step 3: Add mobile fallback CSS inside the existing max-width media query**

Inside `@media (max-width: 760px)`, after the `.table { min-width: 640px; }` block, add:

```css
  .modal {
    max-height: 92vh;
    width: calc(100vw - 24px);
  }

  .import-grid__header {
    display: none;
  }

  .import-grid__row {
    gap: 12px;
    grid-template-columns: 1fr;
    min-width: 0;
  }

  .import-grid__field > span {
    color: var(--muted);
    display: block;
    font-size: 12px;
    font-weight: 700;
  }

  .import-grid__action {
    justify-content: flex-start;
  }

  .import-modal__footer {
    align-items: stretch;
    flex-direction: column;
  }

  .import-modal__footer-actions {
    justify-content: flex-end;
  }
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
cd frontend/paper-trading && npm run test -- features/accounts/import-positions-modal.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit styling**

```bash
git add frontend/paper-trading/app/globals.css
git commit -m "style: align import positions modal grid"
```

---

### Task 4: Verify account-page integration and regressions

**Files:**
- Test: `frontend/paper-trading/features/accounts/accounts-page.test.tsx`
- Test: `frontend/paper-trading/features/accounts/import-positions-modal.test.tsx`

**Interfaces:**
- Consumes: redesigned modal from Tasks 2-3.
- Produces: confidence that existing Accounts page import trigger, success handling, and refresh behavior still work.

- [ ] **Step 1: Run modal tests**

```bash
cd frontend/paper-trading && npm run test -- features/accounts/import-positions-modal.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Run accounts page tests**

```bash
cd frontend/paper-trading && npm run test -- features/accounts/accounts-page.test.tsx
```

Expected: PASS. If failures only reference the old accessible dialog name `Import positions for demo`, update those test queries to `Import initial positions for demo` without changing production behavior.

- [ ] **Step 3: Run full frontend test suite**

```bash
cd frontend/paper-trading && npm run test
```

Expected: PASS.

- [ ] **Step 4: Run frontend lint if dependencies are installed**

```bash
cd frontend/paper-trading && npm run lint
```

Expected: PASS. If lint cannot run because dependencies are not installed, stop and report the missing dependency error exactly.

- [ ] **Step 5: Commit final verification adjustments if any were needed**

If Task 4 required test-only updates, commit them:

```bash
git add frontend/paper-trading/features/accounts/accounts-page.test.tsx frontend/paper-trading/features/accounts/import-positions-modal.test.tsx
git commit -m "test: update import positions modal integration expectations"
```

If no files changed in Task 4, do not create an empty commit.

---

## Self-Review

- Spec coverage: Tasks 1-3 cover header/copy, guidance strip, aligned grid, date placeholder/helper text, error placement, footer summary/actions, and responsive fallback. Task 4 covers regression verification.
- Placeholder scan: no `TBD`, `TODO`, or unspecified implementation steps remain.
- Type consistency: component props and API payload shape remain unchanged; new class names and test IDs are defined in Task 2 and consumed in Task 3/tests.
- Scope check: no backend, CSV, account-page layout, or cash behavior changes are included.
