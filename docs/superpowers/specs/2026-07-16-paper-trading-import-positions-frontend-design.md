# Paper Trading Import Positions Frontend Design

## Goal

Add frontend support for importing existing stock holdings into a paper trading account.

Users should be able to select a paper trading account, manually enter one or more existing stock positions, submit them through the existing paper trading API proxy, and see the refreshed account holdings after a successful import.

## Scope

This design covers the paper trading frontend account flow only.

It adds UI and client support for:

- opening an import positions form from the Accounts page;
- manually entering stock holdings in a small editable table;
- submitting holdings to `POST /api/paper/accounts/{account_id}/positions/import`;
- displaying validation and request errors;
- refreshing selected account state after a successful import.

It does not add CSV upload, broker synchronization, backend import behavior, order, trade, matching, snapshot, or analytics changes.

## Current Frontend Context

The Accounts page is rendered by:

- `frontend/paper-trading/app/accounts/page.tsx`
- `frontend/paper-trading/features/accounts/accounts-page.tsx`

The selected account workspace already loads and renders:

- account details;
- positions through `listPositions(accountId)`;
- cash ledger through `listCashLedger(accountId)`;
- account creation and fee editing controls.

Browser requests should continue to go through the Next.js proxy at `/api/paper/*`. The proxy forwards requests to the backend `/paper/*` routes and injects the backend bearer token.

## User Experience

Use a modal dialog for manual import.

The primary entry point should be the selected account detail or positions area on the Accounts page. The action should be visible only when an account is selected, because the import endpoint is account-scoped.

The button label should be concise, for example `Import positions`.

The modal should explain the important backend semantics before submission:

- importing is for one-time initialization of existing holdings;
- importing does not change account cash;
- accounts with existing positions or lots cannot be imported again.

This keeps users from mistaking the feature for recurring broker sync or cash-adjusting purchase history.

## Form Behavior

The form contains an editable table with one row per imported lot. Each row has these fields:

- `symbol`: required string, typically a 6-digit A-share code such as `000001`;
- `quantity`: required positive integer;
- `cost_price`: required non-negative decimal;
- `buy_trade_date`: required strict `YYYY-MM-DD` date string.

The modal starts with one empty row. Users can add rows and remove rows. Removing the last row should leave one empty row so the form never becomes visually empty.

Duplicate symbols are allowed. They represent separate lots with separate cost prices or buy dates. The backend aggregates them into one position while preserving separate lots.

Submit should run lightweight client-side validation before sending a request:

- all fields are present;
- quantity is an integer greater than zero;
- cost price is a valid number greater than or equal to zero;
- buy date matches `YYYY-MM-DD` exactly.

The backend remains the final source of validation. Backend `422` responses should be shown in the modal without clearing the user's input.

## API Client Contract

Add frontend types in `frontend/paper-trading/lib/types.ts`:

```ts
export interface ImportPositionInput {
  symbol: string
  quantity: number
  cost_price: string
  buy_trade_date: string
}

export interface ImportPositionsInput {
  positions: ImportPositionInput[]
}

export interface ImportPositionsResult {
  imported_count: number
  lots_count: number
}
```

Add a frontend API helper in `frontend/paper-trading/lib/api-client.ts`:

```ts
importPositions(
  accountId: number,
  input: ImportPositionsInput,
): Promise<ImportPositionsResult>
```

The helper sends:

```http
POST /api/paper/accounts/{account_id}/positions/import
Content-Type: application/json
```

with a body shaped like:

```json
{
  "positions": [
    {
      "symbol": "000001",
      "quantity": 1000,
      "cost_price": "10.23",
      "buy_trade_date": "2026-01-15"
    }
  ]
}
```

The response is:

```json
{
  "imported_count": 1,
  "lots_count": 1
}
```

## Data Flow

1. The user selects an account on the Accounts page.
2. The user clicks `Import positions`.
3. The modal opens with one empty import row.
4. The user enters one or more holdings.
5. The form validates the rows locally.
6. The frontend calls `importPositions(account.id, { positions })`.
7. On success, the modal closes and the page shows a success message containing `imported_count` and `lots_count`.
8. The Accounts page refreshes the selected account detail, positions, and cash ledger.

Refreshing cash ledger is intentional even though import does not create cash entries; it confirms the account view remains internally consistent after initialization.

## Error Handling

The modal should remain open on failure.

Expected error cases:

- empty or incomplete rows: show a client-side validation message;
- invalid quantity, cost price, or date: show a client-side validation message;
- backend `422` for existing positions or lots: show `This account already has positions. Import is only available for empty accounts.` or equivalent concise wording;
- other backend `422`: show the server validation message;
- backend `404`: show the existing not-found error shape;
- network or proxy errors: show a form-level request error.

Errors must not clear user input.

## Testing

Add focused frontend tests for:

- the Accounts page shows an `Import positions` action when an account is selected;
- opening the modal shows one empty row and the one-time import/no-cash-change note;
- adding and removing rows works without leaving the form visually empty;
- submitting a valid row calls `POST /api/paper/accounts/{account_id}/positions/import` with the expected body;
- successful import closes the modal, shows the import counts, and refreshes selected account data;
- local validation prevents invalid or incomplete rows from sending a request;
- backend errors keep the modal open and display the error.

Existing account creation, fee editing, delete, select, positions, and cash ledger tests should continue to pass.

## Non-Goals

- No CSV upload or paste support.
- No automatic broker import or synchronization.
- No repeated append import for accounts that already have holdings.
- No cash adjustment during import.
- No backend API changes.
- No changes to order, trade, matching, snapshot, or analytics pages.
