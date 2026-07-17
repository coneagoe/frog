# Paper Trading Fee Rate Percent Display Design

## Goal

Make paper trading account fee rate inputs easier to understand by displaying and accepting percentage values in the frontend, while keeping the backend API contract unchanged. The backend continues to store and calculate rates as decimal fractions.

## Current Behavior

The account creation form and the edit fees modal currently show rate fields as raw decimal values:

- `commission_rate`: `0.0003`
- `stamp_duty_rate`: `0.0005`
- `transfer_fee_rate`: `0.00001`

The backend uses these values directly in fee calculations, multiplying trade amount by the stored decimal rate. For example, `0.0003` means `0.03%`.

## Scope

This change covers the frontend paper trading accounts UI only:

- `Create Account` card fee fields.
- `Edit fees` modal fee fields.
- Frontend tests for account creation and fee editing.

The backend API, database schema, CLI, fee calculation logic, and persisted values remain unchanged.

## User Interface

The three rate fields will be labeled as percentage inputs:

- `Commission rate (%)`
- `Stamp duty rate (%)`
- `Transfer fee rate (%)`

`Minimum commission (CNY)` remains unchanged because it is a currency amount, not a rate.

The UI may include concise helper text stating that rate fields are entered as percentages and are converted before saving.

## Conversion Rules

When reading backend account data into the frontend form, decimal rates are multiplied by 100 for display:

- backend `0.0003` -> UI `0.03`
- backend `0.0005` -> UI `0.05`
- backend `0.00001` -> UI `0.001`

When submitting create or edit requests, percentage inputs are divided by 100 before sending to the API:

- UI `0.03` -> API `0.0003`
- UI `0.05` -> API `0.0005`
- UI `0.001` -> API `0.00001`

Blank optional rate inputs remain blank and are omitted from the API payload where the existing form behavior already omits blank values.

## Validation

Frontend validation remains non-negative numeric validation. Error messages should refer to fee settings or percentage rate fields clearly enough that users know negative percentage inputs are invalid.

## Testing

Update frontend account tests to verify:

- Create account fields use percentage labels.
- Default create account rate values or placeholders display percentage values.
- Creating an account with percentage rate inputs sends decimal rate strings to the API.
- Editing fees displays backend decimal values as percentages.
- Saving edited percentage values sends decimal rate strings to the API.
- Existing validation and unchanged-field behavior still works.

## Non-Goals

- No backend API contract change.
- No database migration.
- No change to CLI input semantics.
- No change to fee calculation logic.
