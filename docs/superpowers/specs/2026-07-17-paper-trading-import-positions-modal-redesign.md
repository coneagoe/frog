# Paper Trading Import Positions Modal Redesign

## Goal

Redesign the existing Paper Trading Accounts page `Import positions` modal so it feels like a coherent import workspace instead of a rough form.

The redesign must fix the current usability defects:

- table headers and row inputs are not aligned;
- the date input has no visible format guidance;
- the modal as a whole lacks clear hierarchy, spacing, and import-specific guidance.

## Scope

This design covers only the existing import positions modal in the paper trading frontend.

In scope:

- modal header, explanation, and import rules;
- editable positions table layout;
- field labels, placeholders, helper text, and error placement;
- add/remove row affordances;
- footer summary and submit/cancel actions;
- responsive behavior for narrower screens;
- frontend tests affected by the modal structure and wording.

Out of scope:

- backend API changes;
- CSV upload or broker synchronization;
- changing account selection or Accounts page main layout;
- changing import semantics, cash behavior, or repeated-import rules.

## Current Context

Relevant files:

- `frontend/paper-trading/features/accounts/import-positions-modal.tsx`
- `frontend/paper-trading/features/accounts/accounts-page.tsx`
- `frontend/paper-trading/features/accounts/import-positions-modal.test.tsx`
- `frontend/paper-trading/features/accounts/accounts-page.test.tsx`
- `frontend/paper-trading/app/globals.css`

The modal already submits through `importPositions(account.id, { positions })` and the Accounts page refreshes selected-account state after success. The redesign should preserve this behavior.

## Recommended Approach

Use a structured "import workspace" modal.

The modal should have four clear zones:

1. **Header:** title, selected account context, close control.
2. **Guidance strip:** concise import semantics before the form.
3. **Aligned edit grid:** one grid template shared by table header and every row.
4. **Footer:** row count / validation status on the left, cancel/import actions on the right.

This approach is preferred because it directly fixes the alignment and date-format issues while keeping the workflow fast for desktop users entering multiple holdings.

## Visual and Interaction Design

### Header

Title: `Import initial positions`.

Supporting copy: `Set starting holdings for this account. Cash will not change.`

If the selected account name is available in the modal props, show it as small context text. If not, do not add extra data plumbing just for this redesign.

### Guidance Strip

Show a compact note near the top of the modal, before the editable grid:

- `Use this once for an empty account.`
- `Lots with the same symbol are allowed.`
- `Importing positions does not add or remove cash.`

The strip should read as operational guidance, not marketing copy.

### Editable Grid

Use a single CSS grid template for the header and each editable row so column labels and controls align exactly.

Suggested desktop columns:

```text
symbol | name/optional note | quantity | cost price | buy date | action
```

If the current data model does not include a stock-name field, do not add one. Use the second column only if it already exists; otherwise use:

```text
symbol | quantity | cost price | buy date | action
```

The same template must be applied to both:

- the header row;
- each editable position row.

Avoid separate table-header and form-row structures that rely on independent widths.

### Date Input

The buy date field must visibly communicate the required format.

Preferred implementation:

- keep a text input for stable display and tests;
- set `placeholder="YYYY-MM-DD"`;
- add `inputMode` or `pattern` only if it does not interfere with existing validation tests;
- keep validation strict for `YYYY-MM-DD`.

Avoid browser-native date display if it causes locale-specific formatting or inconsistent screenshots/tests.

### Error Handling

Keep the modal open on all validation or request errors.

Use two levels of error display:

- form-level error above the grid for request failures or whole-form validation;
- row/field-local feedback only if the existing component structure already supports it simply.

Do not clear user input after errors.

For the known existing-position backend rejection, keep concise wording:

`This account already has positions. Import is only available for empty accounts.`

### Footer

Footer left side:

- row count such as `3 rows ready` when rows are complete;
- or a neutral hint such as `Complete each row before importing`.

Footer right side:

- secondary `Cancel` button;
- primary `Import positions` button.

When submitting, the primary action should show the existing loading/submitting state and remain disabled as appropriate.

## Responsive Behavior

On desktop and tablet widths, keep the grid aligned horizontally.

On narrow mobile widths, switch each row to a compact card-like layout where labels sit above inputs. This mobile fallback may sacrifice horizontal column alignment because desktop alignment is the primary reported defect.

The modal must remain scrollable if the row list grows beyond the viewport.

## Accessibility

- Preserve dialog semantics already present in the modal.
- Ensure every input keeps an accessible label.
- Keep visible focus states for close, add/remove, cancel, and submit controls.
- Associate validation text with fields or the form where practical.
- Do not rely on placeholder text as the only accessible label for the date field.

## Testing

Update or add frontend tests for:

- the modal renders the import guidance copy;
- the date input shows `YYYY-MM-DD` guidance;
- table/grid headers and rows use the redesigned structure;
- add/remove row behavior still works;
- local validation still prevents bad payloads;
- successful import still submits the existing API payload, closes the modal, and refreshes account data;
- backend errors still keep the modal open and preserve input.

Recommended focused commands:

```bash
cd frontend/paper-trading && npm run test -- features/accounts/import-positions-modal.test.tsx
cd frontend/paper-trading && npm run test -- features/accounts/accounts-page.test.tsx
```

Run broader frontend tests if the modal CSS changes shared classes used by other pages.

## Non-Goals

- No backend schema changes.
- No CSV, paste, or broker import.
- No change to import payload shape.
- No change to account cash behavior.
- No redesign of the full Accounts page outside the modal trigger and modal integration.

## Self-Review

- No unresolved placeholders remain.
- Scope is limited to the existing modal and affected tests.
- The alignment fix is explicit: one shared grid template for headers and rows.
- The date-format fix is explicit: visible `YYYY-MM-DD` guidance while preserving accessible labels.
- The design preserves existing API behavior and backend semantics.
