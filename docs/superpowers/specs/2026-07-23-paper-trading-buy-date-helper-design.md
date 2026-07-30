# Paper trading buy-date helper cleanup

## Goal

Simplify the Buy date input in the Accounts page’s Import positions dialog by removing duplicated date-format guidance.

## Scope

- Remove the visible `YYYY-MM-DD` helper beneath the Buy date input in `ImportPositionsModal`.
- Keep the input placeholder as `YYYY-MM-DD`.
- Keep the existing accessible label and `YYYY-MM-DD` validation behavior unchanged.
- Update the focused modal test so it verifies the retained placeholder without expecting the removed helper.

## Out of scope

- Changes to the import grid layout, desktop column headers, responsive mobile labels, or styles.
- Changes to date parsing, validation messages, API payloads, or import behavior.

## Success criteria

The Buy date field displays `YYYY-MM-DD` once, inside the empty input. No date-format helper is rendered underneath it, and the focused import-position modal test passes.
