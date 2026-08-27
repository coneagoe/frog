# Task 1 Implementation Report

## Changed Files

- `paper_trading/domain/precision.py`: Added the shared 12-decimal money, NAV, and shares quantization contract, explicit `ROUND_HALF_UP` mode, and finite-value validation.
- `paper_trading/domain/enums.py`: Added `CashEventType.CORPORATE_ACTION`.
- `storage/model/paper_trading.py`: Widened account, cash-ledger, and account-snapshot accounting columns to `Numeric(30, 12)` and added `PaperCashLedger.rounding_residual` with a zero server default.
- `paper_trading/storage/repository.py`: Added residual support to `add_cash_event`, applied the shared quantizers to NAV/share account state, and preserved four-decimal cash-available display quantization.
- `paper_trading/services/cash_service.py`: Applied finite validation and shared quantization to cash flows; calculated signed residuals from the requested amount minus persisted share delta times effective NAV; retained existing cumulative deposit/withdrawal behavior and error display formatting.
- `paper_trading/schemas/accounts.py`: Exposed `rounding_residual` with a zero default in `CashLedgerResponse`.
- `test/paper_trading/services/test_cash_service.py`: Added positive and negative residual reconciliation coverage.
- `test/paper_trading/storage/test_repository.py`: Added zero-default residual coverage.

## Design Choices

- Used `ROUND_HALF_UP` explicitly as the repository's documented financial rounding mode.
- Kept cash-flow amounts positive in service APIs and used the signed ledger amount for withdrawal residual reconciliation.
- Kept cumulative external deposit and withdrawal totals based on the requested amount, excluding residuals.
- Preserved existing four-decimal display formatting for cash availability and withdrawal validation messages.
- Kept existing display serializer behavior while widening persisted accounting precision.

## Test Commands And Output

Command:

```bash
uv run pytest test/paper_trading/services/test_cash_service.py test/paper_trading/storage/test_repository.py -q
```

Output:

```text
........................................................................ [ 75%]
.......................                                                  [100%]
95 passed in 61.21s (0:01:01)
```

Command:

```bash
uv run ruff check paper_trading/domain/precision.py paper_trading/domain/enums.py storage/model/paper_trading.py paper_trading/storage/repository.py paper_trading/services/cash_service.py paper_trading/schemas/accounts.py test/paper_trading/services/test_cash_service.py test/paper_trading/storage/test_repository.py
```

Output:

```text
All checks passed!
```

Command:

```bash
git diff --check
```

Output: no output; passed.

## Self-Review

- Verified exact residual identity for both deposit and withdrawal paths after persisted quantization.
- Verified residuals are non-zero for a rounding case and have the correct sign.
- Verified repository-created ledger events default residual to `Decimal("0.000000000000")`.
- Verified existing focused cash-flow and repository behavior remains green.
- Reviewed diff whitespace and ran Ruff on every touched implementation and test file.

## Concerns

- This task was constrained to the brief's named files. No runtime migration was added for databases that already contain `paper_cash_ledger` or the existing narrower accounting columns. A startup/schema upgrade outside the allowed file list will be needed for those databases; fresh metadata-created databases use the new definitions and legacy ORM rows without a residual value receive the model server default.

## Review Fix Report

### Changes

- Added a 24-decimal residual quantizer and widened `PaperCashLedger.rounding_residual` to `Numeric(30, 24)`, allowing the exact product of persisted 12-decimal shares and NAV to be represented deterministically.
- Changed `PaperTradingRepository.add_cash_event` to quantize amount, NAV, and shares first, then derive the persisted residual as `persisted_amount - persisted_share_delta * persisted_nav` whenever both accounting inputs are present.
- Removed service-side residual calculation so the repository is the single persistence boundary for reconciliation.
- Added regression coverage for post-reload deposit and withdrawal identity, including residuals beyond the 12-decimal boundary, plus direct repository derivation coverage.

### Test Command And Output

Command:

```bash
uv run pytest test/paper_trading/services/test_cash_service.py test/paper_trading/storage/test_repository.py -q
```

Output:

```text
........................................................................ [ 73%]
..........................                                               [100%]
98 passed in 63.71s (0:01:03)
```

### Self-Review

- Confirmed deposit and withdrawal persisted ledger rows satisfy `rounding_residual == amount - share_delta * net_asset_value` after session commit and reload.
- Confirmed the residual is derived from persisted/quantized values rather than a caller-provided independently quantized value.
- Confirmed cumulative external deposit and withdrawal totals remain based on the requested amounts.
- Confirmed the focused test suite passes and `git diff --check` reports no whitespace errors.
- Simplify review: no further safe simplification identified within the requested fix scope.

### Fix Concerns

- The residual column scale change still requires the existing database schema upgrade path for already-created databases; no migration was added because the requested scope excludes plan/spec and unrelated files.
