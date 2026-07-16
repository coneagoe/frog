# Paper Trading Fee Edit Frontend Design

## Goal

Add frontend support for updating fee fields on existing paper trading accounts.

Users should be able to review the selected account's current fee configuration, edit one or more fee fields, save the changes through the existing paper trading API proxy, and see the refreshed account values after a successful update.

## Scope

This design covers the paper trading frontend account flow only.

It adds UI and client support for:

- opening a fee edit form from the Accounts page;
- pre-filling the form from the selected account;
- submitting changed fee fields to `PATCH /paper/accounts/{account_id}`;
- displaying validation and request errors;
- refreshing account data after a successful update.

It does not change order, trade, matching, snapshot, analytics, backend schema, or historical recalculation behavior.

## Current Frontend Context

The Accounts page is rendered by:

- `frontend/paper-trading/app/accounts/page.tsx`
- `frontend/paper-trading/features/accounts/accounts-page.tsx`

Current account functionality includes create, list, select, view details, and delete. Account creation already supports fee fields through `create-account-form.tsx`, and account responses already include:

- `fee_preset`
- `commission_rate`
- `min_commission`
- `stamp_duty_rate`
- `transfer_fee_rate`

The frontend does not yet have an edit account flow or an API client helper for `PATCH /paper/accounts/{account_id}`.

## User Experience

Use a modal dialog for editing fees.

The primary entry point should be the selected account detail header on the Accounts page. This keeps the action tied to the account currently being inspected and avoids crowding the account list. A row-level list action can be added later if the page needs faster multi-account operations.

The button label should be concise, for example `Edit fees`.

When clicked, the modal opens with fields pre-filled from the selected `Account` object:

- `commission_rate`
- `min_commission`
- `stamp_duty_rate`
- `transfer_fee_rate`

The modal should also show a short note: fee changes affect future orders and trades only; existing trades, cash ledger entries, and snapshots are not recalculated.

## Form Behavior

The form allows partial updates.

On submit, the frontend compares current input values with the account values used to open the modal and sends only changed fields. If no fields changed, the save action should be disabled or the form should show a clear no-change message without sending an empty request.

Field validation should be lightweight and match the API contract:

- values must be valid decimals;
- values must be non-negative;
- empty strings are not submitted as updates.

The backend remains the final source of validation. If the backend returns a validation error, the modal stays open and displays the error without clearing the user's inputs.

## API Client Contract

Add a frontend API helper in `frontend/paper-trading/lib/api-client.ts`:

```ts
updateAccountFees(accountId: number, input: UpdateAccountFeesInput): Promise<Account>
```

The helper sends:

```http
PATCH /paper/accounts/{account_id}
```

The request body supports only these optional string decimal fields:

```ts
{
  commission_rate?: string
  min_commission?: string
  stamp_duty_rate?: string
  transfer_fee_rate?: string
}
```

`fee_preset` must not be included in the update payload.

Add a matching `UpdateAccountFeesInput` type in `frontend/paper-trading/lib/types.ts`. It should reuse the same fee field names as `Account` and `CreateAccountInput` to avoid introducing a separate naming model.

## Data Flow

1. The user selects an account on the Accounts page.
2. The user clicks `Edit fees` in the selected account detail header.
3. The modal form initializes from the selected `Account` values.
4. The user edits one or more fee fields.
5. The form builds a payload containing only changed fields.
6. The frontend calls `updateAccountFees(account.id, payload)`.
7. On success, the modal closes.
8. The Accounts page refreshes account data so the detail view and list fee summary show the updated values.

The response from `PATCH /paper/accounts/{account_id}` is the updated account. The page may use that response immediately, but it should still refresh or reconcile the account list so all rendered summaries stay consistent.

## Error Handling

The modal should remain open on failure.

Expected error cases:

- no changed fields: handled client-side without sending a request;
- invalid decimal or negative value: show a field-level or form-level validation message;
- backend `422`: show the server validation message in the modal;
- backend `404`: show the existing not-found error shape and let the user close the modal or refresh the page;
- network/proxy errors: show a form-level request error.

Errors must not clear user input.

## Testing

Add focused frontend tests for:

- the Accounts page shows an `Edit fees` action for the selected account;
- opening the modal pre-fills current fee values;
- submitting changed values calls `PATCH /paper/accounts/{account_id}` with only changed fields;
- unchanged forms do not send an empty PATCH payload;
- successful updates close the modal and refresh/reconcile account data;
- validation or server errors keep the modal open and display the error.

Existing create, delete, select, and detail loading tests should continue to pass.

## Non-Goals

- No support for editing `fee_preset` after account creation.
- No historical fee recalculation.
- No changes to order, trade, matching, snapshot, or analytics pages.
- No reusable fee profile management UI.
- No account edits beyond fee fields.
