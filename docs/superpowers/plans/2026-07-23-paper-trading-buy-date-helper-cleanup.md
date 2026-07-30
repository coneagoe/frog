# Paper Trading Buy-Date Helper Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the redundant visible date-format helper from the Import positions dialog’s Buy date field while retaining its placeholder and validation.

**Architecture:** This is a presentation-only change in the existing `ImportPositionsModal` row markup. The focused Vitest component test will change from expecting duplicate guidance to asserting the input retains its one, in-field placeholder and no `<small>` helper is rendered.

**Tech Stack:** Next.js 15, React 19, TypeScript, Vitest, React Testing Library.

## Global Constraints

- Keep the Buy date input placeholder exactly `YYYY-MM-DD`.
- Keep the `aria-label="Buy trade date"` and existing `YYYY-MM-DD` validation behavior unchanged.
- Do not modify import-grid layout, desktop headers, mobile labels, styles, API payloads, or validation messages.
- Run frontend commands from `frontend/paper-trading`.

---

## File Structure

- Modify `frontend/paper-trading/features/accounts/import-positions-modal.tsx`: remove the redundant `<small>` helper beneath the Buy date input.
- Modify `frontend/paper-trading/features/accounts/import-positions-modal.test.tsx`: verify the retained placeholder and absence of the helper.

### Task 1: Remove duplicate Buy date guidance

**Files:**
- Modify: `frontend/paper-trading/features/accounts/import-positions-modal.test.tsx:45-50`
- Modify: `frontend/paper-trading/features/accounts/import-positions-modal.tsx:197-206`

**Interfaces:**
- Consumes: `ImportPositionsModal` renders a date input labeled `Buy trade date`.
- Produces: The Buy date field exposes only its `YYYY-MM-DD` placeholder as format guidance; all existing input props and event handling remain intact.

- [ ] **Step 1: Change the focused test to describe the intended single source of guidance**

Replace the test at `import-positions-modal.test.tsx:45-50` with:

```tsx
  it("shows YYYY-MM-DD guidance only in the buy date input", () => {
    render(<ImportPositionsModal account={demoAccount} open onClose={vi.fn()} onImported={vi.fn()} />);

    expect(screen.getByLabelText("Buy trade date")).toHaveAttribute("placeholder", "YYYY-MM-DD");
    expect(screen.queryByText("YYYY-MM-DD", { selector: "small" })).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the targeted test to verify it fails before the markup change**

Run: `npm test -- --run features/accounts/import-positions-modal.test.tsx`

Expected: FAIL in `shows YYYY-MM-DD guidance only in the buy date input`, because a `<small>YYYY-MM-DD</small>` element is still rendered.

- [ ] **Step 3: Remove only the redundant helper element**

In the Buy date field in `import-positions-modal.tsx`, retain the input unchanged and delete the visible helper:

```tsx
                  <label className="import-grid__field">
                    <span>Buy date</span>
                    <input
                      aria-label="Buy trade date"
                      placeholder="YYYY-MM-DD"
                      value={row.buy_trade_date}
                      onChange={(e) => updateRow(index, "buy_trade_date", e.target.value)}
                    />
                  </label>
```

- [ ] **Step 4: Run the targeted test to verify the cleanup**

Run: `npm test -- --run features/accounts/import-positions-modal.test.tsx`

Expected: PASS, including the changed Buy date guidance assertion and all existing import-modal tests.

- [ ] **Step 5: Run the scoped frontend linter**

Run: `npm run lint`

Expected: exit code 0 with no ESLint errors.

- [ ] **Step 6: Commit the focused change when explicitly requested and the working tree is safe to stage**

Run:

```bash
git add frontend/paper-trading/features/accounts/import-positions-modal.tsx frontend/paper-trading/features/accounts/import-positions-modal.test.tsx
git commit -m "fix(paper-trading): remove duplicate buy date guidance"
```

Expected: a commit containing only the two intended frontend files. Do not stage unrelated workspace changes.

## Plan Self-Review

- **Spec coverage:** Task 1 removes the helper, preserves the exact placeholder and accessibility label, avoids all out-of-scope layout/style/behavior changes, and validates the focused component behavior.
- **Placeholder scan:** No TBDs, generic implementation instructions, or unspecified test behavior remain.
- **Consistency:** Both test and implementation use the existing `Buy trade date` accessible label and exact `YYYY-MM-DD` placeholder.
