# Paper Trading Cash Flows And NAV Design

## Goal

Add explicit deposits and withdrawals to paper trading, and change performance analytics so external cash flows do not distort returns, drawdown, or risk-adjusted metrics. The design uses a fund-style share and NAV model: account scale is tracked as assets and cash, while investment performance is tracked through unit NAV.

## Current Context

- Account creation seeds cash by writing an initial `DEPOSIT` cash-ledger entry.
- Buy orders freeze cash, matching releases excess frozen cash, sell fills add trade proceeds, and snapshots summarize cash, market value, total assets, and PnL.
- Analytics currently computes `total_return` from latest snapshot `total_assets` versus `initial_cash`, and risk metrics use total-assets history.
- The frontend account page already displays positions and cash ledger entries, and the analytics page already displays assets, returns, risk metrics, and an asset chart.

## Chosen Approach

Use a fund-style NAV/share model with pre-market cash-flow effectiveness.

Alternatives considered:

- Computing cash-flow-adjusted returns only in analytics would avoid some schema changes, but it would make drawdown and risk metrics harder to explain and audit.
- Tracking only net invested capital would be quicker, but large deposits or withdrawals would still make return and risk metrics misleading.

## Domain Rules

- Initial account setup starts at NAV `1.0` with shares equal to `initial_cash`.
- Deposits are effective before trading on their `trade_date`, increase available cash, and mint shares at the current account NAV.
- Withdrawals are effective before trading on their `trade_date`, reduce available cash, and redeem shares at the current account NAV.
- A withdrawal cannot exceed available cash. It does not auto-sell positions, use frozen cash, or create negative cash.
- Trading and matching never change share count. They only change cash, positions, realized PnL, unrealized PnL, and therefore later NAV.
- Deposits and withdrawals are immutable audit entries. User mistakes are corrected by entering an opposite cash-flow event rather than editing or deleting history.
- A cash flow by itself does not change unit NAV; only investment performance changes unit NAV.

## Data Model

Extend `PaperCashLedger` so external cash-flow rows can record NAV/share effects:

- `event_type`: keep `DEPOSIT`; add `WITHDRAWAL`.
- `amount`: positive for deposits, negative for withdrawals, consistent with available-cash summing.
- `trade_date`: effective date for the cash flow.
- `note`: optional user note.
- `nav`: account NAV used to mint or redeem shares.
- `share_delta`: positive for deposits and negative for withdrawals.

Extend `PaperAccount` with current NAV/share state:

- `share_count`: current account shares.
- `net_asset_value`: latest unit NAV.
- `cumulative_deposit`: lifetime external deposits, including initial cash.
- `cumulative_withdrawal`: lifetime external withdrawals as a positive reporting amount.

Extend `PaperAccountSnapshot` with NAV-aware fields:

- `net_asset_value`: `total_assets / share_count` when shares are positive.
- `share_count`: account shares at snapshot time.
- `cumulative_deposit`: cumulative external deposits at snapshot time.
- `cumulative_withdrawal`: cumulative external withdrawals at snapshot time.
- `net_cash_flow`: cumulative deposits minus cumulative withdrawals at snapshot time.

Historical compatibility:

- Existing accounts without NAV fields are treated as NAV `1.0` and `share_count = initial_cash`.
- Existing snapshots without NAV fields can be backfilled or derived as `total_assets / initial_cash` with `share_count = initial_cash`.
- If initial cash or share count is invalid, analytics should return unavailable metric reasons instead of dividing by zero.

## Backend API And CLI

Add account-scoped cash-flow endpoints:

- `POST /paper/accounts/{account_id}/cash/deposit`
- `POST /paper/accounts/{account_id}/cash/withdraw`

Request fields:

- `amount`: positive decimal amount.
- `trade_date`: effective date.
- `note`: optional note.

Response fields should include the created cash-ledger row plus current account cash, NAV, and share count.

Add a `CashService` or equivalent service boundary responsible for:

- Validating account status, positive amounts, and withdrawal cash availability.
- Reading the current account NAV and available cash.
- Creating the cash-ledger row with `nav` and `share_delta`.
- Updating account `share_count`, cumulative cash-flow totals, current NAV, and available cash through ledger effects.

Add CLI commands:

```bash
uv run tools/paper_trading_cli.py account deposit --account-id 1 --amount 10000 --trade-date 2026-07-20 --note "add cash"
uv run tools/paper_trading_cli.py account withdraw --account-id 1 --amount 5000 --trade-date 2026-07-20 --note "withdraw cash"
```

The existing cash-ledger listing should include the new cash-flow fields where available.

## Analytics Design

Keep absolute-money metrics unchanged:

- `total_assets`
- `cash_available`
- `cash_frozen`
- `market_value`
- `realized_pnl`
- `unrealized_pnl`

Add NAV metrics:

- `net_asset_value`: latest unit NAV. Frontend copy may use `NAV` as the display label, but backend schemas should use the explicit field name.
- `share_count`: current account shares.
- `nav_return`: latest NAV versus first valid NAV.

Retain the existing `total_return` API field but change its meaning to NAV return so existing frontend code can migrate with less churn. Add `simple_asset_return` for the old total-assets-versus-initial-cash view, labelled as a scale-sensitive reference metric.

Risk and performance metrics should use the NAV series, not total assets:

- `max_drawdown`
- `current_drawdown`
- `sharpe`
- `sortino`
- `calmar`

Charts should default to the NAV curve. A total-assets curve can remain available as an account-size reference, but it should not be presented as the main performance curve.

## Frontend Design

Add deposits and withdrawals to the account detail page rather than creating a separate funding page.

Account detail actions:

- Add `Deposit` and `Withdraw` buttons near existing account actions.
- Open a lightweight form or modal with `amount`, `trade_date`, and `note`.
- The withdrawal form displays the current maximum withdrawable amount from available cash.
- On success, refresh account details, positions, and cash ledger entries.

Cash-ledger table updates:

- Display user-friendly types for deposits, withdrawals, freezes, releases, trades, and fees.
- Show execution NAV and share delta for deposit and withdrawal rows.
- Leave NAV/share fields empty for trading-related rows when not applicable.

Analytics page updates:

- Add current NAV and share count to overview cards.
- Rename the primary return label to NAV Return or the equivalent Chinese copy.
- Default charts to NAV over time.
- Keep total assets visible as an account-size metric, not as the primary return basis.

Frontend validation should show clear errors for non-positive amounts, withdrawals above available cash, and inactive accounts.

## Testing Strategy

Backend service and repository tests:

- Account creation initializes NAV `1.0`, share count, cumulative deposits, and the initial cash-ledger row.
- Deposit increases available cash and shares while leaving NAV unchanged.
- Withdrawal decreases available cash and shares while leaving NAV unchanged.
- Withdrawal above available cash fails without writing a ledger row.
- Matching and snapshot generation update NAV as `total_assets / share_count` without changing shares.
- Deposits and withdrawals do not distort NAV return.

API and CLI tests:

- Deposit and withdrawal success responses include ledger, cash, NAV, and share data.
- Invalid amount, inactive account, and excess withdrawal paths return explicit errors.
- CLI `account deposit` and `account withdraw` pass the expected payloads and render useful output.

Frontend tests:

- Deposit and withdrawal forms validate required fields and positive amounts.
- Withdrawal form displays available-cash limits and handles excess-withdrawal errors.
- Successful cash-flow submission refreshes account detail data and cash ledger rows.
- Analytics overview and charts show NAV return and NAV series.

Documentation tests or examples:

- `docs/paper_trading.md` documents the endpoints, CLI commands, NAV/share model, and changed return semantics.
- Analytics documentation makes clear that `total_return` now means NAV return, while total-assets return is a separate scale-sensitive reference metric.

## Migration And Rollout

Schema migration should add the new account, snapshot, and cash-ledger fields without deleting existing data. Backfill old accounts with NAV `1.0` and shares equal to `initial_cash`. Backfill old snapshots where practical; otherwise keep service-level compatibility that derives NAV fields for old rows.

Implementation should keep old account creation behavior visible to users: creating an account still looks like an initial deposit, but it also initializes the NAV/share state. Existing trading, matching, and snapshot commands should continue to work without requiring users to enter cash flows.

## Error Handling

- Reject non-positive deposit and withdrawal amounts.
- Reject withdrawals above available cash and include the available amount in the error where practical.
- Reject cash flows for inactive or deleted accounts.
- Return unavailable analytics metrics with reasons when NAV/share history is insufficient or invalid.
- Keep cash-flow ledger writes and account share updates transactional.

## Open Questions Resolved

- Return model: fund-style NAV/share model.
- Effective timing: pre-market on `trade_date`.
- Withdrawal limit: available cash only.
- Corrections: immutable ledger with reverse cash-flow correction.
- Frontend entry: account detail page actions.
