# Positions Unrealized Return Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Accounts Positions cost column with a clearly formatted unrealized return percentage.

**Architecture:** Keep the existing `PositionTable` and `Position` API contract. Add a small local formatter/class resolver for the return cell, then render the existing columns plus `Return` without transforming or sorting rows.

**Tech Stack:** Next.js, React, TypeScript, Testing Library, Vitest, existing CSS semantic classes.

## Global Constraints

- Calculate return as `unrealized_pnl / cost_amount * 100`.
- Exclude realized PnL.
- Render two decimal places, explicit `+` for positive values, `-` for negative values, and neutral zero.
- Render a muted em dash for zero cost, missing required valuation data, and non-finite results.
- Preserve backend row order and the compact Accounts layout.
- Do not change backend APIs, database models, sorting, or unrelated tables.

---

### Task 1: Add return-cell behavior and focused tests

**Files:**
- Modify: `frontend/paper-trading/features/trading/trading-tables.tsx:12-27`
- Test: `frontend/paper-trading/features/accounts/accounts-page.test.tsx` (append Positions display tests)

**Interfaces:**
- Consumes: existing `Position` fields `cost_amount`, `unrealized_pnl`, and `realized_pnl`; existing `DataTable` and semantic CSS classes.
- Produces: `PositionTable` columns `Symbol`, `Stock`, `Total`, `Frozen`, `Return` in that exact order.

- [ ] **Step 1: Add failing Accounts-page tests for the rendered contract**

Add tests using two mocked positions in backend order. Assert that the compact Positions table headers are exactly `Symbol`, `Stock`, `Total`, `Frozen`, `Return`, that `Cost` and `Unrealized PnL` are absent, and that the first row remains before the second row in the table body.

Add boundary positions covering:

```ts
{ cost_amount: "5000.00", unrealized_pnl: "250.00", realized_pnl: "999999.00" } // +5.00%
{ cost_amount: "4000.00", unrealized_pnl: "-100.00", realized_pnl: "-999999.00" } // -2.50%
{ cost_amount: "3000.00", unrealized_pnl: "0.00", realized_pnl: "500.00" } // 0.00%
{ cost_amount: "0.00", unrealized_pnl: "1.00" } // unavailable
{ cost_amount: "1000.00", unrealized_pnl: null } // unavailable
{ cost_amount: "not-a-number", unrealized_pnl: "1.00" } // unavailable
```

Assert positive, negative, zero, and unavailable cells have the existing scoped semantic classes: `positive`, `negative`, `default`, and `muted` respectively. Use accessible cell queries and `within` the Positions table so account-list cells do not interfere.

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `cd frontend/paper-trading && npm test -- --run features/accounts/accounts-page.test.tsx`

Expected: FAIL because the current table still renders `Cost` and `Unrealized PnL` and has no return formatting.

- [ ] **Step 3: Implement the minimal return calculation and rendering**

In `trading-tables.tsx`, add a local helper that accepts `Position` and returns either an unavailable marker or a cell object/value with formatted text and semantic class. Convert the two string inputs with `Number`, reject missing values, zero cost, non-finite inputs, and non-finite division results, and calculate only `unrealizedPnl / cost * 100`.

Format valid values with `toFixed(2)`, prefix `+` when the numeric result is greater than zero, append `%`, and use neutral text for zero. Render the unavailable case as a muted em dash. Replace the Cost and Unrealized PnL columns with one right-aligned `Return` column. Keep `positions` directly as `rows` so API order is unchanged.

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `cd frontend/paper-trading && npm test -- --run features/accounts/accounts-page.test.tsx`

Expected: PASS, including the new column, calculation, formatting, semantic states, boundary handling, order, and compact-layout assertions.

- [ ] **Step 5: Run frontend typecheck/build validation**

Run: `cd frontend/paper-trading && npm run lint && npm run build`

Expected: PASS with no TypeScript, lint, or production-build errors.

- [ ] **Step 6: Commit the implementation**

```bash
git add frontend/paper-trading/features/trading/trading-tables.tsx frontend/paper-trading/features/accounts/accounts-page.test.tsx
git commit -m "feat: show unrealized return in positions"
```

### Task 2: Repository-level review and verification

**Files:**
- Review: `frontend/paper-trading/features/trading/trading-tables.tsx`
- Review: `frontend/paper-trading/features/accounts/accounts-page.test.tsx`
- Review: `docs/superpowers/specs/2026-08-22-positions-unrealized-return-design.md`

**Interfaces:**
- Consumes: Task 1's `PositionTable` behavior and focused test evidence.
- Produces: verified issue #80 implementation with no unrelated changes.

- [ ] **Step 1: Inspect the final diff and check scope**

Run: `git diff HEAD~1 -- frontend/paper-trading/features/trading/trading-tables.tsx frontend/paper-trading/features/accounts/accounts-page.test.tsx`

Confirm the diff does not reorder rows, include realized PnL, alter API types, or change unrelated tables.

- [ ] **Step 2: Run the project frontend test suite**

Run: `cd frontend/paper-trading && npm test -- --run`

Expected: PASS for all frontend tests.

- [ ] **Step 3: Run simplify review before completion**

Inspect whether the helper and tests can be made clearer without changing behavior or broadening scope. Apply only a targeted simplification if it removes duplication or ambiguity, then rerun the focused tests.

- [ ] **Step 4: Run final status check**

Run: `git status --short`

Confirm only intended issue #80 files and the explicitly tracked design/plan documentation are present.
